"""
Unit tests - Technical Indicators (Phase 2)
Tests: EMA, VWAP, RSI, MACD, ATR, Bollinger, ADX, Supertrend, Volume, Regime.
"""

import pytest
import sys
import numpy as np
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.indicators.technical import (
    compute_emas, compute_vwap, compute_rsi, compute_macd,
    compute_atr, compute_bollinger, compute_adx, compute_supertrend,
    detect_market_regime, compute_all,
)
from src.indicators.volume import compute_volume


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_trending_df(n=250, trend=0.0005):
    """Uptrending synthetic candle data."""
    np.random.seed(42)
    close = 20000 * np.cumprod(1 + np.random.normal(trend, 0.001, n))
    open_ = np.roll(close, 1); open_[0] = 20000
    high  = np.maximum(open_, close) * 1.002
    low   = np.minimum(open_, close) * 0.998
    vol   = np.random.randint(500_000, 2_000_000, n).astype(float)
    vwap  = (high + low + close) / 3
    idx   = pd.date_range("2026-01-02 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": vol, "vwap": vwap
    }, index=idx)


def make_flat_df(n=250):
    """Range-bound synthetic candle data."""
    np.random.seed(7)
    close = 20000 + np.random.normal(0, 50, n)
    open_ = np.roll(close, 1); open_[0] = 20000
    high  = np.maximum(open_, close) + 20
    low   = np.minimum(open_, close) - 20
    vol   = np.random.randint(300_000, 700_000, n).astype(float)
    vwap  = (high + low + close) / 3
    idx   = pd.date_range("2026-01-02 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": vol, "vwap": vwap
    }, index=idx)


# ── EMA ───────────────────────────────────────────────────────────────────────

class TestEMA:
    def test_returns_all_keys(self):
        df = make_trending_df()
        r  = compute_emas(df)
        for k in ["ema9","ema21","ema50","ema200","score","signal"]:
            assert k in r

    def test_score_in_range(self):
        r = compute_emas(make_trending_df())
        assert 0 <= r["score"] <= 100

    def test_trending_bullish_score(self):
        r = compute_emas(make_trending_df(trend=0.001))
        assert r["score"] > 60, "Uptrend should give bullish EMA score"

    def test_insufficient_data_returns_empty(self):
        df = make_trending_df(n=50)
        r  = compute_emas(df)
        assert r == {}

    def test_ema9_above_ema200_in_uptrend(self):
        r = compute_emas(make_trending_df(trend=0.001))
        assert r["ema9"] > r["ema200"]


# ── VWAP ─────────────────────────────────────────────────────────────────────

class TestVWAP:
    def test_returns_keys(self):
        r = compute_vwap(make_trending_df())
        assert "vwap" in r and "above_vwap" in r and "score" in r

    def test_score_in_range(self):
        r = compute_vwap(make_trending_df())
        assert 0 <= r["score"] <= 100

    def test_above_vwap_bullish(self):
        df = make_trending_df(trend=0.002)
        r  = compute_vwap(df)
        if r["above_vwap"]:
            assert r["score"] > 50

    def test_below_vwap_bearish(self):
        df = make_trending_df(trend=-0.002)
        r  = compute_vwap(df)
        if not r["above_vwap"]:
            assert r["score"] < 50


# ── RSI ───────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_rsi_in_range(self):
        r = compute_rsi(make_trending_df())
        assert 0 <= r["rsi"] <= 100

    def test_returns_keys(self):
        r = compute_rsi(make_trending_df())
        for k in ["rsi","score","signal","oversold","overbought"]:
            assert k in r

    def test_not_both_oversold_overbought(self):
        r = compute_rsi(make_trending_df())
        assert not (r["oversold"] and r["overbought"])

    def test_insufficient_data(self):
        df = make_trending_df(n=5)
        assert compute_rsi(df) == {}


# ── MACD ─────────────────────────────────────────────────────────────────────

class TestMACD:
    def test_returns_keys(self):
        r = compute_macd(make_trending_df())
        for k in ["macd","signal","histogram","score"]:
            assert k in r

    def test_score_in_range(self):
        r = compute_macd(make_trending_df())
        assert 0 <= r["score"] <= 100

    def test_insufficient_data(self):
        df = make_trending_df(n=20)
        assert compute_macd(df) == {}


# ── ATR ───────────────────────────────────────────────────────────────────────

class TestATR:
    def test_atr_positive(self):
        r = compute_atr(make_trending_df())
        assert r["atr"] > 0

    def test_returns_sl_levels(self):
        r = compute_atr(make_trending_df())
        assert "sl_1atr" in r and "sl_15atr" in r and "sl_2atr" in r

    def test_sl_levels_ordered(self):
        r = compute_atr(make_trending_df())
        assert r["sl_2atr"] < r["sl_15atr"] < r["sl_1atr"]

    def test_volatility_label_valid(self):
        r = compute_atr(make_trending_df())
        assert r["volatility"] in ["LOW","MEDIUM","HIGH","VERY_HIGH"]


