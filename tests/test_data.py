"""
Unit tests - Data Pipeline (Phase 2)
Tests: cache, validator, market data provider, futures agent, options chain.
"""

import pytest
import sys
import time
import datetime
import pandas as pd
import pytz
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.data.data_cache     import DataCache
from src.data.data_validator  import DataValidator
from src.data.market_data     import MockDataProvider, create_data_provider
from src.data.futures_data    import FuturesDataAgent, classify_oi_signal
from src.data.options_chain   import OptionsChainAgent

IST = pytz.timezone("Asia/Kolkata")


# ── Cache tests ───────────────────────────────────────────────────────────────

class TestDataCache:
    def test_set_and_get(self):
        c = DataCache(default_ttl=60)
        c.set("key1", {"value": 42})
        assert c.get("key1") == {"value": 42}

    def test_miss_returns_none(self):
        c = DataCache()
        assert c.get("nonexistent") is None

    def test_ttl_expiry(self):
        c = DataCache(default_ttl=1)
        c.set("key_exp", "data", ttl=1)
        time.sleep(1.1)
        assert c.get("key_exp") is None

    def test_invalidate(self):
        c = DataCache()
        c.set("k", "v")
        c.invalidate("k")
        assert c.get("k") is None

    def test_invalidate_prefix(self):
        c = DataCache()
        c.set("candles:NIFTY:5min", "a")
        c.set("candles:BANKNIFTY:5min", "b")
        c.set("futures:NIFTY", "c")
        removed = c.invalidate_prefix("candles:")
        assert removed == 2
        assert c.get("futures:NIFTY") == "c"

    def test_hit_rate_tracking(self):
        c = DataCache()
        c.set("x", 1)
        c.get("x")
        c.get("x")
        c.get("missing")
        stats = c.stats()
        assert stats["hits"]   == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(66.7, 0.1)

    def test_clear(self):
        c = DataCache()
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert c.stats()["entries"] == 0


# ── Validator tests ───────────────────────────────────────────────────────────

class TestDataValidator:
    def _make_df(self, rows=250):
        import numpy as np
        arr = np.arange(rows, dtype=float)
        return pd.DataFrame({
            "open":   19000 + arr * 0.5,
            "high":   19010 + arr * 0.5,
            "low":    18990 + arr * 0.5,
            "close":  19005 + arr * 0.5,
            "volume": np.ones(rows) * 1_000_000,
        })

    def test_valid_candles_pass(self):
        result = DataValidator.validate_candles(self._make_df(), "NIFTY")
        assert result.valid is True

    def test_empty_df_fails(self):
        result = DataValidator.validate_candles(pd.DataFrame(), "NIFTY")
        assert result.valid is False
        assert any("Empty" in e for e in result.errors)

    def test_missing_column_fails(self):
        df = self._make_df().drop(columns=["volume"])
        result = DataValidator.validate_candles(df, "NIFTY")
        assert result.valid is False

    def test_high_less_than_low_fails(self):
        df = self._make_df()
        # Use iloc to avoid index type issues across pandas versions
        low_val = float(df.iloc[5]["low"])
        df.iloc[5, df.columns.get_loc("high")] = low_val - 10
        result = DataValidator.validate_candles(df, "NIFTY")
        assert result.valid is False

    def test_stale_snapshot_fails(self):
        old_time = datetime.datetime.now() - datetime.timedelta(seconds=300)
        data = {"spot": 24500.0, "timestamp": old_time.isoformat()}
        result = DataValidator.validate_snapshot(data, "NIFTY")
        assert result.valid is False
        assert any("stale" in e.lower() for e in result.errors)

    def test_fresh_snapshot_passes(self):
        data = {"spot": 24500.0, "timestamp": datetime.datetime.now().isoformat()}
        result = DataValidator.validate_snapshot(data, "NIFTY")
        assert result.valid is True

    def test_zero_spot_fails(self):
        data = {"spot": 0, "timestamp": datetime.datetime.now().isoformat()}
        result = DataValidator.validate_snapshot(data)
        assert result.valid is False

    def test_gap_detection(self):
        idx = pd.to_datetime([
            "2026-08-18 09:15", "2026-08-18 09:20",
            "2026-08-18 10:00",   # gap here
            "2026-08-18 10:05",
        ])
        df = pd.DataFrame({"close": [1, 2, 3, 4]}, index=idx)
        gaps = DataValidator.detect_gaps(df, timeframe_minutes=5)
        assert len(gaps) == 1
        assert gaps[0]["missing_candles"] >= 7


# ── Market data provider tests ────────────────────────────────────────────────

