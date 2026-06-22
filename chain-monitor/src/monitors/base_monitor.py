"""Base monitor class providing common lifecycle for all chain-monitor modules."""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from src.db.store import Store
from src.notifiers.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class BaseMonitor(ABC):
    """Abstract base for all monitoring modules."""

    name: str = "base"

    def __init__(self, store: Store = None, notifier: TelegramNotifier = None):
        self.store = store or Store()
        self.notifier = notifier or TelegramNotifier()
        self._running = False
        self.stats = {"runs": 0, "alerts": 0, "errors": 0, "last_run": None}

    @abstractmethod
    async def run_once(self) -> None:
        """Execute one monitoring cycle. Subclasses implement this."""
        ...

    async def run_loop(self, interval_seconds: int = 60):
        """Run the monitor in a loop with the given interval."""
        self._running = True
        logger.info("[%s] Starting loop, interval=%ds", self.name, interval_seconds)
        while self._running:
            try:
                await self.run_once()
                self.stats["runs"] += 1
                self.stats["last_run"] = datetime.now().isoformat()
            except Exception as e:
                self.stats["errors"] += 1
                logger.error("[%s] Error in run_once: %s", self.name, e, exc_info=True)
            await asyncio.sleep(interval_seconds)

    def stop(self):
        self._running = False

    def log_alert(self, alert_type: str, title: str, message: str,
                  severity: str = "info", raw_data: dict = None, push: bool = True):
        self.store.log_alert(alert_type, title, message, severity, raw_data, push)
        self.stats["alerts"] += 1
        if push:
            asyncio.create_task(self.notifier.send_alert(alert_type, title, message))
