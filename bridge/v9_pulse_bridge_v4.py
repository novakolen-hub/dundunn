"""
V9 Institutional Pulse Bridge v4.0
====================================
Data sources:
  - Tastytrade API  → IVR, IV Percentile, IV 5-day change,
                       per-expiration IV, expected move (OAuth2)
  - Yahoo Finance   → VIX level, VIX term structure
                       (VIX9D, VIX3M, VIX1D, VVIX)
  - CBOE            → Put/Call ratio
  - CNN             → Fear & Greed Index
  - AAII            → Weekly sentiment

v4.0 additions:
  - VIX term structure: contango/backwardation detection
  - TastyTrade IV 5-day change + per-expiration IV curve
  - SPY expected daily move (from IV index)

No password prompt — just run it.
"""

import time
import json
import threading
import requests
import re
from datetime import datetime, date
from flask import Flask, jsonify
from pyngrok import ngrok, conf
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

NGROK_AUTHTOKEN    = "3AB3HmPcFehIAK8spAsapQ7ctqK_7FPFKhdgLBrC7PLkWBz5h"
NGROK_DOMAIN       = "ecclesiastically-ratio-lauran.ngrok-free.dev"
FLASK_PORT         = 5000

TT_CLIENT_ID       = "3300a3a5-dce3-463e-a46c-b571e245a4e3"
TT_CLIENT_SECRET   = "ee72a6837101b756d53eaa22dcae2ee25eaec0d5"
TT_REFRESH_TOKEN   = "eyJhbGciOiJFZERTQSIsInR5cCI6InJ0K2p3dCIsImtpZCI6Ik9UTUMzeThCTVB0Q3hxbHBSWUlod2N0UzY3aGdfd3hEM0NOYXdSX2lXanMiLCJqa3UiOiJodHRwczovL2ludGVyaW9yLWFwaS5hcjIudGFzdHl0cmFkZS5zeXN0ZW1zL29hdXRoL2p3a3MifQ.eyJpc3MiOiJodHRwczovL2FwaS50YXN0eXRyYWRlLmNvbSIsInN1YiI6IlU5ODNlZTBkNC1iZjJiLTQzODItOWFhYi1mMzYzMGRhODhhYTciLCJpYXQiOjE3NzIwNTYxNTQsImF1ZCI6IjMzMDBhM2E1LWRjZTMtNDYzZS1hNDZjLWI1NzFlMjQ1YTRlMyIsImdyYW50X2lkIjoiR2Y0Y2NiYjBmLThkYWItNDQxNC1iYmFhLWRjMjUxNjMzZDIyOCIsInNjb3BlIjoicmVhZCJ9.JtuUD7w3JECe0zYB-G40M-efSAsU2fW6zwXCrMelyIBNUUoWoN6oLr2EEKhe8HWfViewkdVX5E3kHL5FQXaiBw"
TT_API             = "https://api.tastytrade.com"

IV_SYMBOLS         = ["SPY", "QQQ", "IWM"]
CACHE_TTL          = 300  # 5 minutes

# ─────────────────────────────────────────────
# GLOBALS
# ─────────────────────────────────────────────

app = Flask(__name__)
_cache        = {"data": None, "ts": 0}
_cache_lock   = threading.Lock()
_access_token = {"value": None, "expires": 0}

# ─────────────────────────────────────────────
# TASTYTRADE OAUTH2
# ─────────────────────────────────────────────

