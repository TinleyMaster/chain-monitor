"""Token price alert monitor: polls DefiLlama price API and triggers
notifications on price changes crossing configured thresholds."""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from src.config import get_config
from src.monitors.base_monitor import BaseMonitor
from src.utils.formatters import format_price_alert

logger = logging.getLogger(__name__)

DEFILLAMA_PRICE_URL = "https://coins.llama.fi/prices/current"


class PriceAlertMonitor(BaseMonitor):
    name = "price_alert"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cfg = get_config().get("monitors", {}).get("price_alert", {})
        self.tokens = cfg.get("tokens", [])
        self.interval_minutes = cfg.get("interval_minutes", 3)
        self._session = None
        self._prev_prices = {}  # cobridge_id -> (price, timestamp)

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def run_once(self) -> None:
        if not self.tokens:
            return
        id_to_config = {}
        addresses = []
        for t in self.tokens:
            cg_id = t.get("cobridge_id", "")
            if cg_id:
                id_to_config[cg_id] = t
                addresses.append(cg_id)
        if not addresses:
            return
        prices_raw = await self._fetch_prices(addresses)
        now = datetime.now(timezone.utc)
        coins = prices_raw.get("coins", {})
        for cg_id, tcfg in id_to_config.items():
            coin_data = coins.get(cg_id, {})
            price = coin_data.get("price")
            if price is None:
                continue
            symbol = tcfg.get("symbol", "?")
            chain = tcfg.get("chain", "?")
            self.store.save_price(dict(token=symbol, chain=chain,
                price_usd=price, volume_24h=coin_data.get("volume"),
                change_24h=None, timestamp=now))
            await self._check_alerts(tcfg, cg_id, symbol, chain, price, now)
            self._prev_prices[cg_id] = (price, now)

    async def _check_alerts(self, tcfg, cg_id, symbol, chain, price, now):
        alerts = tcfg.get("alerts", [])
        prev = self._prev_prices.get(cg_id)
        prev_price = prev[0] if prev else None
        prev_time = prev[1] if prev else None
        for a in alerts:
            atype = a.get("type", "")
            title = ""
            extra = {}
            triggered = False
            if atype == "percent_change" and prev_price and prev_time:
                threshold = a.get("threshold", 5)
                window = a.get("window_minutes", 5)
                elapsed = (now - prev_time).total_seconds() / 60
                if elapsed <= window:
                    pct = ((price - prev_price) / prev_price) * 100
                    if abs(pct) >= threshold:
                        triggered = True
                        title = "Price Change | " + symbol
                        extra = dict(change_pct=round(pct,2), prev_price_usd=round(prev_price,4))
            elif atype == "above" and price >= a.get("threshold_usd", 1e9):
                triggered = True
                title = "Price Above \$" + str(a["threshold_usd"]) + " | " + symbol
            elif atype == "below" and price <= a.get("threshold_usd", 0):
                triggered = True
                title = "Price Below \$" + str(a["threshold_usd"]) + " | " + symbol
            if triggered:
                data = dict(token=symbol, chain=chain, price_usd=price, high_24h=None, low_24h=None, **extra)
                msg = format_price_alert(data)
                await self.notifier.send_alert("price_alert", title, msg)

    async def _fetch_prices(self, coingecko_ids):
        ids = ",".join(coingecko_ids)
        url = DEFILLAMA_PRICE_URL + "/" + ids + "?searchWidth=4h"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
        except Exception as e:
            logger.error("[%s] Failed to fetch prices: %s", self.name, e)
            return {}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()