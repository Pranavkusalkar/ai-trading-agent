"""
Unit tests - Signal Engine, AI Decision Agent, Orchestrator (Phase 3)
"""

import pytest
import sys
import numpy as np
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.strategies.signal_engine import SignalEngine, DEFAULT_WEIGHTS, CONFIDENCE_BANDS
from src.agents.decision_agent    import AIDecisionAgent
from src.strategies.orchestrator  import SignalOrchestrator


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_candles(n=250, trend=0.0005):
    np.random.seed(42)
    close = 24500 * np.cumprod(1 + np.random.normal(trend, 0.001, n))
    open_ = np.roll(close, 1); open_[0] = 24500
    high  = np.maximum(open_, close) * 1.002
    low   = np.minimum(open_, close) * 0.998
    vol   = np.random.randint(500_000, 2_000_000, n).astype(float)
    vwap  = (high + low + close) / 3
    idx   = pd.date_range("2026-01-02 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": vol, "vwap": vwap
    }, index=idx)


def make_tech(bullish=True):
    score = 72.0 if bullish else 28.0
    sig   = "BULLISH" if bullish else "BEARISH"
    return {
        "ema": {
            "score": score, "signal": sig, "price": 24500,
            "ema9": 24520, "ema21": 24480, "ema50": 24300, "ema200": 24000,
            "above_200": bullish, "above_50": bullish,
            "golden_cross": bullish, "death_cross": not bullish,
            "ema9_above_21": bullish,
        },
        "vwap":       {"score": score, "signal": sig, "vwap": 24450, "above_vwap": bullish, "pct_from_vwap": 0.2},
        "rsi":        {"score": score, "signal": sig, "rsi": 62.0 if bullish else 38.0, "oversold": False, "overbought": False},
        "macd":       {"score": score, "signal": sig, "histogram": 0.5 if bullish else -0.5, "crossover_bull": bullish, "crossover_bear": not bullish},
        "atr":        {"atr": 120.0, "atr_pct": 0.49, "volatility": "MEDIUM", "sl_1atr": 24380, "sl_15atr": 24320, "sl_2atr": 24260},
        "bollinger":  {"score": 55.0, "signal": "NEUTRAL", "pct_b": 0.55, "upper": 24800, "middle": 24500, "lower": 24200, "bandwidth": 2.5, "squeeze": False},
        "adx":        {"score": score, "signal": sig, "adx": 28.0, "plus_di": 25.0, "minus_di": 18.0, "trending": True, "bullish_di": bullish},
        "supertrend": {"score": 70.0 if bullish else 30.0, "signal": sig, "direction": "BULLISH" if bullish else "BEARISH", "supertrend": 24300},
        "market_regime": "BULL" if bullish else "BEAR",
        "tech_score":    score,
        "tech_signal":   sig,
    }


def make_volume(bullish=True):
    return {
        "score": 72.0 if bullish else 28.0,
        "signal": "BULLISH" if bullish else "BEARISH",
        "volume_ratio": 1.6,
        "volume_class": "HIGH",
        "price_volume_signal": "BULLISH_CONFIRMATION" if bullish else "BEARISH_CONFIRMATION",
        "price_up": bullish,
        "spike": False,
        "contraction": False,
        "current_volume": 1_500_000,
        "volume_ma": 950_000,
        "price_change_pct": 0.3 if bullish else -0.3,
    }


def make_futures(bullish=True):
    return {
        "symbol": "NIFTY",
        "price": 24510.0,
        "prev_price": 24400.0,
        "price_change_pct": 0.45 if bullish else -0.45,
        "oi": 12_500_000,
        "prev_oi": 12_000_000,
        "change_in_oi": 500_000 if bullish else -500_000,
        "change_in_oi_pct": 4.2,
        "basis": 10.0,
        "oi_signal": "LONG_BUILDUP" if bullish else "SHORT_BUILDUP",
        "oi_signal_description": "Fresh longs being added",
        "volume": 450_000,
        "expiry": "2026-08-21",
    }


def make_options(bullish=True):
    return {
        "symbol": "NIFTY",
        "pcr_oi": 0.85 if bullish else 1.4,
        "pcr_volume": 0.9,
        "pcr_change_oi": 0.8,
        "max_call_oi_strike": 24600,
        "max_put_oi_strike": 24400,
        "call_resistance": 24600,
        "put_support": 24400,
        "atm_iv": 14.5,
        "iv_environment": "NORMAL_IV",
        "oi_score": 62.0 if bullish else 38.0,
        "total_call_oi": 8_000_000,
        "total_put_oi": 6_800_000,
    }


# ── Signal Engine tests ───────────────────────────────────────────────────────

