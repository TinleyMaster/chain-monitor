"""Daily report monitor: queries DuckDB for last 24h of alerts and generates
a structured summary pushed to Telegram. Designed to run once daily at 09:00."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from src.config import get_config
from src.monitors.base_monitor import BaseMonitor
from src.monitors.tvl_trend import TvlTrendMonitor

logger = logging.getLogger(__name__)


class DailyReportMonitor(BaseMonitor):
    name = "daily_report"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cfg = get_config().get("monitors", {}).get("daily_report", {})
        self.report_hour = cfg.get("report_hour", 9)

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)
        text = await self._build_report(start, now)
        await self.notifier.send(text)
        logger.info("[%s] Daily report sent, %d chars", self.name, len(text))

    async def _build_report(self, start: datetime, end: datetime) -> str:
        lines = [
            "<b>Daily Chain Monitor Report</b>",
            end.strftime("%Y-%m-%d"),
            "",
        ]

        # --- Whale Transfers ---
        whales = self._query(
            "SELECT chain, token_symbol, amount_usd, from_address, to_address, tx_hash "
            "FROM transfers WHERE timestamp BETWEEN ? AND ? "
            "ORDER BY amount_usd DESC LIMIT 5",
            [start.isoformat(), end.isoformat()]
        )
        if whales:
            lines.append("<b>--- Top 5 Whale Transfers ---</b>")
            for w in whales:
                fr = w[3][:6] + "..." + w[3][-4:] if len(w[3]) > 10 else w[3]
                to = w[4][:6] + "..." + w[4][-4:] if len(w[4]) > 10 else w[4]
                lines.append(
                    f"{w[0].upper()}: {w[1]} ${w[2]:,.0f} "
                    f"{fr} -> {to}"
                )
            lines.append("")

        # --- Price Movers ---
        prices = self._query(
            "SELECT token, chain, price_usd, timestamp FROM prices "
            "WHERE timestamp BETWEEN ? AND ? "
            "ORDER BY timestamp DESC LIMIT 50",
            [start.isoformat(), end.isoformat()]
        )
        if prices:
            lines.append("<b>--- Latest Prices ---</b>")
            seen = set()
            for p in prices:
                key = p[0] + p[1]
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"{p[1].upper()} {p[0]}: ${p[2]:,.2f}")
            lines.append("")

        # --- TVL Digest ---
        try:
            tvl_monitor = TvlTrendMonitor(store=self.store, notifier=self.notifier)
            digest = await tvl_monitor.generate_daily_digest()
            lines.append(digest)
        except Exception as e:
            logger.warning("[%s] TVL digest failed: %s", self.name, e)

        return "\n".join(lines)

    def _query(self, sql: str, params: list):
        try:
            return self.store.conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.error("[%s] DB query error: %s", self.name, e)
            return []

    async def close(self):
        pass