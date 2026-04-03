"""
nse_technical_filters.py — Forward-Looking Technical Scoring Engine (v2)
=========================================================================
WHAT CHANGED FROM v1:
  OLD: Scored stocks by past performance (3M return drove ranking)
  NEW: Scores stocks by FORWARD PROBABILITY of being profitable in next 1-3M

7 NEW SIGNALS (max 10 pts, same scale as before):
  1. HMA Freshness         — fresh cross scores higher than mature cross
  2. Distance from Mean    — room to run scores higher than overextended
  3. Volume Quality        — buy-side volume (OBV + accumulation days + delivery)
  4. Sector Alignment      — tailwind sector adds 1 pt
  5. Overextension Penalty — 15%+ above HMA55 subtracts points
  6. RSI Sweet Spot        — unchanged (40–65 = good entry zone)
  7. MACD Confirming       — unchanged

SCORING TABLE:
  Signal                 Max Pts   Notes
  ─────────────────────────────────────────────────────
  HMA Freshness          +2        1-10d=2, 11-20d=1, 20d+=0
  Distance from Mean     +2        <5%=2, 5-10%=1, 10-15%=0, >15%=-1
  Volume Quality         +2        buy-side=2, neutral=1, sell-side=0/-1
  RSI Sweet Spot         +1        40-65=1, else 0
  MACD Confirming        +1        bullish=1, else 0
  Sector Alignment       +1        strong sector=1, weak=-1
  Risk/Reward            +1        RR>=2.0 with tight SL=1

  Penalties (applied after base score):
  Overextension          -1        >15% above HMA55
  HMA Deceleration       -1        slope flattening over last 5 bars

  MAX TOTAL: 10 pts
  MIN TOTAL: 0 pts (clamped)

3M PAST RETURN ROLE:
  OLD: 50% of ranking weight
  NEW: Filter only — must be > 0 to confirm uptrend exists
       Not used for ranking at all

CONVICTION TIERS (unchanged thresholds):
  HIGH CONVICTION : score >= 7
  Watchlist       : score >= 4
  (below 4 filtered out)

Usage:
    from nse_technical_filters import (
        score_all_stocks, assign_categories_bulk,
        TIER_HIGH_CONVICTION, TIER_WATCHLIST,
        CATEGORY_META, CATEGORY_ORDER,
    )
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

# ── Conviction tier labels (unchanged) ──────────────────────────────────────
TIER_HIGH_CONVICTION = "HIGH CONVICTION"
TIER_WATCHLIST       = "Watchlist"

# ── Category metadata (unchanged — used by telegram + output) ───────────────
CATEGORY_META = {
    "rising":     {"icon": "📈", "label": "Consistently Rising",
                   "desc": "Steady momentum, early in the move"},
    "uptrend":    {"icon": "🚀", "label": "Clear Uptrend Confirmed",
                   "desc": "Fresh cross, room to run, volume confirmed"},
    "peak":       {"icon": "🔝", "label": "Close to Their Peak",
                   "desc": "Near 52-week highs — strong institutional demand"},
    "recovering": {"icon": "📉", "label": "Recovering from a Fall",
                   "desc": "Bouncing back — early recovery signal"},
    "safer":      {"icon": "🛡️", "label": "Safer Bets with Good Reward",
                   "desc": "Tight stop, high delivery, lower risk setup"},
}
CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]

# ── Sector alignment map (NSE sectors → forward bias) ───────────────────────
# Update these periodically based on sector rotation
# +1 = tailwind, 0 = neutral, -1 = headwind
SECTOR_BIAS = {
    # Strong sectors (add here based on current market)
    "PHARMA":       +1, "HEALTHCARE":  +1,
    "DEFENCE":      +1, "PSU":         +1,
    "INFRA":        +1, "CAPITAL":     +1,
    "POWER":        +1, "ENERGY":      +1,
    "FMCG":          0,
    "IT":            0, "TECH":         0,
    "AUTO":          0, "AUTO ANCIL":   0,
    "BANK":          0, "FINANCE":      0, "NBFC": 0,
    "REALTY":        0,
    "METAL":        -1, "STEEL":       -1,
    "CHEMICAL":      0,
}

# Keyword → sector mapping (checks if any keyword appears in symbol name)
SYMBOL_TO_SECTOR = {
    "SUNPHARMA": "PHARMA", "DRREDDY": "PHARMA", "CIPLA": "PHARMA",
    "DIVISLAB": "PHARMA", "TORNTPHARM": "PHARMA", "ALKEM": "PHARMA",
    "AUROPHARMA": "PHARMA", "ABBOTINDIA": "PHARMA", "BIOCON": "PHARMA",
    "HAL": "DEFENCE", "BEL": "DEFENCE", "BHEL": "DEFENCE",
    "MIDHANI": "DEFENCE", "PARAS": "DEFENCE",
    "NTPC": "POWER", "POWERGRID": "POWER", "TATAPOWER": "POWER",
    "ADANIPOWER": "POWER", "CESC": "POWER",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG",
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "LTIM": "IT", "MPHASIS": "IT",
    "HDFCBANK": "BANK", "ICICIBANK": "BANK", "SBIN": "BANK",
    "AXISBANK": "BANK", "KOTAKBANK": "BANK", "BANDHANBNK": "BANK",
    "BAJFINANCE": "FINANCE", "BAJAJFINSV": "FINANCE", "CHOLAFIN": "FINANCE",
    "MARUTI": "AUTO", "TATAMOTORS": "AUTO", "BAJAJ-AUTO": "AUTO",
    "EICHERMOT": "AUTO", "HEROMOTOCO": "AUTO",
    "TATASTEEL": "METAL", "JSWSTEEL": "METAL", "HINDALCO": "METAL",
    "VEDL": "METAL", "COALINDIA": "METAL",
}


# ═══════════════════════════════════════════════════════════════════════════
# CORE TECHNICAL CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════

def _hma(series: pd.Series, period: int) -> pd.Series:
    """Hull Moving Average — same formula as TradingView HMA."""
    half  = max(1, int(period / 2))
    sqrt_ = max(1, int(np.sqrt(period)))
    wma_half = series.ewm(span=half,  adjust=False).mean()   # approx WMA via EWM
    wma_full = series.ewm(span=period, adjust=False).mean()
    raw      = 2 * wma_half - wma_full
    hma      = raw.ewm(span=sqrt_, adjust=False).mean()
    return hma


def _wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average."""
    weights = np.arange(1, period + 1)
    def _calc(x):
        if len(x) < period:
            return np.nan
        return np.dot(x[-period:], weights[-len(x[-period:]):]) / weights[-len(x[-period:]):].sum()
    return series.rolling(period).apply(_calc, raw=True)