class TestMockDataProvider:
    def setup_method(self):
        self.provider = MockDataProvider(seed=42)

    def test_get_spot_returns_price(self):
        spot = self.provider.get_spot("NIFTY")
        assert spot is not None
        assert 15000 < spot < 35000

    def test_get_spot_banknifty(self):
        spot = self.provider.get_spot("BANKNIFTY")
        assert spot is not None
        assert 30000 < spot < 80000

    def test_unknown_symbol_returns_none(self):
        assert self.provider.get_spot("XYZ") is None

    def test_get_candles_shape(self):
        df = self.provider.get_candles("NIFTY", "5min", count=100)
        assert len(df) == 100
        assert set(["open","high","low","close","volume","vwap"]).issubset(df.columns)

    def test_candles_ohlc_integrity(self):
        df = self.provider.get_candles("NIFTY", "5min", count=100)
        assert (df["high"] >= df["low"]).all()
        assert (df["close"] > 0).all()

    def test_candles_sorted(self):
        df = self.provider.get_candles("NIFTY", "5min", count=50)
        assert df.index.is_monotonic_increasing

    def test_snapshot_structure(self):
        snap = self.provider.get_market_snapshot("NIFTY")
        assert "spot"    in snap
        assert "future"  in snap
        assert "basis"   in snap
        assert snap["data_quality"] == 100

    def test_create_data_provider_mock(self):
        p = create_data_provider("mock")
        assert isinstance(p, MockDataProvider)


# ── Futures agent tests ───────────────────────────────────────────────────────

class TestFuturesDataAgent:
    def setup_method(self):
        self.agent = FuturesDataAgent(mock=True)

    def test_snapshot_keys(self):
        snap = self.agent.get_futures_snapshot("NIFTY")
        for key in ["price","oi","change_in_oi","oi_signal","basis","expiry"]:
            assert key in snap, f"Missing key: {key}"

    def test_oi_signal_is_valid(self):
        snap = self.agent.get_futures_snapshot("NIFTY")
        assert snap["oi_signal"] in [
            "LONG_BUILDUP","SHORT_BUILDUP","LONG_UNWINDING","SHORT_COVERING"
        ]

    def test_oi_score_range(self):
        score = self.agent.get_oi_buildup_score("NIFTY")
        assert 0 <= score <= 100

    def test_classify_long_buildup(self):
        assert classify_oi_signal(100, 500)  == "LONG_BUILDUP"

    def test_classify_short_buildup(self):
        assert classify_oi_signal(-50, 300) == "SHORT_BUILDUP"

    def test_classify_long_unwinding(self):
        assert classify_oi_signal(-50, -200) == "LONG_UNWINDING"

    def test_classify_short_covering(self):
        assert classify_oi_signal(100, -300) == "SHORT_COVERING"

    def test_banknifty_snapshot(self):
        snap = self.agent.get_futures_snapshot("BANKNIFTY")
        assert snap["symbol"] == "BANKNIFTY"
        assert snap["price"]  > 0


# ── Options chain tests ───────────────────────────────────────────────────────

class TestOptionsChainAgent:
    def setup_method(self):
        self.agent = OptionsChainAgent(mock=True)

    def test_chain_length(self):
        chain = self.agent.get_chain("NIFTY", depth=10)
        assert len(chain) == 21 * 2  # 21 strikes x 2 types (CE+PE)

    def test_chain_fields(self):
        chain = self.agent.get_chain("NIFTY", depth=5)
        row = chain[0]
        for f in ["strike","option_type","ltp","oi","volume","iv","delta","gamma","theta","vega"]:
            assert f in row, f"Missing field: {f}"

    def test_option_types(self):
        chain = self.agent.get_chain("NIFTY", depth=3)
        types = {r["option_type"] for r in chain}
        assert types == {"CE","PE"}

    def test_ltp_positive(self):
        chain = self.agent.get_chain("NIFTY", depth=5)
        assert all(r["ltp"] > 0 for r in chain)

    def test_iv_positive(self):
        chain = self.agent.get_chain("NIFTY", depth=5)
        assert all(r["iv"] > 0 for r in chain)

    def test_analysis_keys(self):
        analysis = self.agent.analyse("NIFTY")
        for k in ["pcr_oi","max_call_oi_strike","max_put_oi_strike",
                  "atm_iv","iv_environment","oi_score"]:
            assert k in analysis, f"Missing key: {k}"

    def test_pcr_positive(self):
        analysis = self.agent.analyse("NIFTY")
        assert analysis["pcr_oi"] > 0

    def test_oi_score_range(self):
        score = self.agent.get_oi_score("NIFTY")
        assert 0 <= score <= 100

    def test_iv_environment_valid(self):
        analysis = self.agent.analyse("NIFTY")
        assert analysis["iv_environment"] in [
            "LOW_IV","NORMAL_IV","ELEVATED_IV","HIGH_IV","UNKNOWN"
        ]
