"""
Technical Indicators Engine (Spec section 4)
All indicators use pandas + numpy only (no pandas-ta dependency).
Each returns a typed dict with value, signal, and score (0-100).
score > 65 = bullish, < 35 = bearish, 35-65 = neutral.
"""

import logging
import numpy as np
import pandas as pd
from typing import Optional

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _signal(score: float) -> str:
    if score >= 65: return "BULLISH"
    if score <= 35: return "BEARISH"
    return "NEUTRAL"


def _require(df: pd.DataFrame, min_bars: int, name: str) -> bool:
    if len(df) < min_bars:
        log.debug(f"{name}: need {min_bars} bars, got {len(df)}")
        return False
    return True


# ── EMA ───────────────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_emas(df: pd.DataFrame) -> dict:
    """EMA 9, 21, 50, 200 with crossover detection."""
    if not _require(df, 200, "EMA"):
        return {}

    close  = df["close"].astype(float)
    e9     = ema(close, 9)
    e21    = ema(close, 21)
    e50    = ema(close, 50)
    e200   = ema(close, 200)
    price  = float(close.iloc[-1])

    above_9   = price > float(e9.iloc[-1])
    above_21  = price > float(e21.iloc[-1])
    above_50  = price > float(e50.iloc[-1])
    above_200 = price > float(e200.iloc[-1])
    golden_cross = float(e50.iloc[-1]) > float(e200.iloc[-1])
    death_cross  = float(e50.iloc[-1]) < float(e200.iloc[-1])
    ema9_above_21 = float(e9.iloc[-1]) > float(e21.iloc[-1])

    score = 50.0
    if above_9:    score += 8
    if above_21:   score += 8
    if above_50:   score += 10
    if above_200:  score += 12
    if golden_cross: score += 12
    elif death_cross: score -= 15
    if ema9_above_21: score += 10
    score = min(max(score, 0), 100)

    return {
        "ema9":          round(float(e9.iloc[-1]),   2),
        "ema21":         round(float(e21.iloc[-1]),  2),
        "ema50":         round(float(e50.iloc[-1]),  2),
        "ema200":        round(float(e200.iloc[-1]), 2),
        "price":         round(price, 2),
        "above_9":       above_9,
        "above_21":      above_21,
        "above_50":      above_50,
        "above_200":     above_200,
        "golden_cross":  golden_cross,
        "death_cross":   death_cross,
        "ema9_above_21": ema9_above_21,
        "score":         round(score, 1),
        "signal":        _signal(score),
    }


# ── VWAP ──────────────────────────────────────────────────────────────────────

def compute_vwap(df: pd.DataFrame) -> dict:
    """VWAP relative to current price."""
    if not _require(df, 10, "VWAP"):
        return {}

    if "vwap" in df.columns and df["vwap"].notna().all():
        vwap_val = float(df["vwap"].iloc[-1])
    else:
        typical  = (df["high"] + df["low"] + df["close"]) / 3
        vwap_val = float((typical * df["volume"]).cumsum().iloc[-1] /
                          df["volume"].cumsum().iloc[-1])

    price    = float(df["close"].iloc[-1])
    pct_diff = (price - vwap_val) / vwap_val * 100

    if price > vwap_val:
        score = min(65 + abs(pct_diff) * 5, 90)
    else:
        score = max(35 - abs(pct_diff) * 5, 10)

    return {
        "vwap":        round(vwap_val, 2),
        "price":       round(price, 2),
        "above_vwap":  price > vwap_val,
        "pct_from_vwap": round(pct_diff, 3),
        "score":       round(score, 1),
        "signal":      _signal(score),
    }


# ── RSI ───────────────────────────────────────────────────────────────────────

def compute_rsi(df: pd.DataFrame, period: int = 14) -> dict:
    if not _require(df, period + 1, "RSI"):
        return {}

    close  = df["close"].astype(float)
    delta  = close.diff()
    gain   = delta.clip(lower=0).rolling(period).mean()
    loss   = (-delta.clip(upper=0)).rolling(period).mean()
    rs     = gain / loss.replace(0, np.nan)
    rsi_s  = 100 - (100 / (1 + rs))
    rsi    = float(rsi_s.iloc[-1])

    if rsi   <= 30: score = 85.0
    elif rsi <= 40: score = 65.0
    elif rsi <= 55: score = 52.0
    elif rsi <= 65: score = 48.0
    elif rsi <= 70: score = 35.0
    else:           score = 15.0

    return {
        "rsi":     round(rsi, 2),
        "score":   round(score, 1),
        "signal":  _signal(score),
        "oversold":    rsi <= 30,
        "overbought":  rsi >= 70,
    }


# ── MACD ─────────────────────────────────────────────────────────────────────

