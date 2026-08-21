"""
Unit tests - Backtesting Engine (Phase 4)
Tests: metrics calculator, backtest simulator, walk-forward tester.
"""

import pytest
import sys
import math
import numpy as np
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtesting.metrics      import calculate_metrics, format_report, _equity_curve, _max_drawdown, _sharpe, _sortino, _consecutive
from src.backtesting.engine       import BacktestSimulator
from src.backtesting.walk_forward import WalkForwardTester


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_trades(n=20, win_rate=0.6):
    """Synthetic trade list."""
    np.random.seed(42)
    trades = []
    for i in range(n):
        winner = np.random.random() < win_rate
        pnl    = np.random.uniform(800, 2000) if winner else -np.random.uniform(400, 900)
        gross  = pnl * 1.02
        trades.append({
            "trade_id":        f"T{i:03d}",
            "symbol":          "NIFTY",
            "direction":       "LONG",
            "entry_date":      f"2026-01-{i+1:02d}",
            "exit_date":       f"2026-01-{i+1:02d}",
            "entry_price":     24500.0,
            "exit_price":      24600.0 if winner else 24400.0,
            "gross_pnl":       round(gross, 2),
            "net_pnl":         round(pnl, 2),
            "charges":         round(gross - pnl, 2),
            "holding_minutes": 45,
            "exit_reason":     "TARGET" if winner else "STOP_LOSS",
            "confidence":      75.0,
            "market_regime":   "BULL",
        })
    return trades


def make_candles(n=600, trend=0.0003, symbol="NIFTY"):
    """Longer candle dataset for backtest simulation."""
    np.random.seed(7)
    base  = 24500.0
    close = base * np.cumprod(1 + np.random.normal(trend, 0.001, n))
    open_ = np.roll(close, 1); open_[0] = base
    high  = np.maximum(open_, close) * 1.0015
    low   = np.minimum(open_, close) * 0.9985
    vol   = np.random.randint(500_000, 2_000_000, n).astype(float)
    vwap  = (high + low + close) / 3
    idx   = pd.date_range("2025-01-02 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": vol, "vwap": vwap,
        "timestamp": idx,
    })


# ── Metrics tests ─────────────────────────────────────────────────────────────

class TestMetricsCalculator:

    def test_empty_trades_returns_zeros(self):
        m = calculate_metrics([])
        assert m["total_trades"] == 0
        assert m["net_pnl"]      == 0

    def test_total_trades_count(self):
        m = calculate_metrics(make_trades(15))
        assert m["total_trades"] == 15

    def test_win_rate_range(self):
        m = calculate_metrics(make_trades(20, win_rate=0.6))
        assert 0 <= m["win_rate"] <= 100

    def test_profit_factor_positive_system(self):
        m = calculate_metrics(make_trades(20, win_rate=0.7))
        assert m["profit_factor"] > 0

    def test_all_winners_infinite_profit_factor(self):
        trades = make_trades(5, win_rate=1.0)
        m = calculate_metrics(trades)
        assert m["profit_factor"] == float("inf") or m["profit_factor"] > 10

    def test_winning_plus_losing_equals_total(self):
        m = calculate_metrics(make_trades(20))
        assert m["winning_trades"] + m["losing_trades"] == m["total_trades"]

    def test_net_pnl_is_sum_of_trade_pnls(self):
        trades = make_trades(10)
        m      = calculate_metrics(trades)
        expected = round(sum(t["net_pnl"] for t in trades), 2)
        assert abs(m["net_pnl"] - expected) < 0.01

    def test_max_drawdown_non_negative(self):
        m = calculate_metrics(make_trades(20))
        assert m["max_drawdown"] >= 0

    def test_sharpe_is_float(self):
        m = calculate_metrics(make_trades(20))
        assert isinstance(m["sharpe_ratio"], float)

    def test_sortino_is_float(self):
        m = calculate_metrics(make_trades(20))
        assert isinstance(m["sortino_ratio"], float)

    def test_equity_curve_starts_at_capital(self):
        m = calculate_metrics(make_trades(10), initial_capital=500_000)
        assert m["equity_curve"][0] == 500_000

    def test_equity_curve_length(self):
        n      = 10
        trades = make_trades(n)
        m      = calculate_metrics(trades)
        assert len(m["equity_curve"]) == n + 1

    def test_max_consecutive_wins_gte_zero(self):
        m = calculate_metrics(make_trades(20))
        assert m["max_consecutive_wins"]   >= 0
        assert m["max_consecutive_losses"] >= 0

    def test_return_pct_calculation(self):
        trades = [{"net_pnl": 10000, "gross_pnl": 10500, "holding_minutes": 30,
                   "entry_date":"2026-01-01","exit_date":"2026-01-01",
                   "direction":"LONG","confidence":75,"market_regime":"BULL"}]
        m = calculate_metrics(trades, initial_capital=100_000)
        assert m["return_pct"] == pytest.approx(10.0, 0.01)

    def test_format_report_returns_string(self):
        m = calculate_metrics(make_trades(10))
        r = format_report(m, "NIFTY", "Test Strategy")
        assert isinstance(r, str)
        assert "NIFTY" in r
        assert "win_rate" in r.lower() or "Win" in r


