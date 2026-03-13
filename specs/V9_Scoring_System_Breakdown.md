# V9 Scoring System — Complete Breakdown

## The Pipeline: How a Stock Goes from Raw Data to Trade Signal

```
TradeStation API
    │
    ├─ Quotes (462/477 tickers every 5 min — price, volume, bid/ask)
    │     └─ Zero extra cost — batched in groups of 50
    │
    └─ Bars (5-min candles, barsback=30 — OHLCV per bar)
          └─ Tiered: T1 every 5min, T2 every 15min, T3 every 30min
          └─ THIS is what costs fetches
    │
    ▼
calcConfluence() — per ticker, runs on every ticker that got bars
    │
    ├─ CONFLUENCE SCORE (0-38) — "how tradeable is this ticker right now?"
    │     Long confluence + Short confluence computed separately
    │
    ├─ SETUP SCORES (0-25 each) — "which specific pattern does this match?"
    │     13 long setups + 10 short setups scored independently
    │
    └─ BEST PICK — highest scoring setup wins, determines Side (LONG/SHORT)
    │
    ▼
Watchlist Sheet — one row per ticker with 51 columns
    │
    ▼
getDashboardData() — reads sheet, serves JSON to dashboard
    │
    ▼
Dashboard — renders cards, modals, grids
```

---

## LAYER 1: CONFLUENCE SCORE (0-38)

Confluence answers: "Is this a good environment for THIS stock right now?" It's direction-aware — long and short confluence are computed separately.

### Core Components (0-5 each, total 0-30)

**1. Market Context (0-5)** — same for all tickers, same for long/short
| Breadth Score | Market Ctx |
|---|---|
| ≥ 9.5 (GP-A) | 5 |
| ≥ 6 | 4 |
| ≥ 3 (GP-B) | 3 |
| ≥ 0 | 2.5 |
| ≥ -3 (GP-C) | 2 |
| < -3 (GP-D) | 1 |

**2. Price Structure (0-5)** — DIFFERENT for long vs short

LONG Price Structure:
- Last > VWAP: +1.5
- Last > EMA9: +1
- Last > EMA20: +1
- EMA9 > EMA20 (bullish stack): +0.5
- Last > OR High: +1 (or > OR Low: +0.5)
- Cap: 5

SHORT Price Structure (mirror):
- Last < VWAP: +1.5
- Last < EMA9: +1
- Last < EMA20: +1
- EMA9 < EMA20 (bearish stack): +0.5
- Last < OR Low: +1 (or < OR High: +0.5)
- Cap: 5

**3. Momentum (0-5)** — DIFFERENT for long vs short

LONG Momentum:
- RSI 40-60 (ideal zone): +3
- RSI 55-75: +2.5
- RSI 30-40: +1.5
- RSI > 75: +0.5
- RSI < 30: +1
- Bullish EMA cascade (last > EMA9 > EMA20): +2
- Just last > EMA9: +1
- Cap: 5

SHORT Momentum:
- RSI 40-60: +3
- RSI 25-45: +2.5
- RSI 60-70: +1.5
- RSI < 25: +0.5
- RSI > 70: +1
- Bearish cascade (last < EMA9 < EMA20): +2
- Just last < EMA9: +1
- Cap: 5

**4. Volume (0-5)** — same for long/short
| RVOL | Score |
|---|---|
| ≥ 3.0 | 5 |
| ≥ 2.0 | 4 |
| ≥ 1.5 | 3 |
| ≥ 1.0 | 2 |
| ≥ 0.75 | 1 |

**5. Key Level Proximity (0-5)** — same for long/short
- Within 0.3% of VWAP: +2.5 (0.5%: +1.5, 1%: +0.5)
- Within 0.3% of OR High: +2.5 (0.5%: +1.5)
- Cap: 5

**6. Execution Quality (0-5)** — same for long/short
- Spread < 0.03%: +2.5 (< 0.05%: +2, < 0.1%: +1)
- Volume > 5M: +1.5 (> 1M: +1, > 500K: +0.5)
- Power hours (9:30-11 ET or 3-4 ET): +1
- Cap: 5

