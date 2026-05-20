"""
Swing Scanner — Flask Web App
==============================
Serves a single-page dashboard that reads live data from Firebase Realtime DB.
All HTML / CSS / JS is inlined (same pattern as the existing stockscanner).

Environment variables:
  FIREBASE_URL          — Firebase Realtime Database URL
  FIREBASE_API_KEY      — Firebase Web API key
  FIREBASE_AUTH_DOMAIN  — Firebase auth domain  (e.g. project.firebaseapp.com)
  FIREBASE_PROJECT_ID   — Firebase project ID
  FIREBASE_APP_ID       — Firebase web app ID

Flask routes:
  GET /                        — main dashboard
  GET /api/detail/<ticker>     — fresh yfinance snapshot for expanded card view
"""

import os

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Firebase config (injected from env into the JS template)
# ---------------------------------------------------------------------------

FIREBASE_CFG = {
    "apiKey":      os.environ.get("FIREBASE_API_KEY",     ""),
    "authDomain":  os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
    "databaseURL": os.environ.get("FIREBASE_URL",         ""),
    "projectId":   os.environ.get("FIREBASE_PROJECT_ID",  ""),
    "appId":       os.environ.get("FIREBASE_APP_ID",      ""),
}

ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")

# ---------------------------------------------------------------------------
# Helpers (shared with scanner.py logic, duplicated here to keep app.py standalone)
# ---------------------------------------------------------------------------

