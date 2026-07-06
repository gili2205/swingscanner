import os
import json
import requests
import yfinance as yf
from flask import Flask, jsonify, request

app = Flask(__name__)

VERSION = "v4.4.6"

FIREBASE_CONFIGS = {
    "production": {
        "apiKey": "AIzaSyAi_mL9BbKwwknyOm38B9lL68wI7wwLcaw",
        "authDomain": "stockscanner-f9f81.firebaseapp.com",
        "databaseURL": "https://stockscanner-f9f81-default-rtdb.firebaseio.com",
        "projectId": "stockscanner-f9f81",
        "storageBucket": "stockscanner-f9f81.firebasestorage.app",
        "messagingSenderId": "1066582982090",
        "appId": "1:1066582982090:web:359e1c670b8c3ca8222333"
    },
    "staging": {
        "apiKey": "AIzaSyA-zd6GX6QB_-q0x2HvVUSdYVsjtNqcuTk",
        "authDomain": "stockscanner-staging.firebaseapp.com",
        "databaseURL": "https://stockscanner-staging-default-rtdb.firebaseio.com",
        "projectId": "stockscanner-staging",
        "storageBucket": "stockscanner-staging.firebasestorage.app",
        "messagingSenderId": "342956679780",
        "appId": "1:342956679780:web:573fc062c897cbb3e8b571"
    }
}

ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")
FIREBASE_CONFIG = FIREBASE_CONFIGS["staging" if ENVIRONMENT == "staging" else "production"]