class TestSignalEngine:

    def setup_method(self):
        self.engine = SignalEngine()

    def test_compute_returns_required_keys(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        for k in ["timestamp","underlying","direction","decision",
                  "confidence","confidence_band","market_regime",
                  "strategy","score_breakdown","reasons","invalidation"]:
            assert k in sig, f"Missing key: {k}"

    def test_bullish_composite_score(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        assert sig["confidence"] > 55, f"Expected bullish score, got {sig['confidence']}"

    def test_bearish_composite_score(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(False), make_volume(False),
            make_futures(False), make_options(False)
        )
        assert sig["confidence"] < 45, f"Expected bearish score, got {sig['confidence']}"

    def test_score_in_range(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert 0 <= sig["confidence"] <= 100

    def test_decision_no_trade_on_low_score(self):
        # Neutral tech should produce low confidence
        tech = make_tech()
        for k in ["ema","vwap","rsi","macd","adx","supertrend","bollinger"]:
            if isinstance(tech.get(k), dict):
                tech[k]["score"] = 50.0
        tech["market_regime"] = "RANGE"
        tech["tech_score"]    = 50.0
        vol  = make_volume(); vol["score"] = 50.0
        fut  = make_futures(); fut["oi_signal"] = ""
        opt  = make_options(); opt["oi_score"] = 50.0; opt["atm_iv"] = 20.0
        sig  = self.engine.compute("NIFTY", tech, vol, fut, opt)
        assert sig["decision"] in ["NO_TRADE","BUY","SELL"]   # any valid decision

    def test_confidence_band_valid_values(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert sig["confidence_band"] in ["STRONG","VALID","WEAK","NO_TRADE"]

    def test_strategy_string_not_empty(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert isinstance(sig["strategy"], str)
        assert len(sig["strategy"]) > 0

    def test_score_breakdown_has_all_dimensions(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        for dim in DEFAULT_WEIGHTS.keys():
            assert dim in sig["score_breakdown"], f"Missing dimension: {dim}"

    def test_breakdown_contributions_sum_to_composite(self):
        sig    = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        total  = sum(v["contribution"] for v in sig["score_breakdown"].values())
        assert abs(total - sig["confidence"]) < 0.5

    def test_reasons_list(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        assert isinstance(sig["reasons"], list)
        assert len(sig["reasons"]) > 0

    def test_invalidation_list(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert isinstance(sig["invalidation"], list)
        assert len(sig["invalidation"]) > 0

    def test_entry_sl_target_present_on_valid_signal(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        if sig["decision"] != "NO_TRADE":
            assert sig["entry"]     is not None
            assert sig["stop_loss"] is not None
            assert sig["target"]    is not None
            assert sig["risk_reward"] > 0

    def test_custom_weights(self):
        custom = {k: 100//len(DEFAULT_WEIGHTS) for k in DEFAULT_WEIGHTS}
        engine = SignalEngine(weights=custom)
        sig    = engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert 0 <= sig["confidence"] <= 100

    def test_banknifty_signal(self):
        sig = self.engine.compute(
            "BANKNIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        assert sig["underlying"] == "BANKNIFTY"

    def test_bull_bias_gives_ce_option_type(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        if sig["direction"] == "LONG":
            assert sig["option_type"] == "CE"

    def test_bear_bias_gives_pe_option_type(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(False), make_volume(False),
            make_futures(False), make_options(False)
        )
        if sig["direction"] == "SHORT":
            assert sig["option_type"] == "PE"


# ── Score extraction tests ────────────────────────────────────────────────────

class TestScoreExtraction:

    def setup_method(self):
        self.engine = SignalEngine()

    def test_long_buildup_gives_high_futures_score(self):
        fut = make_futures(bullish=True)
        fut["oi_signal"] = "LONG_BUILDUP"
        scores = self.engine._extract_scores(make_tech(), make_volume(), fut, make_options(), None)
        assert scores["futures_oi"] >= 75

    def test_short_buildup_gives_low_futures_score(self):
        fut = make_futures()
        fut["oi_signal"] = "SHORT_BUILDUP"
        scores = self.engine._extract_scores(make_tech(), make_volume(), fut, make_options(), None)
        assert scores["futures_oi"] <= 25

    def test_high_iv_penalises_iv_score(self):
        opt = make_options()
        opt["atm_iv"] = 35.0
        scores = self.engine._extract_scores(make_tech(), make_volume(), make_futures(), opt, None)
        assert scores["iv"] <= 35

    def test_normal_iv_gives_good_score(self):
        opt = make_options()
        opt["atm_iv"] = 15.0
        scores = self.engine._extract_scores(make_tech(), make_volume(), make_futures(), opt, None)
        assert scores["iv"] >= 55

    def test_strong_bull_regime_score(self):
        tech = make_tech()
        tech["market_regime"] = "STRONG_BULL"
        scores = self.engine._extract_scores(tech, make_volume(), make_futures(), make_options(), None)
        assert scores["market_regime"] >= 85

    def test_range_regime_neutral_score(self):
        tech = make_tech()
        tech["market_regime"] = "RANGE"
        scores = self.engine._extract_scores(tech, make_volume(), make_futures(), make_options(), None)
        assert scores["market_regime"] == 50.0


# ── AI Decision Agent tests ───────────────────────────────────────────────────

class TestAIDecisionAgent:

    def test_no_api_key_uses_fallback(self):
        agent = AIDecisionAgent(api_key="")
        signal = {"confidence": 72, "decision": "BUY", "confidence_band": "VALID"}
        result = agent.decide("NIFTY", signal, {})
        assert result["ai_used"] is False
        assert "ai_notes" in result

    def test_fallback_preserves_signal(self):
        agent  = AIDecisionAgent(api_key="")
        signal = {"confidence": 80, "decision": "BUY", "underlying": "NIFTY"}
        result = agent.decide("NIFTY", signal, {})
        assert result["decision"]   == "BUY"
        assert result["confidence"] == 80
        assert result["underlying"] == "NIFTY"

    def test_merge_blends_confidence(self):
        agent  = AIDecisionAgent(api_key="fake_key_for_test")
        signal = {"confidence": 70, "decision": "BUY"}
        ai_out = {
            "direction": "LONG", "decision": "BUY", "confidence": 80,
            "instrument_type": "OPTION", "option_type": "CE",
            "entry_zone": "above 24500", "stop_loss_rationale": "below VWAP",
            "target_rationale": "next resistance", "risk_reward": 2.0,
            "market_regime": "BULL", "reasons": ["EMA bullish"],
            "invalidation": ["breaks VWAP"], "ai_notes": "Strong setup",
        }
        merged = agent._merge(signal, ai_out)
        # 70 * 0.6 + 80 * 0.4 = 74
        assert merged["confidence"] == pytest.approx(74.0, 0.1)
        assert merged["ai_used"]    is True

    def test_ai_no_trade_overrides_buy(self):
        agent  = AIDecisionAgent(api_key="fake_key_for_test")
        signal = {"confidence": 72, "decision": "BUY"}
        ai_out = {
            "direction": "NEUTRAL", "decision": "NO_TRADE", "confidence": 45,
            "instrument_type": "OPTION", "option_type": None,
            "entry_zone": "N/A", "stop_loss_rationale": "N/A",
            "target_rationale": "N/A", "risk_reward": 0,
            "market_regime": "RANGE", "reasons": ["conflicting signals"],
            "invalidation": [], "ai_notes": "Too many conflicting signals",
        }
        merged = agent._merge(signal, ai_out)
        assert merged["decision"]    == "NO_TRADE"
        assert merged["ai_override"] is True

    def test_prompt_contains_key_fields(self):
        agent  = AIDecisionAgent(api_key="")
        signal = {"confidence": 72, "decision": "BUY", "confidence_band": "VALID",
                  "market_regime": "BULL", "strategy": "Long call"}
        ctx    = {**make_tech(), "futures": make_futures(), "options": make_options(), "volume": make_volume()}
        prompt = agent._build_prompt("NIFTY", signal, ctx)
        assert "NIFTY"      in prompt
        assert "RSI"        in prompt
        assert "VWAP"       in prompt
        assert "Futures"    in prompt
        assert "PCR"        in prompt
        assert "72"         in prompt


# ── Orchestrator tests ────────────────────────────────────────────────────────

class TestSignalOrchestrator:

    def setup_method(self):
        self.orch = SignalOrchestrator(use_ai=False)

    def test_run_returns_signal(self):
        sig = self.orch.run("NIFTY")
        assert "underlying"  in sig
        assert "decision"    in sig
        assert "confidence"  in sig

    def test_run_nifty(self):
        sig = self.orch.run("NIFTY")
        assert sig["underlying"] == "NIFTY"

    def test_run_banknifty(self):
        sig = self.orch.run("BANKNIFTY")
        assert sig["underlying"] == "BANKNIFTY"

    def test_run_confidence_in_range(self):
        sig = self.orch.run("NIFTY")
        assert 0 <= sig["confidence"] <= 100

    def test_run_all_returns_sorted(self):
        results = self.orch.run_all(["NIFTY","BANKNIFTY"])
        assert len(results) == 2
        assert results[0]["confidence"] >= results[1]["confidence"]

    def test_decision_valid_value(self):
        sig = self.orch.run("NIFTY")
        assert sig["decision"] in ["BUY","SELL","NO_TRADE"]

    def test_market_regime_present(self):
        sig = self.orch.run("NIFTY")
        assert "market_regime" in sig
        assert isinstance(sig["market_regime"], str)

    def test_score_breakdown_present(self):
        sig = self.orch.run("NIFTY")
        assert "score_breakdown" in sig
        assert len(sig["score_breakdown"]) == len(DEFAULT_WEIGHTS)

    def test_orchestrator_with_custom_weights(self):
        weights = {k: 100//9 for k in DEFAULT_WEIGHTS}
        orch    = SignalOrchestrator(weights=weights, use_ai=False)
        sig     = orch.run("NIFTY")
        assert 0 <= sig["confidence"] <= 100
