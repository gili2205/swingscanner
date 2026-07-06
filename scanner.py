"""
Swing Trading Scanner v1.0
Scores NYSE + NASDAQ stocks (and crypto) using a swing trading algorithm:
  - BB squeeze quality, BB breakout, EMA alignment, RSI, RVOL, EMA9 proximity
Firebase path: /swing_scanner
"""

from __future__ import annotations
import os, time, logging, requests, pickle, json
from datetime import datetime, date, timedelta
from pathlib import Path
import pytz

# Load .env automatically so the script works from any shell without
# needing to manually source it first.
def _load_dotenv():
    for candidate in [Path(__file__).parent / ".env", Path("/home/scanner/.env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return
_load_dotenv()

import pandas as pd
import numpy as np
import firebase_admin
from firebase_admin import credentials, db
import yfinance as yf

_handlers = [logging.StreamHandler()]   # journal captures stdout under systemd
try:
    _handlers.append(logging.FileHandler("/var/log/swingscanner.log"))
except (PermissionError, FileNotFoundError):
    pass   # not writable (e.g. local run) — stdout/journal only
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=_handlers)
log = logging.getLogger(__name__)

FIREBASE_URL  = os.environ["FIREBASE_URL"]
FIREBASE_CRED = os.environ["FIREBASE_CRED"]
ALPACA_KEY    = os.environ["ALPACA_KEY"]
ALPACA_SECRET = os.environ["ALPACA_SECRET"]
ET   = pytz.timezone("America/New_York")
HDRS = {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}

CACHE_FILE      = "/home/scanner/swing_cache.pkl"
FUND_CACHE_FILE = "/home/scanner/fundamentals_cache.json"

cred = credentials.Certificate(FIREBASE_CRED)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
ref = db.reference("/swing_scanner")

_funds_cache, _funds_ts = {}, {}
_fund_file_cache = {}
FUNDS_TTL = 6 * 3600

# ── Quality minimums ──────────────────────────────────────────────────────────
# NOTE: deliberately NO minimum-RVOL gate. Pre-breakout stocks are QUIET —
# volume contracts during the coil and only expands at the breakout itself.
# Gating on RVOL would filter out exactly the setups we want to catch early.
MIN_PRICE       = 10.0           # 180d backtest: sub-$10 signals had negative edge
MAX_PRICE       = 600.0          # loosened from 150 to widen the universe
MIN_DOLLAR_VOL  = 5_000_000      # liquidity: must be tradeable ($/day)
PIVOT_LOOKBACK  = 50             # trading days for the breakout pivot high

# ── Crypto universe ───────────────────────────────────────────────────────────
CRYPTO_TICKERS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "DOGE-USD", "ADA-USD", "TRX-USD", "AVAX-USD", "SHIB-USD",
    "TON-USD", "DOT-USD", "MATIC-USD", "LINK-USD", "LTC-USD",
    "BCH-USD", "UNI-USD", "ATOM-USD", "XLM-USD", "ICP-USD",
]

# ── Scoring weights — PRE-BREAKOUT swing model ────────────────────────────────
# Philosophy: reward the COILED SPRING, not the stock that already popped.
# A primed setup = tight volatility squeeze + volume dry-up + price parked
# a bit under a pivot, inside an uptrend. Points total 100; penalties subtract.
# Weights tuned 2026-07-06 from a 180-day full-universe backtest (5,798
# signals): edge concentrates in squeeze ≤10th pct, dry-up 0.50–0.65,
# and 2–7% below pivot; being AT the pivot (0–2%) underperformed.
DEFAULT_WEIGHTS = {
    # 1. Volatility squeeze (max 30) — only the tightest decile pays
    "squeeze_5":       30,
    "squeeze_10":      25,
    "squeeze_20":      10,
    "squeeze_35":       4,
    "squeeze_50":       2,
    # 2. Volume dry-up (max 20) — 0.50–0.65 was the strongest single factor
    "dryup_50":        18,
    "dryup_65":        20,
    "dryup_80":         6,
    "dryup_100":        3,
    # 3. Proximity to breakout pivot (max 20) — buy the coil EARLY (2–7%),
    #    not at resistance
    "pivot_2":         12,
    "pivot_4":         20,
    "pivot_7":         16,
    "pivot_12":         6,
    # 4. Trend stack / Stage-2 uptrend (max 15)
    "trend_full":      15,   # price > ema20 > sma50 > sma200
    "trend_mid":       10,   # price > sma50 > sma200
    "trend_weak":       5,   # price > sma200
    # 5. Base tightness — proximity to EMA20 support (max 10)
    "base_3":          10,
    "base_6":           6,
    "base_10":          2,
    # 6. Constructive RSI (max 5) — room to run, not overbought
    "rsi_sweet":        5,   # 50–65
    "rsi_ok":           3,   # 45–50 or 65–70
    # Penalties
    "penalty_extended":    20,   # price >15% above EMA9 = chasing
    "penalty_overbought":  12,   # RSI > 75 = already ran
    "penalty_downtrend":   18,   # below SMA200 = wrong stage
    "penalty_far_pivot":    8,   # >15% below pivot = not near a breakout
    # Score thresholds — PRIMED means top-of-book (backtest: score≥75 carries
    # the edge; 65 admitted ~17 signals/day with barely any)
    "threshold_primed":   75,
    "threshold_coiling":  48,
    "threshold_watch":    32,
}

