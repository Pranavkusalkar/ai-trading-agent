"""
Unit tests - Risk Manager
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.risk.risk_manager import RiskManager

CAPITAL  = 500_000
BASE_CFG = {
    "risk": {
        "max_risk_per_trade":     0.005,
        "max_daily_loss":         0.02,
        "max_weekly_loss":        0.05,
        "max_trades_per_day":     5,
        "max_consecutive_losses": 3,
        "max_open_positions":     3,
        "min_risk_reward":        1.5,
        "min_confidence":         70,
    }
}

VALID_SIGNAL = {
    "confidence":  80,
    "risk_reward": 2.0,
    "entry":       19000.0,
    "stop_loss":   18800.0,
    "target":      19400.0,
}


def make_rm():
    rm = RiskManager(BASE_CFG, CAPITAL)
    rm.state.broker_connected = True
    import datetime
    rm.state.data_last_received = datetime.datetime.now()
    return rm


class TestSignalValidation:
    def test_valid_signal_approved(self):
        rm = make_rm()
        assert rm.validate_signal(VALID_SIGNAL).approved is True

    def test_low_confidence_rejected(self):
        rm = make_rm()
        r = rm.validate_signal({**VALID_SIGNAL, "confidence": 60})
        assert r.approved is False
        assert "Confidence" in r.reason

    def test_low_rr_rejected(self):
        rm = make_rm()
        r = rm.validate_signal({**VALID_SIGNAL, "risk_reward": 1.0})
        assert r.approved is False
        assert "R:R" in r.reason

    def test_missing_stoploss_rejected(self):
        rm = make_rm()
        sig = {**VALID_SIGNAL}
        del sig["stop_loss"]
        assert rm.validate_signal(sig).approved is False

    def test_broker_disconnected_rejected(self):
        rm = make_rm()
        rm.state.broker_connected = False
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "Broker" in r.reason

    def test_stale_data_rejected(self):
        import datetime
        rm = make_rm()
        rm.state.data_last_received = datetime.datetime.now() - datetime.timedelta(seconds=300)
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "stale" in r.reason.lower()

    def test_no_data_received_rejected(self):
        rm = make_rm()
        rm.state.data_last_received = None
        assert rm.validate_signal(VALID_SIGNAL).approved is False


class TestDailyLimits:
    def test_daily_loss_limit_halts_trading(self):
        rm = make_rm()
        rm.state.daily_pnl = -(CAPITAL * 0.021)
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert rm.state.is_trading_halted is True

    def test_max_trades_per_day_rejected(self):
        rm = make_rm()
        rm.state.trades_today = 5
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "trades" in r.reason.lower()

    def test_consecutive_losses_halts(self):
        rm = make_rm()
        rm.state.consecutive_losses = 3
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert rm.state.is_trading_halted is True

    def test_max_positions_rejected(self):
        rm = make_rm()
        rm.state.open_positions = 3
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "positions" in r.reason.lower()


class TestPositionSizing:
    def test_basic_sizing(self):
        rm = make_rm()
        r = rm.calculate_position_size(entry=200.0, stop_loss=180.0, lot_size=50)
        assert r["lots"] >= 1
        assert r["risk_pct"] <= rm.max_risk_pct * 100 * 2

    def test_zero_risk_returns_error(self):
        rm = make_rm()
        r = rm.calculate_position_size(entry=200.0, stop_loss=200.0, lot_size=50)
        assert "error" in r

    def test_quantity_is_multiple_of_lot(self):
        rm = make_rm()
        r = rm.calculate_position_size(entry=250.0, stop_loss=220.0, lot_size=50)
        assert r["quantity"] % 50 == 0


class TestStateTransitions:
    def test_winning_trade_resets_consecutive_losses(self):
        rm = make_rm()
        rm.state.consecutive_losses = 2
        rm.on_trade_closed(pnl=1000)
        assert rm.state.consecutive_losses == 0

    def test_losing_trade_increments_consecutive_losses(self):
        rm = make_rm()
        rm.on_trade_closed(pnl=-500)
        assert rm.state.consecutive_losses == 1

    def test_daily_reset(self):
        rm = make_rm()
        rm.state.daily_pnl    = -12000
        rm.state.trades_today = 4
        rm._halt("daily loss")
        rm.reset_daily()
        assert rm.state.daily_pnl    == 0
        assert rm.state.trades_today == 0
        assert rm.state.is_trading_halted is False