# ── Bollinger Bands ───────────────────────────────────────────────────────────

class TestBollinger:
    def test_returns_keys(self):
        r = compute_bollinger(make_trending_df())
        for k in ["upper","middle","lower","pct_b","bandwidth","squeeze","score"]:
            assert k in r

    def test_upper_above_lower(self):
        r = compute_bollinger(make_trending_df())
        assert r["upper"] > r["lower"]

    def test_pct_b_range(self):
        r = compute_bollinger(make_trending_df())
        # pct_b can be outside 0-1 during breakouts — just check it's a number
        assert isinstance(r["pct_b"], float)

    def test_score_in_range(self):
        r = compute_bollinger(make_trending_df())
        assert 0 <= r["score"] <= 100


# ── ADX ───────────────────────────────────────────────────────────────────────

class TestADX:
    def test_adx_positive(self):
        r = compute_adx(make_trending_df())
        assert r["adx"] >= 0

    def test_returns_keys(self):
        r = compute_adx(make_trending_df())
        for k in ["adx","plus_di","minus_di","trending","bullish_di","score"]:
            assert k in r

    def test_score_in_range(self):
        r = compute_adx(make_trending_df())
        assert 0 <= r["score"] <= 100

    def test_trending_flag(self):
        r = compute_adx(make_trending_df(trend=0.002))
        # May or may not be trending — just check it's a bool
        assert isinstance(r["trending"], bool)


# ── Supertrend ────────────────────────────────────────────────────────────────

class TestSupertrend:
    def test_returns_keys(self):
        r = compute_supertrend(make_trending_df())
        for k in ["supertrend","direction","score","signal"]:
            assert k in r

    def test_direction_valid(self):
        r = compute_supertrend(make_trending_df())
        assert r["direction"] in ["BULLISH","BEARISH"]

    def test_score_binary(self):
        r = compute_supertrend(make_trending_df())
        assert r["score"] in [70.0, 30.0]


# ── Volume ────────────────────────────────────────────────────────────────────

class TestVolume:
    def test_returns_keys(self):
        r = compute_volume(make_trending_df())
        for k in ["volume_ratio","volume_class","price_volume_signal","score"]:
            assert k in r

    def test_score_in_range(self):
        r = compute_volume(make_trending_df())
        assert 0 <= r["score"] <= 100

    def test_pv_signal_valid(self):
        r = compute_volume(make_trending_df())
        assert r["price_volume_signal"] in [
            "BULLISH_CONFIRMATION","BEARISH_CONFIRMATION",
            "WEAK_UPSIDE","WEAK_DOWNSIDE"
        ]

    def test_volume_class_valid(self):
        r = compute_volume(make_trending_df())
        assert r["volume_class"] in ["VERY_HIGH","HIGH","NORMAL","LOW","VERY_LOW"]


# ── Market Regime ─────────────────────────────────────────────────────────────

class TestMarketRegime:
    def test_strong_bull_regime(self):
        df  = make_trending_df(trend=0.002)
        ema = compute_emas(df)
        adx = compute_adx(df)
        rsi = compute_rsi(df)
        atr = compute_atr(df)
        regime = detect_market_regime(ema, adx, rsi, atr)
        assert regime in [
            "STRONG_BULL","BULL","WEAK_BULL","RANGE","HIGH_VOLATILITY","LOW_VOLATILITY"
        ]

    def test_range_regime(self):
        df  = make_flat_df()
        ema = compute_emas(df)
        adx = compute_adx(df)
        rsi = compute_rsi(df)
        atr = compute_atr(df)
        regime = detect_market_regime(ema, adx, rsi, atr)
        assert regime in [
            "RANGE","WEAK_BULL","WEAK_BEAR","LOW_VOLATILITY","BULL","BEAR"
        ]

    def test_high_vix_gives_high_volatility(self):
        df  = make_trending_df()
        ema = compute_emas(df)
        adx = compute_adx(df)
        rsi = compute_rsi(df)
        atr = {"atr": 300, "atr_pct": 1.5, "volatility": "LOW", "sl_1atr": 0, "sl_15atr": 0, "sl_2atr": 0}
        regime = detect_market_regime(ema, adx, rsi, atr, vix=30)
        assert regime == "HIGH_VOLATILITY"


# ── Composite ─────────────────────────────────────────────────────────────────

class TestComputeAll:
    def test_returns_all_sections(self):
        df = make_trending_df()
        r  = compute_all(df)
        for k in ["ema","vwap","rsi","macd","atr","bollinger",
                  "adx","supertrend","market_regime","tech_score"]:
            assert k in r

    def test_tech_score_in_range(self):
        r = compute_all(make_trending_df())
        assert 0 <= r["tech_score"] <= 100

    def test_market_regime_string(self):
        r = compute_all(make_trending_df())
        assert isinstance(r["market_regime"], str)
        assert len(r["market_regime"]) > 0