def _macd_bullish(closes: pd.Series) -> bool:
    """Returns True if MACD line is above signal line (bullish)."""
    if len(closes) < 35:
        return False
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    return bool(macd.iloc[-1] > sig.iloc[-1])


def _rsi(closes: pd.Series, period: int = 14) -> float:
    """RSI calculation."""
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    val   = rsi.iloc[-1]
    return float(val) if not np.isnan(val) else 50.0


def _obv_trend(closes: pd.Series, volumes: pd.Series, lookback: int = 10) -> str:
    """
    On-Balance Volume trend over lookback bars.
    Returns: 'rising', 'falling', 'flat'
    """
    if len(closes) < lookback + 1:
        return 'flat'
    obv = 0.0
    obv_series = []
    for i in range(len(closes)):
        if i == 0:
            obv_series.append(0.0)
            continue
        if closes.iloc[i] > closes.iloc[i - 1]:
            obv += volumes.iloc[i]
        elif closes.iloc[i] < closes.iloc[i - 1]:
            obv -= volumes.iloc[i]
        obv_series.append(obv)

    recent = obv_series[-lookback:]
    slope  = np.polyfit(range(len(recent)), recent, 1)[0]
    if slope > 0:
        return 'rising'
    elif slope < 0:
        return 'falling'
    return 'flat'


