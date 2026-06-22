# chain-monitor

Multi-chain blockchain monitoring system for solo analysts. Zero subscription cost (all free-tier APIs), runs on your local machine or a $5/mo VPS.

## Architecture

```
Data Sources (all free):
  DefiLlama API  -> TVL, token prices, trending tokens
  Alchemy WS     -> EVM real-time event listening
  Helius WS      -> Solana real-time monitoring  
  Covalent API   -> Multi-chain balances, transaction history
  The Graph      -> Protocol-level indexed data

Processing:
  Python (asyncio + aiohttp + web3.py)

Storage:
  DuckDB (local, zero-config columnar database)

Output:
  Telegram Bot (real-time alerts)
  Dune Dashboard (daily trend boards)
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

Edit `config.yaml` and add your API keys:
- Alchemy: https://www.alchemy.com/ (free tier, 300M CU/month)
- Helius: https://www.helius.dev/ (free tier, 25k requests/day)
- Telegram: Create bot via @BotFather

```yaml
api_keys:
  alchemy:
    eth-mainnet: "your_key_here"
    arbitrum: "your_key_here"
    optimism: "your_key_here"
    base: "your_key_here"
    polygon: "your_key_here"
  helius:
    solana: "your_key_here"
  telegram:
    bot_token: "your_bot_token"
    chat_id: "your_chat_id"
```

### 3. Run

```bash
# Run all enabled monitors (continuous loop)
python -m src.main

# Run once and exit (testing)
python -m src.main --once

# Run without Telegram notifications
python -m src.main --once --dry-run

# Run single module
python -m src.main --monitor market_trend --once
```

## Monitor Modules

| Module | Description | Data Source | Interval |
|--------|-------------|-------------|----------|
| market_trend | TVL by chain, trending tokens | DefiLlama | 10 min |
| whale_transfer | Large transfer detection | Alchemy WS + Helius WS | real-time |
| price_alert | Token price alerts | DefiLlama | 3 min |
| portfolio | Wallet balance tracking | Covalent + Alchemy WS | 5 min |
| tvl_trend | TVL trend alerts | DefiLlama | 15 min |

## Deployment

### Local PC
Run during work hours, pauses when PC sleeps.

### Cloud VPS ($5/mo)
```bash
# Hetzner CX22 (€4.5/mo) recommended
ssh your-vps
git clone <repo>
cd chain-monitor
pip install -r requirements.txt
cp config.yaml.example config.yaml  # edit with your keys
nohup python -m src.main &
```

## Cost

All APIs use free tiers. Total monthly cost: $0.

| Service | Free Tier | Monthly Cost |
|---------|-----------|-------------|
| DefiLlama | Unlimited, no key | $0 |
| Alchemy | 300M CU | $0 |
| Helius | 25k req/day | $0 |
| Covalent | 100k credits/day | $0 |
| The Graph | Unlimited (hosted subgraphs) | $0 |
| Dune | 20 queries | $0 |
| Telegram | Unlimited | $0 |
| DuckDB | Local | $0 |

## Project Structure

```
chain-monitor/
├── src/
│   ├── main.py              # Entry point
│   ├── config.py            # YAML config loader
│   ├── monitors/
│   │   ├── base_monitor.py  # Abstract base class
│   │   ├── market_trend.py  # TVL & trending (Phase 1 done)
│   │   ├── whale_transfer.py
│   │   ├── price_alert.py
│   │   ├── portfolio.py
│   │   └── tvl_trend.py
│   ├── notifiers/
│   │   ├── base.py
│   │   └── telegram.py      # Telegram Bot notifier
│   ├── db/
│   │   ├── schema.py        # DuckDB table schemas
│   │   └── store.py         # CRUD operations
│   └── utils/
│       ├── chains.py        # Chain constants
│       └── formatters.py    # Message formatting
├── data/                     # DuckDB database files
├── dashboards/               # Dune SQL query references
├── config.yaml               # User configuration
└── requirements.txt
```

## Implementation Status

- [x] Phase 1: Foundation (project scaffold, config, DB, Telegram, market_trend)
- [ ] Phase 2: Real-time monitoring (whale_transfer, price_alert, portfolio)
- [ ] Phase 3: Dashboards & reporting (Dune, daily/weekly reports)
- [ ] Phase 4: Optional enhancements (Web UI, MEV monitoring, liquidation tracking)
