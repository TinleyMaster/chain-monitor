"""chain-monitor: Multi-chain blockchain monitoring system.

Usage:
  python -m src.main                    # Run all enabled monitors
  python -m src.main --monitor trend    # Run single module
  python -m src.main --once             # Run once and exit (test mode)
  python -m src.main --dry-run          # No telegram push, console only
"""

import argparse
import asyncio
import logging
import os
import sys

from src.config import get_config
from src.monitors.market_trend import MarketTrendMonitor
from src.monitors.whale_transfer import WhaleTransferMonitor
from src.monitors.price_alert import PriceAlertMonitor
from src.monitors.portfolio import PortfolioMonitor
from src.monitors.tvl_trend import TvlTrendMonitor
from src.monitors.daily_report import DailyReportMonitor
from src.web_server import start_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("chain-monitor")

DRY_RUN = False


async def run_monitor_module(module_name: str, once: bool = False):
    """Run a single monitor module."""
    cfg = get_config()
    mc = cfg.get("monitors", {}).get(module_name, {})

    interval_minutes = mc.get("interval_minutes", 10)
    interval_seconds = interval_minutes * 60

    if module_name == "market_trend":
        monitor = MarketTrendMonitor()
    elif module_name == "whale_transfer":
        monitor = WhaleTransferMonitor()
    elif module_name == "price_alert":
        monitor = PriceAlertMonitor()
    elif module_name == "portfolio":
        monitor = PortfolioMonitor()
    elif module_name == "tvl_trend":
        monitor = TvlTrendMonitor()
    elif module_name == "daily_report":
        monitor = DailyReportMonitor()
    else:
        logger.error("Unknown monitor: %s", module_name)
        return

    try:
        if once:
            logger.info("[%s] Running once...", module_name)
            await monitor.run_once()
            logger.info("[%s] Complete. stats=%s", module_name, monitor.stats)
        else:
            await monitor.run_loop(interval_seconds=interval_seconds)
    finally:
        await monitor.close()


async def run_all(once: bool = False):
    """Run all enabled monitors."""
    cfg = get_config()
    monitors_cfg = cfg.get("monitors", {})

    tasks = []
    for name, mc in monitors_cfg.items():
        if not mc.get("enabled", True):
            logger.info("Skipping disabled monitor: %s", name)
            continue

        if name == "market_trend":
            monitor = MarketTrendMonitor()
        elif name == "whale_transfer":
            monitor = WhaleTransferMonitor()
        elif name == "price_alert":
            monitor = PriceAlertMonitor()
        elif name == "portfolio":
            monitor = PortfolioMonitor()
        elif name == "tvl_trend":
            monitor = TvlTrendMonitor()
        elif name == "daily_report":
            monitor = DailyReportMonitor()
        else:
            logger.warning("Monitor not implemented yet: %s", name)
            continue

        if once:
            tasks.append(monitor.run_once())
        else:
            interval_minutes = mc.get("interval_minutes", 10)
            interval_seconds = interval_minutes * 60
            tasks.append(monitor.run_loop(interval_seconds=interval_seconds))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error("Monitor error: %s", r)
    else:
        logger.warning("No enabled monitors found.")


def main():
    global DRY_RUN
    parser = argparse.ArgumentParser(description="Chain Monitor")
    parser.add_argument("--monitor", type=str, help="Run single monitor module")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="No Telegram push")
    parser.add_argument("--web", action="store_true", help="Start web dashboard on port 8080")
    parser.add_argument("--port", type=int, default=8080, help="Web dashboard port")
    args = parser.parse_args()

    if args.dry_run:
        DRY_RUN = True
        os.environ["CHAIN_MONITOR_DRY_RUN"] = "1"
        logger.info("Dry-run mode: no Telegram notifications")

    if args.web:
        start_web_server(port=args.port)
    logger.info("chain-monitor starting...")

    if args.monitor:
        asyncio.run(run_monitor_module(args.monitor, once=args.once))
    else:
        asyncio.run(run_all(once=args.once))


if __name__ == "__main__":
    main()