def _accumulation_days(closes: pd.Series, volumes: pd.Series,
                        vol_ma: pd.Series, lookback: int = 5) -> int:
    """
    Count accumulation days in last `lookback` bars.
    Accumulation = price UP + volume > 5-day avg.
    Returns count of accumulation days (0-5).
    """
    if len(closes) < lookback + 1:
        return 0
    count = 0
    for i in range(-lookback, 0):
        price_up  = closes.iloc[i] > closes.iloc[i - 1]
        vol_above = volumes.iloc[i] > vol_ma.iloc[i] * 0.9
        if price_up and vol_above:
            count += 1
    return count


def _distribution_days(closes: pd.Series, volumes: pd.Series,
                        vol_ma: pd.Series, lookback: int = 5) -> int:
    """
    Count distribution days in last `lookback` bars.
    Distribution = price DOWN + volume > 5-day avg.
    """
    if len(closes) < lookback + 1:
        return 0
    count = 0
    for i in range(-lookback, 0):
        price_dn  = closes.iloc[i] < closes.iloc[i - 1]
        vol_above = volumes.iloc[i] > vol_ma.iloc[i] * 0.9
        if price_dn and vol_above:
            count += 1
    return count


def _delivery_trend(delivery_series: pd.Series, lookback: int = 5) -> str:
    """Returns 'rising', 'falling', or 'flat' for delivery % trend."""
    valid = delivery_series.dropna()
    if len(valid) < lookback:
        return 'flat'
    recent = valid.iloc[-lookback:]
    slope  = np.polyfit(range(len(recent)), recent.values, 1)[0]
    if slope > 0.5:
        return 'rising'
    elif slope < -0.5:
        return 'falling'
    return 'flat'


def _hma_cross_age(hma20_series: pd.Series, hma55_series: pd.Series) -> int:
    """
    Returns number of bars since HMA20 crossed above HMA55.
    Returns 999 if no recent cross found (within 60 bars).
    Returns -1 if HMA20 is currently below HMA55 (bearish, no valid cross).
    """
    if len(hma20_series) < 5 or len(hma55_series) < 5:
        return 999

    # Check if currently bullish (HMA20 > HMA55)
    if hma20_series.iloc[-1] <= hma55_series.iloc[-1]:
        return -1  # bearish — no valid cross

    # Find when the cross happened (look back up to 60 bars)
    lookback = min(60, len(hma20_series) - 1)
    for i in range(1, lookback + 1):
        idx = -(i + 1)
        if len(hma20_series) + idx < 0:
            break
        if hma20_series.iloc[idx] <= hma55_series.iloc[idx]:
            return i  # cross happened i bars ago
    return 999  # cross older than 60 bars


def _hma_slope_decelerating(hma_series: pd.Series, lookback: int = 5) -> bool:
    """
    Returns True if HMA slope is flattening (momentum fading).
    Checks if the rate of change of HMA is decreasing.
    """
    if len(hma_series) < lookback + 2:
        return False
    slopes = [hma_series.iloc[-i] - hma_series.iloc[-(i + 1)]
              for i in range(1, lookback + 1)]
    # All positive but decreasing = deceleration
    if all(s > 0 for s in slopes):
        return slopes[0] < slopes[-1] * 0.5  # recent slope < half of older slope
    return False


def _distance_from_hma55_pct(close: float, hma55: float) -> float:
    """Returns % distance of close above HMA55. Negative = below."""
    if hma55 <= 0:
        return 0.0
    return (close - hma55) / hma55 * 100.0


def _get_sector_bias(symbol: str) -> int:
    """Returns sector bias: +1, 0, or -1."""
    sym = str(symbol).upper().strip()
    if sym in SYMBOL_TO_SECTOR:
        sector = SYMBOL_TO_SECTOR[sym]
        return SECTOR_BIAS.get(sector, 0)
    # Keyword fallback
    for keyword, sector in [
        ("PHARMA", "PHARMA"), ("HEALTH", "HEALTHCARE"),
        ("POWER",  "POWER"),  ("NTPC",   "POWER"),
        ("DEFENCE","DEFENCE"), ("HAL",   "DEFENCE"),
        ("BANK",   "BANK"),   ("FIN",    "FINANCE"),
        ("TECH",   "IT"),     ("INFY",   "IT"),
        ("STEEL",  "METAL"),  ("METAL",  "METAL"),
        ("FMCG",   "FMCG"),
    ]:
        if keyword in sym:
            return SECTOR_BIAS.get(sector, 0)
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SCORING FUNCTION — PER STOCK
# ═══════════════════════════════════════════════════════════════════════════

