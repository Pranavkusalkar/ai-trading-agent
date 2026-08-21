"""
Volume Analysis (Spec section 6)
Implements price-volume relationship rules and volume spike detection.
"""

import logging
import pandas as pd
import numpy as np

log = logging.getLogger(__name__)


def compute_volume(df: pd.DataFrame, ma_period: int = 20) -> dict:
    """
    Volume analysis with price-volume relationship rules from spec section 6.

    Rules:
      High price + high volume   -> bullish confirmation
      Low price  + high volume   -> bearish confirmation
      Breakout   + high volume   -> stronger breakout
      Breakout   + low volume    -> possible false breakout
    """
    if len(df) < ma_period + 1:
        return {}

    close  = df["close"].astype(float)
    volume = df["volume"].astype(float)

    vol_ma      = volume.rolling(ma_period).mean()
    curr_vol    = float(volume.iloc[-1])
    curr_vol_ma = float(vol_ma.iloc[-1])
    vol_ratio   = curr_vol / curr_vol_ma if curr_vol_ma > 0 else 1.0

    # Price direction
    price_up    = float(close.iloc[-1]) > float(close.iloc[-2])
    price_change_pct = (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2]) * 100

    # Volume classification
    if vol_ratio >= 2.0:   vol_class = "VERY_HIGH"
    elif vol_ratio >= 1.5: vol_class = "HIGH"
    elif vol_ratio >= 0.8: vol_class = "NORMAL"
    elif vol_ratio >= 0.5: vol_class = "LOW"
    else:                  vol_class = "VERY_LOW"

    high_vol = vol_ratio >= 1.5

    # Price-volume relationship (spec rules)
    if price_up and high_vol:
        pv_signal = "BULLISH_CONFIRMATION"
        score     = 75.0
    elif not price_up and high_vol:
        pv_signal = "BEARISH_CONFIRMATION"
        score     = 25.0
    elif price_up and not high_vol:
        pv_signal = "WEAK_UPSIDE"
        score     = 55.0
    else:
        pv_signal = "WEAK_DOWNSIDE"
        score     = 45.0

    # Volume spike detection
    vol_std    = float(volume.rolling(ma_period).std().iloc[-1])
    spike      = curr_vol > (curr_vol_ma + 2 * vol_std) if vol_std > 0 else False

    # Contraction (low volume squeeze — often precedes breakout)
    contraction = vol_ratio < 0.6 and float(volume.rolling(5).mean().iloc[-1]) < curr_vol_ma * 0.7

    return {
        "current_volume":   int(curr_vol),
        "volume_ma":        int(curr_vol_ma),
        "volume_ratio":     round(vol_ratio, 3),
        "volume_class":     vol_class,
        "price_volume_signal": pv_signal,
        "price_up":         price_up,
        "price_change_pct": round(price_change_pct, 3),
        "spike":            spike,
        "contraction":      contraction,
        "score":            round(score, 1),
        "signal":           "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL",
    }
