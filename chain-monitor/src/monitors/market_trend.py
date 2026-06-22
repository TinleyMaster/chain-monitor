"""Market trend monitor using DefiLlama API (free, no API key required).

Tracks: TVL by chain, trending tokens, DEX volumes, yields.
"""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from src.config import get_config
from src.monitors.base_monitor import BaseMonitor
from src.utils.chains import DEFILLAMA_CHAIN_IDS
from src.utils.formatters import format_bignumber, format_tvl_alert

logger = logging.getLogger(__name__)

DEFILLAMA_BASE = "https://api.llama.fi"


class MarketTrendMonitor(BaseMonitor):
    name = "market_trend"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cfg = get_config().get("monitors", {}).get("market_trend", {})
        self.chains = cfg.get("chains", ["ethereum", "solana"])
        self.interval_minutes = cfg.get("interval_minutes", 10)
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def run_once(self) -> None:
        """Fetch TVL and trending data, then push alerts on significant changes."""
        tvls = await self._fetch_tvl_all()
        trends = await self._fetch_trending()

        now = datetime.now(timezone.utc)
        for item in tvls:
            chain = item["chain"]
            tvl = item["tvl"]
            chg_24h = item.get("change_24h") or 0
            chg_1h = item.get("change_1h") or 0

            self.store.save_tvl({
                "chain": chain,
                "tvl": tvl,
                "change_1h": chg_1h,
                "change_24h": chg_24h,
                "change_7d": item.get("change_7d"),
                "timestamp": now,
            })

            # Check for significant TVL changes
            threshold = get_config().get("monitors", {}).get("tvl_trend", {}) \
                .get("tvl_change_threshold_percent", 5)
            if abs(chg_1h) >= threshold:
                await self.notifier.send_alert(
                    "tvl_alert",
                    f"Significant TVL Change | {chain.upper()}",
                    format_tvl_alert({
                        "chain": chain,
                        "tvl": tvl,
                        "change_1h": chg_1h,
                        "change_24h": chg_24h,
                    })
                )

        # Log trending tokens summary
        if trends:
            top_tokens = trends[:5]
            msg = "\n".join(
                f"  {t.get('symbol','?')}: vol ${t.get('volume_24h',0)/1e6:,.0f}M"
                for t in top_tokens
            )
            logger.info("Trending tokens:\n%s", msg)

    async def _fetch_tvl_all(self) -> list[dict]:
        try:
            async with self.session.get(f"{DEFILLAMA_BASE}/v2/chains") as resp:
                data = await resp.json()
        except Exception as e:
            logger.error("Failed to fetch TVL: %s", e)
            return []

        results = []
        for item in data:
            name = item.get("name", "").lower()
            gecko_id = item.get("gecko_id", "").lower()
            chain_match = None
            for c in self.chains:
                dl_name = DEFILLAMA_CHAIN_IDS.get(c, "").lower()
                if name == dl_name or gecko_id == dl_name:
                    chain_match = c
                    break

            if not chain_match:
                continue

            tvl = item.get("tvl", 0)
            chg_1h = item.get("change_1h")
            chg_24h = item.get("change_1d") or item.get("change_24h")
            chg_7d = item.get("change_7d")

            results.append({
                "chain": chain_match,
                "tvl": tvl,
                "change_1h": chg_1h,
                "change_24h": chg_24h,
                "change_7d": chg_7d,
            })

        results.sort(key=lambda x: x["tvl"], reverse=True)
        return results

    async def _fetch_trending(self) -> list[dict]:
        try:
            async with self.session.get(
                f"{DEFILLAMA_BASE}/v2/tokens/trending"
            ) as resp:
                data = await resp.json()
        except Exception as e:
            logger.error("Failed to fetch trending: %s", e)
            return []
        return data if isinstance(data, list) else []

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