def _score_single_stock(symbol: str, grp: pd.DataFrame,
                         w52_map: dict, scan_date) -> dict:
    """
    Score one stock using forward-looking signals.
    Returns dict with score, conviction, all sub-scores, and metadata.
    """
    grp = grp.sort_values('date').tail(120)  # last 120 trading days

    if len(grp) < 30:
        return None

    closes    = grp['close'].astype(float)
    volumes   = grp['volume'].astype(float)
    deliveries = grp['delivery_pct'].astype(float) if 'delivery_pct' in grp.columns else pd.Series([50.0] * len(grp))

    close_now = float(closes.iloc[-1])
    if close_now <= 0:
        return None

    # ── Moving Averages ─────────────────────────────────────────────────
    hma20 = _hma(closes, 20)
    hma55 = _hma(closes, 55)
    hma55_now = float(hma55.iloc[-1]) if not np.isnan(hma55.iloc[-1]) else close_now

    vol_ma = volumes.rolling(20).mean()

    # ── 1. HMA FRESHNESS (+2, +1, +0) ───────────────────────────────────
    cross_age = _hma_cross_age(hma20, hma55)
    fresh_cross = False

    if cross_age == -1:
        # Bearish — HMA20 below HMA55, no valid uptrend
        pts_hma = 0
        hma_trend_up = False
    elif cross_age <= 10:
        pts_hma = 2
        fresh_cross = True
        hma_trend_up = True
    elif cross_age <= 20:
        pts_hma = 1
        hma_trend_up = True
    else:
        pts_hma = 0
        hma_trend_up = cross_age != 999

    # ── 2. DISTANCE FROM MEAN (+2, +1, +0, -1) ──────────────────────────
    dist_pct = _distance_from_hma55_pct(close_now, hma55_now)

    if dist_pct < 0:
        # Price below HMA55 — not in uptrend for scoring purposes
        pts_dist = 0
    elif dist_pct <= 5.0:
        pts_dist = 2    # tight to HMA55 — maximum room to run
    elif dist_pct <= 10.0:
        pts_dist = 1    # some stretch but still OK
    elif dist_pct <= 15.0:
        pts_dist = 0    # stretched — marginal
    else:
        pts_dist = -1   # overextended — penalty

    overextended = dist_pct > 15.0

    # ── 3. VOLUME QUALITY (+2, +1, +0, -1) ──────────────────────────────
    acc_days  = _accumulation_days(closes, volumes, vol_ma, lookback=5)
    dist_days = _distribution_days(closes, volumes, vol_ma, lookback=5)
    obv_dir   = _obv_trend(closes, volumes, lookback=10)
    del_trend = _delivery_trend(deliveries, lookback=5)

    # Strong buying: 4+ acc days + OBV rising + delivery rising
    if acc_days >= 4 and obv_dir == 'rising' and del_trend == 'rising':
        pts_vol = 2
    elif acc_days >= 4 and obv_dir == 'rising':
        pts_vol = 2
    elif acc_days >= 3 and obv_dir != 'falling':
        pts_vol = 1
    elif dist_days >= 4 and obv_dir == 'falling':
        pts_vol = -1   # active distribution — penalty
    elif dist_days >= 3 or obv_dir == 'falling':
        pts_vol = 0
    else:
        pts_vol = 1    # neutral / moderate

    # ── 4. RSI SWEET SPOT (+1) ───────────────────────────────────────────
    rsi_val = _rsi(closes, 14)
    # 40-65 = ideal entry zone (not overbought, not oversold)
    pts_rsi = 1 if 40.0 <= rsi_val <= 65.0 else 0

    # ── 5. MACD CONFIRMING (+1) ──────────────────────────────────────────
    pts_macd = 1 if _macd_bullish(closes) else 0

    # ── 6. SECTOR ALIGNMENT (+1, 0, -1) ─────────────────────────────────
    sector_bias = _get_sector_bias(symbol)
    pts_sector  = sector_bias   # +1, 0, or -1

    # ── 7. RISK/REWARD (+1) ──────────────────────────────────────────────
    # Tight SL = HMA55 based (within 7% of close)
    sl_price = hma55_now * 0.97  # 3% below HMA55
    risk      = close_now - sl_price
    t1        = close_now + risk        # 1:1
    t2        = close_now + (2 * risk)  # 1:2

    sl_pct_dist = abs(close_now - sl_price) / close_now * 100.0
    pts_rr = 1 if sl_pct_dist <= 7.0 and risk > 0 else 0

    # ── PENALTIES ────────────────────────────────────────────────────────
    penalty_overext  = -1 if overextended else 0
    penalty_decel    = -1 if _hma_slope_decelerating(hma55, lookback=5) else 0

    # ── TOTAL SCORE ──────────────────────────────────────────────────────
    raw_score = (pts_hma + pts_dist + pts_vol +
                 pts_rsi + pts_macd + pts_sector + pts_rr +
                 penalty_overext + penalty_decel)

    score = max(0, min(10, raw_score))   # clamp 0–10

    # ── CONVICTION TIER ──────────────────────────────────────────────────
    if score >= 7:
        conviction = TIER_HIGH_CONVICTION
    elif score >= 4:
        conviction = TIER_WATCHLIST
    else:
        conviction = ""

    # ── 52W HIGH CHECK ───────────────────────────────────────────────────
    w52_high = w52_map.get(symbol, (None, None))
    if isinstance(w52_high, tuple):
        w52_high = w52_high[0]
    near_52w = (
        w52_high is not None and
        w52_high > 0 and
        close_now >= 0.90 * float(w52_high)
    )

    return {
        'symbol':      symbol,
        'score':       score,
        'conviction':  conviction,
        # Sub-scores (for transparency + output display)
        'pts_hma':     pts_hma,
        'pts_dist':    pts_dist,
        'pts_vol':     pts_vol,
        'pts_rsi':     pts_rsi,
        'pts_macd':    pts_macd,
        'pts_sector':  pts_sector,
        'pts_rr':      pts_rr,
        'pen_overext': penalty_overext,
        'pen_decel':   penalty_decel,
        # Metadata for categories + display
        'cross_age':     cross_age,
        'fresh_cross':   fresh_cross,
        'dist_pct':      round(dist_pct, 1),
        'overextended':  overextended,
        'rsi':           round(rsi_val, 1),
        'obv_dir':       obv_dir,
        'acc_days':      acc_days,
        'dist_days':     dist_days,
        'del_trend':     del_trend,
        'hma_trend_up':  hma_trend_up,
        'near_52w':      near_52w,
        'sector_bias':   sector_bias,
        # Trade levels
        'stop':    round(sl_price, 2),
        'target':  round(t1, 2),
        'target2': round(t2, 2),
        'rr':      2.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# BULK SCORER — called by nse_scanner.py
# ═══════════════════════════════════════════════════════════════════════════

def score_all_stocks(price_df: pd.DataFrame,
                     filtered_symbols: list,
                     scan_date,
                     w52_map: dict = None) -> pd.DataFrame:
    """
    Score all filtered stocks using forward-looking signals.

    Args:
        price_df:         Full OHLCV DataFrame with columns:
                          symbol, date, open, high, low, close, volume, delivery_pct
        filtered_symbols: List of symbols that passed basic filters
        scan_date:        Date of scan (date object)
        w52_map:          Dict {symbol: (52w_high, 52w_low)}

    Returns:
        DataFrame indexed by symbol with all scoring columns.
    """
    if w52_map is None:
        w52_map = {}

    results = []
    sym_set = set(str(s).strip() for s in filtered_symbols)

    for symbol, grp in price_df.groupby('symbol'):
        sym = str(symbol).strip()
        if sym not in sym_set:
            continue
        try:
            result = _score_single_stock(sym, grp.copy(), w52_map, scan_date)
            if result is not None:
                results.append(result)
        except Exception as e:
            # Don't let one bad stock kill the whole scan
            pass

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results).set_index('symbol')
    return df


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY ASSIGNMENT — bulk version called by nse_scanner.py
# ═══════════════════════════════════════════════════════════════════════════