def compute_macd(
    df: pd.DataFrame,
    fast: int = 12, slow: int = 26, signal_period: int = 9
) -> dict:
    if not _require(df, slow + signal_period, "MACD"):
        return {}

    close      = df["close"].astype(float)
    ema_fast   = ema(close, fast)
    ema_slow   = ema(close, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram  = macd_line - signal_line

    hist_val   = float(histogram.iloc[-1])
    macd_val   = float(macd_line.iloc[-1])
    sig_val    = float(signal_line.iloc[-1])

    # Bullish: histogram positive and growing
    hist_prev  = float(histogram.iloc[-2]) if len(histogram) > 1 else hist_val
    growing    = hist_val > hist_prev

    if hist_val > 0 and growing:   score = 75.0
    elif hist_val > 0:              score = 60.0
    elif hist_val < 0 and not growing: score = 25.0
    else:                           score = 40.0

    crossover_bull = float(macd_line.iloc[-2]) < float(signal_line.iloc[-2]) and macd_val > sig_val
    crossover_bear = float(macd_line.iloc[-2]) > float(signal_line.iloc[-2]) and macd_val < sig_val

    if crossover_bull: score = min(score + 10, 90)
    if crossover_bear: score = max(score - 10, 10)

    return {
        "macd":            round(macd_val,  4),
        "signal":          round(sig_val,   4),
        "histogram":       round(hist_val,  4),
        "crossover_bull":  crossover_bull,
        "crossover_bear":  crossover_bear,
        "score":           round(score, 1),
        "signal_label":    _signal(score),
    }


# ── ATR ───────────────────────────────────────────────────────────────────────

def compute_atr(df: pd.DataFrame, period: int = 14) -> dict:
    """ATR for stop-loss sizing. Returns value and volatility label."""
    if not _require(df, period + 1, "ATR"):
        return {}

    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    atr_val = float(atr.iloc[-1])

    price   = float(close.iloc[-1])
    atr_pct = atr_val / price * 100

    if atr_pct < 0.3:   vol_label = "LOW"
    elif atr_pct < 0.6: vol_label = "MEDIUM"
    elif atr_pct < 1.0: vol_label = "HIGH"
    else:               vol_label = "VERY_HIGH"

    return {
        "atr":       round(atr_val, 2),
        "atr_pct":   round(atr_pct, 3),
        "volatility": vol_label,
        "sl_1atr":   round(price - atr_val, 2),
        "sl_15atr":  round(price - atr_val * 1.5, 2),
        "sl_2atr":   round(price - atr_val * 2, 2),
    }


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def compute_bollinger(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> dict:
    if not _require(df, period, "Bollinger"):
        return {}

    close = df["close"].astype(float)
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = mid + std * std_dev
    lower = mid - std * std_dev
    pct_b = (close - lower) / (upper - lower)
    bw    = (upper - lower) / mid * 100  # bandwidth

    price   = float(close.iloc[-1])
    pct_b_v = float(pct_b.iloc[-1])
    bw_v    = float(bw.iloc[-1])

    # Near lower band = oversold = bullish setup
    if pct_b_v < 0.2:   score = 72.0
    elif pct_b_v < 0.4: score = 58.0
    elif pct_b_v < 0.6: score = 50.0
    elif pct_b_v < 0.8: score = 42.0
    else:               score = 30.0

    return {
        "upper":        round(float(upper.iloc[-1]), 2),
        "middle":       round(float(mid.iloc[-1]),   2),
        "lower":        round(float(lower.iloc[-1]), 2),
        "pct_b":        round(pct_b_v, 3),
        "bandwidth":    round(bw_v,    3),
        "squeeze":      bw_v < 2.0,
        "score":        round(score, 1),
        "signal":       _signal(score),
    }


# ── ADX ───────────────────────────────────────────────────────────────────────

def compute_adx(df: pd.DataFrame, period: int = 14) -> dict:
    """ADX for trend strength. DI+ / DI- for direction."""
    if not _require(df, period * 2, "ADX"):
        return {}

    high   = df["high"].astype(float)
    low    = df["low"].astype(float)
    close  = df["close"].astype(float)

    up_move   = high.diff()
    down_move = -low.diff()

    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_s    = tr.ewm(span=period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(span=period,  adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr_s
    dx       = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx_s    = dx.ewm(span=period, adjust=False).mean()

    adx_v     = float(adx_s.iloc[-1])
    plus_di_v = float(plus_di.iloc[-1])
    minus_di_v= float(minus_di.iloc[-1])

    trending  = adx_v > 25
    bullish   = plus_di_v > minus_di_v

    if trending and bullish:       score = 75.0
    elif trending and not bullish: score = 25.0
    elif adx_v > 15 and bullish:   score = 60.0
    elif adx_v > 15:               score = 40.0
    else:                          score = 50.0

    return {
        "adx":        round(adx_v,      2),
        "plus_di":    round(plus_di_v,  2),
        "minus_di":   round(minus_di_v, 2),
        "trending":   trending,
        "bullish_di": bullish,
        "score":      round(score, 1),
        "signal":     _signal(score),
    }


# ── Supertrend ────────────────────────────────────────────────────────────────

def compute_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> dict:
    if not _require(df, period + 1, "Supertrend"):
        return {}

    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    hl2   = (high + low) / 2
    tr1   = high - low
    tr2   = (high - close.shift()).abs()
    tr3   = (low  - close.shift()).abs()
    tr    = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr   = tr.ewm(span=period, adjust=False).mean()

    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(index=df.index, dtype=int)

    for i in range(1, len(df)):
        prev_close = float(close.iloc[i - 1])
        ub = float(upper_basic.iloc[i])
        lb = float(lower_basic.iloc[i])

        prev_st  = float(supertrend.iloc[i - 1]) if not pd.isna(supertrend.iloc[i - 1]) else lb
        prev_dir = int(direction.iloc[i - 1]) if not pd.isna(direction.iloc[i - 1]) else 1

        if prev_dir == 1:
            st = lb if float(close.iloc[i]) > prev_st else ub
            d  = 1  if float(close.iloc[i]) > st else -1
        else:
            st = ub if float(close.iloc[i]) < prev_st else lb
            d  = -1 if float(close.iloc[i]) < st else 1

        supertrend.iloc[i] = st
        direction.iloc[i]  = d

    last_dir = int(direction.iloc[-1]) if not pd.isna(direction.iloc[-1]) else 0
    last_st  = float(supertrend.iloc[-1]) if not pd.isna(supertrend.iloc[-1]) else 0.0
    bullish  = last_dir == 1

    score = 70.0 if bullish else 30.0

    return {
        "supertrend":  round(last_st, 2),
        "direction":   "BULLISH" if bullish else "BEARISH",
        "score":       score,
        "signal":      _signal(score),
    }


# ── Market Regime ─────────────────────────────────────────────────────────────

def detect_market_regime(
    ema_result:  dict,
    adx_result:  dict,
    rsi_result:  dict,
    atr_result:  dict,
    vix:         Optional[float] = None,
) -> str:
    """
    Classify market into one of 9 regimes (spec section 11).
    STRONG_BULL | BULL | WEAK_BULL | RANGE |
    WEAK_BEAR   | BEAR | STRONG_BEAR |
    HIGH_VOLATILITY | LOW_VOLATILITY
    """
    adx  = adx_result.get("adx", 15)
    rsi  = rsi_result.get("rsi", 50)
    atr_vol = atr_result.get("volatility", "MEDIUM")
    bullish_ema  = ema_result.get("above_200", False) and ema_result.get("golden_cross", False)
    bearish_ema  = not ema_result.get("above_200", True)
    bullish_di   = adx_result.get("bullish_di", True)
    ema_score    = ema_result.get("score", 50)

    if atr_vol == "VERY_HIGH" or (vix and vix > 25):
        return "HIGH_VOLATILITY"
    if atr_vol == "LOW" and adx < 15:
        return "LOW_VOLATILITY"
    if adx > 25:
        if bullish_di and ema_score > 70:
            return "STRONG_BULL" if ema_score > 80 else "BULL"
        if not bullish_di and ema_score < 30:
            return "STRONG_BEAR" if ema_score < 20 else "BEAR"
    if adx < 15:
        return "RANGE"
    if ema_score > 60:
        return "WEAK_BULL"
    if ema_score < 40:
        return "WEAK_BEAR"
    return "RANGE"


# ── Full composite ────────────────────────────────────────────────────────────

def compute_all(df: pd.DataFrame, vix: Optional[float] = None) -> dict:
    """
    Run every indicator and return a unified dict.
    The signal engine reads this output.
    """
    emas    = compute_emas(df)
    vwap    = compute_vwap(df)
    rsi     = compute_rsi(df)
    macd    = compute_macd(df)
    atr     = compute_atr(df)
    boll    = compute_bollinger(df)
    adx     = compute_adx(df)
    st      = compute_supertrend(df)

    regime = detect_market_regime(emas, adx, rsi, atr, vix) if all([emas, adx, rsi, atr]) else "UNKNOWN"

    # Composite technical score (equal weight across indicators)
    scores = [
        emas.get("score", 50),
        vwap.get("score", 50),
        rsi.get("score",  50),
        macd.get("score", 50),
        boll.get("score", 50),
        adx.get("score",  50),
        st.get("score",   50),
    ]
    valid_scores  = [s for s in scores if s is not None]
    tech_score    = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 50.0

    return {
        "ema":          emas,
        "vwap":         vwap,
        "rsi":          rsi,
        "macd":         macd,
        "atr":          atr,
        "bollinger":    boll,
        "adx":          adx,
        "supertrend":   st,
        "market_regime": regime,
        "tech_score":   tech_score,
        "tech_signal":  _signal(tech_score),
    }