STAGING_BANNER = ""
if ENVIRONMENT == "staging":
    STAGING_BANNER = '<div style="background:#e67e22;color:#000;font-size:11px;font-weight:700;text-align:center;padding:4px;letter-spacing:.5px">STAGING ENVIRONMENT — Not production data</div>'

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swing Scanner {ver}</title>
<style>
.staging-banner{{background:#e67e22;color:#000;font-size:11px;font-weight:700;text-align:center;padding:4px;letter-spacing:.5px;display:block;}}
:root{{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}}
.header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:100;min-height:56px;}}
.header h1{{font-size:16px;font-weight:600;}}.header p{{color:var(--muted);font-size:11px;margin-top:1px;}}
.hright{{display:flex;align-items:center;gap:10px;}}
.ver{{font-size:10px;color:var(--muted);background:var(--bg3);border:1px solid var(--border);padding:3px 8px;border-radius:20px;font-family:monospace;}}
.dot{{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px;}}
.dot.g{{background:var(--green);animation:pulse 1.5s infinite;}}.dot.a{{background:var(--amber);animation:pulse 1.5s infinite;}}.dot.r{{background:var(--red);}}.dot.x{{background:var(--muted);}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.regime{{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid;}}
.regime.open{{background:#1a3d2b;color:var(--green);border-color:#27ae6055;}}.regime.pre{{background:#1a2a3d;color:var(--blue);border-color:#3498db55;}}.regime.after{{background:#2d1a3d;color:#9b59b6;border-color:#9b59b655;}}.regime.closed{{background:var(--bg3);color:var(--muted);border-color:var(--border);}}
.sbar{{padding:0 24px;font-size:12px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border);min-height:32px;position:relative;overflow:hidden;}}
.sbar.ok{{background:#1a3d2b33;color:var(--green);}}.sbar.warn{{background:#3d2e1033;color:var(--amber);}}.sbar.err{{background:#3d1a1a;color:var(--red);}}.sbar.conn{{background:var(--bg2);color:var(--muted);}}.sbar.dl{{background:#1a2a3d55;color:var(--blue);}}
.sbar-dot{{width:7px;height:7px;border-radius:50%;background:currentColor;flex-shrink:0;animation:pulse 1.4s infinite;}}
.sbar-right{{margin-left:auto;font-size:11px;opacity:.65;display:flex;gap:16px;}}
.metrics{{display:flex;gap:10px;padding:12px 24px;flex-wrap:wrap;background:var(--bg2);border-bottom:1px solid var(--border);}}
.metric{{background:var(--bg3);border-radius:8px;padding:8px 14px;min-width:110px;}}
.mlabel{{font-size:10px;color:var(--muted);margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px;}}.mval{{font-size:19px;font-weight:700;}}.msub{{font-size:10px;color:var(--muted);margin-top:1px;}}
.lookup-panel{{background:var(--bg2);border-bottom:2px solid var(--blue);padding:12px 24px;display:flex;align-items:center;gap:12px;}}
.lookup-panel input{{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:9px 14px;font-size:14px;font-weight:600;letter-spacing:1px;outline:none;width:150px;transition:border-color .2s;text-transform:uppercase;}}
.lookup-panel input:focus{{border-color:var(--blue);}}.lookup-btn{{background:var(--blue);color:#fff;border:none;border-radius:8px;padding:9px 18px;font-size:13px;font-weight:600;cursor:pointer;}}.lookup-btn:hover{{background:#2980b9;}}
.lookup-hint{{font-size:12px;color:var(--muted);}}.lookup-hint strong{{color:var(--text);}}
.lookup-result{{padding:14px 24px 0;}}
.filterpanel{{background:var(--bg2);border-bottom:2px solid var(--border);}}
.filter-toggle{{display:flex;align-items:center;gap:8px;padding:8px 24px;cursor:pointer;user-select:none;font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.5px;}}
.filter-toggle:hover{{color:var(--text);}}.filter-toggle .ftarrow{{font-size:10px;transition:transform .2s;}}.filter-toggle.open .ftarrow{{transform:rotate(180deg);}}
.filter-active-badge{{background:var(--amber);color:#000;font-size:10px;font-weight:700;border-radius:10px;padding:1px 6px;display:none;}}
.filter-body{{display:none;padding:10px 24px 12px;}}
.filter-body.open{{display:block;}}
.filterrow{{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;margin-bottom:8px;}}.filterrow:last-child{{margin-bottom:0;}}
.fgroup{{display:flex;flex-direction:column;gap:5px;}}.fgrouplabel{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;font-weight:600;}}
.fchips{{display:flex;gap:4px;flex-wrap:wrap;}}
.fchip{{display:flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;border:1px solid var(--border);background:var(--bg3);color:var(--muted);cursor:pointer;font-size:11px;font-weight:500;transition:all .15s;user-select:none;white-space:nowrap;}}
.fchip:hover{{border-color:var(--blue);color:var(--text);}}.fchip.on{{color:#fff;box-shadow:0 2px 6px rgba(0,0,0,.3);}}.fchip.on.green{{background:var(--green);border-color:var(--green);}}.fchip.on.blue{{background:var(--blue);border-color:var(--blue);}}.fchip.on.amber{{background:var(--amber);border-color:var(--amber);}}.fchip.on.purple{{background:#9b59b6;border-color:#9b59b6;}}.fchip.on.red{{background:var(--red);border-color:var(--red);}}.fchip.on.teal{{background:#1abc9c;border-color:#1abc9c;}}
.fchip .fcheck{{width:11px;height:11px;border-radius:2px;border:1.5px solid currentColor;display:flex;align-items:center;justify-content:center;font-size:8px;flex-shrink:0;}}.fchip.on .fcheck::after{{content:'✓';}}
.filteractions{{display:flex;align-items:center;gap:10px;margin-top:6px;}}
.resetbtn{{background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;}}.resetbtn:hover{{color:var(--red);border-color:var(--red);}}
.activedesc{{font-size:11px;color:var(--blue);flex:1;font-style:italic;}}.cnt{{font-size:11px;color:var(--muted);margin-left:auto;}}
.sortrow{{display:flex;align-items:center;gap:10px;padding:8px 24px;background:var(--bg);border-bottom:1px solid var(--border);}}
.sortrow select{{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:11px;outline:none;cursor:pointer;}}
.alertbox{{background:#1a3d2b;border:1px solid var(--green);border-radius:8px;padding:10px 16px;margin:8px 24px;font-size:12px;color:var(--green);display:none;}}
.grid{{display:flex;flex-direction:column;gap:16px;padding:20px 24px;}}
.card{{background:var(--bg2);border:1px solid var(--border);border-left:4px solid var(--border);border-radius:14px;overflow:hidden;transition:box-shadow .2s;box-shadow:0 4px 16px rgba(0,0,0,.35);}}
.card:hover{{box-shadow:0 8px 24px rgba(0,0,0,.5);}}
.card.primed{{border-left-color:#f1c40f;}}
.card.pre{{border-left-color:var(--green);}}
.card.watch{{border-left-color:var(--amber);}}
.card-header{{display:block;padding:18px 20px;cursor:pointer;user-select:none;}}
.card-header:hover{{background:#ffffff05;}}

.card-rank{{width:32px;height:32px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:var(--muted);flex-shrink:0;}}
.card-rank.top{{background:#1a3d2b;color:var(--green);}}
.card-score-block{{text-align:right;}}
.msl{{margin-left:6px;}}
.sec-title{{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin:14px 0 8px;}}
.card-fold{{display:flex;align-items:center;gap:12px;padding:14px 18px;cursor:pointer;user-select:none;}}.card-fold:hover{{background:#ffffff05;}}
.fold-rank{{width:26px;height:26px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--muted);flex-shrink:0;}}.fold-rank.top{{background:#1a3d2b;color:var(--green);}}
.fold-info{{flex:1;min-width:0;}}.fold-ticker{{font-size:17px;font-weight:700;letter-spacing:-.2px;}}.fold-sub{{font-size:11px;color:var(--muted);margin-top:2px;}}
.fold-metrics{{display:flex;gap:20px;flex-shrink:0;}}
.fold-metric{{text-align:center;min-width:48px;}}.fold-mlbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px;}}.fold-mval{{font-size:14px;font-weight:600;}}.fold-msub{{font-size:10px;margin-top:1px;}}
.fold-score{{text-align:right;flex-shrink:0;margin-left:14px;}}.fold-snum{{font-size:26px;font-weight:700;line-height:1;cursor:pointer;}}.fold-snum:hover{{opacity:.8;}}.fold-slbl{{font-size:10px;font-weight:600;letter-spacing:.5px;margin-top:2px;}}
.rank-badge{{width:32px;height:32px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:var(--muted);}}
.rank-badge.top{{background:#1a3d2b;color:var(--green);}}
.score-track{{height:3px;background:var(--bg3);}}.score-fill{{height:100%;transition:width .3s;}}
.card-body{{border-top:1px solid var(--border);padding:16px 18px;display:none;}}.card-body.open{{display:block;}}
.sec-lbl{{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:8px;margin-top:14px;}}.sec-lbl:first-child{{margin-top:0;}}
.factors{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}}
.fbox{{background:var(--bg3);border-radius:8px;padding:10px 12px;}}.flbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}}.fval{{font-size:15px;font-weight:600;}}.fsub{{font-size:10px;color:var(--muted);margin-top:2px;}}
.fg{{color:var(--green);}}.fa{{color:var(--amber);}}.fr{{color:var(--red);}}
.rr-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;}}
.rr-box{{border-radius:8px;padding:12px;text-align:center;}}.rr-lbl{{font-size:9px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;opacity:.8;}}.rr-val{{font-size:20px;font-weight:700;}}.rr-sub{{font-size:10px;margin-top:4px;}}
.sig-pills{{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;justify-content:center;}}
.setup-row{{border-radius:10px;padding:11px 14px;display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}}
.setup-name{{font-size:14px;font-weight:700;}}.tf-badge{{font-size:11px;font-weight:600;}}
.action-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.action-box{{background:var(--bg3);border-radius:8px;padding:10px 14px;}}.action-lbl{{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:4px;}}.action-val{{font-size:18px;font-weight:700;}}.action-sub{{font-size:10px;margin-top:2px;}}
.sigs{{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;}}
.sig{{font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px;}}.sg{{background:#1a3d2b;color:var(--green);}}.sa{{background:#3d2e10;color:var(--amber);}}.sb{{background:#1a2a3d;color:var(--blue);}}.sp{{background:#2d1a3d;color:#9b59b6;}}.sr{{background:#3d1a1a;color:var(--red);}}
.chart-btn{{background:transparent;color:var(--blue);border:1px solid var(--border);border-radius:7px;padding:7px 14px;font-size:11px;font-weight:600;cursor:pointer;margin-top:12px;display:inline-flex;align-items:center;gap:6px;transition:background .15s;}}.chart-btn:hover{{background:var(--bg3);}}.chart-btn.open{{background:var(--bg3);border-color:var(--blue);}}
.chart-panel{{height:320px;background:#000;border-top:1px solid var(--border);display:none;position:relative;}}.chart-panel iframe{{width:100%;height:100%;border:none;display:block;}}
.chart-close{{position:absolute;top:8px;right:8px;background:#1a1d26dd;border:1px solid var(--border);color:var(--muted);border-radius:5px;padding:3px 8px;font-size:10px;cursor:pointer;z-index:10;}}
.breakdown-popup{{position:fixed;z-index:1000;background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;min-width:280px;box-shadow:0 8px 32px rgba(0,0,0,.6);display:none;}}
.bp-title{{font-size:13px;font-weight:700;margin-bottom:12px;}}.bp-row{{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--border);}}.bp-label{{font-size:12px;color:var(--muted);}}.bp-bar{{flex:1;margin:0 10px;height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;}}.bp-fill{{height:100%;border-radius:3px;}}.bp-val{{font-size:12px;font-weight:700;min-width:40px;text-align:right;}}
.cup{{color:var(--green);}}.cdn{{color:var(--red);}}
.empty{{text-align:center;padding:60px;color:var(--muted);font-size:14px;line-height:2;}}
.pgfoot{{padding:14px 24px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);text-align:center;margin-top:8px;}}
.nav-pills{{display:flex;gap:6px;align-items:center;}}
.nav-pill{{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;text-decoration:none;border:1px solid var(--border);color:var(--muted);transition:all .15s;background:var(--bg3);}}
.nav-pill:hover{{color:var(--text);border-color:var(--blue);}}
.nav-pill.active{{background:var(--blue);color:#fff;border-color:var(--blue);}}
.mcap-badge{{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--bg3);color:var(--muted);border:1px solid var(--border);vertical-align:middle;margin-left:6px;font-weight:400;}}
.perf-row{{display:flex;border-top:1px solid var(--border);margin-top:10px;padding-top:10px;}}
.perf-item{{flex:1;text-align:center;border-right:1px solid var(--border);}}
.perf-item:last-child{{border-right:none;}}
.perf-lbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}}
.perf-val{{font-size:13px;font-weight:600;}}
@media(max-width:700px){{.grid{{padding:10px;gap:8px;}}.fold-metrics{{display:none;}}.filter-toggle{{padding:8px 14px;}}.filter-body{{padding:8px 14px 10px;}}}}
</style>
</head>
<body>
{staging_banner}
<div class="header">
  <div>
    <h1><span class="dot x" id="dot"></span>Swing Scanner</h1>
    <p>Scans NYSE + NASDAQ + Crypto &middot; BB Squeeze &middot; RVOL &middot; EMA Alignment &middot; RSI &middot; Updates every 60s</p>
  </div>
  <div class="hright">
    <div class="nav-pills"><a class="nav-pill active" href="/">&#128202; Dashboard</a><a class="nav-pill" href="/analytics">&#128200; Analytics</a></div>
    <span class="ver" id="verspan">{ver}</span>
    <span class="regime closed" id="regime">&#9679; Connecting...</span>
  </div>
</div>

<div class="sbar conn" id="sbar">
  <div class="sbar-progress" id="sbar-progress" style="width:0%"></div>
  <span class="sbar-dot"></span>
  <span id="smsg">Connecting to Firebase...</span>
  <span class="sbar-right"><span id="sbar-age"></span>&nbsp;<span id="sbar-dur"></span></span>
</div>

<div class="metrics">
  <div class="metric"><div class="mlabel">Total scanned</div><div class="mval" id="m-total">&#8212;</div><div class="msub">full universe</div></div>
  <div class="metric"><div class="mlabel">Primed</div><div class="mval" style="color:#f1c40f" id="m-ready">&#8212;</div><div class="msub">coiled &amp; at pivot</div></div>
  <div class="metric"><div class="mlabel">Coiling</div><div class="mval" style="color:var(--amber)" id="m-watch">&#8212;</div><div class="msub">base building</div></div>
  <div class="metric"><div class="mlabel">Breakout</div><div class="mval" style="color:var(--green)" id="m-pre">&#8212;</div><div class="msub">just crossed pivot</div></div>
  <div class="metric"><div class="mlabel">Crypto</div><div class="mval" style="color:#9b59b6" id="m-flags">&#8212;</div><div class="msub">in universe</div></div>
  <div class="metric"><div class="mlabel">Last scan</div><div class="mval" style="font-size:13px" id="m-time">&#8212;</div><div class="msub" id="m-sess">&#8212;</div></div>
</div>

<!-- __ Ticker lookup __ -->
<div class="lookup-panel">
  <div class="lookup-icon">&#128269;</div>
  <input type="text" id="lookup-input" placeholder="e.g. NVDA" maxlength="6"
    onkeydown="if(event.key==='Enter')lookupTicker()"
    oninput="this.value=this.value.toUpperCase()">
  <button class="lookup-btn" onclick="lookupTicker()">Analyze</button>
  <div class="lookup-divider"></div>
  <span class="lookup-hint">&#9889; Full analysis on <strong>any stock</strong> &mdash; even outside top 200</span>
</div>
<div id="lookup-wrap" style="display:none;position:relative"><button onclick="document.getElementById('lookup-wrap').style.display='none';document.getElementById('lookup-input').value=''" style="position:absolute;top:10px;right:16px;background:none;border:none;color:var(--muted);font-size:18px;cursor:pointer;line-height:1;z-index:10" title="Close">&times;</button><div class="lookup-result" id="lookup-result"></div></div>

<!-- __ Multi-select filter panel __ -->
<div class="filterpanel">
  <div class="filter-toggle" id="filter-toggle" onclick="toggleFilterPanel()">
    &#9881; Filters <span class="ftarrow">&#9660;</span>
    <span class="filter-active-badge" id="filter-active-badge">0</span>
    <span id="filter-desc" style="font-weight:400;margin-left:8px;font-size:11px"></span>
  </div>
  <div class="filter-body" id="filter-body">

  <div class="filterrow">
    <!-- Size -->
    <div class="fgroup">
      <div class="fgrouplabel">&#127970; Size</div>
      <div class="fchips">
        <div class="fchip green" data-group="size" data-val="mega" onclick="toggleChip(this)"><span class="fcheck"></span>&#129432; Mega &gt;$200B</div>
        <div class="fchip green" data-group="size" data-val="large" onclick="toggleChip(this)"><span class="fcheck"></span>&#128024; Large $10B-$200B</div>
        <div class="fchip green" data-group="size" data-val="mid" onclick="toggleChip(this)"><span class="fcheck"></span>&#128002; Mid $2B-$10B</div>
        <div class="fchip green" data-group="size" data-val="small" onclick="toggleChip(this)"><span class="fcheck"></span>&#128041; Small &lt;$2B</div>
      </div>
    </div>

    <!-- Setup -->
    <div class="fgroup">
      <div class="fgrouplabel">&#128202; Setup Type</div>
      <div class="fchips">
        <div class="fchip amber" data-group="setup" data-val="primed" onclick="toggleChip(this)"><span class="fcheck"></span>&#10024; Primed</div>
        <div class="fchip amber" data-group="setup" data-val="coiling" onclick="toggleChip(this)"><span class="fcheck"></span>&#128138; Coiling</div>
        <div class="fchip amber" data-group="setup" data-val="breakout" onclick="toggleChip(this)"><span class="fcheck"></span>&#128293; Breakout</div>
        <div class="fchip amber" data-group="setup" data-val="watch" onclick="toggleChip(this)"><span class="fcheck"></span>&#128202; Watch</div>
        <div class="fchip amber" data-group="setup" data-val="squeeze" onclick="toggleChip(this)"><span class="fcheck"></span>&#128064; BB Squeeze</div>
        <div class="fchip amber" data-group="setup" data-val="dryup" onclick="toggleChip(this)"><span class="fcheck"></span>&#128201; Vol dry-up</div>
        <div class="fchip amber" data-group="setup" data-val="at_pivot" onclick="toggleChip(this)"><span class="fcheck"></span>&#127919; At pivot</div>
        <div class="fchip purple" data-group="setup" data-val="crypto" onclick="toggleChip(this)"><span class="fcheck"></span>&#8383; Crypto only</div>
        <div class="fchip teal" data-group="setup" data-val="equity" onclick="toggleChip(this)"><span class="fcheck"></span>&#127970; Equities only</div>
      </div>
    </div>
  </div>

  <div class="filterrow">
    <!-- Sector -->
    <div class="fgroup">
      <div class="fgrouplabel">&#127970; Sector</div>
      <div class="fchips">
        <div class="fchip teal" data-group="sector" data-val="Technology" onclick="toggleChip(this)"><span class="fcheck"></span>&#128187; Tech</div>
        <div class="fchip teal" data-group="sector" data-val="Healthcare" onclick="toggleChip(this)"><span class="fcheck"></span>&#127973; Health</div>
        <div class="fchip teal" data-group="sector" data-val="Financial Services" onclick="toggleChip(this)"><span class="fcheck"></span>&#127970; Finance</div>
        <div class="fchip teal" data-group="sector" data-val="Consumer Cyclical" onclick="toggleChip(this)"><span class="fcheck"></span>&#128717; Consumer</div>
        <div class="fchip teal" data-group="sector" data-val="Industrials" onclick="toggleChip(this)"><span class="fcheck"></span>&#9881; Industrial</div>
        <div class="fchip teal" data-group="sector" data-val="Communication Services" onclick="toggleChip(this)"><span class="fcheck"></span>&#128225; Telecom</div>
        <div class="fchip teal" data-group="sector" data-val="Energy" onclick="toggleChip(this)"><span class="fcheck"></span>&#9889; Energy</div>
        <div class="fchip teal" data-group="sector" data-val="Real Estate" onclick="toggleChip(this)"><span class="fcheck"></span>&#127968; Real Estate</div>
      </div>
    </div>
  </div>

  <div class="filterrow">
    <div class="fgroup">
      <div class="fchips">
        <div class="fchip" onclick="resetAll()">&#10005; Show all</div>
      </div>
    </div>
  </div>

  <div class="filteractions">
    <span class="activedesc" id="activedesc">Showing all stocks &mdash; select filters above to narrow down</span>
    <span class="cnt" id="cnt"></span>
  </div>
  </div><!-- /filter-body -->
</div>


<div class="sortrow">
  <select id="ssort" onchange="render()">
    <option value="buy_now">Sort: Swing Score</option>
    <option value="bb_squeeze">Sort: Squeeze (tightest)</option>
    <option value="dryup">Sort: Vol dry-up (driest)</option>
    <option value="pivot">Sort: Closest to pivot</option>
    <option value="rvol">Sort: RVOL (highest)</option>
    <option value="rsi">Sort: RSI (lowest first)</option>
  </select>
</div>

<div class="alertbox" id="alertbox"></div>
<div class="grid" id="grid"><div class="empty">&#9203; Connecting to live scanner...</div></div>
<div class="pgfoot">Swing Scanner {ver} &middot; Alpaca + Firebase + GCP VM &middot; &#9888; Not financial advice. Always use stop losses.</div>

<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
var VER = "{ver}";
var CFG = {cfg};
var connected = false, lastDataTime = null, watchdogTimer = null;
var stockData = {{}}, allStockData = {{}}, prevData = {{}}, seen = {{}}, firstSeenData = {{}};
// ── Filter state — which chips are ON per group ───────────────────────────────
// Empty set = no filter for that group (show all)
var activeFilters = {{ size:[], setup:[], sector:[] }};

function toggleFilterPanel() {{
  var toggle = document.getElementById('filter-toggle');
  var body   = document.getElementById('filter-body');
  var isOpen = body.classList.contains('open');
  if (isOpen) {{
    body.classList.remove('open');
    toggle.classList.remove('open');
  }} else {{
    body.classList.add('open');
    toggle.classList.add('open');
  }}
}}

function updateFilterBadge() {{
  var total = 0;
  Object.values(activeFilters).forEach(function(v){{ total += v.length; }});
  var badge = document.getElementById('filter-active-badge');
  var desc  = document.getElementById('filter-desc');
  if (badge) {{ badge.style.display = total>0?'inline':'none'; badge.textContent=total; }}
  if (desc)  {{ desc.textContent = total>0?'('+total+' active)':''; }}
}}

function toggleChip(el) {{
  var group = el.dataset.group;
  var val   = el.dataset.val;
  var color = el.classList[1]; // green, blue, amber, purple, red
  el.classList.toggle("on");
  if (el.classList.contains("on")) {{
    if (!activeFilters[group]) activeFilters[group] = [];
    if (!activeFilters[group].includes(val)) activeFilters[group].push(val);
  }} else {{
    activeFilters[group] = activeFilters[group].filter(function(v){{return v!==val;}});
  }}
  updateFilterBadge();
  render();
}}

function setChip(group, val, on) {{
  var el = document.querySelector('.fchip[data-group="'+group+'"][data-val="'+val+'"]');
  if (!el) return;
  var color = el.classList[1];
  if (on) {{
    el.classList.add("on");
    if (!activeFilters[group]) activeFilters[group] = [];
    if (!activeFilters[group].includes(val)) activeFilters[group].push(val);
  }} else {{
    el.classList.remove("on");
    activeFilters[group] = (activeFilters[group]||[]).filter(function(v){{return v!==val;}});
  }}
}}

function resetAll() {{
  document.querySelectorAll(".fchip[data-group]").forEach(function(c){{c.classList.remove("on");}});
  activeFilters = {{ size:[], setup:[], sector:[] }};
  updateFilterBadge();
  render();
}}

// ── Quick presets ─────────────────────────────────────────────────────────────

// ── Filter logic ──────────────────────────────────────────────────────────────
// Parse "4.6B" → 4.6e9, "1.2T" → 1.2e12, "500M" → 500e6
function parseMcap(str) {{
  if (!str) return 0;
  var s = String(str).trim();
  var n = parseFloat(s);
  if (isNaN(n)) return 0;
  if (s.indexOf("T")>=0) return n*1e12;
  if (s.indexOf("B")>=0) return n*1e9;
  if (s.indexOf("M")>=0) return n*1e6;
  return n;
}}
// Bucket by market cap (uses s.market_cap if present, otherwise falls back to price)
function capBucket(s) {{
  var mc = parseMcap(s.market_cap);
  if (mc >= 200e9) return "mega";
  if (mc >= 10e9)  return "large";
  if (mc >= 2e9)   return "mid";
  if (mc > 0)      return "small";
  // Fallback: price-based buckets when market_cap not yet populated
  var p = s.price || 0;
  return p>=300?"mega":p>=80?"large":p>=20?"mid":"small";
}}
function passesFilters(s) {{
  // Size — if any size chips selected, stock must match one of them (uses market cap)
  if (activeFilters.size.length > 0 && !activeFilters.size.includes(capBucket(s))) return false;

  // Sector — if any sector chips selected, stock must match one of them
  if (activeFilters.sector && activeFilters.sector.length > 0) {{
    var stockSector = s.sector || "";
    if (!activeFilters.sector.includes(stockSector)) return false;
  }}

  // Setup — if any setup chips selected, stock must match AT LEAST ONE
  if (activeFilters.setup.length > 0) {{
    var setupOk = false;
    var swingStatus = (s.status || 'BUILDING').toUpperCase();
    if (activeFilters.setup.includes("primed")   && swingStatus==="PRIMED")   setupOk = true;
    if (activeFilters.setup.includes("coiling")  && swingStatus==="COILING")  setupOk = true;
    if (activeFilters.setup.includes("breakout") && swingStatus==="BREAKOUT") setupOk = true;
    if (activeFilters.setup.includes("watch")    && swingStatus==="WATCH")    setupOk = true;
    if (activeFilters.setup.includes("squeeze")  && (s.bb_squeeze_pct!=null&&s.bb_squeeze_pct<=20)) setupOk = true;
    if (activeFilters.setup.includes("dryup")    && (s.dryup_ratio!=null&&s.dryup_ratio<=0.75)) setupOk = true;
    if (activeFilters.setup.includes("at_pivot") && (s.dist_to_pivot!=null&&s.dist_to_pivot>=0&&s.dist_to_pivot<=4)) setupOk = true;
    if (activeFilters.setup.includes("crypto")   && s.is_crypto)              setupOk = true;
    if (activeFilters.setup.includes("equity")   && !s.is_crypto)             setupOk = true;
    if (!setupOk) return false;
  }}

  return true;
}}

function getActiveDesc() {{
  var parts = [];
  if (activeFilters.size.length)     parts.push(activeFilters.size.join(" or ").replace(/mega/g,"Mega").replace(/large/g,"Large").replace(/mid/g,"Mid").replace(/small/g,"Small")+" cap");
  if (activeFilters.sector && activeFilters.sector.length) parts.push(activeFilters.sector.join(" or "));
  if (activeFilters.setup.length)    parts.push(activeFilters.setup.map(function(v){{return {{primed:"Primed",coiling:"Coiling",breakout:"Breakout",watch:"Watch",squeeze:"BB Squeeze",dryup:"Vol dry-up",at_pivot:"At pivot",crypto:"Crypto",equity:"Equities"}}[v]||v;}}).join(" or "));
  if (!parts.length) return "Showing all stocks \u2014 select filters above to narrow down";
  return "Filters: " + parts.join(" \u00b7 ");
}}

// ── Status helpers ────────────────────────────────────────────────────────────
function setStatus(type, msg, progress, age, dur) {{
  var b=document.getElementById("sbar"); b.className="sbar "+type;
  document.getElementById("smsg").textContent=msg;
  var pg=document.getElementById("sbar-progress"); if(pg)pg.style.width=(progress||0)+"%";
  var ael=document.getElementById("sbar-age"); if(ael)ael.textContent=age||"";
  var del2=document.getElementById("sbar-dur"); if(del2)del2.textContent=dur||"";
}}

function startWatchdog() {{
  clearInterval(watchdogTimer);
  watchdogTimer = setInterval(function() {{
    if (!lastDataTime) return;
    var age = (Date.now()-lastDataTime)/1000;
    var _n2=new Date(),_h2=(_n2.getUTCHours()-4+24)%24,_d2=_n2.getUTCDay();
    var mktOpen2=_d2>=1&&_d2<=5&&_h2>=9&&_h2<16;
    var errT=mktOpen2?600:86400,warnT=mktOpen2?180:3600;
    if (age>errT) {{ setStatus("err","No data for "+Math.round(age/60)+" min \u2014 check GCP VM"); document.getElementById("dot").className="dot r"; }}
    else if (age>120) {{ setStatus("warn","Last update "+Math.round(age/60)+" min ago",0,"",""); document.getElementById("dot").className="dot a"; }}
  }}, 15000);
}}

try {{ firebase.initializeApp(CFG); }} catch(e) {{ setStatus("err","Firebase init: "+e.message,0,"",""); }}
var fdb = firebase.database();

fdb.ref(".info/connected").on("value", function(snap) {{
  connected = snap.val();
  if (connected) {{ setStatus("ok","Connected \u2014 waiting for scanner data..."); document.getElementById("dot").className="dot g"; }}
  else {{ setStatus("err","Lost Firebase connection",0,"",""); document.getElementById("dot").className="dot r"; }}
}});

fdb.ref("/swing_scanner").on("value", function(snap) {{
  var d = snap.val();
  lastDataTime = Date.now();
  if (!d) {{ setStatus("warn","No scanner data yet",0,"",""); return; }}

  // Keep app version in header; show scanner version in status bar only

  var _n=new Date(),_h=(_n.getUTCHours()-4+24)%24,_d=_n.getUTCDay();
  var mktOpen=_d>=1&&_d<=5&&_h>=9&&_h<16;
  var warnThresh=mktOpen?180:3600;
  var md = d.metadata || d;   // scanner writes stats under /metadata
  var dlPct=d.download_progress?d.download_progress.pct||0:0;
  var age = md.last_updated_ts ? Math.round((Date.now()/1000-md.last_updated_ts)) : (md.last_updated ? Math.round((Date.now()-new Date(md.last_updated))/1000) : 0);
  var scanTime = md.last_scan_time ? " \u00b7 "+md.last_scan_time : "";
  var duration = md.scan_duration_sec ? " ("+md.scan_duration_sec+"s)" : "";
  var scanned  = md.stocks_scanned||0;

  // A fresh download_progress heartbeat means the scanner is busy fetching
  // history (daily refresh / cold start) — show that instead of a stale alarm.
  var dp = d.download_progress || {{}};
  var dlActive = dp.ts && (Date.now()/1000 - dp.ts) < 300;
  if (dlActive) setStatus("dl","Downloading market data \u2014 "+(dp.loaded||0).toLocaleString()+" stocks ("+(dp.pct||0)+"%) \u2014 scans resume when done",dp.pct||0,"","");
  else if (scanned===0) setStatus("dl","Downloading market data\u2026");
  else if (age>warnThresh) setStatus("warn","Data is "+Math.round(age/60)+" min old"+scanTime,100,"","");
  else setStatus("ok","LIVE \u00b7 "+scanned.toLocaleString()+" stocks \u00b7 Updated "+age+"s ago"+scanTime+duration);

  document.getElementById("m-total").textContent = scanned.toLocaleString();
  // Compute Breakout/Watch/HighRVOL/Crypto counts from swing score data
  var _stocks = d.all_stocks || d.stocks || {{}};
  var _tickers = Object.keys(_stocks);
  if (_tickers.length > 0) {{
    var _nPrimed = 0, _nCoiling = 0, _nBreakout = 0, _nCrypto = 0;
    _tickers.forEach(function(t) {{
      var s = _stocks[t];
      var status = s.status || '';
      if (status === 'PRIMED')   _nPrimed++;
      else if (status === 'COILING')  _nCoiling++;
      else if (status === 'BREAKOUT') _nBreakout++;
      if (s.is_crypto) _nCrypto++;
    }});
    document.getElementById("m-ready").textContent = _nPrimed;
    document.getElementById("m-watch").textContent = _nCoiling;
    document.getElementById("m-pre").textContent   = _nBreakout;
    document.getElementById("m-flags").textContent = _nCrypto;
  }} else {{
    document.getElementById("m-ready").textContent = md.primed_count || 0;
    document.getElementById("m-watch").textContent = md.coiling_count || 0;
    document.getElementById("m-pre").textContent   = md.breakout_count || 0;
    document.getElementById("m-flags").textContent = md.crypto_count || 0;
  }}
  if (md.last_updated) {{
    var t = new Date(md.last_updated);
    document.getElementById("m-time").textContent = t.toLocaleTimeString([],{{hour:"2-digit",minute:"2-digit"}});
  }}
  if (md.session) document.getElementById("m-sess").textContent = md.session;

  var r=document.getElementById("regime"), dot=document.getElementById("dot"), sess=md.session||"";
  if      (sess.indexOf("Market Open")>=0)  {{ r.textContent="\u25cf Market Open";  r.className="regime open";   if(scanned>0) dot.className="dot g"; }}
  else if (sess.indexOf("Pre-Market")>=0)   {{ r.textContent="\u25d0 Pre-Market";   r.className="regime pre";    dot.className="dot a"; }}
  else if (sess.indexOf("After-Hours")>=0)  {{ r.textContent="\u25d1 After-Hours";  r.className="regime after";  dot.className="dot a"; }}
  else                                       {{ r.textContent="\u25cb Market Closed"; r.className="regime closed"; dot.className="dot x"; }}

  if (d.all_stocks&&Object.keys(d.all_stocks).length>0) allStockData=d.all_stocks;
  else if (d.stocks&&Object.keys(d.stocks).length>0) allStockData=d.stocks;

  if (d.stocks) {{
    var nr = [];
    Object.keys(d.stocks).forEach(function(t) {{
      var s = d.stocks[t];
      var vs=s.status||'BUILDING';
      var wasPrimed = prevData[t] && (prevData[t].status==='PRIMED');
      if (vs==="PRIMED" && !wasPrimed && !seen[t+"-r"]) {{ nr.push(t); seen[t+"-r"]=true; }}
      if (vs!=="PRIMED") delete seen[t+"-r"];
    }});
    if (nr.length) {{
      var ab=document.getElementById("alertbox");
      ab.textContent="NEW PRIMED SETUP: "+nr.join(", ")+" \u2014 check TradingView!";
      ab.style.display="block";
      setTimeout(function(){{ab.style.display="none";}},30000);
    }}
    prevData = JSON.parse(JSON.stringify(d.stocks));
    if (Object.keys(d.stocks).length>0) stockData = d.stocks;
  }}
  if (Object.keys(allStockData).length>0 || Object.keys(stockData).length>0) render();
}}, function(err) {{ setStatus("err","Firebase error: "+err.message,0,"",""); }});

startWatchdog();

// ── sessionStorage cache helper (10-min TTL) ─────────────────────────────────
function fbCached(path, ttl, onData) {{
  var key = 'fb|' + path;
  try {{
    var raw = sessionStorage.getItem(key);
    if (raw) {{
      var obj = JSON.parse(raw);
      if (obj.data != null && Date.now() - obj.ts < ttl) {{ onData(obj.data); return; }}
    }}
  }} catch(e) {{}}
  fdb.ref(path).once('value', function(snap) {{
    var data = snap.val();
    if (data != null) {{
      try {{ sessionStorage.setItem(key, JSON.stringify({{ts: Date.now(), data: data}})); }} catch(e) {{}}
    }}
    onData(data);
  }});
}}
var BADGE_CACHE_TTL = 10 * 60 * 1000; // 10 min

// ── Load smart money tickers for badge display ────────────────────────────────
// ── Render ────────────────────────────────────────────────────────────────────
function render() {{
  var sortBy   = document.getElementById("ssort").value;
  var grid     = document.getElementById("grid");
  var universe = Object.values(allStockData);
  if (!universe.length) universe = Object.values(stockData);
  // Filter out stocks with significantly negative analyst upside
  universe = universe.filter(function(s) {{
    var up = s.analyst_upside!=null?parseFloat(s.analyst_upside):null;
    return up===null || up>-10;
  }});
  if (!universe.length) return;

  // Apply combined filters — get best 10 from matching stocks
  var filtered = universe.filter(passesFilters);

  var fns = {{
    score:      function(a,b){{ return (b.score||0)-(a.score||0); }},
    buy_now:    function(a,b){{ return (b.score||0)-(a.score||0); }},
    rvol:       function(a,b){{ return (b.rvol||0)-(a.rvol||0); }},
    bb_squeeze: function(a,b){{ return (a.bb_squeeze_pct!=null?a.bb_squeeze_pct:100)-(b.bb_squeeze_pct!=null?b.bb_squeeze_pct:100); }},
    ema9_dist:  function(a,b){{ return Math.abs(a.ema9_dist_pct||99)-Math.abs(b.ema9_dist_pct||99); }},
    dryup:      function(a,b){{ return (a.dryup_ratio!=null?a.dryup_ratio:9)-(b.dryup_ratio!=null?b.dryup_ratio:9); }},
    pivot:      function(a,b){{ var da=(a.dist_to_pivot!=null&&a.dist_to_pivot>=0)?a.dist_to_pivot:99; var db=(b.dist_to_pivot!=null&&b.dist_to_pivot>=0)?b.dist_to_pivot:99; return da-db; }},
    rsi:        function(a,b){{ return (a.rsi||50)-(b.rsi||50); }}
  }};

  filtered.sort(fns[sortBy]||fns.score);
  var top10 = filtered.slice(0,10);

  document.getElementById("activedesc").textContent = getActiveDesc();
  document.getElementById("cnt").textContent = filtered.length+" stocks match \u00b7 showing top 10";

  if (!top10.length) {{
    grid.innerHTML = '<div class="empty">No stocks match this combination.<br><span style="font-size:12px;color:var(--muted)">Try removing some filters or click <strong style="color:var(--blue)">Show all</strong> to reset.</span></div>';
  }} else {{
  // Save which cards and charts are open before rebuild
  var openCards  = {{}};
  var openCharts = {{}};
  document.querySelectorAll('.card-body').forEach(function(b) {{
    if(b.style.display==='block') openCards[b.id]=true;
  }});
  document.querySelectorAll('[id^="cpanel-"]').forEach(function(p) {{
    if(p.style.display==='block') openCharts[p.id.replace('cpanel-','')]=true;
  }});
  grid.innerHTML = top10.map(function(s,i){{return makeCard(s,i+1);}}).join("");
  // Restore open cards
  Object.keys(openCards).forEach(function(id) {{
    var el=document.getElementById(id);
    if(el) el.style.display='block';
  }});
  // Restore open charts (re-inject iframe src so TV widget reloads)
  Object.keys(openCharts).forEach(function(ticker) {{
    var panel=document.getElementById('cpanel-'+ticker);
    var frame=document.getElementById('cframe-'+ticker);
    var btn=document.getElementById('cbtn-'+ticker);
    if(panel&&frame) {{
      panel.style.display='block';
      frame.src='https://s.tradingview.com/widgetembed/?symbol=NASDAQ%3A'+ticker+'&interval=D&theme=dark&style=1&hide_side_toolbar=0&allow_symbol_change=0&save_image=0&toolbarbg=1a1d26&show_popup_button=0';
      if(btn){{btn.className='chart-btn open';btn.innerHTML='&times; Close';}}
    }}
  }});
  setTimeout(prefetchAllFundamentals, 100);
  }}
}}

// ── Card helpers ──────────────────────────────────────────────────────────────
function sc(s)   {{ return s==="PRIMED"?"#f1c40f":s==="BREAKOUT"?"#27ae60":s==="COILING"?"#e67e22":s==="WATCH"?"#3498db":"#8892a4"; }}
function lc(l)   {{ return l==="ATH"?"#27ae60":(l&&l.indexOf("52")>=0)?"#3498db":"#e67e22"; }}
function ec(e)   {{ return e==="full"?"fg":e==="partial"?"fa":"fr"; }}
function rsiC(v) {{ if(!v||isNaN(v)) return "#8892a4"; return v>=70?"#e74c3c":v>=60?"#e67e22":v<=30?"#9b59b6":"#27ae60"; }}
function rsiL(v) {{ if(!v||isNaN(v)) return "N/A"; return v>=70?"Overbought":v>=60?"Hot":v<=30?"Oversold":"Healthy"; }}
function peC(v)  {{ if(!v||isNaN(v)||v<=0) return "#8892a4"; return v<20?"#27ae60":v<40?"#e67e22":"#e74c3c"; }}

function makeCard(s, rank) {{
  if (!s||!s.ticker) return '';
  var price  = s.price||0;
  // Show today's intraday change when market is open, else yesterday's completed day
  function isMarketOpen() {{
    var et = new Date(new Date().toLocaleString('en-US',{{timeZone:'America/New_York'}}));
    var day = et.getDay();
    if (day===0||day===6) return false;
    var mins = et.getHours()*60+et.getMinutes();
    return mins >= 570 && mins < 960; // 9:30–16:00
  }}
  var marketOpen = isMarketOpen();
  var todayChg = s.change_pct!=null ? s.change_pct : 0;
  var yesterChg= s.prev_day_pct!=null ? s.prev_day_pct : null;
  var chg    = (marketOpen || yesterChg===null) ? todayChg : yesterChg;
  var chgCls = chg>=0?'cup':'cdn';
  var chgStr = (chg>=0?'+':'')+chg.toFixed(2)+'%';
  var pe     = s.pe_ratio, rsi=s.rsi, target=s.analyst_target;
  var upside = s.analyst_upside;
  var upsidePct = upside!=null?parseFloat(upside):null;
  var rc    = rsiC(rsi);
  var swingStatus = s.status || 'BUILDING';
  var color = sc(swingStatus);
  var isTop = rank<=3;
  var buyPct = s.analyst_buy_pct||0;
  var numAna = s.num_analysts||0;
  var earn   = s.days_to_earnings;
  var swScore = s.score != null ? s.score : 0;
  var scoreColor = swScore>=75?'#f1c40f':swScore>=48?'#e67e22':swScore>=32?'#3498db':'#8892a4';

  // Trade plan — thresholds from the 180d backtest:
  // entry just above the pivot; stop -4% (avg max drawdown of top signals);
  // target +7% (avg max gain within 1 month)
  var pivotP  = s.pivot != null ? s.pivot : null;
  var entryNum  = pivotP != null ? pivotP*1.002 : price*1.002;
  var stopNum   = entryNum*0.96;
  var targetNum = entryNum*1.07;

  // Signal chips — pre-breakout swing model
  var sigs='';
  var _sq = s.bb_squeeze_pct, _dry = s.dryup_ratio, _dp = s.dist_to_pivot, _rv = s.rvol;
  if(swingStatus==='PRIMED')   sigs+='<span class="sig sg">&#10024; PRIMED</span>';
  if(swingStatus==='COILING')  sigs+='<span class="sig sa">&#128138; COILING</span>';
  if(swingStatus==='BREAKOUT') sigs+='<span class="sig sg">&#128293; BREAKOUT</span>';
  if(_sq!=null&&_sq<=20) sigs+='<span class="sig sp">&#128064; Squeeze '+_sq.toFixed(0)+'th</span>';
  if(_dry!=null&&_dry<=0.75) sigs+='<span class="sig sg">&#128201; Vol dry-up '+_dry.toFixed(2)+'x</span>';
  if(_dp!=null&&_dp>=0&&_dp<=4) sigs+='<span class="sig sg">&#127919; '+_dp.toFixed(1)+'% under pivot</span>';
  if(s.above_ema20&&s.above_sma50&&s.above_sma200) sigs+='<span class="sig sb">&#9650; Full stack</span>';
  else if(s.above_sma200) sigs+='<span class="sig sb">Above SMA200</span>';
  if(_rv!=null&&_rv>=1.5) sigs+='<span class="sig sa">RVOL '+_rv.toFixed(2)+'x</span>';
  if(earn!=null&&earn>=0&&earn<=14) sigs+='<span class="sig sa">&#128197; Earnings '+earn+'d</span>';
  if(rsi!=null&&rsi>75) sigs+='<span class="sig sr">RSI overbought</span>';
  if(s.is_crypto) sigs+='<span style="font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px;background:#2d1a3d;color:#9b59b6">&#8383; Crypto</span>';

  var h='';
  h += '<div class="card '+(swingStatus==='PRIMED'?'primed':swingStatus==='BREAKOUT'?'pre':swingStatus==='COILING'?'watch':'')+'" id="card-'+s.ticker+'">';

  // ── Click-to-fold header ──────────────────────────────────────────────────
  var tgtCol2=upsidePct!=null&&upsidePct>5?'var(--green)':upsidePct!=null&&upsidePct<-5?'var(--red)':'var(--muted)';
  h += '<div class="card-header" data-ticker="'+s.ticker+'" onclick="event.stopPropagation();toggleCard(this.dataset.ticker)">';
  // Row 1: rank + ticker + sector | score
  h += '<div style="display:flex;justify-content:space-between;align-items:center">';
  h += '<div style="display:flex;align-items:center;gap:12px">';
  h += '<div class="card-rank '+(isTop?'top':'')+'">'+rank+'</div>';
  h += '<div>';
  var cryptoBadge = s.is_crypto ? '<span style="font-size:9px;font-weight:700;padding:2px 6px;border-radius:10px;background:#2d1a3d;color:#9b59b6;border:1px solid #9b59b644;margin-left:6px;vertical-align:middle">CRYPTO</span>' : '';
  h += '<div style="font-size:20px;font-weight:700">'+s.ticker+cryptoBadge+'<span class="mcap-badge" id="mcap-'+s.ticker+'">&#8212;</span><span style="font-size:12px;font-weight:400;color:var(--muted);margin-left:8px">'+(s.sector||'')+'</span></div>';
  h += '<div style="font-size:13px;color:var(--muted);margin-top:3px">$'+price.toFixed(2)+'<span class="chg '+chgCls+'" style="margin-left:6px">'+chgStr+'</span>'+'</div>';
  h += '</div></div>';
  h += '<div style="text-align:right">';
  h += '<div>';
  h += '<div style="font-size:32px;font-weight:700;color:'+scoreColor+';line-height:1">'+swScore+'</div>';
  h += '<div style="font-size:9px;font-weight:700;letter-spacing:.8px;color:'+scoreColor+';margin-top:2px;text-align:center">SCORE</div>';
  h += '</div>';
  h += '<div style="font-size:10px;font-weight:700;letter-spacing:.5px;color:'+color+';margin-top:5px;text-align:right">'+swingStatus+'</div>';
  h += '</div>';
  h += '</div>';
  // Performance row — directly under title, no 1D (already shown in price line)
  h += '<div class="perf-row" style="margin-top:10px">';
  h += '<div class="perf-item"><div class="perf-lbl">1W</div><div class="perf-val" id="p1w-'+s.ticker+'">&mdash;</div></div>';
  h += '<div class="perf-item"><div class="perf-lbl">1M</div><div class="perf-val" id="p1m-'+s.ticker+'">&mdash;</div></div>';
  h += '<div class="perf-item"><div class="perf-lbl">3M</div><div class="perf-val" id="p3m-'+s.ticker+'">&mdash;</div></div>';
  h += '<div class="perf-item"><div class="perf-lbl">6M</div><div class="perf-val" id="p6m-'+s.ticker+'">&mdash;</div></div>';
  h += '</div>';

  // Row 2: the four pillars of the pre-breakout model — Squeeze | Dry-up | →Pivot | RSI
  var rvol = s.rvol != null ? s.rvol : null;
  var bbSq = s.bb_squeeze_pct != null ? s.bb_squeeze_pct : null;
  var bbSqColor = bbSq!=null?(bbSq<=10?'#27ae60':bbSq<=25?'#e67e22':'#8892a4'):'#8892a4';
  var dryup = s.dryup_ratio != null ? s.dryup_ratio : null;
  var dryupColor = dryup!=null?(dryup<=0.65?'#27ae60':dryup<=0.85?'#e67e22':'#8892a4'):'#8892a4';
  var dpiv = s.dist_to_pivot != null ? s.dist_to_pivot : null;
  // primed = parked just under the pivot (0–4% below); negative = already broke out
  var dpivColor = dpiv!=null?((dpiv>=0&&dpiv<=4)?'#27ae60':(dpiv>=-3&&dpiv<6)?'#e67e22':'#8892a4'):'#8892a4';
  var ema9d = s.ema9_dist_pct != null ? s.ema9_dist_pct : null;
  h += '<div id="fold-'+s.ticker+'" style="display:flex;margin-top:10px;border-top:1px solid var(--border);padding-top:10px">';
  h += '<div style="flex:1;text-align:center;border-right:1px solid var(--border);padding:0 8px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Squeeze</div>';
  h += '<div style="font-size:18px;font-weight:700;color:'+bbSqColor+'">'+(bbSq!=null?bbSq.toFixed(0)+'th':'&mdash;')+'</div>';
  h += '<div style="font-size:10px;color:var(--muted);margin-top:2px">'+(bbSq!=null?(bbSq<=10?'Coiled tight':bbSq<=25?'Tightening':'Loose'):'')+'</div>';
  h += '</div>';
  h += '<div style="flex:1;text-align:center;border-right:1px solid var(--border);padding:0 8px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Vol Dry-up</div>';
  h += '<div style="font-size:18px;font-weight:700;color:'+dryupColor+'">'+(dryup!=null?dryup.toFixed(2)+'x':'&mdash;')+'</div>';
  h += '<div style="font-size:10px;color:var(--muted);margin-top:2px">'+(dryup!=null?(dryup<=0.65?'Sellers gone':dryup<=0.85?'Quieting':'Active'):'')+'</div>';
  h += '</div>';
  h += '<div style="flex:1;text-align:center;border-right:1px solid var(--border);padding:0 8px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">&rarr; Pivot</div>';
  h += '<div style="font-size:18px;font-weight:700;color:'+dpivColor+'">'+(dpiv!=null?(dpiv<0?'':'-')+Math.abs(dpiv).toFixed(1)+'%':'&mdash;')+'</div>';
  h += '<div style="font-size:10px;color:var(--muted);margin-top:2px">'+(dpiv!=null?(dpiv<0?'Broke out':dpiv<=4?'At pivot':dpiv<=8?'Approaching':'Far'):'')+'</div>';
  h += '</div>';
  h += '<div style="flex:1;text-align:center;padding:0 8px">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">RSI (14)</div>';
  h += '<div class="fund-rsi-val" style="font-size:18px;font-weight:700;color:'+rc+'">'+(rsi!=null?rsi.toFixed(0):'&mdash;')+'</div>';
  h += '<div class="fund-rsi-sub" style="font-size:10px;color:var(--muted);margin-top:2px">'+rsiL(rsi)+'</div>';
  h += '</div>';
  h += '</div>';
  h += '</div>'; // end card-header
  // Score bar removed — left border color already conveys status

  // ── Expandable body ───────────────────────────────────────────────────────
  h += '<div class="card-body" id="body-'+s.ticker+'" style="display:none">';

  // Fundamentals shown in header — not repeated here

  // Analyst row
  if(buyPct>0||numAna>0) {{
    h += '<div style="font-size:11px;color:var(--muted);padding:6px 0;display:flex;gap:16px;flex-wrap:wrap">';
    if(numAna>0) h += '<span>&#128101; '+numAna+' analysts</span>';
    if(buyPct>0) h += '<span style="color:'+(buyPct>=70?'#27ae60':buyPct>=50?'#e67e22':'#e74c3c')+'">&#128200; '+buyPct+'% Buy rating</span>';
    if(s.recommendation) h += '<span style="text-transform:capitalize">Consensus: <strong>'+s.recommendation+'</strong></span>';
    h += '</div>';
  }}

  // Signal chips
  if(sigs) h += '<div class="sigs" style="margin:8px 0">'+sigs+'</div>';

  // Technical factors — swing metrics
  var ema9v  = s.ema9  != null ? s.ema9  : null;
  var ema20v = s.ema20 != null ? s.ema20 : null;
  var sma50v = s.sma50 != null ? s.sma50 : null;
  var sma200v= s.sma200!= null ? s.sma200: null;
  var bbUpper= s.bb_upper != null ? s.bb_upper : null;
  var bbWidth= s.bb_width != null ? s.bb_width : null;
  var pctB   = s.pct_b   != null ? s.pct_b   : null;
  h += '<div class="sec-title">Swing Factors</div>';
  h += '<div class="factors">';
  h += '<div class="fbox"><div class="flbl">RVOL</div><div class="fval '+(rvol!=null&&rvol>=2?'fg':rvol!=null&&rvol>=1.5?'fa':'fr')+'">'+(rvol!=null?rvol.toFixed(2):'&mdash;')+'</div><div class="fsub">'+(rvol!=null?(rvol>=2?'Strong':rvol>=1.5?'Active':'Low'):'')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">BB Squeeze %</div><div class="fval '+(bbSq!=null&&bbSq<=10?'fg':bbSq!=null&&bbSq<=25?'fa':'fr')+'">'+(bbSq!=null?bbSq.toFixed(0)+'th':'&mdash;')+'</div><div class="fsub">'+(bbSq!=null?(bbSq<=10?'Tight':bbSq<=25?'Building':'Normal'):'')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">%B (BB pos)</div><div class="fval '+(pctB!=null&&pctB>1?'fg':pctB!=null&&pctB>0.8?'fa':'fr')+'">'+(pctB!=null?(pctB*100).toFixed(0)+'%':'&mdash;')+'</div><div class="fsub">'+(pctB!=null?(pctB>1?'Above upper':pctB>0.8?'Near upper':pctB<0.2?'Near lower':'Mid-band'):'')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">EMA9 dist</div><div class="fval '+(ema9d!=null&&Math.abs(ema9d)<=2?'fg':ema9d!=null&&Math.abs(ema9d)<=5?'fa':'fr')+'">'+(ema9d!=null?(ema9d>=0?'+':'')+ema9d.toFixed(1)+'%':'&mdash;')+'</div><div class="fsub">'+(ema9d!=null?(Math.abs(ema9d)<=2?'At EMA9':Math.abs(ema9d)<=5?'Close':'Extended'):'')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">EMA align</div><div class="fval '+(s.above_ema20&&s.above_sma50&&s.above_sma200?'fg':s.above_ema20&&s.above_sma50?'fa':'fr')+'">'+(s.above_ema20&&s.above_sma50&&s.above_sma200?'Full':s.above_ema20&&s.above_sma50?'Good':s.above_ema20?'Partial':'Weak')+'</div><div class="fsub">'+(s.above_sma200?'Above SMA200':'Below SMA200')+'</div></div>';
  h += '<div class="fbox"><div class="flbl">RSI (14)</div><div class="fval '+rsiC(rsi).replace('#','fg').replace('var(--','').replace(')','').replace('muted','fr').replace('#27ae60','fg').replace('#e74c3c','fr').replace('#e67e22','fa').replace('#9b59b6','fp')+'" style="color:'+rsiC(rsi)+'">'+(rsi!=null?rsi.toFixed(0):'&mdash;')+'</div><div class="fsub">'+rsiL(rsi)+'</div></div>';
  h += '</div>';

  // Score breakdown — server-computed points per component (score_parts)
  var sp = s.score_parts || {{}};
  var PARTS = [
    ['squeeze','Squeeze',30], ['dryup','Vol dry-up',20], ['pivot','Pivot dist',20],
    ['trend','Trend',15], ['base','Base',10], ['rsi','RSI',5]
  ];
  h += '<div class="sec-title">Score Breakdown</div>';
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;margin:8px 0">';
  PARTS.forEach(function(pt) {{
    var v = sp[pt[0]] != null ? sp[pt[0]] : 0, mx = pt[2];
    var pc2 = Math.round(v/mx*100);
    var barCol = pc2>=80?'#27ae60':pc2>=40?'#e67e22':'#4a5568';
    h += '<div><div style="display:flex;justify-content:space-between;font-size:10px;margin-bottom:3px">';
    h += '<span style="color:var(--muted)">'+pt[1]+'</span><span style="font-weight:700;color:'+barCol+'">'+v+'/'+mx+'</span></div>';
    h += '<div style="height:4px;background:var(--bg2);border-radius:2px"><div style="height:100%;width:'+pc2+'%;background:'+barCol+';border-radius:2px"></div></div></div>';
  }});
  h += '</div>';
  if ((sp.penalty||0) < 0) {{
    h += '<div style="font-size:11px;color:var(--red);margin:2px 0 8px">&#9888; Penalties: '+sp.penalty+' pts (extended / overbought / downtrend / far from pivot)</div>';
  }}

  // Trade plan — levels from the backtest (stop -4% = avg max drawdown of
  // top signals; target +7% = avg max gain within 1 month)
  h += '<div class="sec-title">Trade Plan</div>';
  h += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px">';
  h += '<div style="background:var(--bg3);border-radius:10px;padding:12px;text-align:center">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Buy above pivot</div>';
  h += '<div style="font-size:19px;font-weight:700;color:#27ae60">$'+entryNum.toFixed(2)+'</div>';
  h += '<div style="font-size:10px;color:var(--muted);margin-top:2px">'+(pivotP!=null?'pivot $'+pivotP.toFixed(2):'')+'</div>';
  h += '</div>';
  h += '<div style="background:var(--bg3);border-radius:10px;padding:12px;text-align:center">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Stop loss</div>';
  h += '<div style="font-size:19px;font-weight:700;color:#e74c3c">$'+stopNum.toFixed(2)+'</div>';
  h += '<div style="font-size:10px;color:#e74c3c;margin-top:2px">-4%</div>';
  h += '</div>';
  h += '<div style="background:var(--bg3);border-radius:10px;padding:12px;text-align:center">';
  h += '<div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Target (1m)</div>';
  h += '<div style="font-size:19px;font-weight:700;color:#f1c40f">$'+targetNum.toFixed(2)+'</div>';
  h += '<div style="font-size:10px;color:#f1c40f;margin-top:2px">+7%</div>';
  h += '</div></div>';
  h += '<div style="font-size:10px;color:var(--muted);margin-bottom:6px">Levels from the 180-day backtest of this scoring model. Not financial advice.</div>';

  // Footer
  h += '<div style="padding-top:12px;display:flex;justify-content:flex-end">';
  h += '<button class="chart-btn" id="cbtn-'+s.ticker+'" onclick="doChart(this)" data-ticker="'+s.ticker+'">&#128202; Chart</button>';
  h += '</div>';
  h += '</div>'; // card-body

  // Chart panel
  h += '<div class="chart-panel" id="cpanel-'+s.ticker+'">';
  h += '<button class="chart-close" data-ticker="'+s.ticker+'" onclick="doClose(this)">&times; Close</button>';
  h += '<iframe id="cframe-'+s.ticker+'" src="" scrolling="no" allowtransparency="true"></iframe>';
  h += '</div>';
  h += '</div>'; // card
  return h;
}}


function toggleCard(ticker) {{
  var body = document.getElementById('body-'+ticker);
  if (!body) return;
  var isOpen = body.offsetHeight > 0 && body.style.display !== 'none';
  body.style.display = isOpen ? 'none' : 'block';
  if (isOpen) {{ closeChart(ticker); }} else {{ fetchFundamentals(ticker); }}
}}

// _cardData stores combined fundamentals+perf persistently across re-renders.
// Replaces the old separate _fundData/_perfData — halves yfinance API calls.
var _cardData  = {{}};
var _cardCache = {{}};

function applyCardData(ticker) {{
  var d = _cardData[ticker];
  if (!d) return;
  var card = document.getElementById('card-'+ticker);
  if (!card) return;
  // ── Fundamentals ──────────────────────────────────────────────────────────
  if (d.pe_ratio) {{
    var pe = d.pe_ratio;
    var peEl = card.querySelector('.fund-pe-val'), peSub = card.querySelector('.fund-pe-sub');
    if (peEl) {{ peEl.textContent = pe.toFixed(1); peEl.style.color = pe<20?'var(--green)':pe<40?'var(--amber)':'var(--red)'; }}
    if (peSub) peSub.textContent = pe<20?'Cheap':pe<40?'Fair':'Pricey';
  }}
  if (d.rsi != null) {{
    var rsi = d.rsi;
    var rsiEl = card.querySelector('.fund-rsi-val'), rsiSub = card.querySelector('.fund-rsi-sub');
    if (rsiEl) {{ rsiEl.textContent = rsi.toFixed(0); rsiEl.style.color = rsi>=70?'var(--red)':rsi<=30?'var(--blue)':'var(--green)'; }}
    if (rsiSub) rsiSub.textContent = rsi>=70?'Overbought':rsi<=30?'Oversold':'Healthy';
  }}
  var upEl = card.querySelector('.fund-tgt-val'), subEl = card.querySelector('.fund-tgt-sub');
  var tgt = d.analyst_target, up = d.analyst_upside != null ? parseFloat(d.analyst_upside) : null;
  var col = up!=null&&up>5?'var(--green)':up!=null&&up<-5?'var(--red)':'var(--muted)';
  if (upEl && tgt) {{ upEl.textContent = '$'+tgt.toFixed(0); upEl.style.color = col; }}
  if (subEl) {{ subEl.textContent = up!=null?(up>=0?'+':'')+up.toFixed(1)+'%':''; subEl.style.color = col; }}
  // ── Market cap ───────────────────────────────────────────────────────────
  var mcap = document.getElementById('mcap-'+ticker);
  if (mcap && d.market_cap) mcap.textContent = d.market_cap;
  // ── 1W/1M/3M/6M performance ──────────────────────────────────────────────
  function setPct(id, val) {{
    var el = document.getElementById(id);
    if (!el) return;
    if (val == null) {{ el.textContent = '—'; el.className = 'perf-val'; return; }}
    el.textContent = (val >= 0 ? '+' : '') + val.toFixed(1) + '%';
    el.className = 'perf-val ' + (val >= 0 ? 'fg' : 'fr');
  }}
  setPct('p1w-'+ticker, d.change_1w);
  setPct('p1m-'+ticker, d.change_1m);
  setPct('p3m-'+ticker, d.change_3m);
  setPct('p6m-'+ticker, d.change_6m);
}}

async function fetchCardData(ticker, attempt) {{
  attempt = attempt || 1;
  if (_cardData[ticker]) {{ applyCardData(ticker); return; }}
  if (_cardCache[ticker]) return;
  _cardCache[ticker] = true;
  try {{
    var resp = await fetch('/api/card-data/' + ticker);
    if (!resp.ok) {{
      _cardCache[ticker] = false;
      // Retry once after 4s on rate-limit or server error
      if (attempt < 3) setTimeout(function() {{ fetchCardData(ticker, attempt+1); }}, 4000 * attempt);
      return;
    }}
    var d = await resp.json();
    if (d.error) {{ _cardCache[ticker] = false; return; }}
    _cardData[ticker] = d;
    applyCardData(ticker);
  }} catch(e) {{ _cardCache[ticker] = false; }}
}}

// Keep legacy aliases so any other callers still work
function fetchFundamentals(ticker) {{ fetchCardData(ticker); }}
function fetchPerf(ticker)         {{ fetchCardData(ticker); }}

function prefetchAllFundamentals() {{
  var headers = document.querySelectorAll('.card-header');
  var needFetch = [];
  headers.forEach(function(hdr) {{
    var ticker = hdr.getAttribute('data-ticker');
    if (!ticker) return;
    if (_cardData[ticker]) {{
      applyCardData(ticker); // instant — from in-memory cache
    }} else {{
      needFetch.push(ticker);
    }}
  }});
  // Stagger: one request per card, 250 ms apart — avoids hammering Yahoo Finance
  needFetch.forEach(function(ticker, i) {{
    setTimeout(function() {{ fetchCardData(ticker); }}, i * 250);
  }});
}}

function doChart(btn) {{
  var t=btn.getAttribute('data-ticker');
  toggleChart(btn,'cpanel-'+t,'cframe-'+t);
}}
function doClose(btn) {{
  var t=btn.getAttribute('data-ticker');
  closeChart(t);
}}
function toggleChart(btn,panelId,frameId) {{
  var panel=document.getElementById(panelId),frame=document.getElementById(frameId);
  var open=panel.style.display==='block';
  if(open){{ panel.style.display='none'; frame.src=''; btn.className='chart-btn'; btn.innerHTML='&#128202; Chart'; }}
  else {{
    panel.style.display='block';
    frame.src='https://s.tradingview.com/widgetembed/?symbol=NASDAQ%3A'+frameId.replace('cframe-','')+'&interval=D&theme=dark&style=1&hide_side_toolbar=0&allow_symbol_change=0&save_image=0&toolbarbg=1a1d26&show_popup_button=0';
    btn.className='chart-btn open'; btn.innerHTML='&times; Close';
  }}
}}
function closeChart(t) {{
  var p=document.getElementById('cpanel-'+t),f=document.getElementById('cframe-'+t),b=document.getElementById('cbtn-'+t);
  if(p)p.style.display='none'; if(f)f.src=''; if(b){{b.className='chart-btn';b.innerHTML='&#128202; Chart';}}
}}
async function lookupTicker() {{
  var ticker=document.getElementById('lookup-input').value.trim().toUpperCase();
  if(!ticker)return;
  var wrap=document.getElementById('lookup-wrap'),result=document.getElementById('lookup-result');
  wrap.style.display='block';
  result.innerHTML='<div style="color:var(--muted);padding:12px 0">&#9203; Fetching '+ticker+'...</div>';
  var baseData = (allStockData&&allStockData[ticker]) ? allStockData[ticker]
               : (stockData&&stockData[ticker])       ? stockData[ticker]
               : null;
  var foundLabel = (allStockData&&allStockData[ticker]) ? '&#10003; Found in scanner'
                 : (stockData&&stockData[ticker])       ? '&#10003; Found in top 10'
                 : null;
  if(baseData) {{
    // Always fetch fresh market data so RSI / PE / analyst fields are populated
    var enriched = Object.assign({{}}, baseData);
    try {{
      var resp2 = await fetch('/lookup?t='+ticker);
      if(resp2.ok) {{
        var d2 = await resp2.json();
        if(!d2.error) {{
          // Lookup wins on market data; scanner wins on score/status/signals
          enriched.price          = d2.price          || enriched.price;
          enriched.change_pct     = d2.change_pct     != null ? d2.change_pct : enriched.change_pct;
          enriched.rsi            = d2.rsi            != null ? d2.rsi : enriched.rsi;
          enriched.pe_ratio       = d2.pe_ratio       != null ? d2.pe_ratio : enriched.pe_ratio;
          enriched.analyst_target = d2.analyst_target != null ? d2.analyst_target : enriched.analyst_target;
          enriched.analyst_upside = d2.analyst_upside != null ? String(d2.analyst_upside) : enriched.analyst_upside;
          enriched.name           = d2.name           || enriched.name;
          enriched.sector         = d2.sector         || enriched.sector;
        }}
      }}
    }} catch(e) {{/* use scanner data only */}}
    result.innerHTML='<div style="color:var(--green);font-size:12px;margin-bottom:8px">'+foundLabel+'</div>'+makeCard(enriched,'&mdash;');
    setTimeout(function(){{ fetchPerf(ticker); }}, 50);
    return;
  }}
  try {{
    var resp=await fetch('/lookup?t='+ticker);
    if(!resp.ok)throw new Error('HTTP '+resp.status);
    var data=await resp.json();
    if(data.error)throw new Error(data.error);
    var cl=data.closes,hi=data.highs,lo=data.lows,vo=data.vols;
    var n=cl.length,price=data.price,chg=data.change_pct;
    function ema(a,p){{var k=2/(p+1),e=a[0];for(var i=1;i<a.length;i++)e=(a[i]||e)*k+e*(1-k);return e;}}
    // Swing-native metrics from the 60d window (squeeze pctile is approximate —
    // the scanner uses 252d; enough for a directional read on a lookup)
    var e9=ema(cl,9), e20=ema(cl,20), sma50=n>=50?cl.slice(-50).reduce(function(a,b){{return a+b;}},0)/50:null;
    var widths=[];
    for(var i=19;i<n;i++){{
      var w20=cl.slice(i-19,i+1), m=w20.reduce(function(a,b){{return a+b;}},0)/20;
      var sd=Math.sqrt(w20.reduce(function(a,b){{return a+(b-m)*(b-m);}},0)/20);
      widths.push(m>0?(4*sd)/m:0);
    }}
    var curW=widths[widths.length-1]||0;
    var sqPct=widths.length>5?Math.round(widths.filter(function(w){{return w<curW;}}).length/widths.length*100):null;
    var vr5=vo.slice(-5).reduce(function(a,b){{return a+b;}},0)/5;
    var vb20=vo.slice(-20).reduce(function(a,b){{return a+b;}},0)/20;
    var dry=vb20>0?Math.round(vr5/vb20*100)/100:null;
    var voEx=vo.slice(-21,-1).reduce(function(a,b){{return a+b;}},0)/Math.min(20,n-1);
    var rvol=voEx>0?Math.round(vo[n-1]/voEx*100)/100:null;
    var pv=Math.max.apply(null,hi.slice(0,-1));
    var dPiv=price>0?Math.round((pv-price)/price*10000)/100:null;
    var s={{ticker:ticker,name:data.name||ticker,sector:'',price:price,change_pct:chg,
      score:null,status:'LOOKUP',
      bb_squeeze_pct:sqPct,dryup_ratio:dry,rvol:rvol,
      pivot:Math.round(pv*100)/100,dist_to_pivot:dPiv,broke_out:price>pv,
      ema9:e9,ema20:e20,sma50:sma50,sma200:null,
      above_ema20:price>e20,above_sma50:sma50!=null&&price>sma50,above_sma200:false,
      ema9_dist_pct:e9>0?Math.round((price-e9)/e9*10000)/100:null,
      ema20_dist:e20>0?Math.round(Math.abs(price-e20)/e20*10000)/100:null,
      pct_b:null,rsi:data.rsi||null,pe_ratio:data.pe_ratio||null,
      analyst_target:data.analyst_target||null,
      analyst_upside:data.analyst_upside!=null?String(data.analyst_upside):null}};
    result.innerHTML='<div style="color:var(--amber);font-size:12px;margin-bottom:8px">&#9889; Live lookup &mdash; Yahoo Finance 60d</div>'+makeCard(s,'&mdash;');
    setTimeout(function(){{ fetchPerf(ticker); }}, 50);
  }} catch(e) {{
    result.innerHTML='<div style="color:var(--red);padding:12px 0">Could not fetch <strong>'+ticker+'</strong>: '+e.message+'</div>';
  }}
}}
</script>

</body>
</html>"""

@app.route('/lookup')
def lookup():
    ticker = request.args.get('t','').upper().strip()
    if not ticker or len(ticker) > 6:
        return jsonify({'error': 'Invalid ticker'}), 400
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period='60d', interval='1d')
        if hist.empty:
            return jsonify({'error': 'No data found for '+ticker}), 404
        info = tk.info or {}
        fi   = tk.fast_info
        closes = [round(x,2) for x in hist['Close'].tolist()]
        highs  = [round(x,2) for x in hist['High'].tolist()]
        lows   = [round(x,2) for x in hist['Low'].tolist()]
        vols   = hist['Volume'].tolist()
        price  = getattr(fi, 'last_price', None) or closes[-1]
        chg    = round((price - closes[-2]) / closes[-2] * 100, 2) if len(closes) > 1 else 0
        # Fundamentals
        pe          = info.get('trailingPE') or info.get('forwardPE')
        target      = info.get('targetMeanPrice')
        name        = info.get('shortName') or info.get('longName') or ticker
        sector      = info.get('sector','')
        upside      = round((target - price) / price * 100, 1) if target and price else None
        # RSI (14) calculated from closes
        rsi = None
        if len(closes) >= 15:
            deltas = [closes[i]-closes[i-1] for i in range(1,len(closes))]
            gains  = [max(d,0) for d in deltas[-14:]]
            losses = [abs(min(d,0)) for d in deltas[-14:]]
            avg_g  = sum(gains)/14
            avg_l  = sum(losses)/14
            if avg_l == 0 and avg_g > 0:
                rsi = 100.0
            elif avg_l > 0:
                rs  = avg_g / avg_l
                rsi = round(100 - 100/(1+rs), 1)
        return jsonify({
            'ticker':     ticker,
            'name':       name,
            'sector':     sector,
            'price':      round(price, 2),
            'change_pct': chg,
            'pe_ratio':   round(pe, 1) if pe else None,
            'rsi':        rsi,
            'analyst_target': round(target, 2) if target else None,
            'analyst_upside': round(upside, 1) if upside is not None else None,
            'closes':     closes,
            'highs':      highs,
            'lows':       lows,
            'vols':       vols,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/api/perf/<ticker>')
def api_perf(ticker):
    """Return market cap + 1W/1M/3M/6M performance for a ticker."""
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 6:
        return jsonify({'error': 'Invalid ticker'}), 400
    try:
        tk   = yf.Ticker(ticker)
        hist = tk.history(period='1y', interval='1d')
        if hist.empty:
            return jsonify({'error': 'No data'}), 404
        closes = hist['Close'].tolist()
        price  = closes[-1]

        def pct(n):
            # closes[-n] = price n days ago; need at least n+1 points (current + n back)
            if len(closes) >= n and n > 0:
                base = closes[-n]
                if base and base > 0:
                    return round((price - base) / base * 100, 1)
            return None

        mc     = getattr(tk.fast_info, 'market_cap', None)
        mc_str = None
        if mc:
            if   mc >= 1e12: mc_str = f"{mc/1e12:.1f}T"
            elif mc >= 1e9:  mc_str = f"{mc/1e9:.1f}B"
            else:             mc_str = f"{mc/1e6:.0f}M"

        return jsonify({
            'market_cap': mc_str,
            'change_1w':  pct(5),
            'change_1m':  pct(21),
            'change_3m':  pct(63),
            'change_6m':  pct(126),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/card-data/<ticker>')
def api_card_data(ticker):
    """
    Combined endpoint: returns fundamentals + performance in a single yfinance call.
    Replaces the separate /lookup and /api/perf calls to halve Yahoo Finance requests
    and avoid rate-limit timeouts that left cards with all-dash values.
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 6:
        return jsonify({'error': 'Invalid ticker'}), 400
    try:
        import time as _time
        tk   = yf.Ticker(ticker)
        hist = tk.history(period='1y', interval='1d')
        if hist.empty:
            # Retry once — Yahoo Finance occasionally rate-limits the first call
            _time.sleep(1.0)
            hist = tk.history(period='3mo', interval='1d')
        if hist.empty:
            return jsonify({'error': 'No data'}), 404

        import math as _math
        # Strip NaN — yfinance returns NaN for today's unsettled bar
        closes = [c for c in hist['Close'].tolist() if c is not None and not _math.isnan(c)]
        if len(closes) < 2:
            return jsonify({'error': 'No data'}), 404
        price  = closes[-1]

        # ── Performance (uses full 1y history) ───────────────────────────────
        def pct(n):
            if len(closes) > n and n > 0:
                base = closes[-(n+1)]
                if base and base > 0:
                    return round((price - base) / base * 100, 1)
            return None

        # ── RSI (14) from last 15 closes ─────────────────────────────────────
        rsi = None
        if len(closes) >= 15:
            deltas = [closes[i] - closes[i-1] for i in range(len(closes)-14, len(closes))]
            gains  = [max(d, 0) for d in deltas]
            losses = [abs(min(d, 0)) for d in deltas]
            avg_g  = sum(gains) / 14
            avg_l  = sum(losses) / 14
            if avg_l == 0 and avg_g > 0:
                rsi = 100.0
            elif avg_l > 0:
                rsi = round(100 - 100 / (1 + avg_g / avg_l), 1)

        # ── Fundamentals (fast_info first to avoid slow info dict) ────────────
        fi     = tk.fast_info
        mc     = getattr(fi, 'market_cap', None)
        mc_str = None
        if mc:
            if   mc >= 1e12: mc_str = f"{mc/1e12:.1f}T"
            elif mc >= 1e9:  mc_str = f"{mc/1e9:.1f}B"
            else:             mc_str = f"{mc/1e6:.0f}M"

        info   = tk.info or {}
        pe     = info.get('trailingPE') or info.get('forwardPE')
        target = info.get('targetMeanPrice')
        # Use real-time price for upside so intraday moves don't skew the %
        current_price = info.get('currentPrice') or getattr(fi, 'last_price', None) or price
        upside = round((target - current_price) / current_price * 100, 1) if target and current_price else None

        return jsonify({
            'market_cap':      mc_str,
            'pe_ratio':        round(float(pe), 1) if pe and pe > 0 else None,
            'rsi':             rsi,
            'analyst_target':  round(float(target), 2) if target else None,
            'analyst_upside':  upside,
            'change_1w':       pct(5),
            'change_1m':       pct(21),
            'change_3m':       pct(63),
            'change_6m':       pct(126),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/')
def index():
    html = HTML.format(
        ver=VERSION,
        cfg=json.dumps(FIREBASE_CONFIG),
        staging_banner=STAGING_BANNER
    )
    return html






# ── Analytics — picks history + forward returns ───────────────────────────────
ANALYTICS_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swing Scanner Analytics</title>
<style>
:root{--bg:#0f1117;--bg2:#1a1d26;--bg3:#22263a;--text:#e8eaf0;--muted:#8892a4;--border:#2a2f42;--green:#27ae60;--amber:#e67e22;--blue:#3498db;--red:#e74c3c;--gold:#f1c40f;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}
.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;}
.header h1{font-size:16px;font-weight:600;}
.nav-pills{display:flex;gap:6px;}
.nav-pill{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;text-decoration:none;border:1px solid var(--border);color:var(--muted);background:var(--bg3);}
.nav-pill.active{background:var(--blue);color:#fff;border-color:var(--blue);}
.wrap{max-width:1150px;margin:0 auto;padding:20px 24px;}
.toolbar{display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap;}
.tlabel{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;}
.wbtn{padding:5px 16px;border-radius:20px;font-size:12px;font-weight:700;border:1px solid var(--border);color:var(--muted);background:var(--bg3);cursor:pointer;}
.wbtn.on{background:var(--blue);color:#fff;border-color:var(--blue);}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:22px;}
.kpi{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px 16px;}
.kpi .kl{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;}
.kpi .kv{font-size:24px;font-weight:700;line-height:1.1;}
.kpi .ks{font-size:11px;color:var(--muted);margin-top:4px;}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-bottom:22px;}
.scard{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;}
.scard h3{font-size:12px;letter-spacing:.5px;margin-bottom:10px;}
.scard table{width:100%;font-size:12px;border-collapse:collapse;}
.scard td,.scard th{padding:4px 6px;text-align:right;}
.scard th{color:var(--muted);font-size:10px;text-transform:uppercase;}
.scard td:first-child,.scard th:first-child{text-align:left;}
.pos{color:var(--green);font-weight:600;}.neg{color:var(--red);font-weight:600;}.na{color:var(--muted);}
.picks{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;}
.picks table{width:100%;font-size:12px;border-collapse:collapse;}
.picks th{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:7px 8px;text-align:left;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap;}
.picks th:hover{color:var(--text);}
.picks th .arr{color:var(--blue);margin-left:3px;}
.picks td{padding:7px 8px;border-bottom:1px solid #2a2f4233;}
.badge{font-size:9px;padding:2px 7px;border-radius:20px;font-weight:700;}
.badge.PRIMED{background:#3d3611;color:var(--gold);}
.badge.BREAKOUT{background:#1a3d2b;color:var(--green);}
.badge.BT{background:var(--bg3);color:var(--muted);}
.badge.LIVE{background:#1a3d2b;color:var(--green);}
.empty{color:var(--muted);text-align:center;padding:60px 0;}
.note{font-size:11px;color:var(--muted);margin:10px 2px 18px;}
.grouphead{font-size:12px;font-weight:700;letter-spacing:.8px;margin:4px 2px 10px;color:var(--green);}
</style>
</head>
<body>
__BANNER__
<div class="header">
  <h1>&#128200; Swing Scanner &mdash; Analytics</h1>
  <div class="nav-pills"><a class="nav-pill" href="/">&#128202; Dashboard</a><a class="nav-pill active" href="/analytics">&#128200; Analytics</a></div>
</div>
<div class="wrap">
  <div class="note">The scanner logs its PRIMED and BREAKOUT signals after each market close; forward returns
  fill in as they mature (1w = 5, 2w = 10, 1m = 21 trading days). BT rows are simulated signals from the
  180-day backtest of the current scoring model &mdash; LIVE rows are what the scanner actually surfaced.</div>

  <div class="toolbar">
    <span class="tlabel">Return window:</span>
    <button class="wbtn" data-w="1w" onclick="setWin('1w')">1 week</button>
    <button class="wbtn" data-w="2w" onclick="setWin('2w')">2 weeks</button>
    <button class="wbtn on" data-w="1m" onclick="setWin('1m')">1 month</button>
  </div>

  <div class="kpis" id="kpis"><div class="empty">Loading...</div></div>
  <div id="cards"><div class="empty">Loading...</div></div>
  <div class="picks"><table id="ptable"><thead><tr id="phead"></tr></thead>
    <tbody id="pbody"><tr><td colspan="9" class="empty">Loading history...</td></tr></tbody></table></div>
</div>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
var CFG = __CFG__;
firebase.initializeApp(CFG);
var fdb = firebase.database();

var allRows = [], win = '1m', sortKey = 'day', sortDir = -1;

var COLS = [
  ['day','Date'], ['source','Src'], ['ticker','Ticker'], ['status','Status'],
  ['score','Score'], ['price','Entry'], ['1w','1w'], ['2w','2w'], ['1m','1m']
];

function fmt(v){ if(v==null) return '<span class="na">&mdash;</span>';
  var c=v>=0?'pos':'neg'; return '<span class="'+c+'">'+(v>=0?'+':'')+v.toFixed(2)+'%</span>'; }

function setWin(w){
  win = w;
  document.querySelectorAll('.wbtn').forEach(function(b){ b.classList.toggle('on', b.dataset.w===w); });
  renderKPIs(); renderCards();
}

function setSort(key){
  if (sortKey===key) sortDir = -sortDir; else {{ sortKey=key; sortDir=-1; }}
  renderTable();
}

function renderKPIs(){
  var m = allRows.map(function(x){ return {v:x.r[win], t:x.ticker, d:x.day, src:x.source}; })
                 .filter(function(x){ return x.v!=null; });
  var el = document.getElementById('kpis');
  if(!m.length){ el.innerHTML='<div class="empty">No matured '+win+' returns yet.</div>'; return; }
  var wins  = m.filter(function(x){return x.v>0;});
  var losses= m.filter(function(x){return x.v<=0;});
  var avgW  = wins.length  ? wins.reduce(function(a,b){return a+b.v;},0)/wins.length : 0;
  var avgL  = losses.length? losses.reduce(function(a,b){return a+b.v;},0)/losses.length : 0;
  var avg   = m.reduce(function(a,b){return a+b.v;},0)/m.length;
  var best  = m.reduce(function(a,b){return b.v>a.v?b:a;});
  var worst = m.reduce(function(a,b){return b.v<a.v?b:a;});
  var pf    = losses.length && avgL!==0 ? (wins.reduce(function(a,b){return a+b.v;},0) / Math.abs(losses.reduce(function(a,b){return a+b.v;},0))) : null;
  function box(lbl, val, cls, sub){
    return '<div class="kpi"><div class="kl">'+lbl+'</div><div class="kv '+(cls||'')+'">'+val+'</div>'+(sub?'<div class="ks">'+sub+'</div>':'')+'</div>';
  }
  el.innerHTML =
    box('Win rate', Math.round(wins.length/m.length*100)+'%', wins.length/m.length>=0.55?'pos':'', m.length+' matured signals')
   + box('Avg return', (avg>=0?'+':'')+avg.toFixed(2)+'%', avg>=0?'pos':'neg', 'per signal, '+win)
   + box('Avg win', '+'+avgW.toFixed(2)+'%', 'pos', wins.length+' winners')
   + box('Avg loss', avgL.toFixed(2)+'%', 'neg', losses.length+' losers')
   + box('Best', best.t, 'pos', '+'+best.v.toFixed(1)+'% &middot; '+best.d)
   + box('Worst', worst.t, 'neg', worst.v.toFixed(1)+'% &middot; '+worst.d)
   + (pf!=null ? box('Profit factor', pf.toFixed(2), pf>=1.5?'pos':pf>=1?'':'neg', 'gross wins / gross losses') : '');
}

function statusCards(pool){
  var cards='';
  ['PRIMED','BREAKOUT'].forEach(function(st){
    var sub = pool.filter(function(x){return x.status===st;});
    if(!sub.length) return;
    var tr='';
    ['1w','2w','1m'].forEach(function(w){
      var m = sub.map(function(x){return x.r[w];}).filter(function(v){return v!=null;});
      if(!m.length){ tr+='<tr><td>'+w+'</td><td colspan="3" class="na">not matured</td></tr>'; return; }
      var wn = m.filter(function(v){return v>0;}).length;
      var avg = m.reduce(function(a,b){return a+b;},0)/m.length;
      tr+='<tr><td>'+w+'</td><td>'+m.length+'</td><td>'+Math.round(wn/m.length*100)+'%</td><td>'+fmt(avg)+'</td></tr>';
    });
    cards+='<div class="scard"><h3><span class="badge '+st+'">'+st+'</span> &nbsp;'+sub.length+' signals</h3>'
         +'<table><tr><th>win</th><th>n</th><th>win rate</th><th>avg</th></tr>'+tr+'</table></div>';
  });
  return cards;
}

function renderCards(){
  var live = allRows.filter(function(x){return x.source!=='backtest';});
  var bt   = allRows.filter(function(x){return x.source==='backtest';});
  var html='';
  html += '<div class="grouphead">&#128994; LIVE SIGNALS ('+live.length+')</div>';
  html += '<div class="cards">'+(statusCards(live)||'<div class="empty" style="padding:20px 0">No live picks yet &mdash; they are logged after each market close.</div>')+'</div>';
  if(bt.length){
    html += '<div class="grouphead" style="color:var(--muted)">&#128202; BACKTEST &mdash; SIMULATED ('+bt.length+')</div>';
    html += '<div class="cards">'+statusCards(bt)+'</div>';
  }
  document.getElementById('cards').innerHTML = html;
}

function renderTable(){
  var head='';
  COLS.forEach(function(c){
    var arr = sortKey===c[0] ? '<span class="arr">'+(sortDir<0?'&#9660;':'&#9650;')+'</span>' : '';
    head += '<th onclick="setSort(\''+c[0]+'\')">'+c[1]+arr+'</th>';
  });
  document.getElementById('phead').innerHTML = head;

  var rows = allRows.slice();
  rows.sort(function(a,b){
    var va, vb;
    if(sortKey==='1w'||sortKey==='2w'||sortKey==='1m'){ va=a.r[sortKey]; vb=b.r[sortKey]; }
    else {{ va=a[sortKey]; vb=b[sortKey]; }}
    var aNull = va==null, bNull = vb==null;
    if(aNull&&bNull) return 0; if(aNull) return 1; if(bNull) return -1;   // nulls last
    if(va<vb) return 1*sortDir; if(va>vb) return -1*sortDir;
    return 0;
  });
  document.getElementById('pbody').innerHTML = rows.slice(0,500).map(function(x){
    var srcB = x.source==='backtest' ? '<span class="badge BT">BT</span>' : '<span class="badge LIVE">LIVE</span>';
    return '<tr><td>'+x.day+'</td><td>'+srcB+'</td><td><strong>'+x.ticker+'</strong></td>'
      +'<td><span class="badge '+x.status+'">'+x.status+'</span></td>'
      +'<td>'+x.score+'</td><td>$'+(+x.price).toFixed(2)+'</td>'
      +'<td>'+fmt(x.r['1w'])+'</td><td>'+fmt(x.r['2w'])+'</td><td>'+fmt(x.r['1m'])+'</td></tr>';
  }).join('') || '<tr><td colspan="9" class="empty">No history yet.</td></tr>';
}

fdb.ref('/swing_scanner/history').once('value', function(snap){
  var hist = snap.val() || {};
  Object.keys(hist).forEach(function(day){
    var picks = hist[day]; if(!picks) return;
    Object.keys(picks).forEach(function(tk){
      var p = picks[tk]; if(!p) return;
      allRows.push({day:day, ticker:tk, status:p.status||'', score:p.score||0,
                    price:p.price||0, source:p.source||'live', r:(p.returns||{})});
    });
  });
  if(!allRows.length){
    document.getElementById('kpis').innerHTML='';
    document.getElementById('cards').innerHTML =
      '<div class="empty">No picks logged yet &mdash; the first entries appear after the next market close.</div>';
    document.getElementById('pbody').innerHTML =
      '<tr><td colspan="9" class="empty">No history yet.</td></tr>';
    return;
  }
  renderKPIs(); renderCards(); renderTable();
});
</script>
</body>
</html>"""

@app.route('/analytics')
def analytics():
    return (ANALYTICS_HTML
            .replace('__CFG__', json.dumps(FIREBASE_CONFIG))
            .replace('__BANNER__', STAGING_BANNER))


if __name__ == '__main__':
    app.run(debug=True)