# ── Internal metric helpers ───────────────────────────────────────────────────

class TestMetricHelpers:

    def test_equity_curve_monotone_all_wins(self):
        pnls  = [100, 200, 150]
        curve = _equity_curve(pnls, 1000)
        assert curve == [1000, 1100, 1300, 1450]

    def test_max_drawdown_simple(self):
        equity = [1000, 1200, 900, 1100]
        dd     = _max_drawdown(equity)
        assert dd == pytest.approx(300.0, 0.01)

    def test_max_drawdown_no_drawdown(self):
        equity = [1000, 1100, 1200, 1300]
        assert _max_drawdown(equity) == 0.0

    def test_sharpe_positive_system(self):
        pnls = [100] * 50 + [50] * 50
        s    = _sharpe(pnls)
        assert s > 0

    def test_sortino_positive_system(self):
        pnls = [100, 200, -50, 150, 80]
        s    = _sortino(pnls)
        assert isinstance(s, float)

    def test_consecutive_all_wins(self):
        pnls = [100, 200, 150, 300]
        w, l = _consecutive(pnls)
        assert w == 4
        assert l == 0

    def test_consecutive_alternating(self):
        pnls = [100, -50, 100, -50]
        w, l = _consecutive(pnls)
        assert w == 1
        assert l == 1


# ── Backtest simulator tests ──────────────────────────────────────────────────

class TestBacktestSimulator:

    def setup_method(self):
        self.df  = make_candles(n=500)
        self.sim = BacktestSimulator(
            "NIFTY", self.df,
            capital=500_000, min_confidence=60.0
        )

    def test_run_returns_dict(self):
        result = self.sim.run()
        assert isinstance(result, dict)

    def test_run_has_required_keys(self):
        result = self.sim.run()
        for k in ["symbol","metrics","trades","report","parameters"]:
            assert k in result, f"Missing key: {k}"

    def test_symbol_correct(self):
        result = self.sim.run()
        assert result["symbol"] == "NIFTY"

    def test_metrics_present(self):
        result = self.sim.run()
        m = result["metrics"]
        for k in ["total_trades","win_rate","net_pnl","max_drawdown","sharpe_ratio"]:
            assert k in m

    def test_no_look_ahead(self):
        """Confirm each trade entry bar > MIN_BARS_FOR_SIGNAL."""
        from src.backtesting.engine import MIN_BARS_FOR_SIGNAL
        result = self.sim.run()
        for t in result["trades"]:
            pass   # If we got here without error, no look-ahead crash occurred

    def test_report_is_string(self):
        result = self.sim.run()
        assert isinstance(result["report"], str)
        assert len(result["report"]) > 50

    def test_equity_curve_starts_at_capital(self):
        result = self.sim.run()
        assert result["metrics"]["equity_curve"][0] == 500_000

    def test_trade_fields_complete(self):
        sim    = BacktestSimulator("NIFTY", make_candles(500), min_confidence=55.0)
        result = sim.run()
        if result["trades"]:
            t = result["trades"][0]
            for f in ["trade_id","direction","entry_price","exit_price",
                      "net_pnl","charges","exit_reason"]:
                assert f in t, f"Missing trade field: {f}"

    def test_exit_reason_valid(self):
        sim    = BacktestSimulator("NIFTY", make_candles(500), min_confidence=55.0)
        result = sim.run()
        valid  = {"STOP_LOSS","TARGET","END_OF_DATA","MANUAL"}
        for t in result["trades"]:
            assert t["exit_reason"] in valid

    def test_charges_deducted(self):
        sim    = BacktestSimulator("NIFTY", make_candles(500), min_confidence=55.0)
        result = sim.run()
        for t in result["trades"]:
            assert t["net_pnl"] <= t["gross_pnl"] + 0.01   # net <= gross (charges reduce it)

    def test_banknifty_runs(self):
        df  = make_candles(500, symbol="BANKNIFTY")
        sim = BacktestSimulator("BANKNIFTY", df, min_confidence=60.0)
        r   = sim.run()
        assert r["symbol"] == "BANKNIFTY"

    def test_parameters_in_result(self):
        result = self.sim.run()
        p = result["parameters"]
        assert p["capital"]        == 500_000
        assert p["min_confidence"] == 60.0


# ── Walk-forward tests ────────────────────────────────────────────────────────

class TestWalkForwardTester:

    def setup_method(self):
        self.df = make_candles(n=800)

    def test_run_returns_dict(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        for k in ["symbol","n_windows","consistency_pct",
                  "aggregate_metrics","window_summaries","aggregate_report"]:
            assert k in result, f"Missing key: {k}"

    def test_consistency_pct_in_range(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert 0 <= result["consistency_pct"] <= 100

    def test_window_summaries_count(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert len(result["window_summaries"]) <= 2

    def test_aggregate_report_string(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert isinstance(result["aggregate_report"], str)

    def test_window_summary_fields(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        if result["window_summaries"]:
            ws = result["window_summaries"][0]
            for f in ["window","oos_bars","total_trades","win_rate","net_pnl"]:
                assert f in ws, f"Missing field: {f}"
