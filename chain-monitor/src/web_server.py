"""Lightweight web dashboard for chain-monitor using Python stdlib.
Serves API endpoints and a single-page dashboard. Zero external deps."""

import json
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timedelta, timezone

from src.config import get_config
from src.db.store import Store

logger = logging.getLogger(__name__)

DAYS_LOOKBACK = 7
STATIC_DIR = Path(__file__).resolve().parent.parent / "web"

# Embedded dashboard HTML (single file, no CDN)
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chain Monitor Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.container{max-width:1400px;margin:0 auto;padding:20px}
h1{font-size:1.5rem;font-weight:600;color:#f0f6fc;margin-bottom:4px}
.subtitle{color:#8b949e;font-size:0.85rem;margin-bottom:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.card h2{font-size:0.8rem;text-transform:uppercase;letter-spacing:0.5px;color:#8b949e;margin-bottom:12px}
.stat-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #21262d;font-size:0.85rem}
.stat-row:last-child{border-bottom:none}
.stat-label{color:#8b949e}
.stat-value{font-weight:600}
.up{color:#3fb950}.down{color:#f85149}
.table{width:100%;border-collapse:collapse;font-size:0.82rem}
.table th{text-align:left;color:#8b949e;padding:6px 4px;border-bottom:1px solid #30363d;font-weight:500}
.table td{padding:6px 4px;border-bottom:1px solid #21262d}
.mono{font-family:'SF Mono','Fira Code',monospace;font-size:0.78rem}
.hash{color:#58a6ff}
.error{color:#f85149;font-style:italic}
.empty{color:#484f58;font-style:italic;padding:12px 0}
.loading{animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
#status-bar{font-size:0.78rem;color:#484f58;margin-top:16px;text-align:center}
</style>
</head>
<body>
<div class="container">
<h1>Chain Monitor</h1>
<div class="subtitle" id="clock">loading...</div>

<div class="grid">
<div class="card">
<h2>TVL by Chain (24h)</h2>
<div id="tvl-list"><span class="loading">loading...</span></div>
</div>
<div class="card">
<h2>Latest Prices</h2>
<div id="prices-list"><span class="loading">loading...</span></div>
</div>
<div class="card">
<h2>Recent Whale Transfers (7d)</h2>
<div id="whale-list"><span class="loading">loading...</span></div>
</div>
<div class="card">
<h2>Portfolio Summary</h2>
<div id="portfolio-list"><span class="loading">loading...</span></div>
</div>
<div class="card">
<h2>Recent Alerts</h2>
<div id="alerts-list"><span class="loading">loading...</span></div>
</div>
<div class="card">
<h2>Monitor Status</h2>
<div id="monitor-status"><span class="loading">loading...</span></div>
</div>
</div>

<div id="status-bar">auto-refresh every 30s</div>
</div>

<script>
async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
function fmt(n, d) { d = d || 0; return Number(n || 0).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}) }
function fmtB(n) { return (Number(n||0)/1e9).toFixed(2) + 'B' }
function pct(n) { const v=Number(n||0).toFixed(1); return (v>0?'+':'')+v+'%' }
function cls(n) { return n>=0?'up':'down' }

async function load() {
  try {
    // Clock
    document.getElementById('clock').textContent = new Date().toLocaleString();

    // TVL
    const tvl = await fetchJSON('/api/tvl/latest');
    var h='<table class="table"><tr><th>Chain</th><th>TVL</th><th>1h</th><th>24h</th></tr>';
    for (var t of tvl) {
      h += '<tr><td>'+t.chain.toUpperCase()+'</td><td>$'+fmtB(t.tvl)+'</td>';
      h += '<td class="'+cls(t.change_1h||0)+'">'+pct(t.change_1h)+'</td>';
      h += '<td class="'+cls(t.change_24h||0)+'">'+pct(t.change_24h)+'</td></tr>';
    }
    document.getElementById('tvl-list').innerHTML = h||'<div class="empty">no data</div>';

    // Prices
    const prices = await fetchJSON('/api/prices/latest');
    h='<table class="table"><tr><th>Token</th><th>Chain</th><th>Price</th></tr>';
    var seen={};
    for (var p of prices.sort((a,b)=>b.price_usd-a.price_usd)) {
      var k = p.token+p.chain;
      if (seen[k]) continue;
      seen[k]=true;
      h += '<tr><td>'+p.token+'</td><td>'+p.chain.toUpperCase()+'</td><td>$'+fmt(p.price_usd,4)+'</td></tr>';
    }
    document.getElementById('prices-list').innerHTML = h||'<div class="empty">no data</div>';

    // Whales
    const whales = await fetchJSON('/api/transfers/recent');
    h='<table class="table"><tr><th>Chain</th><th>Token</th><th>Amount</th><th>TX</th></tr>';
    for (var w of whales.slice(0,8)) {
      h += '<tr><td>'+w.chain.toUpperCase()+'</td><td>'+w.token_symbol+'</td>';
      h += '<td>$'+fmt(w.amount_usd,0)+'</td>';
      h += '<td class="mono hash">'+w.tx_hash.slice(0,10)+'...</td></tr>';
    }
    document.getElementById('whale-list').innerHTML = h||'<div class="empty">no whale transfers</div>';

    // Portfolio
    const pf = await fetchJSON('/api/portfolio/latest');
    h='<table class="table"><tr><th>Address</th><th>Chain</th><th>Token</th><th>Value</th></tr>';
    for (var p of pf.slice(0,8)) {
      h += '<tr><td class="mono hash">'+p.address.slice(0,6)+'...</td>';
      h += '<td>'+p.chain.toUpperCase()+'</td><td>'+p.token+'</td><td>$'+fmt(p.value_usd,2)+'</td></tr>';
    }
    document.getElementById('portfolio-list').innerHTML = h||'<div class="empty">no positions</div>';

    // Alerts
    const alerts = await fetchJSON('/api/alerts/recent');
    h='';
    for (var a of alerts.slice(0,5)) {
      h += '<div class="stat-row"><span>'+a.alert_type+'</span><span>'+a.title+'</span></div>';
    }
    document.getElementById('alerts-list').innerHTML = h||'<div class="empty">no recent alerts</div>';

    // Status
    const status = await fetchJSON('/api/status');
    h='';
    for (var m of status) {
      h += '<div class="stat-row"><span>'+m.name+'</span><span style="color:#3fb950">running</span></div>';
    }
    document.getElementById('monitor-status').innerHTML = h||'<div class="empty">no monitors</div>';
  } catch(e) {
    document.getElementById('status-bar').textContent = 'Error: '+e.message;
  }
}

load();
setInterval(load, 30000);
</script>
</body>
</html>"""


class APIHandler(BaseHTTPRequestHandler):
    store = None  # Set by server

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _json(self, data, code=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content, code=200):
        body = content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/" or path == "/dashboard":
                self._html(DASHBOARD_HTML)
            elif path == "/api/status":
                self._api_status()
            elif path == "/api/tvl/latest":
                self._api_tvl_latest()
            elif path == "/api/prices/latest":
                self._api_prices_latest()
            elif path == "/api/transfers/recent":
                self._api_transfers_recent()
            elif path == "/api/portfolio/latest":
                self._api_portfolio_latest()
            elif path == "/api/alerts/recent":
                self._api_alerts_recent()
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            logger.error("[web] Error handling %s: %s", path, e)
            self._json({"error": str(e)}, 500)

    # --- API endpoints ---

    def _api_status(self):
        cfg = get_config()
        monitors_cfg = cfg.get("monitors", {})
        results = []
        for name in monitors_cfg:
            results.append({"name": name, "running": True})
        self._json(results)

    def _api_tvl_latest(self):
        rows = self._query(
            "SELECT DISTINCT ON (chain) chain, tvl, change_1h, change_24h, timestamp "
            "FROM tvl_snapshots ORDER BY chain, timestamp DESC"
        )
        cols = ["chain", "tvl", "change_1h", "change_24h", "timestamp"]
        results = [dict(zip(cols, row)) for row in rows]
        results.sort(key=lambda x: x["tvl"] or 0, reverse=True)
        self._json(results)

    def _api_prices_latest(self):
        rows = self._query(
            "SELECT token, chain, price_usd, timestamp FROM prices "
            "ORDER BY timestamp DESC LIMIT 30"
        )
        cols = ["token", "chain", "price_usd", "timestamp"]
        self._json([dict(zip(cols, row)) for row in rows])

    def _api_transfers_recent(self):
        start = (datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)).isoformat()
        rows = self._query(
            "SELECT chain, tx_hash, token_symbol, amount_usd, from_address, to_address, timestamp "
            "FROM transfers WHERE timestamp >= ? ORDER BY amount_usd DESC LIMIT 20",
            [start]
        )
        cols = ["chain", "tx_hash", "token_symbol", "amount_usd", "from_address", "to_address", "timestamp"]
        self._json([dict(zip(cols, row)) for row in rows])

    def _api_portfolio_latest(self):
        rows = self._query(
            "SELECT address, chain, token, value_usd, timestamp FROM portfolio_snapshots "
            "ORDER BY timestamp DESC LIMIT 20"
        )
        cols = ["address", "chain", "token", "value_usd", "timestamp"]
        self._json([dict(zip(cols, row)) for row in rows])

    def _api_alerts_recent(self):
        rows = self._query(
            "SELECT alert_type, severity, title, message, created_at FROM alerts_log "
            "ORDER BY created_at DESC LIMIT 10"
        )
        cols = ["alert_type", "severity", "title", "message", "created_at"]
        self._json([dict(zip(cols, row)) for row in rows])

    def _query(self, sql, params=None):
        if APIHandler.store is None:
            APIHandler.store = Store()
        return APIHandler.store.conn.execute(sql, params or []).fetchall()


def start_web_server(host="0.0.0.0", port=8080):
    """Start the HTTP server in a daemon thread. Call before event loop starts."""
    t = threading.Thread(target=_run_server, args=(host, port), daemon=True)
    t.start()
    logger.info("[web] Dashboard available at http://localhost:%d", port)
    return t


def _run_server(host, port):
    server = HTTPServer((host, port), APIHandler)
    APIHandler.store = Store()
    logger.info("[web] Server started on %s:%d", host, port)
    server.serve_forever()
