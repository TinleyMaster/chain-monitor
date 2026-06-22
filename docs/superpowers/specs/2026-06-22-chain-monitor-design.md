# 全链监控系统设计方案

> 版本: v1.0 | 日期: 2026-06-22 | 目标用户: Solo 链上数据分析师

---

## 1. 设计目标

为 solo 程序员搭建一个**零月费成本 / 低维护**的全链监控系统，覆盖 5 大监控场景：

| # | 监控场景 | 实时性要求 | 核心数据源 |
|---|---------|----------|----------|
| 1 | 大盘热点与趋势 | 分钟级(10-30min) | DefiLlama API |
| 2 | 大额转账监控 | 秒级(实时) | Alchemy WS / Helius WS |
| 3 | 代币价格告警 | 分钟级(1-5min) | DefiLlama / Covalent |
| 4 | 持仓变化跟踪 | 秒级(实时) | Covalent + Alchemy WS |
| 5 | TVL 趋势 | 分钟级(10-30min) | DefiLlama API |

**目标链**: Ethereum + Arbitrum + Optimism + Base + Polygon + Solana
**部署模式**: 本地 PC (开发/运行时) + 可选云服务器 $5-10/月 (24h 不间断)
**告警通道**: Telegram Bot
**月运行成本**: $0 (纯本地) / ~$10 (加云服务器)

## 2. 架构总览

```
+----------------------------------------------------------------+
|                        数据采集层                                |
|                                                                  |
|  +----------+  +----------+  +----------+  +----------+         |
|  |DefiLlama |  | Covalent |  | Alchemy  |  | Helius   |         |
|  |REST API  |  | REST API |  | WS/RPC   |  | WS/RPC   |         |
|  |(免费)    |  |(免费100k |  |(免费300M |  |(免费25k  |         |
|  | 免key)   |  | credits/d)|  | CU/月)   |  | req/d)   |         |
|  +----+-----+  +----+-----+  +----+-----+  +----+-----+         |
|       |             |             |              |              |
|       v             v             v              v              |
+----------------------------------------------------------------+
|                        处理层                                   |
|                                                                  |
|  +----------------------------------------------------------+   |
|  |                Python 监控引擎 (异步)                       |   |
|  |                                                           |   |
|  |  market_trend.py    whale_transfer.py    price_alert.py   |   |
|  |  portfolio.py       tvl_trend.py                          |   |
|  |                                                           |   |
|  |  +- Event Filter -+  +- Condition Engine -+              |   |
|  |  |  >$100k 转账   |  |  价格波动 >5%      |              |   |
|  |  |  新 token 部署  |  |  TVL 变化 >10%     |              |   |
|  |  +----------------+  +-------------------+              |   |
|  +----------------------+-----------------------------------+   |
|                         |                                       |
|                         v                                       |
|  +----------------------------------------------------------+  |
|  |           DuckDB (本地列存数据库)                           |  |
|  |  Tables: transfers, prices, portfolio,                    |  |
|  |          tvl_history, alerts_log                           |  |
|  +----------------------------------------------------------+  |
+----------------------------------------------------------------+
|                        输出层                                   |
|                                                                  |
|  +------------------------+  +-----------------------------+    |
|  |  Telegram Bot          |  |  Dune Dashboard             |    |
|  |  -> 实时告警推送        |  |  -> 日频看板                |    |
|  |  -> 日报/周报摘要       |  |  -> TVL 趋势图             |    |
|  |  -> 自定义查询回执      |  |  -> 热点概览                |    |
|  +------------------------+  +-----------------------------+    |
|                                                                  |
|  +----------------------------------------------------------+  |
|  |  (可选) Grafana + DuckDB Data Source                     |  |
|  |  -> 本地实时可视化面板                                     |  |
|  +----------------------------------------------------------+  |
+----------------------------------------------------------------+
```

---

## 3. 数据源选型与成本明细

