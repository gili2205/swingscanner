"""
Swing Trading Scanner
=====================
Scans NYSE + NASDAQ equities and top-20 crypto for swing trade setups.
Scores each asset 0–100 using Bollinger Band squeeze, EMA alignment,
RVOL, RSI, and proximity metrics. Pushes results to Firebase every 60s.

Environment variables required:
  FIREBASE_CRED   — path to Firebase service-account JSON file
  FIREBASE_URL    — Firebase Realtime Database URL
  ALPACA_KEY      — Alpaca API key (paper or live)
  ALPACA_SECRET   — Alpaca API secret

Run:
    python scanner.py
"""

from __future__ import annotations

import os
import time
import pickle
import logging
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, db

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FIREBASE_CRED = os.environ.get("FIREBASE_CRED", "/home/scanner/firebase_cred.json")
FIREBASE_URL  = os.environ.get("FIREBASE_URL",  "https://your-project-default-rtdb.firebaseio.com")
FIREBASE_PATH = os.environ.get("FIREBASE_PATH", "/swing_scanner")   # /swing_scanner_staging for staging
ALPACA_KEY    = os.environ.get("ALPACA_KEY",    "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET", "")
ENVIRONMENT   = os.environ.get("ENVIRONMENT",   "prod")

CACHE_FILE      = f"/home/scanner/swing_cache_{ENVIRONMENT}.pkl"
CACHE_TTL_HOURS = 24          # re-download history every 24 h
SCAN_INTERVAL_S = 60          # rescore every 60 s
PUSH_TOP_N      = 20          # top-N cards on the dashboard
PUSH_ALL_N      = 100         # full list stored in Firebase

ALPACA_BASE_URL = "https://data.alpaca.markets/v2/stocks/quotes/latest"

# Equity filters
MIN_PRICE     = 5.0
MAX_PRICE     = 150.0
MIN_AVG_VOL   = 500_000       # 500K shares/day
MIN_RVOL      = 1.5           # gate: must have 1.5× relative volume to appear

# Indicator periods
BB_PERIOD      = 20
BB_STD         = 2
BB_HIST_DAYS   = 252          # days for BB width percentile
EMA_FAST       = 9
EMA_SLOW       = 20
SMA_MID        = 50
SMA_LONG       = 200
RSI_PERIOD     = 14
RVOL_AVG_DAYS  = 20

# Crypto universe (top 20 via yfinance)
CRYPTO_TICKERS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "DOGE-USD", "ADA-USD", "TRX-USD", "AVAX-USD", "SHIB-USD",
    "TON-USD", "DOT-USD", "MATIC-USD", "LINK-USD", "LTC-USD",
    "BCH-USD", "UNI-USD", "ATOM-USD", "XLM-USD", "ICP-USD",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("swing")

# ---------------------------------------------------------------------------
# Firebase initialisation
# ---------------------------------------------------------------------------

def init_firebase():
    """Initialise Firebase Admin SDK once."""
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CRED)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})

# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Proper exponential moving average with Wilder smoothing (span = period)."""
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    """
    Compute RSI using Wilder's smoothed moving average.
    Returns the latest RSI value as a float.
    """
    delta = closes.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def compute_bollinger(closes: pd.Series, period: int = 20, std_dev: float = 2.0):
    """
    Compute Bollinger Bands.
    Returns (sma, upper, lower, width, pct_b) for the most-recent bar.
    width = (upper - lower) / sma  (normalised)
    """
    sma   = closes.rolling(period).mean()
    std   = closes.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    width = (upper - lower) / sma.replace(0, np.nan)
    denom = (upper - lower).replace(0, np.nan)
    pct_b = (closes - lower) / denom
    return (
        float(sma.iloc[-1]),
        float(upper.iloc[-1]),
        float(lower.iloc[-1]),
        float(width.iloc[-1]),
        float(pct_b.iloc[-1]),
        width,           # full series for percentile calculation
    )

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_swing(ticker: str, df: pd.DataFrame, live_price: float = None,
                is_crypto: bool = False) -> dict | None:
    """
    Score a single asset.  Returns a result dict or None if it fails filters.

    Parameters
    ----------
    ticker     : asset ticker symbol
    df         : daily OHLCV DataFrame, at least BB_HIST_DAYS + SMA_LONG rows
    live_price : real-time price from Alpaca (equities); None → use last close
    is_crypto  : True skips price/volume equity filters
    """
    try:
        if df is None or len(df) < SMA_LONG + 10:
            return None

        closes  = df["Close"].dropna()
        volumes = df["Volume"].dropna()

        if len(closes) < SMA_LONG + 10:
            return None

        price = float(live_price) if live_price else float(closes.iloc[-1])

        # ---- Equity filters ----
        if not is_crypto:
            if price < MIN_PRICE or price > MAX_PRICE:
                return None
            avg_vol_20 = float(volumes.iloc[-RVOL_AVG_DAYS - 1:-1].mean())
            if avg_vol_20 < MIN_AVG_VOL:
                return None

        # ---- RVOL ----
        avg_vol_for_rvol = float(volumes.iloc[-RVOL_AVG_DAYS - 1:-1].mean())
        today_vol        = float(volumes.iloc[-1])
        rvol = (today_vol / avg_vol_for_rvol) if avg_vol_for_rvol > 0 else 0.0

        # Gate: must meet minimum RVOL (applies to equities and crypto equally)
        if rvol < MIN_RVOL:
            return None

        # ---- Bollinger Bands ----
        sma_bb, upper_bb, lower_bb, bb_width, pct_b, bb_width_series = \
            compute_bollinger(closes, BB_PERIOD, BB_STD)

        # BB squeeze percentile: current width vs last BB_HIST_DAYS days
        hist_widths = bb_width_series.dropna().iloc[-BB_HIST_DAYS:]
        if len(hist_widths) >= 20:
            bb_squeeze_pct = float(
                (hist_widths < bb_width).sum() / len(hist_widths) * 100
            )
        else:
            bb_squeeze_pct = 50.0  # neutral if insufficient history

        above_upper_bb = price > upper_bb

        # ---- Moving averages ----
        ema9   = float(compute_ema(closes, EMA_FAST).iloc[-1])
        ema20  = float(compute_ema(closes, EMA_SLOW).iloc[-1])
        sma50  = float(closes.rolling(SMA_MID).mean().iloc[-1])
        sma200 = float(closes.rolling(SMA_LONG).mean().iloc[-1])

        # ---- Macro gate: equity must trade ≥ 80% of SMA200 ----
        if not is_crypto and price < 0.80 * sma200:
            return None

        # ---- RSI ----
        rsi = compute_rsi(closes, RSI_PERIOD)

        # ---- EMA9 distance (overextension) ----
        ema9_dist_pct = (price - ema9) / ema9 * 100 if ema9 > 0 else 0.0

        # ---- Price change (day) ----
        prev_close   = float(closes.iloc[-2]) if len(closes) >= 2 else price
        change_pct   = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0

        # ----------------------------------------------------------------
        # Scoring
        # ----------------------------------------------------------------
        score = 0

        # -- Volume (30 pts) --
        if rvol >= 5.0:
            score += 30
        elif rvol >= 3.0:
            score += 22
        elif rvol >= 2.0:
            score += 15
        elif rvol >= 1.5:
            score += 8

        # -- BB squeeze quality (20 pts) --
        # Lower percentile = tighter squeeze = better
        if bb_squeeze_pct <= 10:
            score += 20
        elif bb_squeeze_pct <= 20:
            score += 15
        elif bb_squeeze_pct <= 35:
            score += 10
        elif bb_squeeze_pct <= 50:
            score += 5

        # -- BB breakout (15 pts) --
        if above_upper_bb:
            score += 15
        elif pct_b >= 0.90:
            score += 8
        elif pct_b >= 0.75:
            score += 3

        # -- EMA alignment (15 pts) --
        ema_bull  = ema9 > ema20
        above_50  = price > sma50
        above_200 = price > sma200
        if ema_bull and above_50 and above_200:
            score += 15
        elif ema_bull and above_50:
            score += 10
        elif ema_bull:
            score += 6
        elif above_50 and above_200:
            score += 4

        # -- RSI (10 pts) --
        if rsi >= 70:
            score += 10
        elif rsi >= 60:
            score += 8
        elif rsi >= 50:
            score += 5

        # -- EMA9 proximity / not overextended (10 pts) --
        if 0 <= ema9_dist_pct <= 3:
            score += 10
        elif 3 < ema9_dist_pct <= 7:
            score += 6
        elif 7 < ema9_dist_pct <= 12:
            score += 2
        # >12% → 0 pts

        # ---- Penalties ----
        if ema9_dist_pct > 20:
            score -= 15
        if rsi < 45:
            score -= 10
        if not is_crypto and not above_200:
            score -= 15
        if above_upper_bb and rvol < 2.0:
            score -= 10  # fake breakout signal

        score = max(0, min(100, score))

        # ---- Status ----
        if rvol >= 2.0 and above_upper_bb and score >= 65:
            status = "BREAKOUT"
        elif score >= 45:
            status = "WATCH"
        else:
            status = "BUILDING"

        # ---- Sector (equities will be filled in later; crypto = "Crypto") ----
        sector = "Crypto" if is_crypto else ""

        return {
            "ticker":          ticker,
            "is_crypto":       is_crypto,
            "price":           round(price, 4),
            "change_pct":      round(change_pct, 2),
            "sector":          sector,
            "score":           score,
            "status":          status,
            # Volume
            "rvol":            round(rvol, 2),
            "avg_vol_20":      int(avg_vol_for_rvol),
            "today_vol":       int(today_vol),
            # Bollinger Bands
            "bb_upper":        round(upper_bb, 4),
            "bb_lower":        round(lower_bb, 4),
            "bb_sma":          round(sma_bb, 4),
            "bb_width":        round(bb_width, 4),
            "bb_squeeze_pct":  round(bb_squeeze_pct, 1),
            "pct_b":           round(pct_b, 3),
            "above_upper_bb":  above_upper_bb,
            # Moving averages
            "ema9":            round(ema9, 4),
            "ema20":           round(ema20, 4),
            "sma50":           round(sma50, 4),
            "sma200":          round(sma200, 4),
            "above_ema20":     ema9 > ema20,
            "above_sma50":     above_50,
            "above_sma200":    above_200,
            # RSI & distance
            "rsi":             round(rsi, 1),
            "ema9_dist_pct":   round(ema9_dist_pct, 2),
            # Timestamp
            "scanned_at":      datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        log.debug("score_swing %s error: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def get_universe() -> list[str]:
    """
    Fetch NYSE + NASDAQ equities from SEC EDGAR company_tickers_exchange.json.
    Filters out tickers longer than 5 chars (ETFs / warrants / preferred).
    """
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    try:
        resp = requests.get(url, headers={"User-Agent": "swing-scanner/1.0"}, timeout=30)
        resp.raise_for_status()
        data   = resp.json()
        fields = data["fields"]   # ['cik', 'name', 'ticker', 'exchange']
        rows   = data["data"]
        t_idx  = fields.index("ticker")
        e_idx  = fields.index("exchange")

        tickers = []
        for row in rows:
            exchange = str(row[e_idx]).upper()
            ticker   = str(row[t_idx]).upper().strip()
            if not ticker or len(ticker) > 5:
                continue
            if exchange not in ("NASDAQ", "NYSE"):
                continue
            tickers.append(ticker)

        log.info("EDGAR: %d raw equity tickers", len(tickers))
        return list(set(tickers))

    except Exception as e:
        log.warning("SEC EDGAR fetch failed: %s — using fallback", e)
        return _fallback_tickers()


def _fallback_tickers() -> list[str]:
    """Hardcoded ~120 liquid NYSE+NASDAQ stocks as a last resort."""
    return [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST",
        "NFLX", "AMD", "QCOM", "AMAT", "LRCX", "KLAC", "SNPS", "CDNS", "MRVL",
        "ADBE", "CRM", "PANW", "CRWD", "FTNT", "ZS", "OKTA", "NET", "DDOG",
        "SNOW", "MDB", "PLTR", "AXON", "SMCI", "ARM", "COIN", "HOOD", "SOFI",
        "AFRM", "UPST", "APP", "HIMS", "SOUN", "ASTS", "CELH", "DUOL", "CAVA",
        "RDDT", "UBER", "LYFT", "DASH", "ABNB", "BKNG", "EXPE", "PCTY", "PAYC",
        "JPM", "BAC", "GS", "MS", "C", "WFC", "V", "MA", "AXP", "BRK-B",
        "XOM", "CVX", "COP", "SLB", "HAL", "MPC", "VLO", "PSX",
        "JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY", "AMGN", "GILD", "BIIB",
        "UNH", "CVS", "CI", "HUM", "MOH", "CNC",
        "HD", "LOW", "TGT", "WMT", "COST", "AMZN", "NKE", "MCD", "SBUX",
        "NEE", "DUK", "SO", "D", "AEP", "EXC",
        "SPY", "QQQ", "IWM",
    ]


# ---------------------------------------------------------------------------
# History download
# ---------------------------------------------------------------------------

def download_history(universe: list[str]) -> dict[str, pd.DataFrame]:
    """
    Download 1 year of daily OHLCV for all equity tickers.
    Done in chunks of 200 to respect yfinance rate limits.
    Returns {ticker: df}.
    """
    history  = {}
    chunk_sz = 200
    chunks   = [universe[i:i + chunk_sz] for i in range(0, len(universe), chunk_sz)]
    total    = len(chunks)

    log.info("Downloading equity history in %d chunks...", total)

    for i, chunk in enumerate(chunks):
        log.info("  chunk %d/%d (%d tickers)...", i + 1, total, len(chunk))
        try:
            raw = yf.download(
                " ".join(chunk),
                period="1y",
                interval="1d",
                progress=False,
                auto_adjust=True,
                group_by="ticker",
            )
            if raw.empty:
                continue

            # Handle both single-ticker (flat) and multi-ticker (MultiIndex) DataFrames
            for ticker in chunk:
                try:
                    if isinstance(raw.columns, pd.MultiIndex):
                        if ticker in raw.columns.get_level_values(0):
                            df = raw[ticker].dropna(subset=["Close"])
                        elif ticker in raw.columns.get_level_values(1):
                            cols = ["Open", "High", "Low", "Close", "Volume"]
                            df = pd.DataFrame(
                                {c: raw[(c, ticker)] for c in cols if (c, ticker) in raw.columns}
                            ).dropna(subset=["Close"])
                        else:
                            continue
                    else:
                        # Single ticker returned flat columns
                        df = raw.dropna(subset=["Close"])

                    if len(df) >= SMA_LONG + 10:
                        history[ticker] = df
                except Exception:
                    continue
        except Exception as e:
            log.warning("  chunk %d failed: %s", i + 1, e)
        time.sleep(0.8)

    log.info("Equity history ready: %d tickers", len(history))
    return history


def download_crypto_history() -> dict[str, pd.DataFrame]:
    """
    Download 1 year of daily OHLCV for all crypto tickers via yfinance.
    Crypto is not handled by Alpaca; prices come from yfinance close.
    """
    log.info("Downloading crypto history (%d tickers)...", len(CRYPTO_TICKERS))
    history = {}
    try:
        raw = yf.download(
            " ".join(CRYPTO_TICKERS),
            period="1y",
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
        if raw.empty:
            return {}

        for ticker in CRYPTO_TICKERS:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    if ticker in raw.columns.get_level_values(0):
                        df = raw[ticker].dropna(subset=["Close"])
                    else:
                        continue
                else:
                    df = raw.dropna(subset=["Close"])

                if len(df) >= SMA_LONG + 10:
                    history[ticker] = df
            except Exception:
                continue
    except Exception as e:
        log.warning("Crypto history download failed: %s", e)

    log.info("Crypto history ready: %d tickers", len(history))
    return history


# ---------------------------------------------------------------------------
# Cache (pickle)
# ---------------------------------------------------------------------------

def load_cache() -> tuple[dict, dict, datetime | None]:
    """
    Load history cache from disk.
    Returns (equity_history, crypto_history, cached_at) or empty dicts if stale/missing.
    """
    try:
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        cached_at = data.get("cached_at")
        if cached_at and (datetime.now() - cached_at).total_seconds() < CACHE_TTL_HOURS * 3600:
            log.info("Cache hit — loaded %d equity + %d crypto from %s",
                     len(data.get("equity", {})), len(data.get("crypto", {})),
                     cached_at.strftime("%H:%M"))
            return data["equity"], data["crypto"], cached_at
        log.info("Cache stale or expired — will re-download")
    except FileNotFoundError:
        log.info("No cache file found — fresh download")
    except Exception as e:
        log.warning("Cache load error: %s", e)
    return {}, {}, None


def save_cache(equity_history: dict, crypto_history: dict):
    """Persist downloaded history to disk."""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump({
                "equity":    equity_history,
                "crypto":    crypto_history,
                "cached_at": datetime.now(),
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        log.info("Cache saved (%d equity, %d crypto)", len(equity_history), len(crypto_history))
    except Exception as e:
        log.warning("Cache save failed: %s", e)


# ---------------------------------------------------------------------------
# Alpaca live prices
# ---------------------------------------------------------------------------

def alpaca_prices(tickers: list[str]) -> dict[str, float]:
    """
    Fetch latest trade prices for equity tickers from Alpaca.
    Returns {ticker: price}. Silently skips failures.
    """
    if not ALPACA_KEY or not tickers:
        return {}

    prices = {}
    chunk_sz = 200
    chunks   = [tickers[i:i + chunk_sz] for i in range(0, len(tickers), chunk_sz)]

    for chunk in chunks:
        try:
            params = {"symbols": ",".join(chunk), "feed": "iex"}
            resp = requests.get(
                ALPACA_BASE_URL,
                params=params,
                headers={
                    "APCA-API-KEY-ID":     ALPACA_KEY,
                    "APCA-API-SECRET-KEY": ALPACA_SECRET,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("quotes", {})
            for ticker, quote in data.items():
                ap = quote.get("ap", 0)   # ask price
                bp = quote.get("bp", 0)   # bid price
                if ap and bp:
                    prices[ticker.upper()] = (ap + bp) / 2
                elif ap:
                    prices[ticker.upper()] = ap
                elif bp:
                    prices[ticker.upper()] = bp
        except Exception as e:
            log.debug("Alpaca chunk error: %s", e)

    log.info("Alpaca: %d live prices fetched", len(prices))
    return prices


# ---------------------------------------------------------------------------
# Rescore & sort
# ---------------------------------------------------------------------------

def fast_rescore(
    equity_history: dict[str, pd.DataFrame],
    crypto_history: dict[str, pd.DataFrame],
    live_prices:    dict[str, float],
) -> list[dict]:
    """
    Rescore every asset using cached OHLCV + live Alpaca price.
    Returns list sorted by score descending.
    """
    results = []

    # Equity
    for ticker, df in equity_history.items():
        live_price = live_prices.get(ticker)
        result = score_swing(ticker, df, live_price=live_price, is_crypto=False)
        if result:
            results.append(result)

    # Crypto (no live price; use last close in df)
    for ticker, df in crypto_history.items():
        result = score_swing(ticker, df, live_price=None, is_crypto=True)
        if result:
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    log.info("Rescored %d assets — top score: %s",
             len(results), results[0]["score"] if results else "n/a")
    return results


# ---------------------------------------------------------------------------
# Firebase push
# ---------------------------------------------------------------------------

def push_results(results: list[dict]):
    """
    Push top-N and full list to Firebase Realtime Database.
    Paths: /swing_scanner/stocks (top 20), /swing_scanner/all_stocks (top 100).
    """
    now = datetime.now(timezone.utc).isoformat()

    top20  = results[:PUSH_TOP_N]
    top100 = results[:PUSH_ALL_N]

    # Convert to dict keyed by rank (Firebase doesn't support lists well)
    def to_fb_dict(lst):
        return {str(i + 1): item for i, item in enumerate(lst)}

    ref = db.reference(FIREBASE_PATH)
    ref.update({
        "stocks":     to_fb_dict(top20),
        "all_stocks": to_fb_dict(top100),
        "metadata": {
            "last_updated":    now,
            "total_scanned":   len(results),
            "top_score":       results[0]["score"] if results else 0,
            "breakout_count":  sum(1 for r in results if r["status"] == "BREAKOUT"),
            "watch_count":     sum(1 for r in results if r["status"] == "WATCH"),
        },
    })
    log.info("Firebase push complete — %d top, %d all, updated %s",
             len(top20), len(top100), now)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    log.info("=== Swing Scanner starting [%s] — Firebase path: %s ===", ENVIRONMENT.upper(), FIREBASE_PATH)
    init_firebase()

    equity_history = {}
    crypto_history = {}
    last_download  = None

    while True:
        try:
            # ---- Re-download history every 24 h ----
            now = datetime.now()
            needs_download = (
                not equity_history
                or last_download is None
                or (now - last_download).total_seconds() >= CACHE_TTL_HOURS * 3600
            )

            if needs_download:
                # Try loading from cache first
                eq, cr, cached_at = load_cache()
                if eq:
                    equity_history = eq
                    crypto_history = cr
                    last_download  = cached_at
                    log.info("Loaded from disk cache")
                else:
                    log.info("Fetching universe from SEC EDGAR...")
                    universe = get_universe()

                    log.info("Downloading equity history for %d tickers...", len(universe))
                    equity_history = download_history(universe)

                    log.info("Downloading crypto history...")
                    crypto_history = download_crypto_history()

                    save_cache(equity_history, crypto_history)
                    last_download = datetime.now()

            # ---- Fetch live Alpaca prices ----
            equity_tickers = list(equity_history.keys())
            live_prices    = alpaca_prices(equity_tickers)

            # ---- Rescore everything ----
            results = fast_rescore(equity_history, crypto_history, live_prices)

            # ---- Push to Firebase ----
            if results:
                push_results(results)
            else:
                log.warning("No results to push (all assets filtered out)")

        except Exception as e:
            log.error("Main loop error: %s", e, exc_info=True)

        log.info("Sleeping %ds...", SCAN_INTERVAL_S)
        time.sleep(SCAN_INTERVAL_S)


if __name__ == "__main__":
    main()
