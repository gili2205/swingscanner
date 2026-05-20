# Swing Scanner — Project Context

## What We're Building
A new standalone swing trading scanner app, separate from an existing breakout scanner (`stockscanner`). The goal is to scan NYSE + NASDAQ + Top 20 crypto for swing trading setups using volume, Bollinger Band squeezes, EMA alignment, and RSI.

## Tech Stack (same as existing project)
- **Backend**: Python / Flask
- **Database**: Firebase Realtime Database (firebase-admin server-side, JS SDK client-side)
- **Data**: yfinance for historical OHLCV, Alpaca REST API for live equity prices
- **Frontend**: Single-page app, all HTML/CSS/JS inline in app.py (no React/Vue)
- **Hosting**: Vercel (app.py), Google Cloud VM (scanner.py runs as systemd service)
- **Theme**: Dark (#0d0d0d bg, #1a1a1a cards, green/amber/red accents)

## Repository
- New separate repo (not part of existing stockscanner repo)
- Directory: `/Users/Gili/swingscanner/`
- Firebase path: `/swing_scanner` (the existing scanner uses `/scanner`)

## Universe
- **Equities**: NYSE + NASDAQ (fetched from SEC EDGAR)
- **Crypto**: Top 20 by market cap via yfinance (-USD pairs):
  BTC-USD, ETH-USD, BNB-USD, SOL-USD, XRP-USD, DOGE-USD, ADA-USD, TRX-USD,
  AVAX-USD, SHIB-USD, TON-USD, DOT-USD, MATIC-USD, LINK-USD, LTC-USD,
  BCH-USD, UNI-USD, ATOM-USD, XLM-USD, ICP-USD

## Quality Gates (before scoring)
| Gate | Equities | Crypto |
|------|----------|--------|
| Min price | $5 | exempt |
| Max price | $150 | exempt |
| Min avg daily volume | 500,000 shares/day | exempt |
| Min RVOL to appear | 1.5x | 1.5x |
| Macro gate | price > SMA200 × 0.80 | exempt |

## Scoring Algorithm (0–100)

### Indicators
1. **RVOL** = today's volume / 20-day avg volume (exclude today from avg)
2. **Bollinger Bands (20, 2)**: upper, lower, SMA, width = (upper−lower)/SMA
3. **BB squeeze %**: percentile of current BB width vs last 252 trading days (lower % = tighter = better)
4. **BB %B**: (price − lower) / (upper − lower)
5. **EMA9, EMA20** (exponential), **SMA50, SMA200** (simple)
6. **EMA9 distance**: (price − EMA9) / EMA9 × 100 (overextension %)
7. **RSI(14)**

### Points Breakdown

**Volume — 30 pts (most important)**
- RVOL ≥ 5.0 → 30
- RVOL ≥ 3.0 → 22
- RVOL ≥ 2.0 → 15
- RVOL ≥ 1.5 → 8

**BB Squeeze Quality — 20 pts**
- Width percentile ≤ 10% → 20 (maximum squeeze)
- Width percentile ≤ 20% → 15
- Width percentile ≤ 35% → 10
- Width percentile ≤ 50% → 5

**BB Breakout — 15 pts**
- Price closed above upper BB → 15
- BB %B ≥ 90% → 8 (approaching breakout)
- BB %B ≥ 75% → 3

**EMA Alignment — 15 pts**
- EMA9 > EMA20 AND price > SMA50 AND price > SMA200 → 15 (full bull stack)
- EMA9 > EMA20 AND price > SMA50 → 10
- EMA9 > EMA20 → 6
- price > SMA50 AND price > SMA200 → 4

**RSI — 10 pts** *(high RSI = bullish for breakouts, NOT a sell signal)*
- RSI ≥ 70 → 10
- RSI ≥ 60 → 8
- RSI ≥ 50 → 5

**EMA9 Proximity — 10 pts** *(not overextended)*
- Within 3% above EMA9 → 10
- 3–7% above → 6
- 7–12% above → 2
- > 12% → 0

### Penalties
- EMA9 distance > 20% → −15 (way overextended)
- RSI < 45 → −10 (weak momentum)
- Price < SMA200 → −15 (against macro trend)
- Price above upper BB but RVOL < 2.0 → −10 (likely fake breakout)

### Status Labels
- **BREAKOUT**: RVOL ≥ 2.0 AND above upper BB AND score ≥ 65
- **WATCH**: score ≥ 45 (squeeze forming, approaching breakout)
- **BUILDING**: score < 45 (early setup)

## File Structure
```
swingscanner/
├── scanner.py      # Live scanner — runs on VM as systemd service
├── app.py          # Flask app — deployed to Vercel
└── requirements.txt
```

## scanner.py — Key Functions
- `compute_ema(series, period)` — proper EMA calculation
- `compute_rsi(closes, period=14)`
- `score_swing(ticker, df, live_price=None, is_crypto=False)` → dict or None
- `get_universe()` — equity universe via SEC EDGAR (NASDAQ + NYSE)
- `download_history(universe)` — yf.download chunks of 200, period="1y" (need 1yr for BB squeeze percentile)
- `load_cache()` / `save_cache(history)` — pickle at `/home/scanner/swing_cache.pkl`
- `alpaca_prices(tickers)` — Alpaca REST for live equity prices (crypto uses yfinance closes)
- `fast_rescore(history, live_prices)` — rescore all tickers, sort by score desc
- `push_results(results)` — top 20 → `/swing_scanner/stocks`, top 100 → `/swing_scanner/all_stocks`
- Main loop: rescore every 60s, re-download history every 24h

## app.py — UI Spec
Single-page dark dashboard. All HTML/CSS/JS inline (no build step). Firebase JS SDK via CDN.

### Layout
- Header: "SWING SCANNER" + last updated + stocks scanned count
- Filter bar: **[All] [Equities] [Crypto]** + **[BREAKOUT] [WATCH] [BUILDING]** status buttons
- Ranked cards grid

### Card Design
Each card shows:
- Rank + ticker name + "CRYPTO" badge (orange) if crypto
- Price + day change %
- Sector (equities) or asset class
- Score (large number, right side): BREAKOUT=green, WATCH=amber, BUILDING=gray
- Metrics row: `RVOL 3.2x` · `BB Squeeze 8%` · `RSI 68` · `EMA9 +2.1%`
- Status badge: ⚡ BREAKOUT (green) / 🔄 SQUEEZE (amber) / 📊 BUILDING (gray)

### Expanded Detail (click card)
- BB width history bar (current vs 52-week range)
- EMA stack table: show EMA9/EMA20/SMA50/SMA200 values + above/below indicator
- Volume comparison: today vs 20-day avg
- RSI value with color coding

### Firebase
- Listen to `/swing_scanner/stocks` for live top 20
- Listen to `/swing_scanner/all_stocks` for filters
- Firebase config injected from Flask env vars

### Flask Routes
- `GET /` — main dashboard
- `GET /api/detail/<ticker>` — fresh yfinance data for expanded card

## Environment Variables (same pattern as existing project)
```
FIREBASE_CRED=/home/scanner/firebase_credentials.json
FIREBASE_URL=https://your-project-default-rtdb.firebaseio.com
ALPACA_KEY=your_key
ALPACA_SECRET=your_secret
FIREBASE_API_KEY=...       (for JS SDK)
FIREBASE_AUTH_DOMAIN=...
FIREBASE_DB_URL=...
FIREBASE_PROJECT_ID=...
FIREBASE_APP_ID=...
```

## Coding Conventions (from existing project)
- Use `{{` and `}}` for literal JS braces inside Python format strings
- Firebase JS SDK: use compat version from CDN
- No React/Vue — plain vanilla JS
- CSS variables for theming: `--green`, `--amber`, `--red`, `--muted`, `--bg`, `--card`
- Cards use CSS class `.card` with click handlers
- All API responses: `jsonify({...})`

## What to Build First
1. `scanner.py` — complete working scanner with swing scoring
2. `app.py` — complete Flask app with card UI
3. `requirements.txt`

Do NOT create README or markdown docs unless asked.
