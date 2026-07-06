"""
One-time seed: import the 180-day backtest signals into /swing_scanner/history
so the Analytics tab has a scoreboard from day one.

Every seeded pick carries source: "backtest" — the Analytics tab shows them
separately from live picks, so simulated results never pass as real ones.

Run on the VM (has Firebase creds):
    cd /home/scanner && venv/bin/python seed_backtest_history.py
"""
from __future__ import annotations
import sys, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scanner                       # loads .env, inits Firebase
from scanner import ref, log

import pandas as pd

CSV = Path(__file__).parent / "backtest_picks_tuned.csv"


def clean(v):
    return None if (v is None or (isinstance(v, float) and math.isnan(v))) else v


def main():
    df = pd.read_csv(CSV)
    log.info(f"Seeding {len(df)} backtest signals from {CSV.name}")
    by_day: dict[str, dict] = {}
    for _, r in df.iterrows():
        rets = {}
        for w in ("1w", "2w", "1m"):
            v = clean(r.get(f"ret_{w}"))
            if v is not None:
                rets[w] = round(float(v), 2)
        by_day.setdefault(str(r["date"]), {})[str(r["ticker"])] = {
            "price":      round(float(r["price"]), 2),
            "score":      int(r["score"]),
            "status":     str(r["status"]),
            "squeeze":    clean(r.get("squeeze")),
            "dryup":      clean(r.get("dryup")),
            "dist_pivot": clean(r.get("dist_pivot")),
            "source":     "backtest",
            "returns":    rets,
        }
    for i, (day, picks) in enumerate(sorted(by_day.items())):
        ref.child("history").child(day).update(picks)
        if (i + 1) % 20 == 0:
            log.info(f"  {i+1}/{len(by_day)} days seeded")
    log.info(f"Done: {len(by_day)} days, {len(df)} signals seeded")


if __name__ == "__main__":
    main()