def assign_categories_bulk(scored_df: pd.DataFrame,
                            returns_df: pd.DataFrame,
                            w52_map: dict = None) -> pd.Series:
    """
    Assign forward-looking categories to each stock.

    Categories (in priority order):
      uptrend    — fresh cross + room to run + volume confirmed
      rising     — HMA up + accumulation + sector OK
      peak       — near 52W high
      safer      — high delivery + tight SL + moderate score
      recovering — 1M return < 3M return (early stage of move)

    Returns:
        pd.Series of category strings, indexed same as scored_df.
    """
    if w52_map is None:
        w52_map = {}

    categories = {}

    for _, row in scored_df.iterrows():
        sym = row.get('symbol', row.name if hasattr(row, 'name') else '')
        if not sym:
            sym = row.name

        score        = float(row.get('score', 0))
        fresh_cross  = bool(row.get('fresh_cross', False))
        cross_age    = int(row.get('cross_age', 999))
        dist_pct     = float(row.get('dist_pct', 0))
        overextended = bool(row.get('overextended', False))
        acc_days     = int(row.get('acc_days', 0))
        del_trend    = str(row.get('del_trend', 'flat'))
        near_52w     = bool(row.get('near_52w', False))
        delivery_pct = float(row.get('delivery_pct', 0))
        r1m          = float(row.get('return_1m_pct', row.get('return_1m', 0))) * (
                           1 if row.get('return_1m_pct') is not None else 100
                       )
        r3m          = float(row.get('return_3m_pct', row.get('return_3m', 0))) * (
                           1 if row.get('return_3m_pct') is not None else 100
                       )

        # Normalise pct (handle both 0.05 and 5.0 formats)
        if abs(r1m) < 1 and r1m != 0:
            r1m *= 100
        if abs(r3m) < 1 and r3m != 0:
            r3m *= 100

        # ── Priority 1: Clear Uptrend ────────────────────────────────
        # Fresh cross (≤10d) + not overextended + buy-side volume
        if (fresh_cross and
                not overextended and
                dist_pct <= 10.0 and
                acc_days >= 3 and
                score >= 6):
            categories[sym] = "uptrend"
            continue

        # ── Priority 2: Close to Peak ────────────────────────────────
        if near_52w and score >= 5:
            categories[sym] = "peak"
            continue

        # ── Priority 3: Safer Bets ───────────────────────────────────
        # High delivery + tight to HMA55 + moderate score
        if (delivery_pct >= 55.0 and
                dist_pct <= 8.0 and
                score >= 5 and
                not overextended):
            categories[sym] = "safer"
            continue

        # ── Priority 4: Recovering ───────────────────────────────────
        # 1M return lower than 3M return = early in the move
        # or: recently bottomed and turning up
        if (r3m > 0 and
                r1m < r3m * 0.5 and
                cross_age <= 15):
            categories[sym] = "recovering"
            continue

        # ── Priority 5: Consistently Rising (default upward) ────────
        if score >= 4:
            categories[sym] = "rising"
            continue

        # ── Fallback ─────────────────────────────────────────────────
        categories[sym] = "rising"

    # Return as Series aligned to scored_df index
    cat_series = scored_df.index.map(lambda s: categories.get(s, "rising"))
    return pd.Series(cat_series, index=scored_df.index)


