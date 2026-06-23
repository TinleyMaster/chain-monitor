"""TVL trend monitor: tracks total value locked per chain via DefiLlama API,
detects ranking shifts and significant changes, generates periodic digests."""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from src.config import get_config
from src.monitors.base_monitor import BaseMonitor
from src.utils.chains import DEFILLAMA_CHAIN_IDS
from src.utils.formatters import format_tvl_alert

logger = logging.getLogger(__name__)

DEFILLAMA_BASE = "https://api.llama.fi"


class TvlTrendMonitor(BaseMonitor):
    name = "tvl_trend"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cfg = get_config().get("monitors", {}).get("tvl_trend", {})
        self.chains = cfg.get("chains", ["ethereum", "solana"])
        self.interval_minutes = cfg.get("interval_minutes", 15)
        self.threshold_pct = cfg.get("tvl_change_threshold_percent", 5)
        self._session = None
        self._last_ranking = {}

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        all_data = await self._fetch_all()
        filtered = [d for d in all_data if d["chain"] in self.chains]
        for d in filtered:
            self.store.save_tvl(dict(
                chain=d["chain"], tvl=d["tvl"],
                change_1h=d.get("change_1h"),
                change_24h=d.get("change_24h"),
                change_7d=d.get("change_7d"),
                timestamp=now,
            ))
            await self._check_alert(d)
        await self._check_ranking_shifts(filtered)

    async def _fetch_all(self) -> list[dict]:
        try:
            async with self.session.get(
                DEFILLAMA_BASE + "/v2/chains",
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json()
        except Exception as e:
            logger.error("[%s] Failed to fetch TVL: %s", self.name, e)
            return []
        results = []
        for item in data:
            name = (item.get("name") or "").lower()
            gecko = (item.get("gecko_id") or "").lower()
            matched = None
            for c in self.chains:
                dl = (DEFILLAMA_CHAIN_IDS.get(c) or "").lower()
                if name == dl or gecko == dl:
                    matched = c
                    break
            if not matched:
                continue
            results.append(dict(
                chain=matched,
                tvl=item.get("tvl", 0),
                change_1h=item.get("change_1h"),
                change_24h=item.get("change_1d") or item.get("change_24h"),
                change_7d=item.get("change_7d"),
            ))
        results.sort(key=lambda x: x["tvl"], reverse=True)
        return results

    async def _check_alert(self, d: dict):
        chg = d.get("change_1h") or 0
        if abs(chg) >= self.threshold_pct:
            direction = "up" if chg > 0 else "down"
            title = "TVL " + direction + " | " + d["chain"].upper()
            msg = format_tvl_alert(d)
            await self.notifier.send_alert("tvl_alert", title, msg)

    async def _check_ranking_shifts(self, current: list[dict]):
        new_ranking = {}
        for i, d in enumerate(current):
            new_ranking[d["chain"]] = i + 1
        if not self._last_ranking:
            self._last_ranking = new_ranking
            return
        for chain, new_rank in new_ranking.items():
            old_rank = self._last_ranking.get(chain)
            if old_rank and old_rank != new_rank:
                shift = old_rank - new_rank
                direction = "+" if shift > 0 else ""
                logger.info("[%s] Ranking shift: %s #%d -> #%d (%s%s)",
                            self.name, chain, old_rank, new_rank, direction, shift)
        self._last_ranking = new_ranking

    async def generate_daily_digest(self) -> str:
        now = datetime.now(timezone.utc)
        all_data = await self._fetch_all()
        if not all_data:
            return "TVL data unavailable for daily digest."
        lines = [
            "<b>Daily TVL Ranking Digest</b>",
            now.strftime("%Y-%m-%d"),
            "",
        ]
        for i, d in enumerate(all_data[:10], 1):
            chg = d.get("change_24h") or 0
            arrow = "up" if chg > 2 else ("down" if chg < -2 else "")
            a = {"up": "^", "down": "v"}
            sym = a.get(arrow, "")
            tvl_b = d["tvl"] / 1e9
            lines.append(
                str(i) + ". " + d["chain"].upper().ljust(6) + " $" + 
                format(tvl_b, ",.2f") + "B (" + format(chg, "+.1f") + "%) " + sym
            )
        return "\n".join(lines)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
