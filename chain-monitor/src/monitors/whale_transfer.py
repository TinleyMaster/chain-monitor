"""Whale transfer monitor: detects large transactions on EVM chains (Alchemy WS)
and Solana (Helius WS). Pushes real-time Telegram alerts."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from web3 import AsyncWeb3
from web3.providers.persistent import PersistentConnectionProvider

from src.config import get_config, get_evm_ws_url
from src.monitors.base_monitor import BaseMonitor
from src.utils.chains import EVM_CHAINS, get_explorer_url
from src.utils.formatters import format_whale_transfer

logger = logging.getLogger(__name__)

# Approximate USD values for native tokens used when no price feed available
NATIVE_TOKEN_PRICES = {
    "ethereum": 3500.0,
    "arbitrum": 3500.0,
    "optimism": 3500.0,
    "base": 3500.0,
    "polygon": 0.70,
    "solana": 145.0,
}
NATIVE_SYMBOLS = {
    "ethereum": "ETH", "arbitrum": "ETH", "optimism": "ETH",
    "base": "ETH", "polygon": "MATIC", "solana": "SOL",
}
NATIVE_DECIMALS = 18


class WhaleTransferMonitor(BaseMonitor):
    name = "whale_transfer"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        cfg = get_config().get("monitors", {}).get("whale_transfer", {})
        self.threshold_usd = cfg.get("threshold_usd", 100000)
        self.evm_chains = [c for c in cfg.get("evm_chains", []) if c in EVM_CHAINS]
        self.solana_enabled = cfg.get("solana_enabled", True)
        self.tracked = set(cfg.get("tracked_addresses", []))
        self.confirmations = cfg.get("confirmations_required", 3)
        self._w3s = {}       # chain -> AsyncWeb3
        self._tasks = []

    async def run_once(self) -> None:
        """Start all WebSocket listeners."""
        tasks = []
        for chain in self.evm_chains:
            tasks.append(self._listen_evm(chain))
        if self.solana_enabled:
            tasks.append(self._listen_solana())
        self._tasks = tasks
        await asyncio.gather(*tasks, return_exceptions=True)

    # ---- EVM chains via Alchemy WS ----

    async def _listen_evm(self, chain: str):
        ws_url = get_evm_ws_url(chain)
        if not ws_url:
            logger.warning("[%s] Skipping %s: no RPC endpoint available", self.name, chain)
            return

        logger.info("[%s] Connecting to %s via Alchemy WS...", self.name, chain)
        w3 = AsyncWeb3(PersistentConnectionProvider(ws_url))
        self._w3s[chain] = w3

        while self._running:
            try:
                await w3.provider.connect()
                # Subscribe to new block headers
                sub_id = await w3.eth.subscribe("newHeads")
                logger.info("[%s] %s: subscribed to newHeads, id=%s", self.name, chain, sub_id)

                async for payload in w3.socket.process_subscriptions():
                    block = payload.get("result", {})
                    block_number = int(block.get("number", "0x0"), 16)
                    await self._scan_evm_block(w3, chain, block_number)
            except Exception as e:
                logger.error("[%s] %s WS error, reconnecting in 10s: %s", self.name, chain, e)
                try:
                    await w3.provider.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(10)

    async def _scan_evm_block(self, w3, chain: str, block_number: int):
        try:
            block = await w3.eth.get_block(block_number, full_transactions=True)
        except Exception as e:
            logger.debug("[%s] %s block %d fetch failed: %s", self.name, chain, block_number, e)
            return

        if not block or not block.get("transactions"):
            return

        for tx in block["transactions"]:
            await self._process_evm_tx(chain, tx)

    async def _process_evm_tx(self, chain: str, tx: dict):
        tx_hash = tx.get("hash", "").hex() if hasattr(tx.get("hash", ""), "hex") else str(tx.get("hash", ""))
        if not tx_hash or self.store.transfer_exists(tx_hash):
            return

        value_wei = tx.get("value", 0)
        if isinstance(value_wei, bytes):
            value_wei = int.from_bytes(value_wei, "big")
        value_eth = float(value_wei) / 1e18

        native_price = NATIVE_TOKEN_PRICES.get(chain, 3500.0)
        amount_usd = value_eth * native_price

        if amount_usd < self.threshold_usd:
            return

        from_addr = tx.get("from", "")
        to_addr = tx.get("to", "")
        if hasattr(from_addr, "hex"):
            from_addr = from_addr.hex()
        if hasattr(to_addr, "hex"):
            to_addr = to_addr

        symbol = NATIVE_SYMBOLS.get(chain, "?")
        data = {
            "chain": chain,
            "tx_hash": tx_hash,
            "from_address": from_addr,
            "to_address": to_addr or "",
            "token_symbol": symbol,
            "token_address": "",
            "amount": value_eth,
            "amount_usd": amount_usd,
            "block_number": tx.get("blockNumber", 0),
            "timestamp": datetime.now(timezone.utc),
        }

        self.store.save_transfer(data)
        await self._alert_whale(data)

    async def _alert_whale(self, data: dict):
        msg = format_whale_transfer(data)
        await self.notifier.send_alert("whale_transfer", f"Whale Transfer | {data['chain'].upper()}", msg)

    # ---- Solana via Helius WS ----

    async def _listen_solana(self):
        cfg = get_config().get("api_keys", {}).get("helius", {})
        api_key = cfg.get("solana", "")
        if not api_key or "YOUR_" in api_key:
            logger.warning("[%s] Skipping Solana: no Helius key configured", self.name)
            return

        # Helius WebSocket for transaction subscription
        ws_url = f"wss://mainnet.helius-rpc.com/?api-key={api_key}"
        logger.info("[%s] Connecting to Solana via Helius WS...", self.name)

        backoff = 1
        while self._running:
            try:
                import websockets
                async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                    # Subscribe to all transactions
                    sub_req = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "transactionSubscribe",
                        "params": [
                            {"vote": False, "failed": False},
                            {"encoding": "jsonParsed", "commitment": "confirmed"}
                        ]
                    }
                    await ws.send(json.dumps(sub_req))
                    logger.info("[%s] Solana: subscribed to transactions", self.name)
                    backoff = 1

                    while self._running:
                        resp = await ws.recv()
                        self._handle_solana_message(resp)
            except Exception as e:
                logger.error("[%s] Solana WS error, reconnect in %ds: %s", self.name, backoff, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def _handle_solana_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        params = msg.get("params", {})
        result = params.get("result", {})
        tx = result.get("transaction", {})
        if not tx:
            return

        # Parse Solana transaction for SOL transfers
        message = tx.get("message", {})
        instructions = message.get("instructions", [])
        account_keys = message.get("accountKeys", [])

        for ix in instructions:
            program_id = ix.get("programId", "")
            if program_id != "11111111111111111111111111111111":  # System program
                continue
            parsed = ix.get("parsed", {})
            if parsed.get("type") != "transfer":
                continue

            info = parsed.get("info", {})
            lamports = int(info.get("lamports", 0))
            sol_amount = lamports / 1e9
            amount_usd = sol_amount * NATIVE_TOKEN_PRICES["solana"]

            if amount_usd < self.threshold_usd:
                return

            signature = tx.get("signatures", [""])[0] if tx.get("signatures") else ""
            if self.store.transfer_exists(signature):
                return

            data = {
                "chain": "solana",
                "tx_hash": signature,
                "from_address": info.get("source", ""),
                "to_address": info.get("destination", ""),
                "token_symbol": "SOL",
                "amount": sol_amount,
                "amount_usd": amount_usd,
                "block_number": 0,
                "timestamp": datetime.now(timezone.utc),
            }
            self.store.save_transfer(data)
            asyncio.create_task(self._alert_whale(data))

    async def close(self):
        self._running = False
        for w3 in self._w3s.values():
            try:
                await w3.provider.disconnect()
            except Exception:
                pass