### Modifiers (±2 each, total ±8)

**ATR Multiple** — same for long/short
| Day Range / ATR | Mod |
|---|---|
| ≤ 0.5 (room to run) | +2 |
| ≤ 1.0 | +1 |
| ≤ 1.5 | 0 |
| ≤ 2.5 | -1 |
| > 2.5 (exhausted) | -2 |

**Gap Analysis** — DIFFERENT for long vs short

LONG: Small gap up is good, big gap is risky
- < 0.5% gap, price > open: +2
- < 1%: +1
- < 2%: 0
- < 3%: -1
- ≥ 3%: -2

SHORT: Gap down with follow-through is good
- < 0.5% gap, price < open: +2
- < 1%: +1
- < 2%: 0
- Gap ≤ -3% (big gap down): +2
- < 3%: -1
- else: -2

**Relative Strength** — DIFFERENT for long vs short

LONG: Strong RS is good
- RS ≥ 3: +2
- RS ≥ 1.5: +1
- RS ≥ -1.5: 0
- RS ≥ -3: -1
- RS < -3: -2

SHORT: Weak RS is good (inverted)
- RS ≤ -3: +2
- RS ≤ -1.5: +1
- RS ≤ 1.5: 0
- RS ≤ 3: -1
- RS > 3: -2

**News/Catalyst Modifier** — same for long/short
- Has news + RVOL ≥ 2.0: +2
- Has news + RVOL ≥ 1.0: +1
- Has news + no vol reaction: 0
- No news: 0

### Final Confluence
```
Long Confluence  = Core(Mkt + PriceStr + Mom + Vol + Level + Exec) + Mods(ATR + Gap + RS + News)
Short Confluence = Core(Mkt + PriceStrShort + MomShort + Vol + Level + Exec) + Mods(ATR + GapShort + RSShort + News)
Best Confluence  = max(Long, Short)   ← this is what shows in the Watchlist
```

Capped at 0-38.

### Quality Tiers (from Best Confluence)
| Score | Quality | Meaning |
|---|---|---|
| ≥ 28 | A+ | Exceptional — everything aligned |
| ≥ 24 | Solid | Strong — minor issues at most |
| ≥ 20 | Playbook | Tradeable — standard V9 setup |
| ≥ 16 | Watch | Developing — monitor for improvement |
| < 16 | Skip | Insufficient confluence |

---

## LAYER 2: SETUP SCORES (0-25 each)

Setup scoring answers: "Does this ticker match a specific trade pattern, and how strongly?"

### The _setupScore Formula
```
If pattern doesn't match → 0 (immediate reject)
If RVOL < minimum required → 0 (immediate reject)
If confluence < minimum required → 0 (immediate reject)

Base: 10 points (you matched the pattern)
+ RVOL bonus: 0-5 (how much above minimum RVOL)
+ Confluence bonus: 0-5 (how much above minimum confluence)
+ Signal bonus: 0-10 (setup-specific extras like tight VWAP, strong RS, etc.)

Max: 25 (theoretical), typical good score: 14-20
```

### LONG SETUPS (13 total)

