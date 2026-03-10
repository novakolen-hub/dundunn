# V9 Trade Management — Unified Data Model v1.0
### Corrected Final — March 3, 2026

Everything reads from and writes to this schema.
Pre-trade cards, portfolio tracker, journal, analytics, TradingView panel,
Flutter app, and TradesViz backward-compat export — one source of truth.

---

## OVERVIEW: 5 TABLES

```
ACCOUNTS        → equity, limits, config (small, rarely changes)
EXECUTIONS      → raw broker fills (auto-synced, append-only)
TRADES          → parent trade records (grouped, enriched) ← CORE TABLE
DAILY_LOG       → one row per trading day (equity curve, day plan)
CONTEXT_SNAPS   → market state at key moments (entry, exit, GP flips)
```

Each table = one Google Sheets tab.
Each row has a primary key.
Relationships are by Trade # and Date.

---

## TABLE 1: ACCOUNTS

Purpose: Store account config, equity, and risk limits.
Frequency: Updated once at market open + on demand intraday.
Rows: 2-4 (one per account).

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 1 | account_id | string | TS-DT | Manual config | PK |
| 2 | label | string | TradeStation Day Trade | Manual config | Display name |
| 3 | broker | string | tradestation | Manual config | tradestation / alpaca |
| 4 | type | string | DT | Manual config | DT / SW / PAPER |
| 5 | bod_equity | number | 52340.00 | Bridge API | Beginning-of-day, refreshed on first trigger |
| 6 | current_equity | number | 52185.00 | Bridge API | Updated intraday |
| 7 | daily_pnl | number | -155.00 | Calculated | current - bod |
| 8 | daily_pnl_pct | number | -0.30 | Calculated | daily_pnl / bod * 100 |
| 9 | daily_loss_limit | number | -500 | Manual config | Hard stop for the day (e.g., DT=-500, SW=-1000) |
| 10 | max_risk_per_trade | number | 250 | Manual config | $ risk ceiling per trade |
| 11 | max_risk_pct | number | 0.50 | Manual config | % of equity per trade |
| 12 | max_positions | number | 4 | Manual config | Concurrent position limit |
| 13 | open_positions | number | 2 | Calculated | Current count of OPEN trades |
| 14 | last_updated | timestamp | 2026-03-02T14:30:00 | Auto | |

Daily Loss Limit Thresholds (for dashboard banner + scorecard):
  - Green: daily_pnl above -50% of limit
  - Yellow: daily_pnl between -50% and -100% of limit
  - Red: daily_pnl at or beyond limit → hard warning on pre-trade card

---

## TABLE 2: EXECUTIONS

