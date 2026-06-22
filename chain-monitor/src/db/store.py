"""DuckDB storage operations for chain-monitor."""

import os
import duckdb
from src.config import get_config


class Store:
    def __init__(self, db_path: str = None):
        if db_path is None:
            cfg = get_config()
            db_path = cfg.get("database", {}).get("path", "data/monitor.duckdb")
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        from src.db.schema import SCHEMA_SQL
        self.conn.execute(SCHEMA_SQL)

    # ---- Transfers ----

    def save_transfer(self, data: dict):
        self.conn.execute("""
            INSERT INTO transfers (chain, tx_hash, from_address, to_address,
                token_symbol, token_address, amount, amount_usd, block_number, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            data["chain"], data["tx_hash"], data["from_address"],
            data["to_address"], data.get("token_symbol"), data.get("token_address"),
            data.get("amount"), data.get("amount_usd"), data.get("block_number"),
            data["timestamp"]
        ])

    def transfer_exists(self, tx_hash: str) -> bool:
        r = self.conn.execute(
            "SELECT COUNT(*) FROM transfers WHERE tx_hash = ?", [tx_hash]
        ).fetchone()
        return r[0] > 0

    # ---- Prices ----

    def save_price(self, data: dict):
        self.conn.execute("""
            INSERT INTO prices (token, chain, price_usd, volume_24h, change_24h, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            data["token"], data["chain"], data["price_usd"],
            data.get("volume_24h"), data.get("change_24h"), data["timestamp"]
        ])

    def get_latest_price(self, token: str, chain: str) -> float | None:
        r = self.conn.execute("""
            SELECT price_usd FROM prices
            WHERE token = ? AND chain = ?
            ORDER BY timestamp DESC LIMIT 1
        """, [token, chain]).fetchone()
        return r[0] if r else None

    # ---- TVL ----

    def save_tvl(self, data: dict):
        self.conn.execute("""
            INSERT INTO tvl_snapshots (chain, tvl, change_1h, change_24h, change_7d, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            data["chain"], data["tvl"], data.get("change_1h"),
            data.get("change_24h"), data.get("change_7d"), data["timestamp"]
        ])

    def get_latest_tvl(self, chain: str) -> dict | None:
        r = self.conn.execute("""
            SELECT chain, tvl, change_1h, change_24h, change_7d, timestamp
            FROM tvl_snapshots
            WHERE chain = ?
            ORDER BY timestamp DESC LIMIT 1
        """, [chain]).fetchone()
        if not r:
            return None
        return {
            "chain": r[0], "tvl": r[1], "change_1h": r[2],
            "change_24h": r[3], "change_7d": r[4], "timestamp": r[5]
        }

    # ---- Portfolio ----

    def save_portfolio_snapshot(self, data: dict):
        self.conn.execute("""
            INSERT INTO portfolio_snapshots (address, chain, token, balance, value_usd, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            data["address"], data["chain"], data["token"],
            data["balance"], data["value_usd"], data["timestamp"]
        ])

    def clear_portfolio_for(self, address: str):
        self.conn.execute(
            "DELETE FROM portfolio_snapshots WHERE address = ?", [address]
        )

    # ---- Alerts ----

    def log_alert(self, alert_type: str, title: str, message: str,
                  severity: str = "info", raw_data: dict = None, notified: bool = False):
        import json
        self.conn.execute("""
            INSERT INTO alerts_log (alert_type, severity, title, message, raw_data, notified)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [alert_type, severity, title, message,
              json.dumps(raw_data) if raw_data else None, notified])

    # ---- Utilities ----

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