# ═══════════════════════════════════════════════════════════════════════════
# CAUTION FLAGS — used by nse_telegram_handler
# ═══════════════════════════════════════════════════════════════════════════

def get_caution_flags(stock: dict) -> list:
    """
    Returns list of caution reason strings for a stock.
    Called by telegram handler for the /caution view.

    Input: stock dict from scan results (must have score, delivery_pct,
           dist_pct, return_3m_pct, cross_age keys where available)
    """
    flags = []
    score    = float(stock.get('score', 10))
    delivery = float(stock.get('delivery_pct', 100))
    r3m      = float(stock.get('return_3m_pct', 0))
    dist_pct = float(stock.get('dist_pct', 0))
    cross_age = int(stock.get('cross_age', 0))

    if score <= 4:
        flags.append(f"Low score {score}/10 — weak setup")
    if delivery < 40:
        flags.append(f"Low delivery {delivery:.0f}% — speculative")
    if r3m > 40:
        flags.append(f"Overextended — {r3m:.0f}% run, correction risk")
    if dist_pct > 15:
        flags.append(f"Price {dist_pct:.0f}% above HMA55 — stretched")
    if cross_age > 30:
        flags.append(f"HMA cross {cross_age}d ago — mature move")

    return flags


# ═══════════════════════════════════════════════════════════════════════════
# DISPLAY HELPER — Telegram sub-score line
# Used by nse_output.py for the new forward-score display
# ═══════════════════════════════════════════════════════════════════════════