| Setup | Pattern Match Requires | Min RVOL | Min Conf | Signal Bonus |
|---|---|---|---|---|
| VWAP-Hold | Above VWAP, within 0.5%, bull EMA stack, RSI 40-60 | 1.0 | 18 | Tighter VWAP distance, RSI sweet spot |
| OR-Break | Broke above OR High, above VWAP, RSI < 75 | 1.5 | 20 | High RVOL, RSI 50-65 |
| Pullback-EMA | Near EMA20, bull EMA stack, RSI 35-55 | 1.0 | 16 | Near EMA9 too, RSI 40-50 |
| Momentum | Above VWAP + EMA9, bull stack, RSI 55-75, RS ≥ 1 | 1.5 | 22 | Stronger RS, higher RVOL |
| Failed-BD | Above VWAP, was below OR Low (false breakdown) | 1.0 | 18 | Near VWAP, high RVOL, bull stack |
| ReturnPullback | VWAP reclaim, within 0.5% of VWAP | 1.0 | 16 | Tighter VWAP, bull stack |
| BigDog | Above VWAP, consolidating ≥ 45 min | 3.0 | 20 | Longer consolidation, RVOL ≥ 4 |
| BigDogBounce | Below VWAP, consolidating ≥ 6 bars | 2.0 | 16 | More bars, RVOL ≥ 3 |
| GapGo | Gap ≥ 3%, above VWAP, gap is positive | 2.0 | 18 | Bigger gap, RVOL ≥ 3 |
| OpeningDrive | First 2 bars, gap ≥ 3% | 2.0 | 16 | Bigger gap, RVOL ≥ 4 |
| DailyBreakout | Near 52-week high, above VWAP | 3.0 | 22 | RVOL ≥ 4, pct52 ≥ 95% |
| SecondDay | Gap ≥ 2%, 3+ bars in, within 1.5% of VWAP | 1.5 | 20 | Bigger gap, near VWAP |
| Scalping | RVOL ≥ 1.5, spread < 0.1% | 1.5 | 16 | Tighter spread, RVOL ≥ 2.5 |

### SHORT SETUPS (10 total)

| Setup | Pattern Match Requires | Min RVOL | Min Conf | Signal Bonus |
|---|---|---|---|---|
| VWAP-Hold | Below VWAP, within 0.8% | 1.0 | 16 | Tighter distance, bear stack, RSI 40-55 |
| OR-Break | Broke below OR Low, below VWAP | 1.5 | 18 | High RVOL, RSI 30-55 |
| Pullback-EMA | Below VWAP, near EMA9/20, bear stack | 1.0 | 16 | Near EMA9, RSI 45-65 |
| Momentum | Below VWAP, below EMA9, RS ≤ -0.5 | 1.5 | 20 | Bear stack, weaker RS, high RVOL |
| Failed-BD | Below VWAP, was above OR High (failed breakout) | 1.0 | 16 | Near VWAP, high RVOL, bear stack |
| ReturnPullback | VWAP reject (touched from below, fell), within 0.8% | 1.0 | 16 | Tighter distance, bear stack |
| BigDog | Below VWAP, consolidating ≥ 45 min | 3.0 | 20 | Longer consolidation, RVOL ≥ 4 |
| GapGo | Gap ≤ -3%, below VWAP | 2.0 | 18 | Bigger gap, RVOL ≥ 3 |
| DailyBreakout | Near 52-week low, below VWAP | 3.0 | 22 | RVOL ≥ 4, pct52 ≤ 5% |
| Scalping | RVOL ≥ 1.5 (only fires when short conf > long conf) | 1.5 | 16 | Tighter spread, RVOL ≥ 2.5 |

### What's NOT Currently Factored Into Setup Scores

These are available in the data but NOT boosting/penalizing setup scores yet:

- **Hot Sector** — sector ETF moving ≥ 1.5% with RVOL ≥ 1.5. Currently only affects WHICH tickers get scanned (tiered refresh boost), not their scores.
- **News/Catalyst** — currently only affects confluence via newsMod (±2). Does NOT directly boost setup scores.
- **Earnings** — displayed in Watchlist, used for row coloring and dynamic watchlist. Zero influence on confluence or setup scores.

**Proposed additions for `_SetupScores` sheet:**
- Hot sector: +2 bonus per matching setup
- News catalyst: +2 if news + RVOL ≥ 2, +1 if news + RVOL ≥ 1
- Earnings today: +2 (high-vol catalyst), tomorrow: +1

---

## LAYER 3: DIRECTION PICK (LONG vs SHORT)

After scoring all 13 long and 10 short setups:

1. Rank long setups by score, pick best
2. Rank short setups by score, pick best
3. Compare:
   - If best short score > best long score → SHORT
   - If scores within 2 points AND short confluence leads by 3+ → SHORT (tiebreaker)
   - Otherwise → LONG
4. Write winning setup name + side to Watchlist

---

## LAYER 4: GAMEPLAN FILTER

The setup might score well, but is it ALLOWED given current market conditions?

### SETUP_REGISTRY — which setups are valid in which GP

