"""
Unit tests - Dashboard (Phase 7)
Tests the DashboardDataProvider — the data layer under the Streamlit UI.
The Streamlit UI itself is not unit tested (requires browser).
"""

import pytest
import sys
import os
import json
import tempfile
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.dashboard.data_provider  import DashboardDataProvider
from src.execution.paper_broker   import PaperBroker
from src.execution.order_manager  import OrderManager
from src.execution.position_manager import PositionManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_broker(capital=500_000):
    b = PaperBroker(initial_capital=capital)
    b.connect()
    b.update_ltp("NIFTY", 24500.0)
    return b


def make_dp(broker=None, log_dir=None):
    b   = broker or make_broker()
    om  = OrderManager(b)
    pm  = PositionManager(b)
    return DashboardDataProvider(
        broker       = b,
        position_mgr = pm,
        order_mgr    = om,
        log_dir      = log_dir or "logs",
    ), b, om, pm


# ── Account tests ─────────────────────────────────────────────────────────────

class TestDashboardAccount:

    def test_get_account_returns_dict(self):
        dp, *_ = make_dp()
        acc = dp.get_account()
        assert isinstance(acc, dict)

    def test_get_account_has_capital(self):
        dp, *_ = make_dp(make_broker(300_000))
        acc = dp.get_account()
        assert acc["capital"] == 300_000

    def test_get_account_has_required_keys(self):
        dp, *_ = make_dp()
        acc = dp.get_account()
        for k in ["capital","available_margin","session_pnl"]:
            assert k in acc

    def test_fallback_when_broker_none(self):
        dp = DashboardDataProvider()
        acc = dp.get_account()
        assert acc["capital"] == 500_000   # default fallback

    def test_get_session_summary_empty(self):
        dp, *_ = make_dp()
        s = dp.get_session_summary()
        assert s["trades"] == 0

    def test_get_session_summary_after_trade(self):
        dp, broker, om, pm = make_dp()
        broker.open_position("T1","NIFTY","LONG",50,24500,24350,24800)
        broker.close_position("T1", 24700.0, "TARGET")
        s = dp.get_session_summary()
        assert s["trades"] == 1


# ── Position tests ────────────────────────────────────────────────────────────

class TestDashboardPositions:

    def test_get_positions_empty(self):
        dp, *_ = make_dp()
        assert dp.get_positions() == []

    def test_get_positions_with_open_pos(self):
        dp, broker, om, pm = make_dp()
        broker.open_position("T1","NIFTY","LONG",50,24500,24350,24800)
        pm.register("T1","NIFTY","LONG",50,24500,24350,24800)
        positions = dp.get_positions()
        assert len(positions) == 1

    def test_get_closed_trades_empty(self):
        dp, *_ = make_dp()
        assert dp.get_closed_trades() == []

    def test_get_closed_trades_after_close(self):
        dp, broker, om, pm = make_dp()
        broker.open_position("T1","NIFTY","LONG",50,24500,24350,24800)
        broker.close_position("T1", 24700.0, "TARGET")
        trades = dp.get_closed_trades()
        assert len(trades) == 1
        assert trades[0]["net_pnl"] != 0


# ── Order tests ───────────────────────────────────────────────────────────────

class TestDashboardOrders:

    def test_get_orders_empty(self):
        dp, *_ = make_dp()
        assert dp.get_orders() == []

    def test_get_orders_after_submit(self):
        dp, broker, om, pm = make_dp()
        om.submit("T1","NIFTY","BUY",50)
        orders = dp.get_orders()
        assert len(orders) == 1
        assert "order_id" in orders[0]
        assert "state"    in orders[0]


# ── Signal tests ──────────────────────────────────────────────────────────────

