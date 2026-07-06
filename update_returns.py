"""
Nightly forward-returns updater for the swing picks history.

Walks /swing_scanner/history, and for every pick missing a matured return
window (1w=5, 2w=10, 1m=21 trading days), fetches daily closes and fills it
in. Run from cron on the VM after the close:

    30 22 * * 1-5 cd /home/scanner && venv/bin/python update_returns.py >> /var/log/swing_returns.log 2>&1

Reuses scanner.py's env loading + Firebase app (import side effect).
"""
from __future__ import annotations
import sys, time, logging
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scanner                     # loads .env, inits Firebase
from scanner import ref, log

import pandas as pd
import yfinance as yf

WINDOWS = {"1w": 5, "2w": 10, "1m": 21}


def main():
    hist = ref.child("history").get() or {}
    if not hist:
        log.info("update_returns: no history yet")
        return

    # Collect picks that still miss at least one window
    todo: dict[str, list[tuple[str, dict]]] = {}   # ticker -> [(day, pick)]
    for day, picks in hist.items():
        if not isinstance(picks, dict):
            continue
        for tk, p in picks.items():
            if not isinstance(p, dict):
                continue
            missing = [w for w in WINDOWS if w not in (p.get("returns") or {})]
            if missing:
                todo.setdefault(tk, []).append((day, p))
    if not todo:
        log.info("update_returns: all picks up to date")
        return

    tickers = sorted(todo)
    log.info(f"update_returns: {sum(len(v) for v in todo.values())} picks "
             f"across {len(tickers)} tickers")

    # One batched download covers every pick (oldest pick sets the span)
    oldest = min(day for v in todo.values() for day, _ in v)
    data = yf.download(tickers, start=oldest, interval="1d", progress=False,
                       auto_adjust=True, group_by="ticker", threads=True)

    updated = 0
    for tk, picks in todo.items():
        try:
            closes = (data[tk]["Close"] if isinstance(data.columns, pd.MultiIndex)
                      else data["Close"]).dropna()
        except Exception:
            continue
        if closes.empty:
            continue
        dates = [d.date() for d in closes.index]
        for day, p in picks:
            d0 = date.fromisoformat(day)
            # index of the pick day (or next trading day)
            idx = next((i for i, d in enumerate(dates) if d >= d0), None)
            if idx is None:
                continue
            entry = p.get("price") or float(closes.iloc[idx])
            rets = dict(p.get("returns") or {})
            changed = False
            for w, nd in WINDOWS.items():
                if w in rets or idx + nd >= len(closes):
                    continue
                px = float(closes.iloc[idx + nd])
                rets[w] = round((px - entry) / entry * 100, 2)
                changed = True
            if changed:
                try:
                    ref.child("history").child(day).child(tk).child("returns").set(rets)
                    updated += 1
                except Exception as e:
                    log.warning(f"write {day}/{tk}: {e}")
        time.sleep(0.1)

    log.info(f"update_returns: updated {updated} picks")


if __name__ == "__main__":
    main()
