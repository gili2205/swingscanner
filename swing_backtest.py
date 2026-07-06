"""
Swing Backtest — replay the LIVE scoring on historical data.

Imports score_swing() from scanner.py (same code path as production) and
evaluates it on point-in-time slices: for each simulated day D, a ticker is
scored using only data up to D. New PRIMED/BREAKOUT signals (not signaled the
prior day) are recorded, and forward returns at +5/+10/+21 trading days are
computed from the same dataset. SPY over the same windows is the benchmark.

Run locally (needs RAM, not the VM):
    python3 swing_backtest.py --days 180
    python3 swing_backtest.py --days 60 --sample 500     # quick validation
Caveat: universe is today's listings — delisted names are absent
(survivorship bias inflates results slightly; fine for relative judgment).
"""
from __future__ import annotations
import os, sys, time, types, pickle, argparse, logging, warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

# ── Mock firebase + env so scanner.py imports without a live backend ──────────
os.environ.setdefault("FIREBASE_URL", "mock")
os.environ.setdefault("FIREBASE_CRED", "mock")
os.environ.setdefault("ALPACA_KEY", "mock")
os.environ.setdefault("ALPACA_SECRET", "mock")

_fb = types.ModuleType("firebase_admin")
_fb.initialize_app = lambda *a, **k: None
_creds = types.ModuleType("firebase_admin.credentials")
_creds.Certificate = lambda *a, **k: None
_dbm = types.ModuleType("firebase_admin.db")
class _Ref:
    def child(self, *a, **k): return self
    def get(self): return {}
    def set(self, *a, **k): pass
    def update(self, *a, **k): pass
_dbm.reference = lambda *a, **k: _Ref()
_fb.credentials, _fb.db = _creds, _dbm
sys.modules.update({"firebase_admin": _fb,
                    "firebase_admin.credentials": _creds,
                    "firebase_admin.db": _dbm})

import pandas as pd
import numpy as np
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
import scanner  # live scoring — score_swing, get_universe, gates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("swing_backtest")

CACHE_FILE = Path(__file__).parent / ".bt_cache.pkl"
SIGNAL_STATUSES = ("PRIMED", "BREAKOUT")
RETURN_WINDOWS = {"1w": 5, "2w": 10, "1m": 21}

