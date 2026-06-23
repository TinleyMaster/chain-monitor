"""Portfolio tracking monitor: fetches multi-chain token balances via Covalent
API and tracks changes. Periodic full refresh + optional WS updates."""
import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
from src.config import get_config
from src.monitors.base_monitor import BaseMonitor
from src.utils.chains import COVALENT_CHAIN_IDS
logger = logging.getLogger(__name__)
COVALENT_BASE = "https://api.covalenthq.com/v1"
class PortfolioMonitor(BaseMonitor):
    name = "portfolio"
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cfg = get_config().get("monitors", {}).get("portfolio", {})
        self.addresses = cfg.get("addresses", [])
        self.interval_minutes = cfg.get("interval_minutes", 15)
        self.evm_chains = cfg.get("evm_chains", ["ethereum"])
        self._session = None
        self._last_balances = {}  # (address, chain, token) -> value_usd
    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    async def run_once(self) -> None:
        if not self.addresses:
            logger.warning("[%s] No addresses configured", self.name)
            return
        for addr in self.addresses:
            for chain in self.evm_chains:
                balances = await self._fetch_balances(chain, addr)
                if balances:
                    await self._update_portfolio(addr, chain, balances)
    async def _fetch_balances(self, chain: str, addr: str) -> list[dict]:
        cc = COVALENT_CHAIN_IDS.get(chain, chain)
        url = COVALENT_BASE + "/" + cc + "/address/" + addr + "/balances_v2/"
        params = {"nft": "false", "no-nft-fetch": "true"}
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
        except Exception as e:
            logger.error("[%s] Covalent fetch error for %s/%s: %s", self.name, chain, addr, e)
            return []
        if data.get("error"):
            logger.warning("[%s] Covalent API error: %s", self.name, data["error"])
            return []
        items = data.get("data", {}).get("items", [])
        results = []
        for item in items:
            balance = int(item.get("balance", 0))
            decimals = int(item.get("contract_decimals", 18))
            quote = float(item.get("quote", 0) or 0)
            if quote <= 0 and balance <= 0:
                continue
            results.append(dict(
                token=item.get("contract_ticker_symbol", "?"),
                token_address=item.get("contract_address", ""),
                balance=balance / (10 ** decimals),
                value_usd=quote,
                decimals=decimals,
            ))
        return results
    async def _update_portfolio(self, addr: str, chain: str, balances: list[dict]):
        now = datetime.now(timezone.utc)
        new_snapshot = {}
        total_usd = 0.0
        for b in balances:
            key = (addr, chain, b["token"])
            new_snapshot[key] = b["value_usd"]
            total_usd += b["value_usd"]
            self.store.save_portfolio_snapshot(dict(
                address=addr, chain=chain, token=b["token"],
                balance=b["balance"], value_usd=b["value_usd"], timestamp=now,
            ))
        # Detect meaningful changes
        for key, new_val in new_snapshot.items():
            old_val = self._last_balances.get(key, 0)
            if old_val > 0 and new_val > 0 and abs(new_val - old_val) / old_val > 0.05:
                a, c, t = key
                chg = new_val - old_val
                direction = "increased" if chg > 0 else "decreased"
                await self.notifier.send_alert(
                    "portfolio_change",
                    "Portfolio Change | " + t,
                    "<b>" + a[:6] + "..." + a[-4:] + "</b>\n"
                    + t + " " + direction + " by $" + str(int(abs(chg))) + "\n"
                    + "Current: $" + str(int(new_val)) + "\nChain: " + c.upper()
                )
        self._last_balances = new_snapshot
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()