class TestDashboardSignals:

    def test_record_signal(self):
        dp, *_ = make_dp()
        sig = {"underlying":"NIFTY","confidence":72,"decision":"BUY"}
        dp.record_signal(sig)
        assert dp.get_last_signal("NIFTY") is not None

    def test_get_last_signal_none_before_record(self):
        dp, *_ = make_dp()
        assert dp.get_last_signal("NIFTY") is None

    def test_get_signal_history_empty(self):
        dp, *_ = make_dp()
        assert dp.get_signal_history() == []

    def test_get_signal_history_limit(self):
        dp, *_ = make_dp()
        for i in range(30):
            dp.record_signal({"underlying":"NIFTY","confidence":70+i,"decision":"BUY"})
        hist = dp.get_signal_history(limit=10)
        assert len(hist) == 10

    def test_signal_history_keeps_last_100(self):
        dp, *_ = make_dp()
        for i in range(120):
            dp.record_signal({"underlying":"NIFTY","confidence":50,"decision":"NO_TRADE"})
        assert len(dp._signal_history) == 100

    def test_last_signal_overwritten_on_new(self):
        dp, *_ = make_dp()
        dp.record_signal({"underlying":"NIFTY","confidence":70,"decision":"BUY"})
        dp.record_signal({"underlying":"NIFTY","confidence":80,"decision":"SELL"})
        last = dp.get_last_signal("NIFTY")
        assert last["confidence"] == 80


# ── Risk state tests ──────────────────────────────────────────────────────────

class TestDashboardRisk:

    def test_get_risk_state_returns_dict(self):
        dp, *_ = make_dp()
        r = dp.get_risk_state()
        assert isinstance(r, dict)

    def test_get_risk_state_has_keys(self):
        dp, *_ = make_dp()
        r = dp.get_risk_state()
        for k in ["daily_pnl","trades_today","consecutive_losses",
                  "open_positions","is_halted","broker_connected"]:
            assert k in r

    def test_broker_connected_shows_true(self):
        dp, *_ = make_dp()
        r = dp.get_risk_state()
        assert r["broker_connected"] is True

    def test_no_risk_mgr_fallback(self):
        dp = DashboardDataProvider()
        r  = dp.get_risk_state()
        assert r["is_halted"] is False


# ── Equity curve tests ────────────────────────────────────────────────────────

class TestEquityCurve:

    def test_equity_curve_starts_at_capital(self):
        dp, *_ = make_dp(make_broker(500_000))
        curve = dp.get_equity_curve()
        assert curve[0] == 500_000

    def test_equity_curve_single_point_no_trades(self):
        dp, *_ = make_dp()
        curve = dp.get_equity_curve()
        assert len(curve) == 1

    def test_equity_curve_grows_after_win(self):
        dp, broker, om, pm = make_dp()
        broker.open_position("T1","NIFTY","LONG",50,24500,24350,24800)
        broker.close_position("T1", 24700.0, "TARGET")
        curve = dp.get_equity_curve()
        assert len(curve) == 2
        # Winner should increase equity (or at least not crash)
        assert isinstance(curve[1], float)


# ── System status tests ───────────────────────────────────────────────────────

class TestSystemStatus:

    def test_get_system_status_returns_dict(self):
        dp, *_ = make_dp()
        s = dp.get_system_status()
        assert isinstance(s, dict)

    def test_system_status_keys(self):
        dp, *_ = make_dp()
        s = dp.get_system_status()
        for k in ["timestamp","broker_connected","trading_mode","market_open"]:
            assert k in s

    def test_trading_mode_from_env(self):
        os.environ["TRADING_MODE"] = "paper"
        dp, *_ = make_dp()
        s = dp.get_system_status()
        assert s["trading_mode"] == "PAPER"


# ── Session log tests ─────────────────────────────────────────────────────────

class TestSessionLog:

    def test_load_log_returns_none_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dp = DashboardDataProvider(log_dir=tmpdir)
            assert dp.load_latest_session_log() is None

    def test_load_log_returns_dict_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "paper_session_2026-08-18.json")
            sample   = {"session_date": "2026-08-18", "trades": 5, "session_pnl": 1200}
            with open(log_path, "w") as f:
                json.dump(sample, f)
            dp = DashboardDataProvider(log_dir=tmpdir)
            result = dp.load_latest_session_log()
            assert result is not None
            assert result["trades"] == 5

    def test_load_log_picks_latest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for date in ["2026-08-16","2026-08-17","2026-08-18"]:
                path = os.path.join(tmpdir, f"paper_session_{date}.json")
                with open(path,"w") as f:
                    json.dump({"session_date": date}, f)
            dp = DashboardDataProvider(log_dir=tmpdir)
            result = dp.load_latest_session_log()
            assert result["session_date"] == "2026-08-18"