def _compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _compute_rsi(closes: pd.Series, period: int = 14) -> float:
    delta    = closes.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    rsi      = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def _compute_bb(closes: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma   = closes.rolling(period).mean()
    std   = closes.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    width = (upper - lower) / sma.replace(0, np.nan)
    denom = (upper - lower).replace(0, np.nan)
    pct_b = (closes - lower) / denom
    return sma.iloc[-1], upper.iloc[-1], lower.iloc[-1], width.iloc[-1], pct_b.iloc[-1], width

# ---------------------------------------------------------------------------
# API route: detail view for expanded card
# ---------------------------------------------------------------------------

@app.route("/api/detail/<ticker>")
def detail(ticker: str):
    """
    Fetch fresh yfinance data for a single ticker and return indicator detail.
    Used by the expanded card in the dashboard.
    """
    ticker = ticker.upper().strip()
    is_crypto = ticker.endswith("-USD")

    try:
        raw = yf.download(ticker, period="1y", interval="1d",
                          progress=False, auto_adjust=True)
        if raw.empty or len(raw) < 50:
            return jsonify({"error": "Insufficient data"}), 404

        # Handle multi-level columns (yfinance ≥ 0.2.x)
        if isinstance(raw.columns, pd.MultiIndex):
            closes  = raw["Close"][ticker].dropna()
            volumes = raw["Volume"][ticker].dropna()
        else:
            closes  = raw["Close"].dropna()
            volumes = raw["Volume"].dropna()

        price = float(closes.iloc[-1])

        ema9   = float(_compute_ema(closes, 9).iloc[-1])
        ema20  = float(_compute_ema(closes, 20).iloc[-1])
        sma50  = float(closes.rolling(50).mean().iloc[-1])
        sma200 = float(closes.rolling(200).mean().iloc[-1])
        rsi    = _compute_rsi(closes, 14)

        sma_bb, upper_bb, lower_bb, bb_width, pct_b, bb_width_series = _compute_bb(closes)

        # BB width percentile over last 252 trading days
        hist_widths  = bb_width_series.dropna().iloc[-252:]
        squeeze_pct  = float((hist_widths < bb_width).sum() / len(hist_widths) * 100) \
                       if len(hist_widths) >= 20 else 50.0

        avg_vol_20 = float(volumes.iloc[-21:-1].mean())
        today_vol  = float(volumes.iloc[-1])
        rvol       = today_vol / avg_vol_20 if avg_vol_20 > 0 else 0

        # Volume chart data: last 20 days
        vol_bars = []
        for i in range(max(0, len(volumes) - 20), len(volumes)):
            vol_bars.append({
                "date":   str(volumes.index[i])[:10],
                "volume": int(volumes.iloc[i]),
            })

        # Recent close prices for spark-like reference
        recent_closes = [round(float(v), 4) for v in closes.iloc[-30:]]

        return jsonify({
            "ticker":        ticker,
            "is_crypto":     is_crypto,
            "price":         round(price, 4),
            # Moving averages
            "ema9":          round(ema9, 4),
            "ema20":         round(ema20, 4),
            "sma50":         round(sma50, 4),
            "sma200":        round(sma200, 4),
            "above_ema9":    price > ema9,
            "above_ema20":   price > ema20,
            "above_sma50":   price > sma50,
            "above_sma200":  price > sma200,
            # Bollinger Bands
            "bb_upper":      round(float(upper_bb), 4),
            "bb_lower":      round(float(lower_bb), 4),
            "bb_sma":        round(float(sma_bb), 4),
            "bb_width":      round(float(bb_width), 4),
            "bb_squeeze_pct": round(squeeze_pct, 1),
            "pct_b":         round(float(pct_b), 3),
            # RSI & volume
            "rsi":           round(rsi, 1),
            "rvol":          round(rvol, 2),
            "avg_vol_20":    int(avg_vol_20),
            "today_vol":     int(today_vol),
            # Chart data
            "vol_bars":      vol_bars,
            "recent_closes": recent_closes,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    import json
    fb_cfg_json = json.dumps(FIREBASE_CFG)
    is_staging  = ENVIRONMENT == "staging"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swing Scanner {"[STAGING]" if is_staging else ""}</title>
<style>
:root{{
  --bg:#0d0d0d;
  --bg2:#1a1a1a;
  --bg3:#252525;
  --text:#e8eaf0;
  --muted:#7a8394;
  --border:#2e2e2e;
  --green:#2ecc71;
  --amber:#f39c12;
  --red:#e74c3c;
  --blue:#3498db;
  --orange:#e67e22;
  --gray:#555;
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}}

/* Header */
.header{{
  background:var(--bg2);
  border-bottom:1px solid var(--border);
  padding:14px 24px;
  display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;gap:12px;flex-wrap:wrap;
}}
.header-left h1{{font-size:18px;font-weight:700;letter-spacing:.5px;}}
.header-left p{{font-size:11px;color:var(--muted);margin-top:2px;}}
.header-right{{display:flex;align-items:center;gap:12px;}}
.live-dot{{width:8px;height:8px;border-radius:50%;background:var(--green);animation:pulse 1.6s infinite;display:inline-block;margin-right:4px;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
.stat-pill{{
  background:var(--bg3);border:1px solid var(--border);
  border-radius:20px;padding:4px 12px;font-size:11px;color:var(--muted);
}}
.stat-pill span{{color:var(--text);font-weight:600;margin-left:4px;}}

/* Filter bar */
.filterbar{{
  background:var(--bg2);border-bottom:1px solid var(--border);
  padding:10px 24px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
}}
.filterbar-label{{font-size:11px;color:var(--muted);margin-right:4px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;}}
.fbtn{{
  padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;
  border:1px solid var(--border);background:var(--bg3);color:var(--muted);
  transition:all .15s;
}}
.fbtn:hover{{color:var(--text);border-color:var(--blue);}}
.fbtn.active{{background:var(--blue);color:#fff;border-color:var(--blue);}}
.fbtn.active.green{{background:var(--green);border-color:var(--green);color:#000;}}
.fbtn.active.amber{{background:var(--amber);border-color:var(--amber);color:#000;}}
.fbtn.active.gray{{background:#444;border-color:#444;color:#fff;}}
.sep{{width:1px;height:20px;background:var(--border);margin:0 4px;}}

/* Grid */
.grid{{padding:20px 24px;display:flex;flex-direction:column;gap:12px;}}

/* Card */
.card{{
  background:var(--bg2);border:1px solid var(--border);
  border-left:4px solid var(--border);border-radius:12px;overflow:hidden;
  transition:box-shadow .2s;box-shadow:0 3px 12px rgba(0,0,0,.3);
}}
.card:hover{{box-shadow:0 6px 20px rgba(0,0,0,.5);}}
.card.breakout{{border-left-color:var(--green);}}
.card.watch{{border-left-color:var(--amber);}}
.card.building{{border-left-color:var(--gray);}}

/* Card header (always visible, click to expand) */
.card-header{{
  display:flex;align-items:center;gap:14px;
  padding:16px 18px;cursor:pointer;user-select:none;
}}
.card-header:hover{{background:rgba(255,255,255,.03);}}

.rank-num{{
  width:30px;height:30px;border-radius:50%;
  background:var(--bg3);display:flex;align-items:center;justify-content:center;
  font-size:12px;font-weight:700;color:var(--muted);flex-shrink:0;
}}
.rank-num.top{{background:#1a3d2b;color:var(--green);}}

.ticker-block{{flex:1;min-width:0;}}
.ticker-name{{font-size:18px;font-weight:700;letter-spacing:-.3px;display:flex;align-items:center;gap:8px;}}
.crypto-badge{{
  background:var(--orange);color:#fff;font-size:9px;font-weight:700;
  padding:2px 7px;border-radius:10px;letter-spacing:.5px;
}}
.ticker-sub{{font-size:11px;color:var(--muted);margin-top:3px;}}

.price-block{{text-align:center;min-width:80px;}}
.price-val{{font-size:16px;font-weight:600;}}
.price-chg{{font-size:11px;margin-top:2px;}}
.up{{color:var(--green);}}.dn{{color:var(--red);}}

.score-block{{text-align:right;flex-shrink:0;}}
.score-num{{font-size:28px;font-weight:700;line-height:1;}}
.score-num.green{{color:var(--green);}}
.score-num.amber{{color:var(--amber);}}
.score-num.gray{{color:var(--gray);}}
.score-lbl{{font-size:10px;font-weight:700;letter-spacing:.8px;margin-top:3px;}}
.score-lbl.green{{color:var(--green);}}
.score-lbl.amber{{color:var(--amber);}}
.score-lbl.gray{{color:var(--gray);}}

/* Key metrics row */
.metrics-row{{
  display:flex;gap:0;border-top:1px solid var(--border);
}}
.metric-item{{
  flex:1;padding:8px 12px;border-right:1px solid var(--border);
  display:flex;flex-direction:column;gap:2px;
}}
.metric-item:last-child{{border-right:none;}}
.metric-label{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;}}
.metric-value{{font-size:13px;font-weight:600;}}

/* BB status row */
.bb-status-row{{
  padding:6px 18px;border-top:1px solid var(--border);
  font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px;
}}
.bb-breakout{{color:var(--green);}}
.bb-squeeze{{color:var(--amber);}}
.bb-building{{color:var(--muted);}}

/* Expanded body */
.card-body{{border-top:2px solid var(--border);padding:18px;display:none;}}
.card-body.open{{display:block;}}

.detail-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
@media(max-width:600px){{.detail-grid{{grid-template-columns:1fr;}}}}

.detail-section{{background:var(--bg3);border-radius:8px;padding:14px;}}
.detail-title{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:10px;}}

/* BB width bar */
.bb-bar-track{{height:8px;background:#333;border-radius:4px;overflow:hidden;margin:6px 0;}}
.bb-bar-fill{{height:100%;border-radius:4px;transition:width .4s;}}

/* EMA stack table */
.ema-row{{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #2a2a2a;}}
.ema-row:last-child{{border-bottom:none;}}
.ema-name{{font-size:12px;color:var(--muted);}}
.ema-val{{font-size:12px;font-weight:600;}}
.ema-status{{font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;}}
.ema-above{{background:#1a3d2b;color:var(--green);}}
.ema-below{{background:#3d1a1a;color:var(--red);}}

/* Volume bar chart */
.vol-chart{{display:flex;align-items:flex-end;gap:2px;height:60px;margin-top:8px;}}
.vol-bar{{flex:1;min-width:3px;border-radius:2px 2px 0 0;transition:height .3s;}}
.vol-bar.today{{background:var(--blue);}}
.vol-bar.normal{{background:#444;}}
.vol-bar.high{{background:var(--amber);}}

/* RSI gauge */
.rsi-track{{height:8px;background:#333;border-radius:4px;overflow:hidden;margin:8px 0;position:relative;}}
.rsi-fill{{height:100%;border-radius:4px;}}
.rsi-zones{{display:flex;justify-content:space-between;font-size:9px;color:var(--muted);margin-top:2px;}}

/* Loading / empty states */
.loading{{text-align:center;padding:60px 24px;color:var(--muted);}}
.loading-spin{{
  width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--blue);
  border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 12px;
}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}

.empty{{text-align:center;padding:60px 24px;color:var(--muted);font-size:13px;line-height:2;}}

.footer{{padding:16px 24px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);text-align:center;}}
</style>
</head>
<body>

<!-- ================================================================ Header -->
<div class="header">
  <div class="header-left">
    <h1><span class="live-dot" id="live-dot"></span>SWING SCANNER{"&nbsp;<span style='font-size:11px;background:#c0392b;padding:2px 8px;border-radius:4px;vertical-align:middle;'>STAGING</span>" if is_staging else ""}</h1>
    <p>NYSE + NASDAQ equities &middot; Top-20 Crypto &middot; Updates every 60s</p>
  </div>
  <div class="header-right">
    <div class="stat-pill">Last updated<span id="hdr-updated">—</span></div>
    <div class="stat-pill">Scanned<span id="hdr-scanned">—</span></div>
    <div class="stat-pill">Breakouts<span id="hdr-breakouts" style="color:var(--green)">—</span></div>
  </div>
</div>

<!-- ============================================================= Filter bar -->
<div class="filterbar">
  <span class="filterbar-label">Asset</span>
  <button class="fbtn active" id="fb-all"      onclick="setAssetFilter('all')">All</button>
  <button class="fbtn"        id="fb-equities" onclick="setAssetFilter('equities')">Equities</button>
  <button class="fbtn"        id="fb-crypto"   onclick="setAssetFilter('crypto')">Crypto</button>
  <div class="sep"></div>
  <span class="filterbar-label">Status</span>
  <button class="fbtn active green" id="fs-BREAKOUT" onclick="toggleStatusFilter('BREAKOUT')">BREAKOUT</button>
  <button class="fbtn active amber" id="fs-WATCH"    onclick="toggleStatusFilter('WATCH')">WATCH</button>
  <button class="fbtn active gray"  id="fs-BUILDING" onclick="toggleStatusFilter('BUILDING')">BUILDING</button>
</div>

<!-- ================================================================= Cards -->
<div class="grid" id="card-grid">
  <div class="loading" id="loading-state">
    <div class="loading-spin"></div>
    <div>Connecting to Firebase...</div>
  </div>
</div>

<div class="footer">Swing Scanner &mdash; powered by Firebase, Alpaca &amp; yfinance</div>

<!-- ============================================================== Firebase + JS -->
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
// ---- Firebase init ----
const FB_CFG = {fb_cfg_json};
firebase.initializeApp(FB_CFG);
const database = firebase.database();

// ---- State ----
let allData      = {{}};   // rank string → result object
let assetFilter  = 'all';
let statusFilter = new Set(['BREAKOUT', 'WATCH', 'BUILDING']);
let expandedTickers = new Set();
let detailCache  = {{}};

// ---- Firebase listeners ----
function startListeners() {{
  // Top-20 live cards
  database.ref('/swing_scanner/stocks').on('value', snap => {{
    const data = snap.val();
    if (!data) return;
    Object.assign(allData, data);
    renderCards();
    updateHeader();
  }});

  // Full list for filtered views
  database.ref('/swing_scanner/all_stocks').on('value', snap => {{
    const data = snap.val();
    if (!data) return;
    allData = data;
    renderCards();
  }});

  // Metadata
  database.ref('/swing_scanner/metadata').on('value', snap => {{
    const m = snap.val();
    if (!m) return;
    document.getElementById('hdr-updated').textContent =
      ' ' + fmtTime(m.last_updated);
    document.getElementById('hdr-scanned').textContent =
      ' ' + (m.total_scanned || '—');
    document.getElementById('hdr-breakouts').textContent =
      ' ' + (m.breakout_count || 0);
  }});
}}

// ---- Filter controls ----
function setAssetFilter(val) {{
  assetFilter = val;
  ['all','equities','crypto'].forEach(id => {{
    const el = document.getElementById('fb-' + id);
    el.classList.toggle('active', id === val);
  }});
  renderCards();
}}

function toggleStatusFilter(status) {{
  if (statusFilter.has(status)) {{
    statusFilter.delete(status);
    document.getElementById('fs-' + status).classList.remove('active');
  }} else {{
    statusFilter.add(status);
    document.getElementById('fs-' + status).classList.add('active');
  }}
  renderCards();
}}

// ---- Render ----
function renderCards() {{
  const grid = document.getElementById('card-grid');
  document.getElementById('loading-state')?.remove();

  // Sort by rank key numerically
  const ranked = Object.entries(allData).sort((a, b) => +a[0] - +b[0]);

  // Apply filters
  const filtered = ranked.filter(([rank, d]) => {{
    if (assetFilter === 'equities' && d.is_crypto) return false;
    if (assetFilter === 'crypto'   && !d.is_crypto) return false;
    if (!statusFilter.has(d.status)) return false;
    return true;
  }});

  if (filtered.length === 0) {{
    grid.innerHTML = '<div class="empty">No assets match current filters.<br>Try adjusting the asset or status filters above.</div>';
    return;
  }}

  // Build HTML for all visible cards
  const html = filtered.map(([rank, d], idx) => buildCard(idx + 1, d)).join('');
  grid.innerHTML = html;

  // Re-attach expand listeners
  grid.querySelectorAll('.card-header').forEach(el => {{
    el.addEventListener('click', () => toggleExpand(el.dataset.ticker));
  }});

  // Restore any previously expanded cards
  expandedTickers.forEach(t => {{
    const body = document.getElementById('body-' + t);
    if (body) body.classList.add('open');
  }});
}}

function buildCard(displayRank, d) {{
  const statusClass = d.status.toLowerCase();
  const scoreColor  = d.status === 'BREAKOUT' ? 'green' :
                      d.status === 'WATCH'     ? 'amber' : 'gray';
  const isTop = displayRank <= 3;

  const chgSign  = d.change_pct >= 0 ? '+' : '';
  const chgClass = d.change_pct >= 0 ? 'up' : 'dn';
  const priceFmt = d.is_crypto && d.price < 1
                     ? d.price.toFixed(6) : d.price.toFixed(2);

  const bbLabel = d.above_upper_bb
    ? '<span class="bb-breakout">&#9889; BREAKOUT</span>'
    : (d.bb_squeeze_pct <= 35
        ? '<span class="bb-squeeze">&#128260; SQUEEZE</span>'
        : '<span class="bb-building">&#128202; BUILDING</span>');

  const cryptoBadge = d.is_crypto
    ? '<span class="crypto-badge">CRYPTO</span>' : '';

  const sectorStr = d.sector || (d.is_crypto ? 'Crypto' : '');

  return `
<div class="card ${{statusClass}}" id="card-${{d.ticker}}">
  <div class="card-header" data-ticker="${{d.ticker}}">
    <div class="rank-num ${{isTop ? 'top' : ''}}">${{displayRank}}</div>
    <div class="ticker-block">
      <div class="ticker-name">${{d.ticker}} ${{cryptoBadge}}</div>
      <div class="ticker-sub">${{sectorStr}}</div>
    </div>
    <div class="price-block">
      <div class="price-val">$${{priceFmt}}</div>
      <div class="price-chg ${{chgClass}}">${{chgSign}}${{d.change_pct}}%</div>
    </div>
    <div class="score-block">
      <div class="score-num ${{scoreColor}}">${{d.score}}</div>
      <div class="score-lbl ${{scoreColor}}">${{d.status}}</div>
    </div>
  </div>

  <div class="metrics-row">
    <div class="metric-item">
      <span class="metric-label">RVOL</span>
      <span class="metric-value">${{d.rvol}}x</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">BB Squeeze</span>
      <span class="metric-value">${{d.bb_squeeze_pct}}%</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">RSI</span>
      <span class="metric-value">${{d.rsi}}</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">EMA9 Dist</span>
      <span class="metric-value">${{d.ema9_dist_pct >= 0 ? '+' : ''}}${{d.ema9_dist_pct}}%</span>
    </div>
  </div>

  <div class="bb-status-row">
    ${{bbLabel}}
  </div>

  <!-- Expanded detail (hidden by default) -->
  <div class="card-body" id="body-${{d.ticker}}">
    <div class="detail-grid" id="detail-${{d.ticker}}">
      <div style="color:var(--muted);font-size:12px;padding:8px;">Loading detail...</div>
    </div>
  </div>
</div>`;
}}

async function toggleExpand(ticker) {{
  const body = document.getElementById('body-' + ticker);
  if (!body) return;

  const isOpen = body.classList.contains('open');
  if (isOpen) {{
    body.classList.remove('open');
    expandedTickers.delete(ticker);
    return;
  }}

  body.classList.add('open');
  expandedTickers.add(ticker);

  // Load detail if not cached
  if (!detailCache[ticker]) {{
    try {{
      const resp = await fetch('/api/detail/' + ticker);
      if (resp.ok) {{
        detailCache[ticker] = await resp.json();
      }}
    }} catch(e) {{
      console.warn('detail fetch error', e);
    }}
  }}

  const det = detailCache[ticker];
  if (!det || det.error) {{
    document.getElementById('detail-' + ticker).innerHTML =
      '<div style="color:var(--muted);font-size:12px;">Could not load detail.</div>';
    return;
  }}

  renderDetail(ticker, det);
}}

function renderDetail(ticker, d) {{
  const container = document.getElementById('detail-' + ticker);

  // ---- BB section ----
  const squeezeBarW = Math.min(100, d.bb_squeeze_pct);
  const bbBarColor  = d.bb_squeeze_pct <= 20 ? 'var(--green)' :
                      d.bb_squeeze_pct <= 50  ? 'var(--amber)' : 'var(--red)';
  const pctBPct     = Math.min(100, Math.max(0, d.pct_b * 100)).toFixed(0);

  // ---- Volume bars ----
  const bars    = d.vol_bars || [];
  const maxVol  = Math.max(...bars.map(b => b.volume), 1);
  const barsHtml = bars.map((b, i) => {{
    const h  = Math.round(b.volume / maxVol * 100);
    const cls = (i === bars.length - 1) ? 'today' : (h > 60 ? 'high' : 'normal');
    return `<div class="vol-bar ${{cls}}" style="height:${{h}}%" title="${{b.date}}: ${{fmtVol(b.volume)}}"></div>`;
  }}).join('');

  // ---- RSI gauge ----
  const rsiColor = d.rsi >= 70 ? 'var(--green)' :
                   d.rsi >= 50  ? 'var(--amber)' : 'var(--red)';

  // ---- EMA alignment table ----
  const emaRows = [
    {{ name: 'EMA 9',   val: d.ema9,   above: d.above_ema9  }},
    {{ name: 'EMA 20',  val: d.ema20,  above: d.above_ema20 }},
    {{ name: 'SMA 50',  val: d.sma50,  above: d.above_sma50 }},
    {{ name: 'SMA 200', val: d.sma200, above: d.above_sma200}},
  ].map(r => `
    <div class="ema-row">
      <span class="ema-name">${{r.name}}</span>
      <span class="ema-val">$${{r.val.toFixed(2)}}</span>
      <span class="ema-status ${{r.above ? 'ema-above' : 'ema-below'}}">${{r.above ? 'ABOVE' : 'BELOW'}}</span>
    </div>`).join('');

  container.innerHTML = `
    <!-- BB Section -->
    <div class="detail-section">
      <div class="detail-title">Bollinger Bands</div>
      <div class="ema-row">
        <span class="ema-name">Upper BB</span>
        <span class="ema-val" style="color:var(--green)">$${{d.bb_upper.toFixed(2)}}</span>
      </div>
      <div class="ema-row">
        <span class="ema-name">Middle (SMA20)</span>
        <span class="ema-val">$${{d.bb_sma.toFixed(2)}}</span>
      </div>
      <div class="ema-row">
        <span class="ema-name">Lower BB</span>
        <span class="ema-val" style="color:var(--red)">$${{d.bb_lower.toFixed(2)}}</span>
      </div>
      <div style="margin-top:10px;">
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);">
          <span>BB Width percentile</span>
          <span style="color:${{bbBarColor}}">${{d.bb_squeeze_pct}}% — ${{d.bb_squeeze_pct <= 20 ? 'TIGHT SQUEEZE' : d.bb_squeeze_pct <= 50 ? 'MODERATE' : 'WIDE'}}</span>
        </div>
        <div class="bb-bar-track">
          <div class="bb-bar-fill" style="width:${{squeezeBarW}}%;background:${{bbBarColor}}"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);">
          <span>%B (position in band)</span>
          <span>${{pctBPct}}%</span>
        </div>
        <div class="bb-bar-track">
          <div class="bb-bar-fill" style="width:${{pctBPct}}%;background:var(--blue)"></div>
        </div>
      </div>
    </div>

    <!-- EMA stack -->
    <div class="detail-section">
      <div class="detail-title">Moving Average Alignment</div>
      ${{emaRows}}
    </div>

    <!-- Volume -->
    <div class="detail-section">
      <div class="detail-title">Volume (last 20 days)</div>
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:4px;">
        <span>Avg 20d: ${{fmtVol(d.avg_vol_20)}}</span>
        <span>Today: <strong style="color:var(--blue)">${{fmtVol(d.today_vol)}}</strong></span>
        <span>RVOL: <strong style="color:${{d.rvol >= 2 ? 'var(--green)' : 'var(--amber)'}}">${{d.rvol}}x</strong></span>
      </div>
      <div class="vol-chart">${{barsHtml}}</div>
    </div>

    <!-- RSI gauge -->
    <div class="detail-section">
      <div class="detail-title">RSI (14)</div>
      <div style="font-size:28px;font-weight:700;color:${{rsiColor}};text-align:center;margin:6px 0;">${{d.rsi}}</div>
      <div class="rsi-track">
        <div class="rsi-fill" style="width:${{d.rsi}}%;background:${{rsiColor}}"></div>
      </div>
      <div class="rsi-zones">
        <span>0</span><span>30 Oversold</span><span>50</span><span>70 Overbought</span><span>100</span>
      </div>
    </div>
  `;
}}

// ---- Utilities ----
function fmtTime(iso) {{
  if (!iso) return '—';
  try {{
    const d = new Date(iso);
    return d.toLocaleTimeString([], {{hour:'2-digit',minute:'2-digit'}});
  }} catch(e) {{ return iso; }}
}}

function fmtVol(n) {{
  if (!n) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return n.toString();
}}

function updateHeader() {{
  // Pulse the live dot briefly to indicate update
  const dot = document.getElementById('live-dot');
  if (dot) {{
    dot.style.background = 'var(--blue)';
    setTimeout(() => {{ dot.style.background = ''; }}, 400);
  }}
}}

// ---- Boot ----
startListeners();
</script>
</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Vercel / gunicorn entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5001)
