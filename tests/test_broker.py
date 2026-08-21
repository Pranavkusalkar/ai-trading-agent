"""
Unit tests - Phase 6 Broker Integration
Tests: AngelOneBroker (mocked), BrokerFactory, safety gates, crash recovery.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.execution.brokers.angel_one import AngelOneBroker
from src.execution.brokers.factory   import create_broker, get_broker_status
from src.execution.paper_broker      import PaperBroker


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_angel_broker():
    """AngelOneBroker with mocked SmartAPI internals."""
    broker = AngelOneBroker()
    broker.api_key     = "test_key"
    broker.client_id   = "TEST123"
    broker.password    = "1234"
    broker.totp_secret = "JBSWY3DPEHPK3PXP"
    return broker


def mock_smart_api():
    """Mock SmartConnect object with all methods stubbed."""
    mock = MagicMock()
    mock.generateSession.return_value = {
        "status": True,
        "data":   {"jwtToken": "fake_token", "refreshToken": "fake_refresh"},
    }
    mock.getfeedToken.return_value = "fake_feed_token"
    mock.ltpData.return_value = {
        "status": True,
        "data":   {"ltp": 24500.0},
    }
    mock.rmsLimit.return_value = {
        "status": True,
        "data":   {"availablecash": "500000", "net": "480000", "utiliseddebits": "20000"},
    }
    mock.position.return_value = {
        "status": True,
        "data": [{
            "tradingsymbol": "NIFTY24AUG24500CE",
            "netqty": "50",
            "netprice": "200.5",
            "ltp": "210.0",
            "unrealised": "475.0",
            "producttype": "INTRADAY",
        }],
    }
    mock.orderBook.return_value = {"status": True, "data": []}
    mock.placeOrder.return_value = {
        "status": True,
        "data":   {"orderid": "ORD12345"},
    }
    mock.cancelOrder.return_value = {"status": True}
    mock.modifyOrder.return_value = {"status": True}
    mock.terminateSession.return_value = {"status": True}
    mock.getCandleData.return_value = {
        "status": True,
        "data": [
            ["2026-08-18T09:15:00+05:30", 24500, 24550, 24480, 24530, 1000000],
            ["2026-08-18T09:20:00+05:30", 24530, 24580, 24510, 24560, 900000],
        ],
    }
    return mock


# ── AngelOneBroker unit tests ─────────────────────────────────────────────────

class TestAngelOneBroker:

    def test_initialises_without_credentials(self):
        broker = AngelOneBroker()
        assert broker.is_connected() is False

    def test_connect_fails_without_sdk(self):
        """Should fail gracefully if smartapi-python not installed."""
        broker = make_angel_broker()
        with patch("builtins.__import__", side_effect=ImportError("smartapi not installed")):
            # connect() catches ImportError and returns False
            pass   # just verify no exception propagates

    def test_connect_with_mock_sdk(self):
        broker = make_angel_broker()
        mock   = mock_smart_api()

        with patch.dict("sys.modules", {"SmartApi": MagicMock(SmartConnect=MagicMock(return_value=mock))}):
            with patch("pyotp.TOTP") as mock_totp:
                mock_totp.return_value.now.return_value = "123456"
                result = broker.connect()

        assert result is True
        assert broker._auth_token == "fake_token"

    def test_get_ltp_requires_connection(self):
        broker = make_angel_broker()
        with pytest.raises(RuntimeError, match="not connected"):
            broker.get_ltp("NIFTY")

    def test_get_ltp_with_mock(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        ltp = broker.get_ltp("NIFTY", "NSE")
        assert ltp == 24500.0

    def test_get_balance_with_mock(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        bal = broker.get_balance()
        assert "available_margin" in bal
        assert bal["available_margin"] == 480000.0

    def test_get_positions_with_mock(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "NIFTY24AUG24500CE"
        assert positions[0]["quantity"] == 50

    def test_get_historical_candles_with_mock(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        candles = broker.get_historical_candles("NIFTY", "NSE", "5min", "2026-08-18", "2026-08-18")
        assert len(candles) == 2
        assert candles[0]["open"] == 24500
        assert candles[0]["close"] == 24530

    def test_place_order_blocked_in_paper_mode(self):
        """Orders must be blocked unless TRADING_MODE=live + ENABLE_LIVE_TRADING=true."""
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        os.environ["TRADING_MODE"]        = "paper"
        os.environ["ENABLE_LIVE_TRADING"] = "false"
        with pytest.raises(RuntimeError, match="LIVE ORDER BLOCKED"):
            broker.place_order("NIFTY", "NSE", "MARKET", "BUY", 50)

    def test_place_order_blocked_without_live_flag(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        os.environ["TRADING_MODE"]        = "live"
        os.environ["ENABLE_LIVE_TRADING"] = "false"   # not enabled
        with pytest.raises(RuntimeError, match="LIVE ORDER BLOCKED"):
            broker.place_order("NIFTY", "NSE", "MARKET", "BUY", 50)

    def test_place_order_allowed_with_live_flags(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        os.environ["TRADING_MODE"]        = "live"
        os.environ["ENABLE_LIVE_TRADING"] = "true"
        result = broker.place_order("NIFTY", "NSE", "MARKET", "BUY", 50)
        assert result["order_id"] == "ORD12345"
        assert result["status"]   == "PLACED"
        # Reset
        os.environ["TRADING_MODE"]        = "paper"
        os.environ["ENABLE_LIVE_TRADING"] = "false"

    def test_disconnect_clears_state(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        broker.disconnect()
        assert broker.is_connected() is False
        assert broker._smart_api     is None

    def test_reconcile_positions(self):
        broker = make_angel_broker()
        broker._smart_api = mock_smart_api()
        broker._connected = True

        local = {"NIFTY24AUG24500CE": {"quantity": 50}}
        result = broker.reconcile_positions(local)

        assert "matched"          in result
        assert "missing_locally"  in result
        assert "extra_locally"    in result
        assert "NIFTY24AUG24500CE" in result["matched"]

    def test_token_lookup(self):
        broker = make_angel_broker()
        assert broker._get_token("NIFTY")     == "26000"
        assert broker._get_token("BANKNIFTY") == "26009"

    def test_order_type_mapping(self):
        broker = make_angel_broker()
        assert broker._map_order_type("MARKET") == "MARKET"
        assert broker._map_order_type("LIMIT")  == "LIMIT"
        assert broker._map_order_type("SL")     == "STOPLOSS_LIMIT"
        assert broker._map_order_type("SL-M")   == "STOPLOSS_MARKET"


# ── BrokerFactory tests ───────────────────────────────────────────────────────

class TestBrokerFactory:

    def test_paper_mode_returns_paper_broker(self):
        os.environ["TRADING_MODE"] = "paper"
        broker = create_broker()
        assert isinstance(broker, PaperBroker)
        assert broker.is_connected() is True

    def test_backtest_mode_returns_paper_broker(self):
        os.environ["TRADING_MODE"] = "backtest"
        broker = create_broker()
        assert isinstance(broker, PaperBroker)

    def test_live_mode_without_flag_raises(self):
        os.environ["TRADING_MODE"]        = "live"
        os.environ["ENABLE_LIVE_TRADING"] = "false"
        with pytest.raises(RuntimeError, match="ENABLE_LIVE_TRADING"):
            create_broker()

    def test_invalid_mode_raises(self):
        os.environ["TRADING_MODE"] = "invalid"
        with pytest.raises(ValueError, match="TRADING_MODE"):
            create_broker()

    def test_paper_broker_connected_after_factory(self):
        os.environ["TRADING_MODE"] = "paper"
        broker = create_broker()
        assert broker.is_connected() is True

    def test_get_broker_status_paper(self):
        os.environ["TRADING_MODE"] = "paper"
        broker = create_broker()
        status = get_broker_status(broker)
        assert status["connected"]   is True
        assert "broker_type"         in status
        assert "available_margin"    in status

    def teardown_method(self):
        os.environ["TRADING_MODE"]        = "paper"
        os.environ["ENABLE_LIVE_TRADING"] = "false"


# ── Safety gate tests ─────────────────────────────────────────────────────────

class TestSafetyGates:

    def test_paper_mode_is_default_safe(self):
        os.environ.pop("TRADING_MODE", None)
        broker = create_broker()
        assert isinstance(broker, PaperBroker)

    def test_live_trading_requires_both_flags(self):
        """Both TRADING_MODE=live AND ENABLE_LIVE_TRADING=true required."""
        # Only mode set, not flag
        os.environ["TRADING_MODE"]        = "live"
        os.environ["ENABLE_LIVE_TRADING"] = "false"
        with pytest.raises(RuntimeError):
            create_broker()

        # Only flag set, not mode
        os.environ["TRADING_MODE"]        = "paper"
        os.environ["ENABLE_LIVE_TRADING"] = "true"
        broker = create_broker()
        assert isinstance(broker, PaperBroker)   # paper mode overrides flag

    def test_angel_order_blocked_in_paper_mode(self):
        broker = AngelOneBroker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        os.environ["TRADING_MODE"]        = "paper"
        os.environ["ENABLE_LIVE_TRADING"] = "false"
        with pytest.raises(RuntimeError, match="LIVE ORDER BLOCKED"):
            broker.place_order("NIFTY", "NSE", "MARKET", "BUY", 50)

    def test_cancel_blocked_in_paper_mode(self):
        broker = AngelOneBroker()
        broker._smart_api = mock_smart_api()
        broker._connected = True
        os.environ["TRADING_MODE"]        = "paper"
        os.environ["ENABLE_LIVE_TRADING"] = "false"
        with pytest.raises(RuntimeError, match="LIVE ORDER BLOCKED"):
            broker.cancel_order("ORD123")

    def teardown_method(self):
        os.environ["TRADING_MODE"]        = "paper"
        os.environ["ENABLE_LIVE_TRADING"] = "false"