def tt_refresh_access_token():
    """Exchange refresh token for a fresh access token."""
    try:
        r = requests.post(
            f"{TT_API}/oauth/token",
            data={
                "grant_type":    "refresh_token",
                "client_id":     TT_CLIENT_ID,
                "client_secret": TT_CLIENT_SECRET,
                "refresh_token": TT_REFRESH_TOKEN,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        if r.status_code == 200:
            token = r.json()["access_token"]
            _access_token["value"]   = token
            _access_token["expires"] = time.time() + 900  # refresh every 15 min
            print("✅ Tastytrade access token refreshed")
            return True
        else:
            print(f"❌ Tastytrade token refresh failed: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Tastytrade token error: {e}")
        return False

def tt_ensure_token():
    """Refresh access token if expired or missing."""
    if not _access_token["value"] or time.time() > _access_token["expires"] - 60:
        tt_refresh_access_token()

def tt_auth_header():
    tt_ensure_token()
    return {"Authorization": f"Bearer {_access_token['value']}"}

# ─────────────────────────────────────────────
# TASTYTRADE — IV RANK
# ─────────────────────────────────────────────

def get_iv_data():
    """Pull IVR, IV%, IV 5-day change, per-expiration IV, and expected move for SPY/QQQ/IWM."""
    try:
        tt_ensure_token()
        r = requests.get(
            f"{TT_API}/market-metrics",
            params={"symbols": ",".join(IV_SYMBOLS)},
            headers=tt_auth_header(),
            timeout=10
        )
        if r.status_code != 200:
            print(f"⚠️  Tastytrade metrics error: {r.status_code}")
            return {s: {"ivr": None, "iv_pct": None, "status": "api_error"} for s in IV_SYMBOLS}

        results = {}
        items = r.json().get("data", {}).get("items", [])
        for item in items:
            sym    = item.get("symbol")
            ivr    = item.get("implied-volatility-index-rank")
            iv_pct = item.get("implied-volatility-percentile")
            iv_idx = item.get("implied-volatility-index")
            iv_5d  = item.get("implied-volatility-index-5-day-change")
            liq    = item.get("liquidity-rating")
            beta   = item.get("beta")
            corr   = item.get("corr-spy-3month")

            # Per-expiration IV curve (near-term vs far-term)
            exp_ivs = []
            raw_exps = item.get("option-expiration-implied-volatilities") or []
            for exp in raw_exps[:6]:  # first 6 expirations
                exp_date = exp.get("expiration-date")
                exp_iv   = exp.get("implied-volatility")
                if exp_date and exp_iv:
                    exp_ivs.append({
                        "date": exp_date,
                        "iv":   round(float(exp_iv) * 100, 1)
                    })

            if sym in IV_SYMBOLS:
                iv_val = round(float(iv_idx) * 100, 1) if iv_idx else None
                results[sym] = {
                    "ivr":       round(float(ivr) * 100, 1)    if ivr    else None,
                    "iv_pct":    round(float(iv_pct) * 100, 1) if iv_pct else None,
                    "iv":        iv_val,
                    "iv_5d_chg": round(float(iv_5d) * 100, 1)  if iv_5d  else None,
                    "liquidity": int(liq)                       if liq    else None,
                    "beta":      round(float(beta), 2)          if beta   else None,
                    "corr_spy":  round(float(corr), 3)          if corr   else None,
                    "exp_ivs":   exp_ivs,
                    "status":    "ok"
                }

                # Calculate expected daily move from IV index
                # Expected move = Price * IV * sqrt(1/252)
                # We don't have price here, so store IV-derived % move
                if iv_val:
                    results[sym]["expected_daily_pct"] = round(iv_val / (252 ** 0.5), 2)

        for sym in IV_SYMBOLS:
            if sym not in results:
                results[sym] = {"ivr": None, "iv_pct": None, "iv": None, "status": "no_data"}

        return results

    except Exception as e:
        print(f"⚠️  IV data error: {e}")
        return {s: {"ivr": None, "iv_pct": None, "status": "error"} for s in IV_SYMBOLS}

# ─────────────────────────────────────────────
# VIX — Yahoo Finance
# ─────────────────────────────────────────────

def get_vix():
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        meta  = r.json()["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        if price:
            level = round(float(price), 2)
            return {
                "level":  level,
                "regime": "HIGH_FEAR"  if level >= 30 else
                          "ELEVATED"   if level >= 20 else
                          "NORMAL"     if level >= 15 else
                          "COMPLACENT",
                "status": "ok"
            }
        return {"level": None, "regime": "UNKNOWN", "status": "no_data"}
    except Exception as e:
        print(f"⚠️  VIX error: {e}")
        return {"level": None, "regime": "UNKNOWN", "status": "error"}

# ─────────────────────────────────────────────
# VIX TERM STRUCTURE — Yahoo Finance
# ─────────────────────────────────────────────

VIX_TERM_SYMBOLS = {
    "VIX1D": "%5EVIX1D",   # 1-day
    "VIX9D": "%5EVIX9D",   # 9-day
    "VIX":   "%5EVIX",     # 30-day (reference, already fetched above)
    "VIX3M": "%5EVIX3M",   # 3-month
    "VIX6M": "%5EVIX6M",   # 6-month
    "VVIX":  "%5EVVIX",    # vol of vol
}

def get_vix_term_structure():
    """Fetch VIX term structure: VIX1D, VIX9D, VIX3M, VIX6M, VVIX from Yahoo."""
    try:
        results = {}
        for name, yahoo_sym in VIX_TERM_SYMBOLS.items():
            if name == "VIX":
                continue  # already fetched in get_vix()
            try:
                r = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=8
                )
                if r.status_code == 200:
                    meta = r.json()["chart"]["result"][0]["meta"]
                    price = meta.get("regularMarketPrice") or meta.get("previousClose")
                    if price:
                        results[name] = round(float(price), 2)
            except Exception as ex:
                print(f"⚠️  {name} fetch error: {ex}")

        # Calculate term structure signals
        vix9d  = results.get("VIX9D")
        vix3m  = results.get("VIX3M")
        vix6m  = results.get("VIX6M")
        vvix   = results.get("VVIX")
        vix1d  = results.get("VIX1D")

        # We need the VIX level from get_vix() — will be merged in build_pulse_data
        # For now, store ratios as None; they'll be calculated in build_pulse_data
        return {
            "vix1d":  vix1d,
            "vix9d":  vix9d,
            "vix3m":  vix3m,
            "vix6m":  vix6m,
            "vvix":   vvix,
            "status": "ok" if len(results) >= 3 else "partial"
        }

    except Exception as e:
        print(f"⚠️  VIX term structure error: {e}")
        return {"status": "error"}

# ─────────────────────────────────────────────
# EXPECTED MOVE — calculated from SPY IV + price
# ─────────────────────────────────────────────

def get_expected_move():
    """Calculate SPY expected daily & weekly move from IV and current price."""
    try:
        # Get SPY price from Yahoo
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/SPY",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8
        )
        if r.status_code != 200:
            return {"status": "price_error"}

        meta  = r.json()["chart"]["result"][0]["meta"]
        price = float(meta.get("regularMarketPrice") or meta.get("previousClose") or 0)
        if price == 0:
            return {"status": "no_price"}

        return {
            "spy_price": round(price, 2),
            "status":    "ok"
        }

    except Exception as e:
        print(f"⚠️  Expected move error: {e}")
        return {"status": "error"}

# ─────────────────────────────────────────────
# PUT/CALL RATIO — via yfinance SPY options
# ─────────────────────────────────────────────

def get_cboe_putcall():
    """Calculate SPY put/call ratio from yfinance options chain."""
    try:
        import yfinance as yf
        spy  = yf.Ticker("SPY")
        exps = spy.options
        if not exps:
            return {"total_pc": None, "status": "no_expirations"}

        # Use nearest expiration
        chain    = spy.option_chain(exps[0])
        call_vol = float(chain.calls["volume"].sum())
        put_vol  = float(chain.puts["volume"].sum())
        call_oi  = float(chain.calls["openInterest"].sum())
        put_oi   = float(chain.puts["openInterest"].sum())

        vol_pc = round(put_vol / call_vol, 2) if call_vol > 0 else None
        oi_pc  = round(put_oi  / call_oi,  2) if call_oi  > 0 else None
        ratio  = vol_pc or oi_pc

        return {
            "total_pc":  ratio,
            "vol_pc":    vol_pc,
            "oi_pc":     oi_pc,
            "call_vol":  int(call_vol),
            "put_vol":   int(put_vol),
            "expiration": exps[0],
            "sentiment": "bearish" if ratio and ratio > 1.1 else
                         "bullish" if ratio and ratio < 0.7 else "neutral",
            "status":    "ok",
            "source":    "yfinance_spy"
        }

    except Exception as e:
        print(f"⚠️  P/C ratio error: {e}")
        return {"total_pc": None, "status": "error"}

# ─────────────────────────────────────────────
# FEAR & GREED — alternative.me (CNN dead)
# ─────────────────────────────────────────────

def get_fear_greed():
    """Fetch Fear & Greed from alternative.me (CNN endpoint is dead)."""
    try:
        r = requests.get(
            "https://api.alternative.me/fng/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        if r.status_code == 200:
            item  = r.json()["data"][0]
            score = round(float(item["value"]), 1)
            rating = item.get("value_classification", "")
            return {
                "score":  score,
                "rating": rating,
                "zone":   "extreme_fear" if score < 25 else
                          "fear"         if score < 45 else
                          "neutral"      if score < 55 else
                          "greed"        if score < 75 else
                          "extreme_greed",
                "status": "ok",
                "source": "alternative.me"
            }
        return {"score": None, "rating": None, "zone": None, "status": "api_error"}
    except Exception as e:
        print(f"⚠️  Fear & Greed error: {e}")
        return {"score": None, "rating": None, "zone": None, "status": "error"}

# ─────────────────────────────────────────────
# AAII SENTIMENT — via stooq CSV fallback
# ─────────────────────────────────────────────

def get_aaii_sentiment():
    """Fetch NAAIM Exposure Index (replaces AAII — updates weekly, more institutional)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(
            "https://naaim.org/programs/naaim-exposure-index/",
            headers=headers, timeout=10
        )
        soup = BeautifulSoup(r.text, "html.parser")

        # Parse table — first row after header is most recent week
        table = soup.find("table")
        if not table:
            return {"exposure": None, "status": "no_table"}

        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            cells = row.find_all("td")
            if len(cells) >= 2:
                try:
                    week_date = cells[0].get_text(strip=True)
                    exposure  = round(float(cells[1].get_text(strip=True)), 2)
                    bearish   = cells[2].get_text(strip=True)
                    bullish   = cells[6].get_text(strip=True) if len(cells) > 6 else None

                    return {
                        "exposure":  exposure,
                        "date":      week_date,
                        "sentiment": "bullish" if exposure > 80 else
                                     "bearish" if exposure < 40 else "neutral",
                        "zone":      "high_exposure"  if exposure > 100 else
                                     "elevated"       if exposure > 70  else
                                     "moderate"       if exposure > 40  else
                                     "low_exposure",
                        "source":    "naaim",
                        "status":    "ok",
                        "note":      "NAAIM = active mgr equity exposure (-200 to +200)"
                    }
                except:
                    continue

        return {"exposure": None, "status": "parse_error"}

    except Exception as e:
        print(f"⚠️  NAAIM error: {e}")
        return {"exposure": None, "status": "error"}

# ─────────────────────────────────────────────
# BUILD PAYLOAD
# ─────────────────────────────────────────────

def build_pulse_data():
    print(f"\n🔄 Building Institutional Pulse — {datetime.now().strftime('%H:%M:%S')}")
    results = {}

    def fetch_iv():   results["iv"]         = get_iv_data()
    def fetch_vix():  results["vix"]        = get_vix()
    def fetch_cboe(): results["cboe"]       = get_cboe_putcall()
    def fetch_fg():   results["fear_greed"] = get_fear_greed()
    def fetch_aaii(): results["aaii"]       = get_aaii_sentiment()
    def fetch_term(): results["term"]       = get_vix_term_structure()
    def fetch_em():   results["em"]         = get_expected_move()

    threads = [threading.Thread(target=f) for f in [fetch_iv, fetch_vix, fetch_cboe, fetch_fg, fetch_aaii, fetch_term, fetch_em]]
    for t in threads: t.start()
    for t in threads: t.join(timeout=20)

    vix  = results.get("vix", {})
    iv   = results.get("iv",  {})
    term = results.get("term", {})
    em   = results.get("em",  {})

    # ── Compute VIX term structure signals ──
    vix_level = vix.get("level")
    vix9d     = term.get("vix9d")
    vix3m     = term.get("vix3m")
    vix6m     = term.get("vix6m")
    vvix      = term.get("vvix")
    vix1d     = term.get("vix1d")

    # Ratios: >1.0 = backwardation (short-term fear > long-term)
    vix_vix3m_ratio = round(vix_level / vix3m, 3) if vix_level and vix3m else None
    vix9d_vix_ratio = round(vix9d / vix_level, 3) if vix9d and vix_level else None
    vix_vix6m_ratio = round(vix_level / vix6m, 3) if vix_level and vix6m else None

    # Term structure state
    if vix_vix3m_ratio and vix9d_vix_ratio:
        if vix9d_vix_ratio > 1.05 and vix_vix3m_ratio > 1.0:
            ts_state = "INVERTED"       # Full backwardation — danger
            ts_signal = "danger"
        elif vix_vix3m_ratio > 1.0:
            ts_state = "BACKWARDATION"  # Near-term fear elevated
            ts_signal = "caution"
        elif vix_vix3m_ratio > 0.92:
            ts_state = "FLAT"           # Normal, low conviction
            ts_signal = "neutral"
        else:
            ts_state = "CONTANGO"       # Normal healthy market
            ts_signal = "calm"
    else:
        ts_state = "UNKNOWN"
        ts_signal = "unknown"

    # VVIX warning
    vvix_warning = None
    if vvix:
        if vvix > 140:
            vvix_warning = "extreme"    # VIX itself could explode
        elif vvix > 120:
            vvix_warning = "elevated"   # Increased VIX movement expected
        elif vvix > 100:
            vvix_warning = "normal"
        else:
            vvix_warning = "low"

    # ── Compute expected daily move for SPY ──
    spy_iv   = iv.get("SPY", {}).get("iv")
    spy_price = em.get("spy_price")
    expected_move = {}
    if spy_iv and spy_price:
        daily_pct  = spy_iv / (252 ** 0.5)
        weekly_pct = spy_iv / (52 ** 0.5)
        expected_move = {
            "daily_pct":    round(daily_pct, 2),
            "daily_pts":    round(spy_price * daily_pct / 100, 2),
            "weekly_pct":   round(weekly_pct, 2),
            "weekly_pts":   round(spy_price * weekly_pct / 100, 2),
            "spy_price":    spy_price,
            "status":       "ok"
        }
    else:
        expected_move = {"status": "insufficient_data"}

    payload = {
        "timestamp":   datetime.now().isoformat(),
        "market_date": date.today().isoformat(),
        "vol_regime": {
            "regime":     vix.get("regime", "UNKNOWN"),
            "vix":        vix.get("level"),
            "spy_ivr":    iv.get("SPY", {}).get("ivr"),
            "qqq_ivr":    iv.get("QQQ", {}).get("ivr"),
            "iwm_ivr":    iv.get("IWM", {}).get("ivr"),
            "spy_iv":     iv.get("SPY", {}).get("iv"),
            "spy_iv_pct": iv.get("SPY", {}).get("iv_pct"),
            "spy_iv_5d_chg": iv.get("SPY", {}).get("iv_5d_chg"),
            "qqq_iv_5d_chg": iv.get("QQQ", {}).get("iv_5d_chg"),
            "iwm_iv_5d_chg": iv.get("IWM", {}).get("iv_5d_chg"),
        },
        "term_structure": {
            "vix1d":           vix1d,
            "vix9d":           vix9d,
            "vix":             vix_level,
            "vix3m":           vix3m,
            "vix6m":           vix6m,
            "vvix":            vvix,
            "vix_vix3m_ratio": vix_vix3m_ratio,
            "vix9d_vix_ratio": vix9d_vix_ratio,
            "vix_vix6m_ratio": vix_vix6m_ratio,
            "state":           ts_state,
            "signal":          ts_signal,
            "vvix_warning":    vvix_warning,
        },
        "expected_move":       expected_move,
        "iv_curve": {
            "SPY": iv.get("SPY", {}).get("exp_ivs", []),
            "QQQ": iv.get("QQQ", {}).get("exp_ivs", []),
            "IWM": iv.get("IWM", {}).get("exp_ivs", []),
        },
        "put_call":   {"cboe": results.get("cboe",       {"status": "not_fetched"})},
        "fear_greed":          results.get("fear_greed", {"status": "not_fetched"}),
        "aaii":                results.get("aaii",        {"status": "not_fetched"}),
        "meta": {
            "bridge_version":   "4.0",
            "tt_authenticated": bool(_access_token["value"]),
            "sources":          ["tastytrade", "yahoo", "yahoo_term_structure", "cboe", "cnn", "aaii"]
        }
    }

    print(f"✅ VIX:{vix.get('level')} | SPY IVR:{iv.get('SPY',{}).get('ivr')} | "
          f"F&G:{results.get('fear_greed',{}).get('score')} | "
          f"NAAIM:{results.get('aaii',{}).get('exposure')} | "
          f"Term:{ts_state} | VIX/3M:{vix_vix3m_ratio} | VVIX:{vvix}")
    if expected_move.get("status") == "ok":
        print(f"   SPY Expected Move: ±${expected_move['daily_pts']} ({expected_move['daily_pct']}%) daily | "
              f"±${expected_move['weekly_pts']} ({expected_move['weekly_pct']}%) weekly")
    return payload

# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────

def get_cached_pulse():
    with _cache_lock:
        if _cache["data"] and (time.time() - _cache["ts"]) < CACHE_TTL:
            return _cache["data"]
    data = build_pulse_data()
    with _cache_lock:
        _cache["data"] = data
        _cache["ts"]   = time.time()
    return data

# ─────────────────────────────────────────────
# FLASK
# ─────────────────────────────────────────────

@app.route("/pulse")
def pulse():
    try:
        return jsonify(get_cached_pulse())
    except Exception as e:
        return jsonify({"error": str(e), "status": "bridge_error"}), 500

@app.route("/pulse/refresh")
def pulse_refresh():
    with _cache_lock:
        _cache["ts"] = 0
    return jsonify(get_cached_pulse())

@app.route("/health")
def health():
    return jsonify({
        "status":           "ok",
        "tt_authenticated": bool(_access_token["value"]),
        "timestamp":        datetime.now().isoformat(),
        "version":          "4.1"
    })

@app.route("/market-metrics")
def market_metrics():
    """Per-ticker IVR, IV, beta, expected move for any symbols.
    Usage: /market-metrics?symbols=AAPL,TSLA,NVDA,SPY
    Returns: {ticker: {ivr, iv, beta, expMove, status}}
    """
    from flask import request as flask_request
    symbols_str = flask_request.args.get("symbols", "")
    if not symbols_str:
        return jsonify({"error": "?symbols= required"}), 400
    
    symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
    if len(symbols) > 50:
        symbols = symbols[:50]
    
    try:
        tt_ensure_token()
        r = requests.get(
            f"{TT_API}/market-metrics",
            params={"symbols": ",".join(symbols)},
            headers=tt_auth_header(),
            timeout=15
        )
        if r.status_code != 200:
            return jsonify({"error": f"tastytrade API {r.status_code}"}), 502
        
        results = {}
        items = r.json().get("data", {}).get("items", [])
        for item in items:
            sym    = item.get("symbol")
            if not sym:
                continue
            ivr    = item.get("implied-volatility-index-rank")
            iv_idx = item.get("implied-volatility-index")
            beta   = item.get("beta")
            liq    = item.get("liquidity-rating")
            
            iv_val = round(float(iv_idx) * 100, 1) if iv_idx else None
            exp_move_pct = round(iv_val / (252 ** 0.5), 2) if iv_val else None
            
            results[sym] = {
                "ivr":     round(float(ivr) * 100, 1) if ivr else None,
                "iv":      iv_val,
                "beta":    round(float(beta), 2) if beta else None,
                "expMove": f"{exp_move_pct}%" if exp_move_pct else None,
                "liq":     int(liq) if liq else None,
                "status":  "ok"
            }
        
        # Fill missing symbols
        for sym in symbols:
            if sym not in results:
                results[sym] = {"ivr": None, "iv": None, "status": "no_data"}
        
        return jsonify(results)
    
    except Exception as e:
        print(f"⚠️  Market metrics error: {e}")
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────
# BACKGROUND REFRESH
# ─────────────────────────────────────────────

def background_refresh():
    while True:
        time.sleep(CACHE_TTL)
        try:
            data = build_pulse_data()
            with _cache_lock:
                _cache["data"] = data
                _cache["ts"]   = time.time()
        except Exception as e:
            print(f"⚠️  Background refresh error: {e}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  V9 Institutional Pulse Bridge v4.0")
    print("  TT OAuth2 + Yahoo + Term Structure + CBOE + NAAIM")
    print("=" * 55)

    # 1. Authenticate Tastytrade
    print("\n🔐 Authenticating Tastytrade...")
    if not tt_refresh_access_token():
        print("⚠️  Continuing without Tastytrade — IVR will be empty")

    # 2. Build initial cache
    print("\n📊 Building initial cache...")
    try:
        initial = build_pulse_data()
        with _cache_lock:
            _cache["data"] = initial
            _cache["ts"]   = time.time()
        print("✅ Cache ready")
    except Exception as e:
        print(f"⚠️  Cache error: {e}")

    # 3. Start ngrok
    print("\n🌐 Starting ngrok tunnel...")
    try:
        conf.get_default().auth_token = NGROK_AUTHTOKEN
        tunnel = ngrok.connect(FLASK_PORT, "http", domain=NGROK_DOMAIN)
        public_url = tunnel.public_url.replace("http://", "https://")
        print(f"✅ Tunnel: {public_url}")
        print(f"\n{'='*55}")
        print(f"  Bridge: {public_url}/pulse")
        print(f"  Health: {public_url}/health")
        print(f"{'='*55}")
    except Exception as e:
        print(f"⚠️  ngrok error: {e}")

    # 4. Background refresh
    threading.Thread(target=background_refresh, daemon=True).start()

    # 5. Run Flask
    print(f"\n🚀 Bridge running — press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)