| 数据源 | 用途 | 免费层配额 | 超额成本 | 按量估价(月) |
|-------|------|-----------|---------|------------|
| DefiLlama | TVL / 价格 / 收益 | 无限制, 无需 key | - | $0 |
| Covalent | 多链余额 / 转账 / holder | 100k credits/天 | $54/月起 | $0 |
| Alchemy | EVM 链实时 WS 监听 | 300M CU/月 | pay-as-you-go | $0 |
| Helius | Solana 实时 WS 监听 | 25k req/天 | $49/月起 | $0 |
| The Graph | 协议深度数据查询 | 无限制(托管子图) | - | $0 |
| Dune | 历史看板/可视化 | 免费版(20 query) | $240/年 | $0 |
| Telegram Bot | 告警推送 | 无限制 | - | $0 |
| DuckDB | 本地数据存储 | 无限制 | - | $0 |

**结论: 所有核心功能均可跑在免费层**

---

## 4. 数据采集层 -- 各模块设计

### 4.1 大盘热点与趋势 (market_trend.py)

**数据源**: DefiLlama API (完全免费, 无需 API Key)

| 端点 | 数据内容 | 轮询频率 | 用途 |
|-----|---------|---------|------|
| /api/v2/chains | 各链 TVL、变化率 | 10min | 全网 TVL 排名变化 |
| /api/v2/tokens/trending | 热点 token 列表 | 10min | 发现新热点 |
| /api/v2/dexs/... | DEX 交易量 | 30min | 链活跃度 |
| /api/v2/yields | 收益池利率 | 30min | 资金流向信号 |

**输出**:
- 定时推送 Telegram: "今日热点: Solana TVL +5.2%, ETH +2.1%..."
- 涨跌幅超过阈值的推送实时告警

### 4.2 大额转账监控 (whale_transfer.py)

**数据源**: Alchemy WebSocket (EVM) + Helius WebSocket (Solana)

**EVM 链 (Alchemy WS)**

核心思路: 监听 pending 交易池 + 过滤大额转账

- eth_subscribe (newPendingTransactions)
- 解析 tx.value 或 tx.data, 匹配 ERC20 Transfer 事件
- 阈值: >$100k / >$500k / >$1M (按 token 汇率换算)

**Solana (Helius WS)**

- 监听大户地址的 token 转账
- 或监听特定 program 的大额交易

**监控地址来源**:
- 预配置知名 whale 地址
- 自动发现: 追踪 TVL top 协议的 treasury 地址
- 用户自定义跟踪地址

**输出**: 实时 Telegram 推送, 含交易详情

### 4.3 代币价格告警 (price_alert.py)

**数据源**: DefiLlama API (无需 key)

API 端点:
- GET /api/v2/tokens/price/current/{token_addresses}
- GET /api/v2/tokens/price/historical/{token_address}

**告警条件配置**:

```
price_alerts:
  - token: "WETH"
    chain: "ethereum"
    alerts:
      - type: "percent_change"   # 5分钟内波动 >5%
        threshold: 5
        direction: "both"
      - type: "above"             # 突破 $4000
        threshold_usd: 4000
      - type: "below"             # 跌破 $2000
        threshold_usd: 2000
```

**输出**: Telegram 实时推送 + 存储历史价格到 DuckDB

### 4.4 持仓变化跟踪 (portfolio.py)

**数据源组合**: Covalent API + Alchemy WS

- 初始拉取: Covalent API 一次性拿全量持仓
- 实时更新: Alchemy WS 监听目标地址的交易, 交易确认后更新持仓状态

**功能**:
- 跟踪多个地址 (自己的 + 关注的)
- 持仓价值汇总 (链上总和, 按 USD 计价)
- 变动推送

### 4.5 TVL 趋势 (tvl_trend.py)

**数据源**: DefiLlama API

API 端点:
- GET /api/v2/chains           # 各链当前 TVL
- GET /api/v2/protocols        # 各协议 TVL
- GET /api/v2/chains/{chain}   # 单链 TVL 历史