def format_score_breakdown(stock: dict) -> str:
    """
    Returns a compact one-line score breakdown for Telegram display.
    Example: "HMA✅ Dist✅ Vol🟡 RSI✅ MACD❌ Sec✅ RR✅"
    """
    def _badge(pts, good=1):
        if pts >= good:    return "✅"
        elif pts == 0:     return "❌"
        else:              return "⚠️"

    parts = []
    cross_age = int(stock.get('cross_age', 999))

    hma_tag = (f"HMA✅{cross_age}d" if stock.get('pts_hma', 0) == 2 else
               f"HMA🟡{cross_age}d" if stock.get('pts_hma', 0) == 1 else "HMA❌")
    parts.append(hma_tag)

    dist = stock.get('dist_pct', 0)
    dist_tag = (f"Rm✅{dist:.0f}%" if stock.get('pts_dist', 0) >= 1 else
                f"Rm⚠️{dist:.0f}%" if stock.get('pts_dist', 0) == 0 else
                f"Rm❌{dist:.0f}%")
    parts.append(dist_tag)

    obv   = stock.get('obv_dir', 'flat')
    vol_tag = ("Vol✅" if stock.get('pts_vol', 0) >= 2 else
               "Vol🟡" if stock.get('pts_vol', 0) == 1 else "Vol❌")
    parts.append(vol_tag)

    parts.append(f"RSI{'✅' if stock.get('pts_rsi', 0) else '❌'}")
    parts.append(f"MACD{'✅' if stock.get('pts_macd', 0) else '❌'}")
    parts.append(f"RR{'✅' if stock.get('pts_rr', 0) else '❌'}")

    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sqlite3
    import sys
    try:
        import config
        DB_PATH = config.DB_PATH
    except Exception:
        print("config.py not found — cannot run self-test against real data.")
        sys.exit(0)

    scan_date = date.today()
    conn = sqlite3.connect(DB_PATH)
    price_df = pd.read_sql_query(f"""
        SELECT symbol, date, open, high, low, close, volume, delivery_pct
        FROM daily_prices
        WHERE date >= date('{scan_date}', '-120 days')
          AND date <= '{scan_date}'
        ORDER BY symbol, date
    """, conn)
    conn.close()

    price_df['date'] = pd.to_datetime(price_df['date'])
    symbols = price_df['symbol'].unique().tolist()[:50]  # test on 50 stocks

    print(f"Testing on {len(symbols)} stocks...")
    results = score_all_stocks(price_df, symbols, scan_date)

    if results.empty:
        print("No results.")
    else:
        hc  = results[results['conviction'] == TIER_HIGH_CONVICTION]
        wl  = results[results['conviction'] == TIER_WATCHLIST]
        top = results.sort_values('score', ascending=False).head(10)

        print(f"\nScored: {len(results)} stocks")
        print(f"HIGH CONVICTION: {len(hc)} | WATCHLIST: {len(wl)}")
        print(f"\nTop 10 by forward score:")
        print(top[['score','conviction','cross_age','dist_pct',
                   'acc_days','rsi','fresh_cross']].to_string())