def load_scoring_weights():
    """Load per-environment scoring weights from Firebase, fallback to defaults."""
    try:
        fw = db.reference("/swing_scanner/scoring_weights").get() or {}
        w  = {**DEFAULT_WEIGHTS, **{k: v for k, v in fw.items() if k in DEFAULT_WEIGHTS}}
        overrides = [k for k in fw if k in DEFAULT_WEIGHTS]
        if overrides:
            log.info(f"Scoring weights: {len(overrides)} overrides from Firebase: {overrides}")
        else:
            log.info("Scoring weights: using all defaults (no Firebase overrides)")
        return w
    except Exception as e:
        log.warning(f"Could not load scoring weights from Firebase ({e}) — using defaults")
        return dict(DEFAULT_WEIGHTS)

W = load_scoring_weights()

# ── Universe ──────────────────────────────────────────────────────────────────
def get_universe():
    """Fetch NYSE + NASDAQ tickers from SEC EDGAR."""
    tickers = _fetch_edgar()
    if tickers: return tickers
    log.warning("Using hardcoded fallback")
    return _hardcoded_fallback()

def _fetch_edgar():
    for attempt in range(3):
        try:
            r = requests.get("https://www.sec.gov/files/company_tickers_exchange.json",
                headers={"User-Agent": "swing-scanner/1.0 scanner@example.com"}, timeout=30)
            if not r.content or len(r.content) < 10:
                time.sleep(2**attempt); continue
            data = r.json()
            fields, rows = data.get("fields",[]), data.get("data",[])
            if not fields or not rows:
                time.sleep(2**attempt); continue
            fi, ei = fields.index("ticker"), fields.index("exchange")
            tickers = sorted({
                str(row[fi]).upper().strip() for row in rows
                if str(row[ei]).upper() in ("NASDAQ", "NYSE")
                and str(row[fi]).strip() and len(str(row[fi]).strip()) <= 6
                and not any(c in str(row[fi]).strip() for c in "-.'+ ")
            })
            if tickers:
                log.info(f"SEC EDGAR: {len(tickers)} tickers")
                return tickers
        except Exception as e:
            log.warning(f"EDGAR attempt {attempt+1}: {e}")
            time.sleep(2**attempt)
    log.error("SEC EDGAR failed"); return []

def _hardcoded_fallback():
    return ["AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","COST",
        "ASML","NFLX","AMD","QCOM","AMAT","LRCX","KLAC","SNPS","CDNS","MRVL",
        "ADBE","CRM","ORCL","PANW","CRWD","FTNT","ZS","OKTA","NET","DDOG",
        "SNOW","MDB","PLTR","NOW","WDAY","ARM","SMCI","ON","MPWR","TXN",
        "HIMS","SOUN","ASTS","CELH","DUOL","CAVA","RDDT","APP","AXON","UBER",
        "DASH","ABNB","BKNG","HOOD","SOFI","COIN","MARA","MRNA","REGN","VRTX",
        "ISRG","DXCM","IONQ","RKLB","DOCS","MU","INTC","AVGO",
        "JPM","BAC","GS","MS","C","WFC","JNJ","UNH","PFE","MRK",
        "XOM","CVX","HD","NKE","DIS","BA","GE","CAT","MMM","IBM"]

