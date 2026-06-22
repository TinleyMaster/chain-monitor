"""Database schema and initialization for chain-monitor."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER,
    chain VARCHAR NOT NULL,
    tx_hash VARCHAR NOT NULL,
    from_address VARCHAR NOT NULL,
    to_address VARCHAR NOT NULL,
    token_symbol VARCHAR,
    token_address VARCHAR,
    amount DOUBLE,
    amount_usd DOUBLE,
    block_number BIGINT,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS prices (
    id INTEGER,
    token VARCHAR NOT NULL,
    chain VARCHAR NOT NULL,
    price_usd DOUBLE NOT NULL,
    volume_24h DOUBLE,
    change_24h DOUBLE,
    timestamp TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER,
    address VARCHAR NOT NULL,
    chain VARCHAR NOT NULL,
    token VARCHAR NOT NULL,
    balance DOUBLE,
    value_usd DOUBLE,
    timestamp TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS tvl_snapshots (
    id INTEGER,
    chain VARCHAR NOT NULL,
    tvl DOUBLE NOT NULL,
    change_1h DOUBLE,
    change_24h DOUBLE,
    change_7d DOUBLE,
    timestamp TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS alerts_log (
    id INTEGER,
    alert_type VARCHAR NOT NULL,
    severity VARCHAR DEFAULT 'info',
    title VARCHAR,
    message TEXT,
    raw_data JSON,
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_transfers_timestamp ON transfers(timestamp);
CREATE INDEX IF NOT EXISTS idx_transfers_amount_usd ON transfers(amount_usd);
CREATE INDEX IF NOT EXISTS idx_prices_timestamp ON prices(timestamp);
CREATE INDEX IF NOT EXISTS idx_tvl_timestamp ON tvl_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts_log(created_at);
"""