| Setup | Valid GP | Side | Min RVOL | Nature |
|---|---|---|---|---|
| VWAP-Hold | A, B, C-Recovery | LONG | 1.0 | structure |
| OR-Break | A, B | LONG | 1.5 | breakout |
| Pullback-EMA | A, B, C-Recovery | LONG | 1.0 | structure |
| Momentum | A, B | LONG | 2.0 | momentum |
| Failed-BD | A, B, C-Recovery | LONG | 1.0 | structure |
| RS-Override | A, B, C-Recovery, C, D | LONG | 2.0 | any |
| Rotation-ETF | A, B, C-Recovery, D | ANY | 0 | any |
| BigDog | A, B | LONG | 3.0 | momentum |
| BigDogBounce | A, B, C-Recovery | LONG | 2.0 | structure |
| GapGo | A, B | LONG | 2.0 | momentum |
| DailyBreakout | A, B | LONG | 3.0 | breakout |
| OpeningDrive | A, B | ANY | 1.5 | momentum |
| MarketPlay | A, B, C-Recovery, D | ANY | 1.5 | any |
| SecondDay | A, B | LONG | 1.5 | momentum |
| ReturnPullback | A, B, C-Recovery | LONG | 1.0 | structure |
| Scalping | A, B, D | ANY | 1.0 | any |

### GP Sizing (% of live equity)

| GP | Position Size | Risk Per Trade |
|---|---|---|
| A (Hunt) | 20-25% | 0.75-1.0% |
| B (Sniper) | 12-18% | 0.50-0.75% |
| C (Bench) | 0% (blocked) | 0% |
| D (Inverse) | 12-18% | 0.50-0.75% |

Sub-modes override: C-Recovery allows 4-7% positions on Tier 1-3 structure setups.

---

## LAYER 5: TRADE CARD SCORECARD (Dashboard)

When you click a ticker, the modal runs quickGrade() — an 8-check pass/fail:

1. **GP × Setup** — is this setup allowed in current GP + sub-mode?
2. **RVOL** — meets minimum for this setup?
3. **VWAP** — correct side (above for long, below for short)?
4. **Confluence** — ≥ 24 green, ≥ 20 yellow, else red
5. **Session** — are we in a valid session for this setup?
6. **VIX** — < 18 green, < 25 yellow, else red
7. **RSI** — in the right zone for direction?
8. **Sector** — how many open positions in same sector?

Grade: A (7+ green, 0 red) → B (6+ green, 0 red) → C (5+ green, ≤ 1 red) → F

---

## THE SELECTION PATH: What to Watch, What to Know

### How Tickers Surface

1. **Config tab** — your manually curated watchlist (~400 tickers in sections)
2. **My Positions** — auto-added from TradeStation API
3. **Dynamic tab** — auto-added from gap scans, earnings, RVOL alerts, Arete (75 max)
4. **Total universe**: ~477 tickers

### How They Get Prioritized (Tiered Refresh)

Every 5 min cycle:
- **T1 (every cycle)**: Your positions + PM watchlist + CF ≥ 20
- **T2 (every 15 min)**: CF ≥ 15
- **T3 (every 30 min)**: CF ≥ 10
- **Hot sector boost**: CF ≥ 15 AND in a hot sector
- **Below 10**: Quotes only, bars on full scan only

### What Makes a Stock Worth Trading

The ideal candidate has:
- **Setup score ≥ 15** (strong pattern match with volume confirmation)
- **Confluence ≥ 20** (market + technicals aligned)
- **RVOL ≥ 1.5** (volume confirming the move)
- **Grade A or B** (scorecard passes most checks)
- **GP allows it** (setup valid in current market regime)
- **Not concentrated** (< 2 positions in same sector)

### Red Flags

- Confluence < 16 (Skip quality)
- RVOL < 1.0 (no volume interest)
- Grade F (multiple scorecard failures)
- Spread > 0.1% (execution cost too high)
- ATR multiple > 2.5 (already exhausted daily range)
- 2+ positions in same sector (concentration risk)
- VIX > 25 (elevated volatility regime)
