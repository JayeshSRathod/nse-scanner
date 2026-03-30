"""
nse_technical_filters.py — Technical Signal Scoring Engine
============================================================
Calculates a 0-10 signal score for each stock based on:

    HMA trend aligned       +2 pts  (HARD REQUIRED — score = 0 if fails)
    Volume buildup          +2 pts
    Price breakout          +2 pts
    RSI sweet spot          +1 pt
    MACD confirming         +1 pt
    Near 52W high           +1 pt
    RR >= 2.0               +1 pt
    ─────────────────────────────
    MAX SCORE               10 pts

Output tiers:
    Score  0-4  : No signal       — excluded from output
    Score  5-7  : Watchlist       — monitor, wait for entry
    Score  8-10 : HIGH CONVICTION — strong setup, act on it

HMA Settings: HMA 20 (short) + HMA 55 (medium)
RR Target    : 2x the risk from entry to stop
Stop         : Below HMA 55 OR 5-day low (whichever is closer)

Usage:
    from nse_technical_filters import score_all_stocks
    results = score_all_stocks(price_history_df, scan_date, filters)
"""

import numpy as np
import pandas as pd
import logging
import sys
import os
from datetime import date

log = logging.getLogger(__name__)

# ── INDICATOR SETTINGS ────────────────────────────────────────
HMA_FAST        = 20      # HMA 20 — short term momentum
HMA_SLOW        = 55      # HMA 55 — medium term trend
RSI_PERIOD      = 14
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9
ATR_PERIOD      = 14

# ── SIGNAL THRESHOLDS ─────────────────────────────────────────
RSI_MIN         = 55.0    # RSI below this = weak momentum
RSI_MAX         = 75.0    # RSI above this = overbought, chasing
VOL_MULTIPLIER  = 1.5     # 5-day avg volume must be > 1.5x 20-day avg
BREAKOUT_DAYS   = 20      # Close must be above N-day high
HMA_CROSS_DAYS  = 5       # HMA20 must have crossed HMA55 within N days
MIN_RR          = 2.0     # Minimum reward-to-risk ratio
W52_HIGH_PCT    = 0.90    # Stock within 90% of 52W high = near high

# ── SCORE WEIGHTS ─────────────────────────────────────────────
SCORE_HMA       = 2       # Hard required
SCORE_VOLUME    = 2
SCORE_BREAKOUT  = 2
SCORE_RSI       = 1
SCORE_MACD      = 1
SCORE_W52       = 1
SCORE_RR        = 1
MAX_SCORE       = 10

# ── OUTPUT TIERS ─────────────────────────────────────────────
TIER_HIGH_CONVICTION = 8   # Score >= 8 = HIGH CONVICTION
TIER_WATCHLIST       = 5   # Score >= 5 = Watchlist
TIER_NO_SIGNAL       = 0   # Score < 5  = excluded


# ═════════════════════════════════════════════════════════════
# INDICATOR CALCULATIONS
# ═════════════════════════════════════════════════════════════

def wma(series: pd.Series, period: int) -> pd.Series:
    """
    Weighted Moving Average.
    Most recent value gets highest weight.
    Required building block for HMA.
    """
    weights = np.arange(1, period + 1, dtype=float)
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(),
        raw=True
    )


def hma(series: pd.Series, period: int) -> pd.Series:
    """
    Hull Moving Average (HMA).
    Formula: WMA(2 * WMA(n/2) - WMA(n), sqrt(n))

    Much faster than EMA/SMA at detecting trend changes.
    Minimal lag — ideal for 1-3 month momentum trades.

    Args:
        series : price series (close prices)
        period : HMA period (20 or 55)

    Returns:
        HMA series (same index as input)
    """
    half   = period // 2
    sq     = int(round(np.sqrt(period)))

    wma_half = wma(series, half)
    wma_full = wma(series, period)

    raw_hma  = 2 * wma_half - wma_full
    return wma(raw_hma, sq)


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """
    Relative Strength Index.
    Uses Wilder's smoothing (standard method).

    Returns:
        RSI series 0-100
    """
    delta  = series.diff()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series,
         fast: int   = MACD_FAST,
         slow: int   = MACD_SLOW,
         signal: int = MACD_SIGNAL) -> pd.DataFrame:
    """
    MACD — Moving Average Convergence Divergence.

    Returns DataFrame with columns:
        macd_line    : fast EMA - slow EMA
        signal_line  : EMA of macd_line
        histogram    : macd_line - signal_line
    """
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    sig_line   = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - sig_line

    return pd.DataFrame({
        "macd_line"   : macd_line,
        "signal_line" : sig_line,
        "histogram"   : histogram,
    })


