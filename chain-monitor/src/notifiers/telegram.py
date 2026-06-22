"""Notification interface and Telegram Bot implementation for chain-monitor."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from telegram import Bot
from telegram.error import TelegramError
from src.config import get_config


class Notifier(ABC):
    @abstractmethod
    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        ...


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str = None, chat_id: str = None):
        cfg = get_config()
        tg = cfg.get("api_keys", {}).get("telegram", {})
        self.bot_token = bot_token or tg.get("bot_token", "")
        self.chat_id = chat_id or tg.get("chat_id", "")
        self._bot: Bot | None = None
        self._disabled = not self.bot_token or not self.chat_id or \
            self.bot_token.startswith("YOUR_") or self.chat_id.startswith("YOUR_")
        if self._disabled:
            import logging
            logging.getLogger(__name__).warning(
                "Telegram bot token or chat_id not configured. Notifications disabled."
            )

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=self.bot_token)
        return self._bot

    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=False,
            )
            return True
        except TelegramError as e:
            print(f"[Telegram] send error: {e}")
            return False

    async def send_alert(self, alert_type: str, title: str, body: str) -> bool:
        emoji_map = {
            "whale_transfer": "\U0001f535",
            "price_alert": "\U0001f4c8",
            "tvl_alert": "\U0001f4ca",
            "market_report": "\U0001f4ca",
            "portfolio_change": "\U0001f4b0",
            "system": "\u26a0\ufe0f",
        }
        emoji = emoji_map.get(alert_type, "\U0001f514")
        text = (
            f"{emoji} <b>{title}</b>\n"
            f"{body}\n"
            f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )
        return await self.send(text)

    async def send_market_report(self, prices: list[dict], tvls: list[dict]) -> bool:
        lines = ["<b>\U0001f4ca Today's Market Report</b>", ""]
        lines.append("<b>--- Prices ---</b>")
        for p in prices:
            chg = p.get("change_24h", 0) or 0
            arrow = "\U0001f525" if chg > 2 else ("\U0001f4c9" if chg < -2 else "")
            lines.append(
                f"{arrow} {p['token']}: ${p['price_usd']:,.2f} "
                f"({chg:+.1f}%)"
            )
        lines.append("")
        lines.append("<b>--- TVL Top 5 ---</b>")
        for i, t in enumerate(tvls[:5], 1):
            chg = t.get("change_24h", 0) or 0
            lines.append(
                f"{i}. {t['chain'].upper():6s} ${t['tvl']/1e9:.2f}B "
                f"({chg:+.1f}%)"
            )
        text = "\n".join(lines)
        return await self.send(text)