**输出**:
- 每日推送 TVL 排名变化日报
- 单链 TVL 突破/跌破阈值告警
- Dune Dashboard 汇总 TVL 趋势图

---

## 5. 系统组件设计

### 5.1 项目结构

```
C:\Users\SuperTing\Documents\BlockChain\chain-monitor\
+-- src/
|   +-- __init__.py
|   +-- main.py                  # 入口: 启动所有监控模块
|   +-- config.py                # 配置加载 (yaml)
|   +-- monitors/
|   |   +-- __init__.py
|   |   +-- base_monitor.py      # 监控器基类
|   |   +-- market_trend.py      # 大盘热点
|   |   +-- whale_transfer.py    # 大额转账
|   |   +-- price_alert.py       # 价格告警
|   |   +-- portfolio.py         # 持仓跟踪
|   |   +-- tvl_trend.py         # TVL 趋势
|   +-- notifiers/
|   |   +-- __init__.py
|   |   +-- base.py              # 通知接口
|   |   +-- telegram.py          # Telegram 实现
|   +-- db/
|   |   +-- __init__.py
|   |   +-- schema.py            # 建表 DDL
|   |   +-- store.py             # DuckDB 读写封装
|   +-- utils/
|       +-- __init__.py
|       +-- chains.py            # 链配置常量
|       +-- formatters.py        # 消息格式化
+-- config.yaml                   # 用户配置
+-- requirements.txt
+-- README.md
```

### 5.2 数据库 (DuckDB) 表结构

```
-- 大额转账记录
CREATE TABLE transfers (
    id BIGSERIAL PRIMARY KEY,
    chain VARCHAR,
    tx_hash VARCHAR,
    from_address VARCHAR,
    to_address VARCHAR,
    token_symbol VARCHAR,
    token_address VARCHAR,
    amount FLOAT,
    amount_usd FLOAT,
    block_number BIGINT,
    timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 价格快照
CREATE TABLE prices (
    id BIGSERIAL PRIMARY KEY,
    token VARCHAR,
    chain VARCHAR,
    price_usd FLOAT,
    volume_24h FLOAT,
    change_24h FLOAT,
    timestamp TIMESTAMP
);

-- 持仓快照
CREATE TABLE portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    address VARCHAR,
    chain VARCHAR,
    token VARCHAR,
    balance FLOAT,
    value_usd FLOAT,
    timestamp TIMESTAMP
);

-- TVL 快照
CREATE TABLE tvl_snapshots (
    id BIGSERIAL PRIMARY KEY,
    chain VARCHAR,
    tvl FLOAT,
    change_24h FLOAT,
    timestamp TIMESTAMP
);

-- 告警日志
CREATE TABLE alerts_log (
    id BIGSERIAL PRIMARY KEY,
    alert_type VARCHAR,
    severity VARCHAR,
    title VARCHAR,
    message TEXT,
    raw_data JSON,
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 5.3 Telegram 告警格式

```
[大额转账 | ETH]
代币: USDC
金额: $1,234,567 (1,234,567 USDC)
发送: 0xABCD...1234
接收: 0xEFGH...5678
交易: etherscan.io/tx/0x...

[价格异动 | ETH]
5分钟内 +6.2%
当前: $3,456