# ── History cache ──────────────────────────────────────────────────────────────
def load_cache(allow_partial=False):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE,"rb") as f: cache = pickle.load(f)
        except Exception as e:
            log.warning(f"Cache unreadable ({e}) — ignoring"); return None
        if cache.get("date") == date.today():
            if cache.get("complete", True):
                log.info(f"Loaded today cache: {len(cache.get('data',{}))} stocks")
                return cache.get("data",{})
            if allow_partial:
                log.info(f"Partial cache from an interrupted download: "
                         f"{len(cache.get('data',{}))} stocks — will resume")
                return cache.get("data",{})
    return None

def save_cache(data, complete=True):
    with open(CACHE_FILE,"wb") as f:
        pickle.dump({"date":date.today(),"data":data,"complete":complete},f)
    if complete: log.info(f"Cache saved: {len(data)} stocks")

def download_history(universe, resume=None):
    # Resume support: a restart mid-download used to lose everything (cache
    # was only written at the end). Now we checkpoint every 40 chunks and
    # skip tickers already fetched today.
    history = dict(resume) if resume else {}
    all_tickers = [t for t in list(universe) + CRYPTO_TICKERS if t not in history]
    log.info(f"=== DAILY HISTORY DOWNLOAD: {len(all_tickers)} stocks"
             + (f" (resuming, {len(history)} cached) ===" if history else " ==="))
    chunks = [all_tickers[i:i+20] for i in range(0,len(all_tickers),20)]
    total  = len(chunks)
    for i, chunk in enumerate(chunks):
        try:
            d = yf.download(chunk, period="1y", interval="1d", progress=False, auto_adjust=True)
            for t in chunk:
                try:
                    if isinstance(d.columns, pd.MultiIndex):
                        if t not in d["Close"].columns: continue
                        df = pd.DataFrame({"Open":d["Open"][t],"High":d["High"][t],
                            "Low":d["Low"][t],"Close":d["Close"][t],"Volume":d["Volume"][t]}).dropna()
                    else:
                        df = d[["Open","High","Low","Close","Volume"]].dropna()
                    if len(df) >= 20: history[t] = df
                except: pass
            if (i+1)%10==0 or (i+1)==total:
                pct = round((i+1)/total*100)
                log.info(f"  Progress: {i+1}/{total} ({pct}%) | {len(history)} stocks")
            if (i+1)%40==0:
                save_cache(history, complete=False)   # checkpoint
            try:
                ref.child('download_progress').set({'loaded':len(history),'total':len(all_tickers),
                    'pct':round(len(history)/len(all_tickers)*100) if len(all_tickers)>0 else 0})
            except: pass
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"  Chunk {i+1} failed: {e}"); time.sleep(2)
    log.info(f"=== DOWNLOAD COMPLETE: {len(history)} stocks ===")
    save_cache(history); return history

# ── Fundamentals (fetched live for top candidates) ────────────────────────────
def load_fund_file_cache():
    global _fund_file_cache
    try:
        if Path(FUND_CACHE_FILE).exists():
            with open(FUND_CACHE_FILE) as f: data = json.load(f)
            if data.get("_date") == str(date.today()):
                _fund_file_cache = data
                log.info(f"Loaded fundamentals file cache: {len(data)-1} stocks")
    except Exception as e:
        log.warning(f"Could not load fundamentals file cache: {e}")

