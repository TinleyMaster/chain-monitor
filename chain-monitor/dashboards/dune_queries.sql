-- chain-monitor Dune Dashboard Queries
-- Copy each query into a new Dune Query at https://dune.com/queries

-- ============================================================
-- 1. TVL Trends by Chain (Daily Time Series)
-- ============================================================

WITH tvl_data AS (
  SELECT
    date_trunc('day', block_time) AS day,
    chain,
    SUM(amount_usd) / 1e9 AS daily_volume_b
  FROM dex.trades
  WHERE block_time >= NOW() - INTERVAL '90' DAY
    AND chain IN ('ethereum','arbitrum','optimism','base','polygon','solana')
  GROUP BY 1, 2
)
SELECT
  day,
  chain,
  SUM(daily_volume_b) OVER (
    PARTITION BY chain ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ) AS rolling_7d_volume_b
FROM tvl_data
ORDER BY day DESC, rolling_7d_volume_b DESC


-- ============================================================
-- 2. Cross-Chain Activity Heatmap (Last 30 Days)
-- ============================================================

SELECT
  chain,
  DATE_TRUNC('day', block_time) AS day,
  COUNT(DISTINCT tx_hash) AS tx_count,
  COUNT(DISTINCT "from") AS active_users,
  SUM(amount_usd) AS total_volume_usd
FROM dex.trades
WHERE block_time >= NOW() - INTERVAL '30' DAY
  AND chain IN ('ethereum','arbitrum','optimism','base','polygon','solana')
GROUP BY 1, 2
ORDER BY day DESC, tx_count DESC


-- ============================================================
-- 3. Top Tokens by DEX Volume (24h)
-- ============================================================

SELECT
  token_symbol,
  chain,
  SUM(amount_usd) AS volume_24h,
  COUNT(DISTINCT "from") AS traders_24h
FROM dex.trades
WHERE block_time >= NOW() - INTERVAL '24' HOUR
  AND chain IN ('ethereum','arbitrum','optimism','base')
GROUP BY 1, 2
ORDER BY volume_24h DESC
LIMIT 20


-- ============================================================
-- 4. Whale Transaction Tracker (>$100k USD, Last 7 Days)
-- ============================================================

SELECT
  block_time,
  chain,
  tx_hash,
  token_symbol,
  amount_usd,
  "from",
  "to"
FROM dex.trades
WHERE block_time >= NOW() - INTERVAL '7' DAY
  AND amount_usd >= 100000
  AND chain IN ('ethereum','arbitrum','optimism','base','polygon')
ORDER BY amount_usd DESC
LIMIT 100


-- ============================================================
-- 5. Chain Dominance Over Time (% Share of Total Volume)
-- ============================================================

WITH daily AS (
  SELECT
    DATE_TRUNC('day', block_time) AS day,
    chain,
    SUM(amount_usd) AS volume
  FROM dex.trades
  WHERE block_time >= NOW() - INTERVAL '90' DAY
    AND chain IN ('ethereum','arbitrum','optimism','base','polygon','solana')
  GROUP BY 1, 2
),
totals AS (
  SELECT day, SUM(volume) AS total
  FROM daily
  GROUP BY 1
)
SELECT
  d.day,
  d.chain,
  d.volume,
  ROUND(d.volume * 100.0 / t.total, 2) AS share_pct
FROM daily d
JOIN totals t ON d.day = t.day
ORDER BY d.day DESC, share_pct DESC