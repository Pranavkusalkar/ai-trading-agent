"""
Unit tests - Paper Trading Engine (Phase 5)
Tests: PaperBroker, OrderManager, PositionManager, AlertSystem, PaperTradingEngine.
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.execution.paper_broker     import PaperBroker, PaperOrder, PaperPosition
from src.execution.order_manager    import OrderManager, OrderState
from src.execution.position_manager import PositionManager
from src.monitoring.alerts          import AlertSystem
from src.execution.paper_engine     import PaperTradingEngine


# ── PaperBroker tests ─────────────────────────────────────────────────────────

class TestPaperBroker:

    def setup_method(self):
        self.broker = PaperBroker(initial_capital=500_000)

    def test_connect_returns_true(self):
        assert self.broker.connect() is True

    def test_is_connected(self):
        assert self.broker.is_connected() is True

    def test_update_and_get_ltp(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        assert self.broker.get_ltp("NIFTY") == 24500.0

    def test_place_market_order_filled(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        order = self.broker.place_order("NIFTY", "BUY", 50, "MARKET")
        assert order.status       == "FILLED"
        assert order.filled_qty   == 50
        assert order.filled_price > 0

    def test_slippage_applied_on_buy(self):
        ltp = 24500.0
        self.broker.update_ltp("NIFTY", ltp)
        order = self.broker.place_order("NIFTY", "BUY", 50, "MARKET")
        assert order.filled_price > ltp   # buy price is slightly higher

    def test_slippage_applied_on_sell(self):
        ltp = 24500.0
        self.broker.update_ltp("NIFTY", ltp)
        order = self.broker.place_order("NIFTY", "SELL", 50, "MARKET")
        assert order.filled_price < ltp   # sell price is slightly lower

    def test_open_and_close_position(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        self.broker.open_position(
            "T001", "NIFTY", "LONG", 50,
            24500.0, 24350.0, 24800.0
        )
        assert len(self.broker.get_positions()) == 1
        record = self.broker.close_position("T001", 24700.0, "TARGET")
        assert record is not None
        assert record["net_pnl"] != 0
        assert len(self.broker.get_positions()) == 0

    def test_close_nonexistent_position_returns_none(self):
        result = self.broker.close_position("FAKE", 24500.0)
        assert result is None

    def test_get_balance_keys(self):
        bal = self.broker.get_balance()
        for k in ["capital","available_margin","session_pnl","open_positions"]:
            assert k in bal

    def test_session_summary_empty(self):
        s = self.broker.get_session_summary()
        assert s["trades"] == 0

    def test_session_summary_after_trade(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        self.broker.open_position("T001","NIFTY","LONG",50,24500,24350,24800)
        self.broker.close_position("T001", 24700.0, "TARGET")
        s = self.broker.get_session_summary()
        assert s["trades"] == 1

    def test_unrealised_pnl_updates(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        self.broker.open_position("T001","NIFTY","LONG",50,24500,24350,24800)
        self.broker.update_ltp("NIFTY", 24600.0)
        pos = self.broker.get_positions()[0]
        assert pos.unrealised_pnl == pytest.approx(50 * 100.0, abs=5)

    def test_cancel_pending_order(self):
        order = self.broker.place_order("NIFTY","BUY",50,"LIMIT",price=24000)
        result = self.broker.cancel_order(order.order_id)
        # PaperBroker fills MARKET orders immediately; LIMIT stays pending
        # Just check no crash
        assert isinstance(result, bool)


# ── OrderManager tests ────────────────────────────────────────────────────────

class TestOrderManager:

    def setup_method(self):
        self.broker = PaperBroker(initial_capital=500_000)
        self.broker.update_ltp("NIFTY", 24500.0)
        self.om = OrderManager(self.broker)

    def test_submit_market_order_filled(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        assert order.state        == OrderState.FILLED
        assert order.filled_price  > 0

    def test_order_stored(self):
        self.om.submit("T001","NIFTY","BUY",50)
        assert len(self.om.get_all_orders()) == 1

    def test_get_order_by_id(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        found = self.om.get_order(order.order_id)
        assert found is not None
        assert found.order_id == order.order_id

    def test_get_trade_orders(self):
        self.om.submit("T001","NIFTY","BUY",50)
        self.om.submit("T001","NIFTY","SELL",50)
        orders = self.om.get_trade_orders("T001")
        assert len(orders) == 2

    def test_complete_filled_order(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        result = self.om.complete(order.order_id)
        assert result is True
        assert self.om.get_order(order.order_id).state == OrderState.COMPLETED

    def test_session_summary_keys(self):
        self.om.submit("T001","NIFTY","BUY",50)
        s = self.om.session_summary()
        for k in ["total","filled","pending","cancelled","rejected"]:
            assert k in s

    def test_invalid_state_transition_ignored(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        # Try invalid transition: FILLED → PENDING
        self.om._transition(order, OrderState.PENDING)
        assert order.state == OrderState.FILLED   # unchanged


# ── PositionManager tests ─────────────────────────────────────────────────────

class TestPositionManager:

    def setup_method(self):
        self.broker = PaperBroker(initial_capital=500_000)
        self.broker.update_ltp("NIFTY", 24500.0)
        self.events = []
        self.pm     = PositionManager(
            broker   = self.broker,
            alert_fn = lambda et, msg, data: self.events.append(et)
        )

    def _open_pos(self, direction="LONG", entry=24500, sl=24350, tgt=24800):
        tid = "T001"
        self.broker.open_position(tid,"NIFTY",direction,50,entry,sl,tgt)
        self.pm.register(tid,"NIFTY",direction,50,entry,sl,tgt)
        return tid

    def test_register_adds_position(self):
        self._open_pos()
        assert self.pm.get_count() == 1

    def test_get_position(self):
        tid = self._open_pos()
        pos = self.pm.get_position(tid)
        assert pos is not None
        assert pos["symbol"] == "NIFTY"

    def test_target_hit_closes_position(self):
        self._open_pos(entry=24500, sl=24350, tgt=24700)
        exits = self.pm.on_price_update("NIFTY", 24750.0)
        assert len(exits) > 0
        assert self.pm.get_count() == 0

    def test_stop_loss_hit_closes_position(self):
        self._open_pos(entry=24500, sl=24350, tgt=24800)
        exits = self.pm.on_price_update("NIFTY", 24300.0)
        assert len(exits) > 0
        assert self.pm.get_count() == 0

    def test_no_exit_between_sl_and_target(self):
        self._open_pos(entry=24500, sl=24350, tgt=24800)
        exits = self.pm.on_price_update("NIFTY", 24550.0)
        assert len(exits) == 0
        assert self.pm.get_count() == 1

    def test_modify_stop(self):
        tid = self._open_pos()
        result = self.pm.modify_stop(tid, 24450.0)
        assert result is True
        assert self.pm.get_position(tid)["stop_loss"] == 24450.0

    def test_force_close_all(self):
        self._open_pos()
        self.pm.force_close_all("EOD")
        assert self.pm.get_count() == 0

    def test_breakeven_applied_after_1r(self):
        # Entry 24500, SL 24350 (risk=150), target 24800
        tid = self._open_pos(entry=24500, sl=24350, tgt=24800)
        # Price moves +150 (1R) — should apply break-even
        self.pm.on_price_update("NIFTY", 24660.0)
        pos = self.pm.get_position(tid)
        if pos:   # if position still open
            assert pos["be_applied"] is True


# ── AlertSystem tests ─────────────────────────────────────────────────────────

class TestAlertSystem:

    def setup_method(self):
        # No Telegram credentials — console only
        self.alerts = AlertSystem(console=True)

    def test_send_returns_bool(self):
        result = self.alerts.send("SESSION_START", "Test alert")
        assert isinstance(result, bool)
        assert result is True

    def test_send_signal(self):
        signal = {
            "underlying": "NIFTY", "decision": "BUY",
            "confidence": 78.0, "strategy": "Long call",
            "market_regime": "BULL", "reasons": ["EMA bullish"],
            "stop_loss": 24350, "target": 24800, "risk_reward": 2.0,
        }
        result = self.alerts.send_signal(signal)
        assert result is True

    def test_send_trade_closed(self):
        result = self.alerts.send_trade_closed({
            "symbol": "NIFTY", "net_pnl": 1200.0, "exit_reason": "TARGET"
        })
        assert result is True

    def test_send_session_summary(self):
        result = self.alerts.send_session_summary({
            "trades": 5, "win_rate": 60.0, "session_pnl": 3500.0
        })
        assert result is True

    def test_no_telegram_no_crash(self):
        a = AlertSystem(telegram_token="", telegram_chat_id="", console=False)
        result = a.send("SESSION_START", "Test")
        assert result is False   # console disabled, telegram not configured


# ── PaperTradingEngine tests ──────────────────────────────────────────────────

class TestPaperTradingEngine:

    def setup_method(self):
        self.engine = PaperTradingEngine(
            symbols        = ["NIFTY"],
            capital        = 500_000,
            min_confidence = 60.0,
            data_mode      = "mock",
        )

    def test_run_bars_returns_dict(self):
        result = self.engine.run_bars(n=3)
        assert isinstance(result, dict)

    def test_run_bars_required_keys(self):
        result = self.engine.run_bars(n=3)
        for k in ["session_date","symbols","bars_processed",
                  "signals_generated","trade_summary","balance"]:
            assert k in result, f"Missing key: {k}"

    def test_signals_generated(self):
        result = self.engine.run_bars(n=5)
        assert result["signals_generated"] >= 5   # 1 per bar per symbol

    def test_balance_keys(self):
        result = self.engine.run_bars(n=2)
        bal    = result["balance"]
        for k in ["capital","available_margin","session_pnl"]:
            assert k in bal

    def test_session_log_saved(self):
        import os
        self.engine.log_dir = "logs_test"
        self.engine.run_bars(n=2)
        log_files = [f for f in os.listdir("logs_test") if f.endswith(".json")]
        assert len(log_files) >= 1
        # Cleanup
        import shutil
        shutil.rmtree("logs_test", ignore_errors=True)

    def test_multi_symbol(self):
        engine = PaperTradingEngine(
            symbols=["NIFTY","BANKNIFTY"], min_confidence=60.0, data_mode="mock"
        )
        result = engine.run_bars(n=2)
        assert "NIFTY"     in result["symbols"]
        assert "BANKNIFTY" in result["symbols"]

    def test_stop_works(self):
        self.engine.stop()
        assert self.engine._running is False

    def test_capital_preserved_structure(self):
        result = self.engine.run_bars(n=3)
        assert result["balance"]["capital"] == 500_000