def get_fundamentals_fast(tickers):
    now = time.time()
    to_fetch = [t for t in tickers
        if t not in _funds_cache or now - _funds_ts.get(t,0) > FUNDS_TTL]

    still_needed = []
    for t in to_fetch:
        if t in _fund_file_cache and isinstance(_fund_file_cache[t], dict):
            _funds_cache[t] = _fund_file_cache[t]
            _funds_ts[t] = now
        else:
            still_needed.append(t)

    log.info(f"Fundamentals: {len(tickers)-len(still_needed)} cached, {len(still_needed)} to fetch")
    for t in still_needed:
        try:
            info = yf.Ticker(t).info
            pe      = info.get("trailingPE") or info.get("forwardPE")
            target  = info.get("targetMeanPrice")
            rec     = info.get("recommendationMean")
            rev_g   = info.get("revenueGrowth")
            eps_g   = info.get("earningsGrowth")
            buy_pct = max(0,min(100,round((3.0-rec)/2.0*100))) if rec else None

            earn_days = None
            try:
                cal = yf.Ticker(t).calendar
                if cal is not None and not cal.empty:
                    cols = list(cal.columns)
                    if cols:
                        ed = cols[0]
                        if hasattr(ed,'date'): ed = ed.date()
                        earn_days = (ed - date.today()).days
            except: pass

            mc     = info.get("marketCap")
            mc_str = None
            if mc:
                if   mc >= 1e12: mc_str = f"{mc/1e12:.1f}T"
                elif mc >= 1e9:  mc_str = f"{mc/1e9:.1f}B"
                else:            mc_str = f"{mc/1e6:.0f}M"

            _funds_cache[t] = {
                "pe_ratio":           round(float(pe),1) if pe and pe>0 else None,
                "analyst_target":     round(float(target),2) if target else None,
                "analyst_buy_pct":    buy_pct,
                "revenue_growth_yoy": round(float(rev_g)*100,1) if rev_g else None,
                "eps_growth_yoy":     round(float(eps_g)*100,1) if eps_g else None,
                "days_to_earnings":   earn_days,
                "sector":             info.get("sector", ""),
                "market_cap_str":     mc_str,
            }
        except:
            _funds_cache[t] = {"pe_ratio":None,"analyst_target":None,"analyst_buy_pct":None,
                "revenue_growth_yoy":None,"eps_growth_yoy":None,"days_to_earnings":None,
                "sector":"","market_cap_str":None}
        _funds_ts[t] = now

    return {t: _funds_cache.get(t, {}) for t in tickers}

# ── Live prices (Alpaca) ──────────────────────────────────────────────────────
def alpaca_prices(tickers):
    prices = {}
    # Alpaca only handles equity tickers, not crypto
    equity_tickers = [t for t in tickers if "-USD" not in t]
    for chunk in [equity_tickers[i:i+1000] for i in range(0,len(equity_tickers),1000)]:
        syms = ",".join(chunk)
        for ep,key in [("quotes","quotes"),("trades","trades")]:
            try:
                r = requests.get(f"https://data.alpaca.markets/v2/stocks/{ep}/latest",
                    params={"symbols":syms,"feed":"iex"}, headers=HDRS, timeout=15)
                if r.status_code==200:
                    for sym,q in r.json().get(key,{}).items():
                        if sym not in prices:
                            if ep=="quotes":
                                a,b=q.get("ap",0),q.get("bp",0)
                                if a>0 and b>0: prices[sym]=round((a+b)/2,2)
                            else:
                                p=q.get("p",0)
                                if p>0: prices[sym]=round(p,2)
            except: pass
    log.info(f"Live prices: {len(prices)} stocks")
    return prices