Purpose: Raw broker fills. Append-only. Auto-synced from bridge.
Frequency: Polled every 1-5 min during market hours via syncTrades().
Rows: ~15-50/day → ~5,000-12,000/year. Archive quarterly (>90 days → Exec Archive tab).

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 1 | exec_id | string | TS-20260302-001 | Broker API | PK (broker's execution ID, dedup key) |
| 2 | trade_num | number | 47 | Grouping logic | FK → TRADES. Assigned when grouped. |
| 3 | timestamp | timestamp | 2026-03-02T07:42:15 | Broker API | Fill time, converted to AZ timezone |
| 4 | account_id | string | TS-DT | Broker API | FK → ACCOUNTS |
| 5 | symbol | string | NVDA | Broker API | |
| 6 | action | string | BUY | Broker API | BUY / SELL / SHORT / COVER |
| 7 | quantity | number | 50 | Broker API | |
| 8 | fill_price | number | 142.35 | Broker API | |
| 9 | commission | number | 0.00 | Broker API | |
| 10 | running_qty | number | 50 | Calculated | Net position after this fill |
| 11 | order_type | string | LIMIT | Broker API | MARKET / LIMIT / STOP |
| 12 | source | string | tradestation | Sync logic | tradestation / alpaca |

Sync Logic:
  - Poll TradeStation: GET /v3/brokerage/accounts/{id}/orders (filled since last check)
  - Poll Alpaca: GET /v2/orders?status=filled&after={last_check}
  - Dedup by exec_id — if already exists, skip
  - Store last sync timestamp in Script Properties (LAST_EXEC_SYNC_TS, LAST_EXEC_SYNC_ALPACA)

Archiving:
  - Quarterly: moveOldExecutions() moves rows >90 days to "Exec Archive" tab
  - Trades tab references trade_num, not exec rows directly, so archive is safe

---

## TABLE 3: TRADES

Purpose: One row per trade idea. The core record everything links to.
Frequency: Created on pre-trade card submit OR first unmatched broker fill.
Rows: ~5-10/day → ~1,200-2,500/year. NEVER archived.

### 3A. IDENTIFICATION (7 fields)

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 1 | trade_num | number | 47 | Auto-increment | PK |
| 2 | symbol | string | NVDA | User / broker | |
| 3 | account_id | string | TS-DT | User / broker | FK → ACCOUNTS |
| 4 | side | string | LONG | User / broker | LONG / SHORT |
| 5 | trade_type | string | DT | User / auto | DT / SW / CORE / PAPER |
| 6 | status | string | OPEN | State machine | PLANNED / OPEN / CLOSED / CANCELLED |
| 7 | was_planned | boolean | true | Auto | Had pre-trade card before entry? |

### 3B. PLAN — from pre-trade card (15 fields)

Filled before entry (pre-trade card) or tagged at EOD for unplanned trades.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 8 | setup_type | string | VWAP-Hold | User input | VWAP-Hold / OR-Break / Pullback-EMA / Momentum / Failed-BD / RS-Override / Rotation-ETF |
| 9 | planned_entry | number | 142.50 | User input | Target entry price |
| 10 | planned_stop | number | 141.20 | User input | Hard stop level |
| 11 | planned_target | number | 145.00 | User input | Primary target (optional — system suggests) |
| 12 | planned_size_dollars | number | 14250 | Auto-calc | Gameplan base → IVR adj → Beta adj → final |
| 13 | planned_shares | number | 100 | Auto-calc | size / current price |
| 14 | dollar_risk | number | 130.00 | Auto-calc | shares * abs(entry - stop) |
| 15 | risk_pct_account | number | 0.25 | Auto-calc | dollar_risk / equity * 100 |
| 16 | scale_plan | string | 50% at 1R, trail rest | Auto-suggest | Default by setup_type, user can override |
| 17 | catalyst | string | AI capex + earnings Wed | User input | One-line thesis |
| 18 | r1_price | number | 143.80 | Auto-calc | 1R target level |
| 19 | r2_price | number | 145.10 | Auto-calc | 2R target level |
| 20 | r3_price | number | 146.40 | Auto-calc | 3R target level |
| 21 | target_vs_em_ratio | number | 1.35 | Auto-calc | Target distance / ticker expected move |
| 22 | stop_vs_em_ratio | number | 0.55 | Auto-calc | Stop distance / ticker expected move |

### 3C. SCORECARD — 8 traffic lights (10 fields)

Auto-evaluated when pre-trade card is submitted. Stored for analytics.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 23 | sc_breadth | string | GREEN | Auto | Breadth confirms for this side? |
| 24 | sc_session | string | GREEN | Auto | Setup matches current session phase? |
| 25 | sc_ivr | string | YELLOW | Auto | IVR supports target distance? |
| 26 | sc_term_structure | string | GREEN | Auto | Term structure safe? (inverted = red) |
| 27 | sc_correlation | string | GREEN | Auto | Not adding correlated exposure? |
| 28 | sc_daily_limit | string | GREEN | Auto | Within daily loss limit? |
| 29 | sc_sector_conc | string | GREEN | Auto | Sector concentration OK? |
| 30 | sc_risk_limit | string | GREEN | Auto | Risk per trade within limits? |
| 31 | sc_score | number | 7 | Auto | Count of GREENs (0-8) |
| 32 | sc_pass | boolean | true | Auto | sc_score >= 6 |

### 3D. KEY CONTEXT AT ENTRY — denormalized for queryability (4 fields)

Duplicated from CONTEXT_SNAPS onto the trade row so analytics queries
don't require joins. These are the fields you'll filter/group by most.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 33 | gameplan_at_entry | string | B | Snapshot | A / B / C / D |
| 34 | confluence_at_entry | number | 26 | Scanner | Confluence score at entry moment |
| 35 | session_phase_at_entry | string | OPEN | Scanner | PM / OPEN / CORE / POWER / AH |
| 36 | vix_at_entry | number | 16.42 | Scanner | VIX at entry |

### 3E. ENTRY (5 fields)

Populated on first broker fill matching this trade.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 37 | entry_time | timestamp | 2026-03-02T07:42:15 | Broker fill | First fill time |
| 38 | entry_price | number | 142.35 | Calculated | Weighted avg across scale-ins |
| 39 | total_shares | number | 100 | Calculated | Max position size reached |
| 40 | position_dollars | number | 14235 | Calculated | total_shares * entry_price |
| 41 | entry_legs | number | 2 | Calculated | Count of additive fills |

### 3F. EXIT (3 fields)

Populated when running_qty reaches 0.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 42 | exit_time | timestamp | 2026-03-02T09:15:30 | Broker fill | Final fill |
| 43 | exit_price | number | 144.80 | Calculated | Weighted avg across exits |
| 44 | exit_legs | number | 1 | Calculated | Count of reductive fills |

### 3G. P&L (6 fields)

Calculated when trade closes.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 45 | gross_pnl | number | 245.00 | Calculated | (exit - entry) * shares (adjusted for side) |
| 46 | net_pnl | number | 245.00 | Calculated | gross_pnl - total commissions |
| 47 | pnl_pct | number | 1.72 | Calculated | net_pnl / position_dollars * 100 |
| 48 | r_multiple | number | 1.88 | Calculated | net_pnl / dollar_risk |
| 49 | mfe | number | 310.00 | Tracked live | Max favorable excursion (best unrealized P&L) |
| 50 | mae | number | -45.00 | Tracked live | Max adverse excursion (worst unrealized P&L) |

### 3H. CONTEXT SNAPSHOT LINKS (2 fields)

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 51 | entry_snap_id | string | SNAP-47-ENTRY | Auto | FK → CONTEXT_SNAPS (full market state at entry) |
| 52 | exit_snap_id | string | SNAP-47-EXIT | Auto | FK → CONTEXT_SNAPS (full market state at exit) |

### 3I. REVIEW — filled at EOD (13 fields)

Maps to TradesViz Trade Plan 15 fields. User fills ~5 fields, rest auto-populated.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 53 | self_grade | string | B | User (EOD) | A / B / C / D / F |
| 54 | followed_system | boolean | true | User (EOD) | |
| 55 | entry_quality | string | On-Time | User (EOD) | Early / On-Time / Late / Chased |
| 56 | exit_quality | string | Plan | User (EOD) | Plan / Trailing / Panic / Time |
| 57 | stop_honored | boolean | true | Auto + User | Auto-detect if stop was hit |
| 58 | target_hit | boolean | true | Auto + User | Auto-detect if target was reached |
| 59 | rr_achieved | number | 1.88 | Calculated | = r_multiple (alias for Trade Plan field 7) |
| 60 | what_worked | string | Clean VWAP hold, scaled at 1R | User (EOD) | |
| 61 | what_didnt | string | Could have held runner longer | User (EOD) | |
| 62 | notes | string | | User (EOD) | Free text |
| 63 | lessons | string | Trust the 1R partial | User (EOD) | |

### 3J. TIMING (2 fields)

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 64 | hold_minutes | number | 93 | Calculated | For day trades (exit_time - entry_time) |
| 65 | hold_days | number | 0 | Calculated | For swings (calendar days) |

**TRADES TABLE TOTAL: 65 columns**

---

## TABLE 4: DAILY_LOG

Purpose: One row per trading day. Replaces TradesViz Day Plan v1.1.
         This IS the equity curve dataset.
Frequency: Auto-created at market open, completed at EOD.
Rows: ~250/year. NEVER archived.

### 4A. MARKET CONTEXT — maps to TradesViz Day Plan fields 1-9

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 1 | date | date | 2026-03-02 | Auto | PK |
| 2 | gameplan | string | B | Scanner | A / B / C / D |
| 3 | breadth_score | number | 6.5 | Scanner | Final EOD score |
| 4 | breadth_pct | number | 62 | Scanner | A/D line % |
| 5 | breadth_high | number | 8.0 | Scanner | Session high |
| 6 | breadth_low | number | 4.5 | Scanner | Session low |
| 7 | breadth_trajectory | string | Improving | Scanner | Improving / Fading / Flat / V-Shape / Inv-V |
| 8 | growth_sectors_green | number | 5 | Scanner | Count of 8 growth sectors positive |
| 9 | vix_regime | string | Normal | Scanner | Low(<15) / Normal(15-18) / Elevated(18-25) / High(>25) |
| 10 | leading_sector | string | XLK | Scanner | XLK/SOXX/SMH/XLY/XLF/XLI/XLC/IWM/XLU/XLP/XLV/XLE/XLB/None |

### 4B. DRIVERS — maps to TradesViz Day Plan fields 10-12

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 11 | market_drivers | string | Earnings, Sector Rotation | User / MBU | Comma-separated multi-select |
| 12 | the_story | string | Tech leading on AI capex... | User / MBU | Narrative summary |
| 13 | arete_aligned | boolean | true | User | |

### 4C. EXECUTION — maps to TradesViz Day Plan fields 13-18

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 14 | followed_system | boolean | true | User (EOD) | Overall for the day |
| 15 | rs_override_used | boolean | false | Auto / User | |
| 16 | sessions_traded | string | Open, Mid-Morning | User (EOD) | Pre-Market/Open/Mid-Morning/Power Hour/Close/After Hours |
| 17 | mistakes_made | string | None | User (EOD) | Overtraded/Chased/No Stop/FOMO/Revenge/Oversized/Early Exit/Late Exit/Traded GP C-D/None |
| 18 | emotional_state | string | Focused | User (EOD) | Calm/Focused/Anxious/FOMO/Frustrated/Overconfident/Hesitant/Tilted |
| 19 | session_quality | string | B | User (EOD) | A / B / C / D / F |

### 4D. RESULTS — maps to TradesViz Day Plan fields 19-22

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 20 | realized_pnl | number | 245.00 | Calculated | Sum of closed TRADES.net_pnl for this date |
| 21 | unrealized_pnl | number | 120.00 | Calculated | Open positions mark-to-market |
| 22 | trades_taken | number | 3 | Calculated | Count of TRADES with entry on this date |
| 23 | win_rate | number | 66.7 | Calculated | % of closed trades with net_pnl > 0 |

### 4E. LEARNING — maps to TradesViz Day Plan fields 23-24

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 24 | key_lesson | string | Trust the 1R partial | User (EOD) | |
| 25 | tomorrow_setup | string | Watch NVDA gap fill if weak open | User (EOD) | |

### 4F. ACCOUNT SNAPSHOT + EQUITY CURVE

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 26 | bod_equity | number | 52340.00 | ACCOUNTS | Snapshot at market open |
| 27 | eod_equity | number | 52585.00 | ACCOUNTS | Snapshot at market close |
| 28 | daily_return_pct | number | 0.47 | Calculated | (eod - bod) / bod * 100 |
| 29 | cumulative_pnl | number | 2585.00 | Calculated | Running total since inception |
| 30 | equity_high_water | number | 52900.00 | Calculated | All-time high equity through this date |
| 31 | drawdown_from_peak | number | -0.60 | Calculated | (eod_equity - high_water) / high_water * 100 |

**DAILY_LOG TOTAL: 31 columns**

---

## TABLE 5: CONTEXT_SNAPS

Purpose: Frozen market state at a specific moment. Referenced by TRADES.
Frequency: Created at each trade entry/exit, GP flips, and key alerts.
Rows: ~10-30/day → ~2,500-7,500/year. Archive annually.

| # | Column | Type | Example | Source | Notes |
|---|--------|------|---------|--------|-------|
| 1 | snap_id | string | SNAP-47-ENTRY | Auto | PK (format: SNAP-{trade_num}-{trigger} or SNAP-{timestamp}-{trigger}) |
| 2 | timestamp | timestamp | 2026-03-02T07:42:15 | Auto | When snapshot was taken |
| 3 | trigger | string | TRADE_ENTRY | Auto | TRADE_ENTRY / TRADE_EXIT / GP_FLIP / ALERT |
| 4 | trade_num | number | 47 | Auto | FK → TRADES (null for GP_FLIP / ALERT) |
| 5 | breadth_score | number | 6.5 | Scanner | |
| 6 | gameplan | string | B | Scanner | |
| 7 | session_phase | string | OPEN | Scanner | PM / OPEN / CORE / POWER / AH |
| 8 | vix | number | 16.42 | Scanner | |
| 9 | vix_regime | string | Normal | Scanner | |
| 10 | term_structure | string | CONTANGO | Scanner | CONTANGO / FLAT / BACKWARDATION / INVERTED |
| 11 | vix_vix3m_ratio | number | 0.87 | Scanner | |
| 12 | vvix | number | 82.5 | Bridge | |
| 13 | spy_ivr | number | 28 | Bridge | |
| 14 | ticker_ivr | number | 35 | Bridge (TastyTrade) | If available |
| 15 | ticker_beta | number | 1.45 | Scanner | |
| 16 | spy_em | number | 4.20 | Bridge | SPY expected daily move $ |
| 17 | fg_score | number | 52 | Bridge | Fear & Greed |
| 18 | naaim | number | 72 | Bridge | NAAIM exposure index |
| 19 | sector_leader | string | XLK | Scanner | |
| 20 | ticker_sector | string | XLK | Scanner | Sector of the traded symbol |
| 21 | spy_price | number | 510.25 | Scanner | SPY at moment |
| 22 | qqq_price | number | 440.80 | Scanner | QQQ at moment |
| 23 | tick | number | 245 | Scanner | $TICK at moment |
| 24 | add | number | 1200 | Scanner | $ADD at moment |
| 25 | confluence | number | 26 | Scanner | Ticker's confluence score at moment |

**CONTEXT_SNAPS TOTAL: 25 columns**

---

## RELATIONSHIPS

```
ACCOUNTS  ←────── EXECUTIONS.account_id
    │                  │
    │                  └── TRADES.trade_num (via EXECUTIONS.trade_num)
    │                          │
    ├────── TRADES.account_id  │
    │                          ├── CONTEXT_SNAPS.snap_id (via entry_snap_id)
    │                          ├── CONTEXT_SNAPS.snap_id (via exit_snap_id)
    │                          │
    │                          └── DAILY_LOG.date (entry_time.date)
    │
    └────── DAILY_LOG (bod/eod equity from accounts)
```

Key queries enabled without joins:
  - TRADES: win rate by gameplan (gameplan_at_entry)
  - TRADES: avg R by confluence bucket (confluence_at_entry)
  - TRADES: performance by session (session_phase_at_entry)
  - TRADES: all plan + result fields on one row
  - DAILY_LOG: equity curve (cumulative_pnl, drawdown_from_peak)
  - CONTEXT_SNAPS: deep drill when you need full market state

---

## GROUPING LOGIC (Executions → Trades)

On each new execution arriving from syncTrades():

```
1. MATCH: Look for OPEN or PLANNED trade where
     symbol matches AND account_id matches

2. IF match found AND action is ADDITIVE (BUY on LONG, SHORT on SHORT):
     → Scale-in leg
     → Recalculate entry_price as weighted average
     → Update total_shares (take max reached)
     → Increment entry_legs
     → If status was PLANNED → change to OPEN
     → Snapshot context if this is the FIRST fill (PLANNED → OPEN)

3. IF match found AND action is REDUCTIVE (SELL on LONG, COVER on SHORT):
     → Scale-out leg
     → Update running_qty
     → Track partial P&L for MFE/MAE
     → IF running_qty == 0:
         → Status → CLOSED
         → Populate exit_time, exit_price, exit_legs
         → Calculate gross_pnl, net_pnl, pnl_pct, r_multiple
         → Snapshot exit context → exit_snap_id
     → IF running_qty < 0 (flip):
         → CLOSE the old trade (qty to 0)
         → CREATE new trade with opposite side, remaining qty

4. IF no match found:
     → Create new TRADES row, status = OPEN
     → Set was_planned = false
     → Snapshot entry context → entry_snap_id
     → Assign trade_num (next auto-increment)

5. ALWAYS: assign execution's trade_num FK to the parent trade

6. ACCOUNT SEPARATION: Same symbol in different accounts = separate
     parent trades. Match key is (symbol + account_id), not just symbol.
```

---

## PRE-TRADE CARD FLOW

```
User opens card (dashboard panel or TV-adjacent page):

1. SELECT SYMBOL
   → Auto-populate from scanner:
     Current price, VWAP, VWAP distance, OR high/low, EMA9/EMA20
     Ticker sector, beta, IVR (if available from TastyTrade)
     Current breadth score, gameplan, session phase, confluence

2. USER INPUTS (5 fields):
     Side (Long / Short)
     Setup Type (7 options)
     Planned Stop (price)
     Planned Target (price — optional, system suggests from R levels)
     Catalyst/Thesis (one line)

3. SYSTEM AUTO-CALCULATES:
     Position size: Gameplan base → IVR adjustment → Beta adjustment → final $
     Shares = size / current price
     Dollar risk = shares * |entry - stop|
     Risk % = dollar_risk / account equity
     R1 / R2 / R3 price levels
     Target vs Expected Move ratio
     Stop vs Expected Move ratio
     Suggested scale plan (from setup_type defaults)

4. SCORECARD evaluates 8 checks → traffic lights:
     Breadth confirms side? → checks gameplan vs side
     Session phase matches? → e.g., no OR-Break before 7:45 AZ
     IVR supports target? → high IVR may compress target
     Term structure safe? → inverted = red for longs
     Not adding correlated? → check open trades for same sector/beta cluster
     Within daily loss limit? → check ACCOUNTS.daily_pnl vs limit
     Sector concentration OK? → no more than 2 positions same sector
     Risk per trade OK? → dollar_risk <= max_risk_per_trade

5. USER REVIEWS → clicks ENTER:
     → Creates TRADES row: status = PLANNED, all plan fields filled
     → Creates CONTEXT_SNAPS: entry_snap_id
     → When broker fill syncs → grouping logic matches by symbol + account
     → Status: PLANNED → OPEN, entry fields populated
     → If user never executes → can CANCEL at EOD

6. UNPLANNED TRADES:
     → Broker fill arrives with no matching PLANNED trade
     → Grouping logic creates OPEN trade with was_planned = false
     → User tags setup_type and review fields at EOD
```

---

## EOD FLOW (replaces TradesViz Day Plan export)

```
At 2:00 PM AZ (or user triggers "EOD"):

STEP 1 — AUTO-POPULATE DAILY_LOG:
  → Market context fields from last scanner state (fields 2-10)
  → Results from TRADES: sum P&L, count trades, calc win rate (fields 20-23)
  → Account snapshot from ACCOUNTS (fields 26-27)
  → Calculate equity curve fields (fields 28-31)

STEP 2 — REVIEW EACH TRADE:
  → List all CLOSED trades for today
  → Highlight any with was_planned = false (need setup_type tag)
  → For each trade, user provides:
     - Setup type (if unplanned)
     - Self-grade (A/B/C/D/F)
     - Entry quality (Early/On-Time/Late/Chased)
     - Exit quality (Plan/Trailing/Panic/Time)
     - Followed system? (Y/N)
     - What worked / what didn't / lessons (optional quick notes)
  → Auto-populated: stop_honored, target_hit, rr_achieved (from P&L data)

STEP 3 — DAILY LOG USER FIELDS:
  → User fills: drivers, the_story, sessions_traded, mistakes,
     emotional_state, session_quality, key_lesson, tomorrow_setup
  → ~5 minute process total

STEP 4 — COACHING SUMMARY (generated by Claude):
  → Compare planned vs actual (did you follow scale plans?)
  → Flag rule violations (traded GP-D, exceeded position limit, etc.)
  → Highlight best trade and worst trade with reasoning
  → Pattern detection if enough history (e.g., "3rd time chasing afternoon")

STEP 5 — BACKWARD COMPAT EXPORT (transition period):
  → Map DAILY_LOG → TradesViz Day Plan 24 fields (text block for copy-paste)
  → Map TRADES review fields → TradesViz Trade Plan 15 fields
  → Once V9 journal is fully built → stop exporting, TradesViz becomes archive
```

---

## TRADESVIZ FIELD MAPPING REFERENCE

### Day Plan (24 fields) → DAILY_LOG columns

| TV# | TradesViz Field | DAILY_LOG Column |
|-----|----------------|------------------|
| 1 | Gameplan | gameplan |
| 2 | Breadth Score | breadth_score |
| 3 | Breadth % | breadth_pct |
| 4 | Breadth High | breadth_high |
| 5 | Breadth Low | breadth_low |
| 6 | Breadth Trajectory | breadth_trajectory |
| 7 | Growth Sectors Green | growth_sectors_green |
| 8 | VIX Regime | vix_regime |
| 9 | Leading Sector | leading_sector |
| 10 | Market Drivers | market_drivers |
| 11 | The Story | the_story |
| 12 | Arete Aligned | arete_aligned |
| 13 | Followed System | followed_system |
| 14 | RS Override Used | rs_override_used |
| 15 | Sessions Traded | sessions_traded |
| 16 | Mistakes Made | mistakes_made |
| 17 | Emotional State | emotional_state |
| 18 | Session Quality | session_quality |
| 19 | Realized P&L | realized_pnl |
| 20 | Unrealized P&L | unrealized_pnl |
| 21 | Trades Taken | trades_taken |
| 22 | Win Rate | win_rate |
| 23 | Key Lesson | key_lesson |
| 24 | Tomorrow Setup | tomorrow_setup |

### Trade Plan (15 fields) → TRADES columns

| TP# | TradesViz Field | TRADES Column |
|-----|----------------|---------------|
| 1 | Setup Type | setup_type |
| 2 | Gameplan at Entry | gameplan_at_entry |
| 3 | Confluence at Entry | confluence_at_entry |
| 4 | Entry Price | entry_price |
| 5 | Exit Price | exit_price |
| 6 | P&L | net_pnl |
| 7 | R:R Achieved | rr_achieved / r_multiple |
| 8 | Stop Honored | stop_honored |
| 9 | Target Hit | target_hit |
| 10 | Entry Quality | entry_quality |
| 11 | Exit Quality | exit_quality |
| 12 | Followed Rules | followed_system |
| 13 | What Worked | what_worked |
| 14 | What Didn't | what_didnt |
| 15 | Grade | self_grade |

All 24 + 15 fields have a 1:1 home in the data model. Zero data loss.

---

## SHEETS TAB LAYOUT

```
Existing tabs (unchanged):
  Market | Config | Watchlist | _Spark | Dashboard | Notes | Weekend

New tabs (this build):
  Accounts     → TABLE 1  (2-4 rows, row 1 = header)
  Executions   → TABLE 2  (append-only, row 1 = header)
  Trades       → TABLE 3  (65 columns, row 1 = header)
  DailyLog     → TABLE 4  (31 columns, row 1 = header)
  Snapshots    → TABLE 5  (25 columns, row 1 = header)
  ExecArchive  → archived executions (quarterly move target)
```

---

## ANALYTICS QUERIES ENABLED

Once 50-100+ trades accumulated, query TRADES + DAILY_LOG for:

  - Win rate by Gameplan (A/B/C/D) → gameplan_at_entry
  - Avg R-multiple by Setup Type → setup_type + r_multiple
  - P&L by Session Phase → session_phase_at_entry
  - Performance by Sector → ticker_sector (via CONTEXT_SNAPS)
  - Win rate by Term Structure → sc_term_structure or snap data
  - Win rate when confluence >= 24 vs < 24 → confluence_at_entry
  - Planned vs unplanned performance → was_planned
  - Scorecard correlation → sc_score vs r_multiple
  - Revenge trading detection → entry_time gaps < 15 min after stop
  - Scale plan adherence → planned scale_plan vs actual exit_legs
  - Drawdown patterns → DAILY_LOG.drawdown_from_peak
  - Best/worst days → DAILY_LOG by daily_return_pct
  - Emotional state impact → emotional_state vs session win rate

---

## BUILD ORDER

Phase 1: Schema (this session)
  1A. Create Accounts tab with header row + manual config rows
  1B. Create Executions tab with header row
  1C. Create Trades tab with 65-column header row
  1D. Create DailyLog tab with 31-column header row
  1E. Create Snapshots tab with 25-column header row

Phase 2: Bridge Endpoints
  2A. /accounts/equity (TS + Alpaca equity snapshots)
  2B. /trades/tradestation (poll filled orders)
  2C. /trades/alpaca (poll filled orders)
  2D. /trades/sync (combined endpoint)

Phase 3: Scanner Functions
  3A. syncTrades() — called on trigger, polls bridge, writes Executions
  3B. logExecution(fill) — writes single row to Executions tab
  3C. groupToTrade(exec) — creates/updates parent Trade row
  3D. snapshotContext(trigger, tradeNum) — writes Snapshots row
  3E. getTradesForDashboard() — includes open trades in doGet response
  3F. updateDailyLog() — auto-populate/update DailyLog at EOD

Phase 4: Pre-Trade Card UI
  4A. Dashboard: ticker selector + auto-populate
  4B. Dashboard: position sizing calculator
  4C. Dashboard: 8-check scorecard with traffic lights
  4D. Dashboard: ENTER button → writes PLANNED trade
  4E. Scanner: logPlannedTrade() + fill matching logic

Phase 5: Portfolio Tracker UI
  5A. Dashboard: open trades with live P&L, R-multiple, scale status
  5B. Dashboard: portfolio risk summary (total heat, sector concentration)
  5C. Dashboard: daily P&L banner with loss limit indicator

Phase 6: EOD Review UI
  6A. Dashboard: "Review Today's Trades" panel
  6B. Dashboard: per-trade tag/grade interface
  6C. Dashboard: daily log completion form
  6D. Scanner: TradesViz export formatter (backward compat)

Phase 7: Analytics + Coaching
  7A. Performance queries against Trades tab
  7B. Claude coaching from trade history patterns
  7C. Monthly system audit automation