[今日行情速报 09:00]
ETH: $3,456 (+2.1%)
SOL: $145.2 (+5.8%)
链TVL TOP5:
1. ETH   $62.1B (+2.1%)
2. TRON  $21.3B (+0.5%)
3. SOL   $12.8B (+5.2%)
```

---

## 6. 部署与运行

### 6.1 依赖安装

pip install aiohttp web3 python-telegram-bot duckdb pyyaml schedule

### 6.2 运行模式

| 模式 | 说明 | 适合场景 |
|-----|------|---------|
| python main.py | 完整模式, 启动所有模块 | 开发调试 / 本地运行 |
| python main.py --monitor whale | 单模块运行 | 调试特定模块 |
| python main.py --dry-run | 不推送, 仅打印到控制台 | 验证配置 |

### 6.3 部署方案

#### 方案1: 本地 PC (推荐起步)

[Windows PC]
  +- Python 进程 (白天运行)
  +- DuckDB (本地文件)
  +- Telegram Bot (实时推送)

成本: $0 | 局限: 电脑关机则暂停

#### 方案2: 本地 + 云服务器 (推荐进阶)

[云服务器 $5-10/月]
  +- Python 进程 (24h 实时监听)
  +- DuckDB (持久化)
  +- Telegram Bot

[本地 PC]
  +- Grafana (可视化看板, 可选)

成本: ~$5-10/月 | 优势: 7x24h 不间断

#### 推荐云服务器

| 供应商 | 配置 | 价格 | 推荐 |
|-------|------|-----|------|
| Hetzner CX22 | 2vCPU / 4GB / 40GB | ~4.5/月 | 性价比首选 |
| Oracle Cloud Free | 4vCPU / 24GB (ARM) | $0/月 | 难申请 |
| DigitalOcean | 2vCPU / 2GB / 60GB | $12/月 | 稳定但略贵 |

---

## 7. 实现路线图

### Phase 1: Foundation (Day 1-2)
- [ ] 项目目录初始化
- [ ] config.yaml 配置框架
- [ ] Telegram Bot 连接测试
- [ ] DuckDB schema 建表
- [ ] DefiLlama API 连接测试
- [ ] market_trend.py TVL 趋势推送

### Phase 2: 实时监控 (Day 3-5)
- [ ] Alchemy WS 连接和订阅
- [ ] whale_transfer.py EVM 链大额转账监听
- [ ] Helius WS 连接和 Solana 监控
- [ ] price_alert.py 价格告警
- [ ] portfolio.py 持仓跟踪
- [ ] 告警消息格式化

### Phase 3: 看板与增强 (Day 6-7)
- [ ] 每日/每周行情摘要报告
- [ ] Dune Dashboard (TVL 趋势 + 大盘热力图)
- [ ] DuckDB 数据保留策略
- [ ] Grafana 本地看板 (可选)
- [ ] README 和部署文档

### Phase 4: 可选增强 (后续)
- [ ] Web 管理界面 (FastAPI + 简单前端)
- [ ] 多用户/多群组推送
- [ ] 链上声誉风险评估
- [ ] MEV / 清算监控

---

## 8. 风险与应对

| 风险 | 影响 | 应对方案 |
|-----|------|---------|
| API 免费层配额超额 | 模块中断 | 设置每日配额预警 |
| WS 断连 | 丢数据 | 自动重连 + 补拉历史块 |
| 本地电脑关机 | 实时监控中断 | 方案2云服务器不受影响 |
| 链分叉 / reorg | 虚假告警 | 等待 N 个确认后再推送 |
| Telegram API 限频 | 推送延迟 | 消息队列 + 聚合告警 |

---

## 9. 附录: API 端点速查

| 数据源 | 端点 | 用途 |
|-------|------|------|
| DefiLlama | https://api.llama.fi/v2/chains | 各链 TVL |
| DefiLlama | https://api.llama.fi/v2/tokens/trending | 热点 token |
| DefiLlama | https://coins.llama.fi/prices/current/{addresses} | 代币价格 |
| Covalent | https://api.covalenthq.com/v1/{chain}/address/{addr}/balances_v2/ | 持仓余额 |
| Covalent | https://api.covalenthq.com/v1/{chain}/address/{addr}/transactions_v2/ | 交易历史 |
| Alchemy | wss://eth-mainnet.g.alchemy.com/v2/{key} | ETH WS 端点 |
| Helius | wss://mainnet.helius-rpc.com/?api-key={key} | Solana WS 端点 |
| The Graph | https://gateway.thegraph.com/api/{key}/subgraphs/id/{id} | 子图查询 |