# ── Technical helpers ─────────────────────────────────────────────────────────
def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Compute EMA with span=period, adjust=False."""
    return series.ewm(span=period, adjust=False).mean()

def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    """Wilder RSI."""
    delta = closes.diff()
    gain  = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs    = gain.iloc[-1] / max(float(loss.iloc[-1]), 1e-10)
    return round(float(100 - 100 / (1 + rs)), 1)

def compute_bollinger(closes: pd.Series, period: int = 20, std_dev: float = 2.0):
    """
    Returns (sma, upper, lower, width, pct_b, width_series).
    width = (upper - lower) / sma
    pct_b = (price - lower) / (upper - lower)
    width_series: the full series of BB widths (for squeeze percentile)
    """
    sma    = closes.rolling(period).mean()
    std    = closes.rolling(period).std(ddof=0)
    upper  = sma + std_dev * std
    lower  = sma - std_dev * std
    width_series = (upper - lower) / sma.replace(0, np.nan)

    last_sma   = float(sma.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])
    last_width = float(width_series.iloc[-1]) if not np.isnan(width_series.iloc[-1]) else 0.0

    price = float(closes.iloc[-1])
    band_range = last_upper - last_lower
    pct_b = (price - last_lower) / band_range if band_range > 0 else 0.5

    return last_sma, last_upper, last_lower, last_width, pct_b, width_series

# ── SCORING — Swing Trading ───────────────────────────────────────────────────
def score_swing(ticker: str, df: pd.DataFrame, live_price: float = None,
                is_crypto: bool = False) -> dict | None:
    """
    Score a stock/crypto using the swing trading algorithm.
    Returns result dict or None if it fails quality gates.
    """
    if df is None or len(df) < 30:
        return None

    try:
        closes = df["Close"].dropna()
        if len(closes) < 20:
            return None

        last_close  = float(closes.iloc[-1])
        yest_close  = float(closes.iloc[-2]) if len(closes) >= 2 else last_close
        prev2_close = float(closes.iloc[-3]) if len(closes) >= 3 else yest_close
        prev_day_chg = round((yest_close - prev2_close) / prev2_close * 100, 2)

        if live_price and live_price > 0 and not is_crypto:
            price = live_price
            chg   = round((price - yest_close) / yest_close * 100, 2)
        else:
            price = last_close
            chg   = prev_day_chg

        vol = df["Volume"]

        # ── Quality gates (liquidity + price range only — NO RVOL gate) ─
        avg_vol = float(vol.iloc[-20:].mean()) if len(vol) >= 20 else float(vol.mean())
        if not is_crypto:
            if price < MIN_PRICE or price > MAX_PRICE:
                return None
            if avg_vol * price < MIN_DOLLAR_VOL:   # must be tradeable
                return None

        today_vol = float(vol.iloc[-1]) if len(vol) > 0 else 0.0
        # RVOL = today's volume / 20-day avg (exclude today). Kept for breakout
        # detection + display only — it is NOT a gate anymore.
        avg_vol_ex = float(vol.iloc[-21:-1].mean()) if len(vol) >= 21 else avg_vol
        rvol = round(today_vol / avg_vol_ex, 2) if avg_vol_ex > 0 else 1.0

        # Volume dry-up: recent 5-day avg vs 20-day base. Lower = drier = the
        # quiet contraction that precedes a breakout.
        recent_vol  = float(vol.iloc[-5:].mean()) if len(vol) >= 5 else today_vol
        base_vol    = float(vol.iloc[-20:].mean()) if len(vol) >= 20 else avg_vol
        dryup_ratio = round(recent_vol / base_vol, 2) if base_vol > 0 else 1.0

        # ── Indicators ────────────────────────────────────────────────
        # Bollinger Bands
        bb_sma, bb_upper, bb_lower, bb_width, pct_b, width_series = compute_bollinger(
            closes, period=20, std_dev=2.0
        )

        # BB squeeze percentile: how tight is current width vs last 252 days?
        if len(width_series.dropna()) >= 20:
            hist_widths = width_series.dropna()
            # Use up to 252 days
            if len(hist_widths) > 252:
                hist_widths = hist_widths.iloc[-252:]
            squeeze_pct = round(
                float((hist_widths < bb_width).mean() * 100), 1
            )
        else:
            squeeze_pct = 50.0

        above_upper_bb = price > bb_upper

        # EMAs and SMAs
        ema9_series  = compute_ema(closes, 9)
        ema20_series = compute_ema(closes, 20)
        sma50_series = closes.rolling(50).mean()
        sma200_series = closes.rolling(200).mean()

        ema9   = float(ema9_series.iloc[-1])
        ema20  = float(ema20_series.iloc[-1])
        sma50  = float(sma50_series.iloc[-1]) if len(closes) >= 50 and not np.isnan(sma50_series.iloc[-1]) else None
        sma200 = float(sma200_series.iloc[-1]) if len(closes) >= 200 and not np.isnan(sma200_series.iloc[-1]) else None

        above_ema20  = price > ema20
        above_sma50  = (price > sma50)  if sma50  is not None else False
        above_sma200 = (price > sma200) if sma200 is not None else False

        # EMA9 distance %
        ema9_dist_pct = round((price - ema9) / ema9 * 100, 2) if ema9 > 0 else 0.0

        # RSI
        rsi = compute_rsi(closes, 14)

        # Breakout pivot: highest HIGH over the last PIVOT_LOOKBACK days,
        # excluding today. Price coiled just under this = primed to break.
        highs = df["High"].dropna()
        if len(highs) >= PIVOT_LOOKBACK + 1:
            pivot = float(highs.iloc[-(PIVOT_LOOKBACK + 1):-1].max())
        elif len(highs) > 1:
            pivot = float(highs.iloc[:-1].max())
        else:
            pivot = price
        dist_to_pivot = round((pivot - price) / price * 100, 2)  # +ve = below pivot
        broke_out = price > pivot

        # Distance to EMA20 support (tightness of the base)
        ema20_dist = round(abs(price - ema20) / ema20 * 100, 2) if ema20 > 0 else 99.0

        # Macro gate — only reject DEEP downtrends (price < 70% of SMA200).
        # Mild dips below SMA200 are kept but penalized in scoring.
        if not is_crypto and sma200 is not None and price < sma200 * 0.70:
            return None

        # ════════════════════════════════════════════════════════════════
        # PRE-BREAKOUT SWING SCORING (0–100)
        # ════════════════════════════════════════════════════════════════
        # Each component's points are kept in `parts` so the UI can show an
        # honest breakdown (server-computed — no client-side re-derivation).
        parts = {}

        # 1. Volatility squeeze — 30 (tighter width percentile = more coiled)
        if   squeeze_pct <= 5:  parts["squeeze"] = W["squeeze_5"]
        elif squeeze_pct <= 10: parts["squeeze"] = W["squeeze_10"]
        elif squeeze_pct <= 20: parts["squeeze"] = W["squeeze_20"]
        elif squeeze_pct <= 35: parts["squeeze"] = W["squeeze_35"]
        elif squeeze_pct <= 50: parts["squeeze"] = W["squeeze_50"]
        else:                   parts["squeeze"] = 0

        # 2. Volume dry-up — 20 (recent volume contracted vs the base)
        if   dryup_ratio <= 0.50: parts["dryup"] = W["dryup_50"]
        elif dryup_ratio <= 0.65: parts["dryup"] = W["dryup_65"]
        elif dryup_ratio <= 0.80: parts["dryup"] = W["dryup_80"]
        elif dryup_ratio <= 1.00: parts["dryup"] = W["dryup_100"]
        else:                     parts["dryup"] = 0

        # 3. Proximity to breakout pivot — 20 (coiled a bit below = primed)
        if   0 <= dist_to_pivot <= 2:  parts["pivot"] = W["pivot_2"]
        elif dist_to_pivot <= 4:       parts["pivot"] = W["pivot_4"]
        elif dist_to_pivot <= 7:       parts["pivot"] = W["pivot_7"]
        elif dist_to_pivot <= 12:      parts["pivot"] = W["pivot_12"]
        elif broke_out and dist_to_pivot >= -3:  # fresh breakout (just crossed)
            parts["pivot"] = W["pivot_7"]
        else:
            parts["pivot"] = 0

        # 4. Trend stack / Stage-2 uptrend — 15
        if (price > ema20 and sma50 and ema20 > sma50 and sma200 and sma50 > sma200):
            parts["trend"] = W["trend_full"]
        elif sma50 and sma200 and price > sma50 > sma200:
            parts["trend"] = W["trend_mid"]
        elif sma200 and above_sma200:
            parts["trend"] = W["trend_weak"]
        else:
            parts["trend"] = 0

        # 5. Base tightness — proximity to EMA20 support — 10
        if   ema20_dist <= 3:  parts["base"] = W["base_3"]
        elif ema20_dist <= 6:  parts["base"] = W["base_6"]
        elif ema20_dist <= 10: parts["base"] = W["base_10"]
        else:                  parts["base"] = 0

        # 6. Constructive RSI — 5 (room to run, not overbought)
        if   50 <= rsi <= 65:                      parts["rsi"] = W["rsi_sweet"]
        elif (45 <= rsi < 50) or (65 < rsi <= 70): parts["rsi"] = W["rsi_ok"]
        else:                                      parts["rsi"] = 0

        score = sum(parts.values())

        # 7. Penalties — punish chasing / wrong stage
        pen = 0
        if ema9_dist_pct > 15:
            pen += W["penalty_extended"]
        if rsi > 75:
            pen += W["penalty_overbought"]
        if not is_crypto and sma200 is not None and not above_sma200:
            pen += W["penalty_downtrend"]
        if dist_to_pivot > 15:
            pen += W["penalty_far_pivot"]
        parts["penalty"] = -min(pen, score)   # what was actually subtracted
        score = max(0, score - pen)

        score = min(100, max(0, score))

        # Drop pure noise — keeps the pushed list meaningful
        if score < 20:
            return None

        # ── Status label (pre-breakout oriented) ──────────────────────
        fresh_breakout = broke_out and dist_to_pivot >= -4 and rvol >= 1.5
        if fresh_breakout:
            status = "BREAKOUT"          # just crossed the pivot on volume
        elif score >= W["threshold_primed"] and dist_to_pivot <= 5 and dryup_ratio <= 0.90:
            status = "PRIMED"            # coiled + dry + at the pivot = imminent
        elif score >= W["threshold_coiling"]:
            status = "COILING"          # base building
        elif score >= W["threshold_watch"]:
            status = "WATCH"            # early
        else:
            status = "BUILDING"

        return {
            "ticker":          ticker,
            "is_crypto":       is_crypto,
            "price":           round(price, 2 if price >= 1 else 6),
            "change_pct":      chg,
            "sector":          "",   # filled in by fundamentals
            "score":           score,
            "status":          status,
            "rvol":            rvol,
            "dryup_ratio":     dryup_ratio,
            "pivot":           round(pivot, 2 if pivot >= 1 else 6),
            "dist_to_pivot":   dist_to_pivot,
            "broke_out":       broke_out,
            "avg_vol_20":      round(avg_vol_ex, 0),
            "today_vol":       round(today_vol, 0),
            "bb_upper":        round(bb_upper, 4),
            "bb_lower":        round(bb_lower, 4),
            "bb_sma":          round(bb_sma, 4),
            "bb_width":        round(bb_width, 4),
            "bb_squeeze_pct":  squeeze_pct,
            "pct_b":           round(pct_b, 3),
            "above_upper_bb":  above_upper_bb,
            "ema9":            round(ema9, 4),
            "ema20":           round(ema20, 4),
            "sma50":           round(sma50, 4) if sma50 is not None else None,
            "sma200":          round(sma200, 4) if sma200 is not None else None,
            "above_ema20":     above_ema20,
            "above_sma50":     above_sma50,
            "above_sma200":    above_sma200,
            "rsi":             rsi,
            "ema9_dist_pct":   ema9_dist_pct,
            "ema20_dist":      ema20_dist,
            "score_parts":     parts,
            "rank":            0,
            "scanned_at":      datetime.now(ET).isoformat(),
        }
    except Exception as e:
        log.debug(f"score_swing {ticker}: {e}")
        return None

# ── Fast rescore ──────────────────────────────────────────────────────────────
def fast_rescore(history, live_prices, fund_data):
    t0 = time.time()
    results = []
    for ticker, df in history.items():
        is_crypto = ticker in CRYPTO_TICKERS or "-USD" in ticker
        live_p = live_prices.get(ticker) if not is_crypto else None
        res = score_swing(ticker, df, live_price=live_p, is_crypto=is_crypto)
        if res:
            # Inject fundamentals for equities
            if not is_crypto:
                fd = fund_data.get(ticker, {})
                res["sector"]     = fd.get("sector", "")
                res["market_cap"] = fd.get("market_cap_str", "")
            results.append(res)

    if not results:
        log.info(f"Rescore: 0 stocks in {round(time.time()-t0,1)}s")
        return []

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results): r["rank"] = i + 1

    primed    = sum(1 for r in results if r["status"] == "PRIMED")
    coiling   = sum(1 for r in results if r["status"] == "COILING")
    breakouts = sum(1 for r in results if r["status"] == "BREAKOUT")
    cryptos   = sum(1 for r in results if r.get("is_crypto"))
    log.info(f"Rescore: {len(results)} stocks | PRIMED={primed} COILING={coiling} "
             f"BREAKOUT={breakouts} CRYPTO={cryptos} | {round(time.time()-t0,1)}s")
    return results

# ── Push to Firebase ──────────────────────────────────────────────────────────
def push_results(results, sess, scan_time, elapsed):
    top20  = results[:20]
    top100 = results[:100]

    # Fetch fundamentals for top 50 equities
    top50_equity = [r["ticker"] for r in results[:50] if not r.get("is_crypto")]
    if top50_equity:
        fund_data = get_fundamentals_fast(top50_equity)
        for r in results[:50]:
            if not r.get("is_crypto") and r["ticker"] in fund_data:
                fd = fund_data[r["ticker"]]
                if not r.get("sector"):     r["sector"]     = fd.get("sector", "")
                if not r.get("market_cap"): r["market_cap"] = fd.get("market_cap_str", "")

    now_et = datetime.now(ET)
    metadata = {
        "stocks_scanned":    len(results),
        "primed_count":      sum(1 for r in results if r["status"] == "PRIMED"),
        "coiling_count":     sum(1 for r in results if r["status"] == "COILING"),
        "breakout_count":    sum(1 for r in results if r["status"] == "BREAKOUT"),
        "watch_count":       sum(1 for r in results if r["status"] == "WATCH"),
        "crypto_count":      sum(1 for r in results if r.get("is_crypto")),
        "market_open":       sess == "Market Open",
        "session":           sess,
        "last_updated":      now_et.isoformat(),
        "last_scan_time":    scan_time,
        "scan_duration_sec": elapsed,
        "scanner_version":   "swing_v2_prebreakout",
    }
    ref.child("metadata").update(metadata)

    # /swing_scanner/stocks — top 20
    try:
        ref.child("stocks").set({r["ticker"]: r for r in top20})
    except Exception as e:
        log.debug(f"stocks push failed: {e}")

    # /swing_scanner/all_stocks — top 100
    try:
        ref.child("all_stocks").set({r["ticker"]: r for r in top100})
    except Exception as e:
        log.debug(f"all_stocks push failed: {e}")

    top20_tickers = [r["ticker"] for r in top20]
    log.info(f"Pushed: top20={top20_tickers} | PRIMED={metadata['primed_count']} "
             f"COILING={metadata['coiling_count']} | [{sess}] | {elapsed}s")

# ── Picks history (feeds the Analytics tab) ──────────────────────────────────
def log_history(results, now_et):
    """After the close, record today's PRIMED/BREAKOUT signals once.
    update_returns.py (nightly cron) fills in forward returns as they mature.
    Writes are idempotent (set per date/ticker), so re-runs are safe."""
    day = now_et.date().isoformat()
    picks = [r for r in results if r["status"] in ("PRIMED", "BREAKOUT")
             and not r.get("is_crypto")]
    if not picks:
        return
    payload = {}
    for r in picks:
        payload[r["ticker"]] = {
            "price":       r["price"],
            "score":       r["score"],
            "status":      r["status"],
            "squeeze":     r["bb_squeeze_pct"],
            "dryup":       r["dryup_ratio"],
            "dist_pivot":  r["dist_to_pivot"],
            "pivot":       r["pivot"],
            "source":      "live",
            "logged_at":   now_et.isoformat(),
            "returns":     {},
        }
    try:
        ref.child("history").child(day).update(payload)
        log.info(f"History: logged {len(payload)} picks for {day}")
    except Exception as e:
        log.warning(f"History log failed: {e}")

# ── Session helper ────────────────────────────────────────────────────────────
def get_session():
    now_et = datetime.now(ET)
    h,m,wd = now_et.hour,now_et.minute,now_et.weekday()
    if   wd<5 and (9,30)<=(h,m)<(16,0): return "Market Open"
    elif wd<5 and (4,0)<=(h,m)<(9,30):  return "Pre-Market"
    elif wd<5 and (16,0)<=(h,m)<(20,0): return "After-Hours"
    else:                                return "Market Closed"

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    log.info("Swing Scanner v2 (pre-breakout) starting")
    load_fund_file_cache()
    universe = get_universe()

    history = load_cache()
    if not history:
        partial = load_cache(allow_partial=True)
        log.info("No complete cache — downloading history"
                 + (" (resuming from checkpoint)..." if partial else "..."))
        history = download_history(universe, resume=partial)

    log.info(f"Ready: {len(history)} stocks. Starting 60s scan loop.")
    last_download_date = date.today()

    full_fund_data = {}
    for ticker in list(history.keys()):
        if ticker in _fund_file_cache and isinstance(_fund_file_cache[ticker], dict):
            full_fund_data[ticker] = _fund_file_cache[ticker]

    log.info(f"Pre-loaded fundamentals for {len(full_fund_data)} stocks from file cache")
    last_history_date = None

    while True:
        try:
            t0     = time.time()
            now_et = datetime.now(ET)
            sess   = get_session()

            if date.today() != last_download_date:
                if now_et.hour == 9 and now_et.minute >= 25:
                    log.info("=== New trading day — refreshing caches ===")
                    history = download_history(universe)
                    load_fund_file_cache()
                    full_fund_data = {t: _fund_file_cache[t] for t in history
                        if t in _fund_file_cache and isinstance(_fund_file_cache[t], dict)}
                    last_download_date = date.today()

            live    = alpaca_prices(list(history.keys()))
            results = fast_rescore(history, live, full_fund_data)

            elapsed   = round(time.time() - t0, 1)
            scan_time = now_et.strftime("%Y-%m-%d %H:%M:%S ET")

            if results:
                push_results(results, sess, scan_time, elapsed)
                # Log the day's signals once, right after the close
                if (sess == "After-Hours" and now_et.weekday() < 5
                        and last_history_date != now_et.date()):
                    log_history(results, now_et)
                    last_history_date = now_et.date()
            log.info("Next scan in 60s...")
            time.sleep(60)

        except KeyboardInterrupt:
            log.info("Stopped."); break
        except Exception as e:
            log.error(f"Loop error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