def atr(high: pd.Series, low: pd.Series,
        close: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    """
    Average True Range.
    Used for stop loss and RR calculation.

    True Range = max of:
        High - Low
        abs(High - Previous Close)
        abs(Low  - Previous Close)
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(span=period, adjust=False).mean()


# ═════════════════════════════════════════════════════════════
# SIGNAL CHECKS — One function per signal
# ═════════════════════════════════════════════════════════════

def check_hma_trend(closes: pd.Series) -> dict:
    """
    HMA Trend Check — HARD REQUIRED (+2 points or disqualified).

    Conditions (ALL must be true):
        1. HMA 20 is pointing UP (today > yesterday)
        2. Price is above HMA 55
        3. HMA 20 > HMA 55 (fast above slow = uptrend)

    Bonus context (not required but logged):
        - HMA 20 crossed above HMA 55 within last 5 days = fresh breakout

    Returns:
        dict with score, pass/fail, and detail values
    """
    result = {
        "score"          : 0,
        "pass"           : False,
        "hma20_today"    : None,
        "hma20_yest"     : None,
        "hma55_today"    : None,
        "hma20_rising"   : False,
        "price_above_55" : False,
        "hma20_above_55" : False,
        "fresh_cross"    : False,
        "detail"         : "",
    }

    if len(closes) < HMA_SLOW + 10:
        result["detail"] = f"insufficient data ({len(closes)} days, need {HMA_SLOW+10})"
        return result

    h20 = hma(closes, HMA_FAST)
    h55 = hma(closes, HMA_SLOW)

    if h20.isna().iloc[-1] or h55.isna().iloc[-1]:
        result["detail"] = "HMA calculation returned NaN"
        return result

    hma20_today = h20.iloc[-1]
    hma20_yest  = h20.iloc[-2]
    hma55_today = h55.iloc[-1]
    price_today = closes.iloc[-1]

    result["hma20_today"]    = round(hma20_today, 2)
    result["hma20_yest"]     = round(hma20_yest, 2)
    result["hma55_today"]    = round(hma55_today, 2)
    result["hma20_rising"]   = hma20_today > hma20_yest
    result["price_above_55"] = price_today > hma55_today
    result["hma20_above_55"] = hma20_today > hma55_today

    # Check fresh cross (HMA20 crossed above HMA55 within last N days)
    cross_window = min(HMA_CROSS_DAYS, len(h20) - 1)
    for i in range(1, cross_window + 1):
        if (h20.iloc[-i] > h55.iloc[-i] and
                h20.iloc[-i-1] <= h55.iloc[-i-1]):
            result["fresh_cross"] = True
            break

    # All three conditions required
    if (result["hma20_rising"] and
            result["price_above_55"] and
            result["hma20_above_55"]):
        result["pass"]   = True
        result["score"]  = SCORE_HMA
        cross_txt = " [FRESH CROSS]" if result["fresh_cross"] else ""
        result["detail"] = (
            f"HMA20={hma20_today:.2f} rising, "
            f"Price > HMA55={hma55_today:.2f}{cross_txt}"
        )
    else:
        fails = []
        if not result["hma20_rising"]:
            fails.append(f"HMA20 falling ({hma20_today:.2f}<{hma20_yest:.2f})")
        if not result["price_above_55"]:
            fails.append(f"Price {price_today:.2f} < HMA55 {hma55_today:.2f}")
        if not result["hma20_above_55"]:
            fails.append(f"HMA20 {hma20_today:.2f} < HMA55 {hma55_today:.2f}")
        result["detail"] = " | ".join(fails)

    return result


def check_volume_buildup(volumes: pd.Series,
                         delivery_pcts: pd.Series) -> dict:
    """
    Volume Buildup Check (+2 points).

    Institutional accumulation signature:
        1. 5-day avg volume > 1.5x the 20-day avg volume
        2. Delivery % rising (3-day avg > 10-day avg)
           = real buying, not just speculation

    Args:
        volumes       : daily volume series
        delivery_pcts : daily delivery % series

    Returns:
        dict with score and detail
    """
    result = {
        "score"         : 0,
        "pass"          : False,
        "vol_5d_avg"    : None,
        "vol_20d_avg"   : None,
        "vol_ratio"     : None,
        "del_3d_avg"    : None,
        "del_10d_avg"   : None,
        "del_rising"    : False,
        "detail"        : "",
    }

    if len(volumes) < 20:
        result["detail"] = "insufficient data for volume check"
        return result

    vol_5d  = volumes.iloc[-5:].mean()
    vol_20d = volumes.iloc[-20:].mean()

    if vol_20d == 0:
        result["detail"] = "zero base volume"
        return result

    vol_ratio = vol_5d / vol_20d

    result["vol_5d_avg"]  = int(vol_5d)
    result["vol_20d_avg"] = int(vol_20d)
    result["vol_ratio"]   = round(vol_ratio, 2)

    # Delivery rising check
    del_rising = False
    if len(delivery_pcts.dropna()) >= 10:
        del_3d  = delivery_pcts.iloc[-3:].mean()
        del_10d = delivery_pcts.iloc[-10:].mean()
        del_rising = del_3d > del_10d
        result["del_3d_avg"]  = round(del_3d, 1)
        result["del_10d_avg"] = round(del_10d, 1)
        result["del_rising"]  = del_rising

    vol_pass = vol_ratio >= VOL_MULTIPLIER

    if vol_pass and del_rising:
        result["pass"]   = True
        result["score"]  = SCORE_VOLUME
        result["detail"] = (
            f"Vol ratio {vol_ratio:.2f}x (5D>{VOL_MULTIPLIER}x 20D) + "
            f"Delivery rising ({result['del_3d_avg']}% > {result['del_10d_avg']}%)"
        )
    elif vol_pass:
        # Volume up but delivery not rising — give 1 point
        result["pass"]   = True
        result["score"]  = 1
        result["detail"] = (
            f"Vol ratio {vol_ratio:.2f}x — delivery not rising "
            f"(3D={result.get('del_3d_avg','?')}% vs 10D={result.get('del_10d_avg','?')}%)"
        )
    else:
        result["detail"] = (
            f"Vol ratio {vol_ratio:.2f}x < {VOL_MULTIPLIER}x required"
        )

    return result


def check_price_breakout(closes: pd.Series,
                         highs: pd.Series,
                         avg_prices: pd.Series) -> dict:
    """
    Price Breakout Check (+2 points).

    Conditions:
        1. Close > 20-day high  (price breakout above resistance)
        2. Close > today's VWAP (avg_price) — buyers in control

    Both required for full 2 points.
    Only condition 1 = 1 point.

    Args:
        closes     : daily close prices
        highs      : daily high prices
        avg_prices : VWAP / avg_price from bhavdata

    Returns:
        dict with score and detail
    """
    result = {
        "score"           : 0,
        "pass"            : False,
        "high_20d"        : None,
        "above_20d_high"  : False,
        "above_vwap"      : False,
        "detail"          : "",
    }

    if len(closes) < BREAKOUT_DAYS:
        result["detail"] = f"insufficient data ({len(closes)} days)"
        return result

    close_today = closes.iloc[-1]
    # 20-day high excludes today (compare to prior resistance)
    high_20d    = highs.iloc[-BREAKOUT_DAYS:-1].max()
    vwap_today  = avg_prices.iloc[-1] if not avg_prices.isna().iloc[-1] else None

    result["high_20d"]       = round(high_20d, 2)
    result["above_20d_high"] = close_today > high_20d
    result["above_vwap"]     = (vwap_today is not None and
                                close_today > vwap_today)

    if result["above_20d_high"] and result["above_vwap"]:
        result["pass"]   = True
        result["score"]  = SCORE_BREAKOUT
        result["detail"] = (
            f"Close {close_today:.2f} > 20D high {high_20d:.2f} "
            f"+ above VWAP {vwap_today:.2f}"
        )
    elif result["above_20d_high"]:
        result["pass"]   = True
        result["score"]  = 1
        result["detail"] = (
            f"Close {close_today:.2f} > 20D high {high_20d:.2f} "
            f"(VWAP not confirmed)"
        )
    else:
        result["detail"] = (
            f"Close {close_today:.2f} <= 20D high {high_20d:.2f} — no breakout"
        )

    return result


def check_rsi(closes: pd.Series) -> dict:
    """
    RSI Sweet Spot Check (+1 point).

    Sweet spot: RSI 55-75
        < 55 = momentum too weak, trend not established
        > 75 = overbought, chasing extended move
        55-75 = trending but still has room to run

    Returns:
        dict with score and RSI value
    """
    result = {
        "score"  : 0,
        "pass"   : False,
        "rsi"    : None,
        "detail" : "",
    }

    if len(closes) < RSI_PERIOD + 10:
        result["detail"] = "insufficient data for RSI"
        return result

    rsi_series = rsi(closes)
    rsi_val    = rsi_series.iloc[-1]

    if pd.isna(rsi_val):
        result["detail"] = "RSI calculation returned NaN"
        return result

    result["rsi"] = round(rsi_val, 1)

    if RSI_MIN <= rsi_val <= RSI_MAX:
        result["pass"]   = True
        result["score"]  = SCORE_RSI
        result["detail"] = f"RSI {rsi_val:.1f} in sweet spot ({RSI_MIN}-{RSI_MAX})"
    elif rsi_val > RSI_MAX:
        result["detail"] = f"RSI {rsi_val:.1f} overbought (> {RSI_MAX})"
    else:
        result["detail"] = f"RSI {rsi_val:.1f} weak (< {RSI_MIN})"

    return result


def check_macd(closes: pd.Series) -> dict:
    """
    MACD Confirming Check (+1 point).

    Conditions (ALL required):
        1. MACD line > signal line  (bullish crossover)
        2. Histogram increasing (momentum accelerating)
           today's bar > yesterday's bar

    Returns:
        dict with score and MACD values
    """
    result = {
        "score"          : 0,
        "pass"           : False,
        "macd_line"      : None,
        "signal_line"    : None,
        "histogram"      : None,
        "hist_rising"    : False,
        "detail"         : "",
    }

    if len(closes) < MACD_SLOW + MACD_SIGNAL + 5:
        result["detail"] = "insufficient data for MACD"
        return result

    m = macd(closes)

    if m["macd_line"].isna().iloc[-1]:
        result["detail"] = "MACD calculation returned NaN"
        return result

    macd_val = m["macd_line"].iloc[-1]
    sig_val  = m["signal_line"].iloc[-1]
    hist_now = m["histogram"].iloc[-1]
    hist_prv = m["histogram"].iloc[-2]

    result["macd_line"]   = round(macd_val, 4)
    result["signal_line"] = round(sig_val, 4)
    result["histogram"]   = round(hist_now, 4)
    result["hist_rising"] = hist_now > hist_prv

    bullish = macd_val > sig_val
    rising  = hist_now > hist_prv

    if bullish and rising:
        result["pass"]   = True
        result["score"]  = SCORE_MACD
        result["detail"] = (
            f"MACD {macd_val:.4f} > Signal {sig_val:.4f}, "
            f"histogram rising ({hist_prv:.4f} -> {hist_now:.4f})"
        )
    elif bullish:
        result["detail"] = (
            f"MACD bullish but histogram slowing "
            f"({hist_prv:.4f} -> {hist_now:.4f})"
        )
    else:
        result["detail"] = (
            f"MACD {macd_val:.4f} < Signal {sig_val:.4f} — bearish"
        )

    return result


def check_52w_high(close_today: float, w52_high: float) -> dict:
    """
    Near 52-Week High Check (+1 point).

    Condition: Close >= 90% of 52-week high
    Stocks near their annual high = strong institutional demand.

    Args:
        close_today : today's close price
        w52_high    : 52-week adjusted high (from week52 table)

    Returns:
        dict with score and detail
    """
    result = {
        "score"       : 0,
        "pass"        : False,
        "w52_high"    : w52_high,
        "pct_of_high" : None,
        "detail"      : "",
    }

    if not w52_high or w52_high == 0:
        result["detail"] = "52W high data not available"
        return result

    pct = close_today / w52_high
    result["pct_of_high"] = round(pct * 100, 1)

    if pct >= W52_HIGH_PCT:
        result["pass"]   = True
        result["score"]  = SCORE_W52
        result["detail"] = (
            f"Close {close_today:.2f} = {pct*100:.1f}% of "
            f"52W high {w52_high:.2f}"
        )
    else:
        result["detail"] = (
            f"Close {close_today:.2f} = {pct*100:.1f}% of "
            f"52W high {w52_high:.2f} (need >= {W52_HIGH_PCT*100:.0f}%)"
        )

    return result


def check_rr(closes: pd.Series,
             highs: pd.Series,
             lows: pd.Series,
             h55: pd.Series) -> dict:
    """
    Risk/Reward Ratio Check (+1 point).

    Entry  = today's close
    Stop   = max(HMA55, 5-day low)  → whichever is higher (tighter stop)
    Target = Entry + (2 x Risk)
    RR     = Risk must give >= 2x reward to pass

    Logic: If stop is Rs 40 away, target must be Rs 80 away.
    Stock must have room to reach target without major resistance.

    Args:
        closes : close price series
        highs  : high price series
        lows   : low price series
        h55    : pre-calculated HMA55 series

    Returns:
        dict with score, entry, stop, target, RR value
    """
    result = {
        "score"  : 0,
        "pass"   : False,
        "entry"  : None,
        "stop"   : None,
        "target" : None,
        "risk"   : None,
        "reward" : None,
        "rr"     : None,
        "detail" : "",
    }

    if len(closes) < 10 or h55.isna().iloc[-1]:
        result["detail"] = "insufficient data for RR"
        return result

    entry      = closes.iloc[-1]
    hma55_val  = h55.iloc[-1]
    low_5d     = lows.iloc[-5:].min()

    # Stop = higher of HMA55 and 5-day low (tighter stop = better RR)
    stop = max(hma55_val, low_5d)

    # If stop is above entry, signal is invalid
    if stop >= entry:
        result["detail"] = (
            f"Stop {stop:.2f} >= Entry {entry:.2f} — invalid setup"
        )
        return result

    risk   = entry - stop
    reward = risk * MIN_RR
    target = entry + reward
    rr     = reward / risk  # = MIN_RR always, but explicit for logging

    result["entry"]  = round(entry, 2)
    result["stop"]   = round(stop, 2)
    result["target"] = round(target, 2)
    result["risk"]   = round(risk, 2)
    result["reward"] = round(reward, 2)
    result["rr"]     = round(rr, 2)

    if rr >= MIN_RR:
        result["pass"]   = True
        result["score"]  = SCORE_RR
        result["detail"] = (
            f"Entry={entry:.2f} Stop={stop:.2f} "
            f"Target={target:.2f} RR={rr:.1f}x"
        )
    else:
        result["detail"] = (
            f"RR {rr:.1f}x < {MIN_RR}x required"
        )

    return result


# ═════════════════════════════════════════════════════════════
# SCORE ONE STOCK
# ═════════════════════════════════════════════════════════════

def score_stock(symbol: str,
                stock_df: pd.DataFrame,
                w52_high: float = None) -> dict:
    """
    Calculate full 0-10 signal score for one stock.

    Args:
        symbol   : stock symbol string
        stock_df : DataFrame with columns:
                   date, close, high, low, volume,
                   delivery_pct, avg_price
                   Sorted by date ascending.
        w52_high : 52-week adjusted high (from week52 table)

    Returns:
        Full result dict with score, tier, all signal details
    """
    result = {
        "symbol"    : symbol,
        "score"     : 0,
        "tier"      : "no_signal",
        "conviction": "",
        "hma"       : {},
        "volume"    : {},
        "breakout"  : {},
        "rsi"       : {},
        "macd"      : {},
        "w52"       : {},
        "rr"        : {},
        # Summary fields for output table
        "hma20"     : None,
        "hma55"     : None,
        "rsi_val"   : None,
        "macd_hist" : None,
        "vol_ratio" : None,
        "entry"     : None,
        "stop"      : None,
        "target"    : None,
        "rr_val"    : None,
        "fresh_cross": False,
    }

    if stock_df is None or len(stock_df) < HMA_SLOW + 5:
        result["tier"]   = "no_signal"
        result["detail"] = f"insufficient history ({len(stock_df) if stock_df is not None else 0} days)"
        return result

    closes   = stock_df["close"].astype(float)
    highs    = stock_df["high"].astype(float)  if "high"         in stock_df.columns else closes
    lows     = stock_df["low"].astype(float)   if "low"          in stock_df.columns else closes
    volumes  = stock_df["volume"].astype(float) if "volume"       in stock_df.columns else pd.Series()
    del_pcts = stock_df["delivery_pct"].astype(float) if "delivery_pct" in stock_df.columns else pd.Series()
    avg_px   = stock_df["avg_price"].astype(float) if "avg_price"  in stock_df.columns else closes

    # Pre-calculate HMA55 for RR check
    h55 = hma(closes, HMA_SLOW)

    # ── Run all checks ──
    hma_res  = check_hma_trend(closes)
    vol_res  = check_volume_buildup(volumes, del_pcts)
    brk_res  = check_price_breakout(closes, highs, avg_px)
    rsi_res  = check_rsi(closes)
    macd_res = check_macd(closes)
    w52_res  = check_52w_high(closes.iloc[-1], w52_high or 0)
    rr_res   = check_rr(closes, highs, lows, h55)

    result["hma"]      = hma_res
    result["volume"]   = vol_res
    result["breakout"] = brk_res
    result["rsi"]      = rsi_res
    result["macd"]     = macd_res
    result["w52"]      = w52_res
    result["rr"]       = rr_res

    # ── HARD GATE: HMA must pass or score = 0 ──
    if not hma_res["pass"]:
        result["score"]  = 0
        result["tier"]   = "no_signal"
        result["detail"] = f"HMA FAIL: {hma_res['detail']}"
        return result

    # ── Sum scores ──
    total = (
        hma_res["score"]  +
        vol_res["score"]  +
        brk_res["score"]  +
        rsi_res["score"]  +
        macd_res["score"] +
        w52_res["score"]  +
        rr_res["score"]
    )

    result["score"] = min(total, MAX_SCORE)

    # ── Assign tier ──
    if result["score"] >= TIER_HIGH_CONVICTION:
        result["tier"]       = "high_conviction"
        result["conviction"] = "HIGH CONVICTION"
    elif result["score"] >= TIER_WATCHLIST:
        result["tier"]       = "watchlist"
        result["conviction"] = "Watchlist"
    else:
        result["tier"]       = "no_signal"
        result["conviction"] = ""

    # ── Populate summary fields ──
    result["hma20"]      = hma_res.get("hma20_today")
    result["hma55"]      = hma_res.get("hma55_today")
    result["fresh_cross"]= hma_res.get("fresh_cross", False)
    result["rsi_val"]    = rsi_res.get("rsi")
    result["macd_hist"]  = macd_res.get("histogram")
    result["vol_ratio"]  = vol_res.get("vol_ratio")
    result["entry"]      = rr_res.get("entry")
    result["stop"]       = rr_res.get("stop")
    result["target"]     = rr_res.get("target")
    result["rr_val"]     = rr_res.get("rr")

    return result


# ═════════════════════════════════════════════════════════════
# SCORE ALL STOCKS — Main entry point
# ═════════════════════════════════════════════════════════════

def score_all_stocks(price_df: pd.DataFrame,
                     filtered_symbols: list,
                     scan_date: date,
                     w52_map: dict = None) -> pd.DataFrame:
    """
    Score all filtered stocks and return ranked results.

    Args:
        price_df         : full price history DataFrame from DB
                           columns: symbol, date, close, high, low,
                                    volume, delivery_pct, avg_price
        filtered_symbols : list of symbols that passed basic filters
        scan_date        : date being scanned
        w52_map          : {symbol: (high, low)} from week52 table

    Returns:
        DataFrame sorted by score desc, filtered to score >= 5
        with all signal details and trade plan columns
    """
    w52_map = w52_map or {}

    # ── Prepare price data ──
    price_df = price_df.copy()
    price_df["date"] = pd.to_datetime(price_df["date"])
    price_df = price_df.sort_values(["symbol", "date"])

    results      = []
    scored       = 0
    disqualified = 0
    no_data      = 0

    print(f"\n  Scoring {len(filtered_symbols)} stocks...")

    for i, symbol in enumerate(filtered_symbols):
        if i % 100 == 0 and i > 0:
            print(f"  Progress: {i}/{len(filtered_symbols)} "
                  f"scored={scored} disq={disqualified}")

        stock_df = price_df[price_df["symbol"] == symbol].copy()

        if stock_df.empty or len(stock_df) < HMA_SLOW + 5:
            no_data += 1
            continue

        w52_high = w52_map.get(symbol, (None, None))
        if isinstance(w52_high, tuple):
            w52_high = w52_high[0]

        res = score_stock(symbol, stock_df, w52_high)

        if res["score"] >= TIER_WATCHLIST:
            results.append(res)
            scored += 1
        else:
            disqualified += 1

    print(f"\n  Scoring complete:")
    print(f"    Scored (>= 5)  : {scored}")
    print(f"    Disqualified   : {disqualified}")
    print(f"    No data        : {no_data}")

    if not results:
        print("  No stocks scored >= 5 today.")
        print("  Market may be in consolidation or downtrend.")
        print("  This is correct behaviour — do not force trades.")
        return pd.DataFrame()

    # ── Build output DataFrame ──
    rows = []
    for r in results:
        rows.append({
            "symbol"      : r["symbol"],
            "score"       : r["score"],
            "conviction"  : r["conviction"],
            "hma20"       : r["hma20"],
            "hma55"       : r["hma55"],
            "fresh_cross" : r["fresh_cross"],
            "rsi"         : r["rsi_val"],
            "macd_hist"   : r["macd_hist"],
            "vol_ratio"   : r["vol_ratio"],
            "entry"       : r["entry"],
            "stop"        : r["stop"],
            "target"      : r["target"],
            "rr"          : r["rr_val"],
            # Signal breakdown
            "pts_hma"     : r["hma"]["score"],
            "pts_vol"     : r["volume"]["score"],
            "pts_brk"     : r["breakout"]["score"],
            "pts_rsi"     : r["rsi"]["score"],
            "pts_macd"    : r["macd"]["score"],
            "pts_52w"     : r["w52"]["score"],
            "pts_rr"      : r["rr"]["score"],
            # Signal details
            "hma_detail"  : r["hma"].get("detail", ""),
            "vol_detail"  : r["volume"].get("detail", ""),
            "brk_detail"  : r["breakout"].get("detail", ""),
            "rsi_detail"  : r["rsi"].get("detail", ""),
            "macd_detail" : r["macd"].get("detail", ""),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "rank"

    high_conv = (df["score"] >= TIER_HIGH_CONVICTION).sum()
    watchlist = (df["score"] < TIER_HIGH_CONVICTION).sum()

    log.info(
        f"Technical scoring: {len(df)} stocks qualify | "
        f"HIGH CONVICTION={high_conv} | Watchlist={watchlist}"
    )

    print(f"\n  Results:")
    print(f"    HIGH CONVICTION (8-10) : {high_conv} stocks")
    print(f"    Watchlist       (5-7)  : {watchlist} stocks")

    return df


# ═════════════════════════════════════════════════════════════
# PRINT TECHNICAL RESULTS
# ═════════════════════════════════════════════════════════════

def print_technical_results(df: pd.DataFrame, scan_date: date):
    """Print technical scanner results in clean table format."""

    if df.empty:
        print("\n  No stocks with score >= 5 today.")
        return

    high_conv = df[df["score"] >= TIER_HIGH_CONVICTION]
    watchlist = df[df["score"] < TIER_HIGH_CONVICTION]

    def print_section(title, section_df):
        if section_df.empty:
            return
        print(f"\n  {'─'*72}")
        print(f"  {title}")
        print(f"  {'─'*72}")
        print(f"  {'#':<4} {'Symbol':<12} {'Score':>5} "
              f"{'HMA20':>7} {'HMA55':>7} {'RSI':>5} "
              f"{'VolX':>5} {'Entry':>8} {'Stop':>8} "
              f"{'Target':>8} {'RR':>4}  Signal Pts")
        print(f"  {'─'*72}")

        for rank, row in section_df.iterrows():
            cross_flag = "[X]" if row.get("fresh_cross") else "   "
            pts = (f"H{int(row['pts_hma'])} V{int(row['pts_vol'])} "
                   f"B{int(row['pts_brk'])} R{int(row['pts_rsi'])} "
                   f"M{int(row['pts_macd'])} W{int(row['pts_52w'])} "
                   f"RR{int(row['pts_rr'])}")

            print(
                f"  {rank:<4} {str(row['symbol']):<12} {row['score']:>5} "
                f"{row['hma20'] or 0:>7.2f} {row['hma55'] or 0:>7.2f} "
                f"{row['rsi'] or 0:>5.1f} "
                f"{row['vol_ratio'] or 0:>5.2f} "
                f"{row['entry'] or 0:>8.2f} {row['stop'] or 0:>8.2f} "
                f"{row['target'] or 0:>8.2f} "
                f"{row['rr'] or 0:>4.1f}  "
                f"{pts} {cross_flag}"
            )

    print(f"\n{'#'*72}")
    print(f"  NSE TECHNICAL SCANNER — {scan_date.strftime('%d-%b-%Y')}")
    print(f"  Scoring: HMA(2) + Volume(2) + Breakout(2) + RSI(1) + MACD(1) + 52W(1) + RR(1)")
    print(f"  [X] = Fresh HMA20 x HMA55 crossover within 5 days")
    print(f"  Pts: H=HMA V=Vol B=Breakout R=RSI M=MACD W=52W RR=RiskReward")
    print(f"{'#'*72}")

    print_section("HIGH CONVICTION  (Score 8-10)", high_conv)
    print_section("WATCHLIST        (Score 5-7) ", watchlist)

    print(f"\n  {'─'*72}")
    print(f"  Total signals  : {len(df)}")
    print(f"  Trade plan     : Entry = today's close | Stop = HMA55 or 5D low")
    print(f"                   Target = Entry + (2 x Risk) | Min RR = {MIN_RR}x")
    print(f"  NOTE: These are signals, not recommendations.")
    print(f"        Always confirm with your own analysis before trading.")
    print(f"{'#'*72}\n")

"""
nse_technical_filters.py — ADDITION
=====================================
INSTRUCTION: Open your existing nse_technical_filters.py
             Find the line:  if __name__ == "__main__":
             Paste EVERYTHING BELOW just ABOVE that line
             Do NOT delete anything existing
"""

# ═══════════════════════════════════════════════════════════════
# PASTE ABOVE  if __name__ == "__main__":
# ═══════════════════════════════════════════════════════════════

# ── CATEGORY DEFINITIONS ──────────────────────────────────────

CATEGORY_META = {
    "rising": {
        "icon":  "📈",
        "label": "Consistently Rising",
        "desc":  "Steady upward momentum over 1-3 months",
    },
    "uptrend": {
        "icon":  "🚀",
        "label": "Clear Uptrend Confirmed",
        "desc":  "Technical breakout confirmed with volume",
    },
    "peak": {
        "icon":  "🔝",
        "label": "Close to Their Peak",
        "desc":  "Near 52-week highs — strong institutional demand",
    },
    "recovering": {
        "icon":  "📉",
        "label": "Recovering from a Fall",
        "desc":  "Bouncing back — early recovery signal",
    },
    "safer": {
        "icon":  "🛡️",
        "label": "Safer Bets with Good Reward",
        "desc":  "Lower risk, consistent returns",
    },
}

CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]


def assign_category(row: dict,
                    return_1m: float,
                    return_2m: float,
                    return_3m: float,
                    delivery_pct: float = 0,
                    w52_high: float = 0,
                    close: float = 0) -> str:
    """
    Assign a layman-friendly category to one stock.

    Priority (first match wins):
        1. uptrend    — fresh HMA cross OR breakout + volume
        2. recovering — 1M return > 3M return (bounce back)
        3. peak       — close >= 90% of 52W high
        4. safer      — high delivery + decent score + good RR
        5. rising     — all returns positive (default)

    Args:
        row          : dict with keys from score_all_stocks
        return_1m    : decimal (0.05 = 5%)
        return_2m    : decimal
        return_3m    : decimal
        delivery_pct : e.g. 58.3
        w52_high     : 52-week adjusted high
        close        : today's close price

    Returns:
        category string
    """
    fresh_cross = bool(row.get("fresh_cross", False))
    pts_brk     = int(row.get("pts_brk", 0))
    pts_vol     = int(row.get("pts_vol", 0))
    score       = int(row.get("score", 0))
    rr          = float(row.get("rr", 0) or 0)

    # 1. UPTREND — fresh cross or breakout + volume
    if fresh_cross:
        return "uptrend"
    if pts_brk >= 2 and pts_vol >= 2:
        return "uptrend"

    # 2. RECOVERING — recent bounce stronger than long-term
    if (return_1m > return_3m + 0.02) and (return_3m < 0.10):
        return "recovering"

    # 3. PEAK — near 52-week high
    if w52_high > 0 and close > 0:
        pct_of_high = close / w52_high
        if pct_of_high >= W52_HIGH_PCT:
            return "peak"

    # 4. SAFER — high delivery, decent RR, good score
    if delivery_pct >= 55 and score >= 6 and rr >= 2.0:
        return "safer"

    # 5. RISING — all positive (default for quality stocks)
    if return_1m > 0 and return_2m > 0 and return_3m > 0:
        return "rising"

    return "rising"


def assign_categories_bulk(scored_df, returns_df, w52_map: dict = None) -> list:
    """
    Assign categories to all scored stocks.

    Args:
        scored_df  : DataFrame from score_all_stocks()
        returns_df : DataFrame with return_1m, return_2m, return_3m
        w52_map    : {symbol: (high, low)}

    Returns:
        List of category strings, same order as scored_df
    """
    w52_map = w52_map or {}
    categories = []

    for _, row in scored_df.iterrows():
        symbol = row["symbol"]

        ret_row = returns_df[returns_df["symbol"] == symbol]
        if ret_row.empty:
            categories.append("rising")
            continue

        ret = ret_row.iloc[0]
        r1m = float(ret.get("return_1m", 0) if "return_1m" in ret.index else 0)
        r2m = float(ret.get("return_2m", 0) if "return_2m" in ret.index else 0)
        r3m = float(ret.get("return_3m", 0) if "return_3m" in ret.index else 0)
        dlv = float(ret.get("delivery_pct", 0))
        cls = float(ret.get("close", 0))

        w52_high = 0
        w52_val = w52_map.get(symbol)
        if isinstance(w52_val, tuple):
            w52_high = w52_val[0] or 0
        elif w52_val:
            w52_high = float(w52_val)

        cat = assign_category(
            row=row.to_dict(),
            return_1m=r1m, return_2m=r2m, return_3m=r3m,
            delivery_pct=dlv, w52_high=w52_high, close=cls,
        )
        categories.append(cat)

    return categories

# ═════════════════════════════════════════════════════════════
# SELF TEST
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 58)
    print("  nse_technical_filters.py -- Indicator Self Test")
    print("=" * 58)

    # Generate synthetic price data for testing
    np.random.seed(42)
    n   = 200
    px  = 500 + np.cumsum(np.random.randn(n) * 3)
    px  = np.maximum(px, 50)

    closes  = pd.Series(px)
    highs   = closes * 1.01
    lows    = closes * 0.99
    volumes = pd.Series(np.random.randint(50000, 200000, n), dtype=float)
    del_pct = pd.Series(np.random.uniform(35, 70, n))
    avg_px  = closes * 0.998

    stock_df = pd.DataFrame({
        "close"        : closes,
        "high"         : highs,
        "low"          : lows,
        "volume"       : volumes,
        "delivery_pct" : del_pct,
        "avg_price"    : avg_px,
    })

    print(f"\n  Test stock: 200 days of synthetic data")
    print(f"  Close range: {closes.min():.2f} - {closes.max():.2f}")

    res = score_stock("TESTSTOCK", stock_df, w52_high=closes.max())

    print(f"\n  SCORE   : {res['score']} / {MAX_SCORE}")
    print(f"  TIER    : {res['tier']}")
    print(f"\n  Signal breakdown:")
    print(f"    HMA      : {res['hma']['score']} pts  -- {res['hma']['detail']}")
    print(f"    Volume   : {res['volume']['score']} pts  -- {res['volume']['detail']}")
    print(f"    Breakout : {res['breakout']['score']} pts  -- {res['breakout']['detail']}")
    print(f"    RSI      : {res['rsi']['score']} pts  -- {res['rsi']['detail']}")
    print(f"    MACD     : {res['macd']['score']} pts  -- {res['macd']['detail']}")
    print(f"    52W High : {res['w52']['score']} pts  -- {res['w52']['detail']}")
    print(f"    RR       : {res['rr']['score']} pts  -- {res['rr']['detail']}")

    print(f"\n  Trade plan:")
    print(f"    Entry  : {res['entry']}")
    print(f"    Stop   : {res['stop']}")
    print(f"    Target : {res['target']}")
    print(f"    RR     : {res['rr_val']}x")
    print("=" * 58)