# ── Data ───────────────────────────────────────────────────────────────────────
def download_universe(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Chunked yfinance download with an on-disk cache keyed by date+size."""
    cache_key = f"{len(tickers)}_{date.today()}"
    if CACHE_FILE.exists():
        try:
            cached = pickle.loads(CACHE_FILE.read_bytes())
            if cached.get("key") == cache_key:
                log.info(f"Cache hit: {len(cached['data'])} tickers")
                return cached["data"]
        except Exception:
            pass

    history: dict[str, pd.DataFrame] = {}
    chunks = [tickers[i:i+100] for i in range(0, len(tickers), 100)]
    for i, chunk in enumerate(chunks):
        try:
            d = yf.download(chunk, period=period, interval="1d",
                            progress=False, auto_adjust=True, group_by="ticker",
                            threads=True)
            for t in chunk:
                try:
                    df = (d[t] if isinstance(d.columns, pd.MultiIndex) else d)
                    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                    if len(df) >= 260:          # need ≥1y before first sim day
                        history[t] = df
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"chunk {i+1}: {e}")
            time.sleep(2)
        if (i + 1) % 10 == 0 or (i + 1) == len(chunks):
            log.info(f"  download {i+1}/{len(chunks)} chunks | {len(history)} usable")
    CACHE_FILE.write_bytes(pickle.dumps({"key": cache_key, "data": history}))
    return history

def prefilter(history: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Drop tickers that could never pass the live gates (speed only —
    the real gates still run inside score_swing on each slice)."""
    keep = {}
    for t, df in history.items():
        px = df["Close"]
        if px.max() < scanner.MIN_PRICE:                    # never above $3
            continue
        dollar = (df["Close"] * df["Volume"]).rolling(20).mean().max()
        if pd.isna(dollar) or dollar < scanner.MIN_DOLLAR_VOL:
            continue
        keep[t] = df
    log.info(f"Prefilter: {len(history)} → {len(keep)} tickers")
    return keep

# ── Simulation ────────────────────────────────────────────────────────────────
def simulate(history: dict[str, pd.DataFrame], n_days: int) -> pd.DataFrame:
    """Walk each ticker forward; score point-in-time slices with the LIVE code."""
    picks = []
    t0 = time.time()
    tickers = list(history.keys())
    for n, tk in enumerate(tickers):
        df = history[tk]
        total = len(df)
        start = max(260, total - n_days)          # leave ≥260 bars of history
        prev_signal = False
        for i in range(start, total):
            res = scanner.score_swing(tk, df.iloc[:i], live_price=None,
                                      is_crypto=False)
            signal = bool(res) and res["status"] in SIGNAL_STATUSES
            if signal and not prev_signal:        # NEW signal only (dedupe)
                row = {"ticker": tk, "date": df.index[i-1].date(),
                       "bar_idx": i - 1, "price": res["price"],
                       "status": res["status"], "score": res["score"],
                       "squeeze": res["bb_squeeze_pct"],
                       "dryup": res["dryup_ratio"],
                       "dist_pivot": res["dist_to_pivot"]}
                # forward returns + max-favorable/adverse within 1m
                closes = df["Close"]
                entry = float(closes.iloc[i-1])
                for w, nd in RETURN_WINDOWS.items():
                    j = i - 1 + nd
                    row[f"ret_{w}"] = round((float(closes.iloc[j]) - entry)
                                            / entry * 100, 2) if j < total else None
                horizon = closes.iloc[i-1: i-1 + 22]
                if len(horizon) > 1:
                    row["max_gain_1m"] = round((horizon.max() - entry) / entry * 100, 2)
                    row["max_dd_1m"]   = round((horizon.min() - entry) / entry * 100, 2)
                picks.append(row)
            prev_signal = signal
        if (n + 1) % 250 == 0:
            el = time.time() - t0
            log.info(f"  scored {n+1}/{len(tickers)} tickers | {len(picks)} signals "
                     f"| {el:.0f}s (~{el/(n+1)*(len(tickers)-n-1):.0f}s left)")
    log.info(f"Simulation done: {len(picks)} signals in {time.time()-t0:.0f}s")
    return pd.DataFrame(picks)

def spy_benchmark(n_days: int) -> dict[str, float]:
    spy = yf.download("SPY", period="2y", interval="1d", progress=False,
                      auto_adjust=True)["Close"].squeeze().dropna()
    out = {}
    win = spy.iloc[-n_days:]
    for w, nd in RETURN_WINDOWS.items():
        rets = (win.shift(-nd) / win - 1).dropna() * 100
        out[w] = round(float(rets.mean()), 2)
    return out

# ── Report ────────────────────────────────────────────────────────────────────
def report(picks: pd.DataFrame, spy: dict[str, float], n_days: int):
    if picks.empty:
        print("\nNo signals generated — nothing to report.")
        return
    print(f"\n{'='*74}\nSWING BACKTEST — last {n_days} trading days "
          f"| {len(picks)} new signals | {picks['ticker'].nunique()} tickers"
          f"\n{'='*74}")
    for status in ["PRIMED", "BREAKOUT"]:
        sub = picks[picks["status"] == status]
        if sub.empty:
            continue
        print(f"\n── {status} ({len(sub)} signals, ~{len(sub)/n_days:.1f}/day) "
              f"────────────────────────────")
        print(f"{'win':>10} {'winrate':>8} {'avg':>7} {'median':>7} {'SPY':>6} {'edge':>6}")
        for w in RETURN_WINDOWS:
            r = sub[f"ret_{w}"].dropna()
            if len(r) < 5:
                print(f"{w:>10}  (only {len(r)} matured)")
                continue
            wr = (r > 0).mean() * 100
            edge = r.mean() - spy[w]
            print(f"{w:>10} {wr:7.1f}% {r.mean():6.2f}% {r.median():6.2f}% "
                  f"{spy[w]:5.2f}% {edge:+5.2f}%")
        mg, dd = sub["max_gain_1m"].dropna(), sub["max_dd_1m"].dropna()
        if len(mg):
            print(f"   within 1m: avg max gain {mg.mean():+.2f}% | "
                  f"avg max drawdown {dd.mean():+.2f}%")
    print(f"\nSPY baseline (avg fwd return): "
          + " | ".join(f"{w}: {v:+.2f}%" for w, v in spy.items()))
    out = Path(__file__).parent / "backtest_picks.csv"
    picks.to_csv(out, index=False)
    print(f"Full pick list → {out}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--sample", type=int, default=0,
                    help="limit universe to N tickers (0 = full)")
    args = ap.parse_args()

    universe = scanner.get_universe()
    if args.sample:
        universe = universe[:args.sample]
    log.info(f"Universe: {len(universe)} tickers | {args.days} sim days")

    history = prefilter(download_universe(universe))
    picks = simulate(history, args.days)
    spy = spy_benchmark(args.days)
    report(picks, spy, args.days)

if __name__ == "__main__":
    main()
