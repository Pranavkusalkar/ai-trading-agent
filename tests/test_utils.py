"""
Unit tests - Transaction costs and time utilities
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.utils.transaction_costs import calculate_fno_charges, round_trip_cost
from src.utils.time_utils import is_market_open, get_session, nearest_expiry
import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")


class TestTransactionCosts:
    def test_option_buy_no_stt(self):
        costs = calculate_fno_charges("option", "buy", 100, 50, 50, 950000)
        assert costs["stt"]       == 0.0
        assert costs["brokerage"] == 20.0
        assert costs["gst"]       > 0
        assert costs["total"]     > 0

    def test_option_sell_has_stt(self):
        costs = calculate_fno_charges("option", "sell", 150, 50, 50, 950000)
        assert costs["stt"] > 0

    def test_total_is_sum_of_components(self):
        costs = calculate_fno_charges("option", "sell", 200, 50, 50, 1000000)
        component_sum = (costs["brokerage"] + costs["stt"] + costs["exchange_charge"] +
                         costs["sebi_fee"]  + costs["stamp_duty"] + costs["gst"])
        assert abs(costs["total"] - component_sum) < 0.01

    def test_round_trip_net_pnl(self):
        result = round_trip_cost("option", 100, 150, 50, 50, 19000)
        assert result["gross_pnl"]     == 2500.0
        assert result["net_pnl"]       < result["gross_pnl"]
        assert result["total_charges"] > 0

    def test_round_trip_losing_trade(self):
        result = round_trip_cost("option", 200, 100, 50, 50, 19000)
        assert result["gross_pnl"] == -5000.0
        assert result["net_pnl"]   < result["gross_pnl"]


class TestTimeUtils:
    def _make_ist(self, hour, minute, weekday_offset=0):
        base = datetime.datetime(2026, 8, 17, hour, minute, 0)
        base += datetime.timedelta(days=weekday_offset)
        return IST.localize(base)

    def test_market_open_during_session(self):
        assert is_market_open(self._make_ist(10, 30)) is True

    def test_market_closed_before_open(self):
        assert is_market_open(self._make_ist(9, 0)) is False

    def test_market_closed_after_close(self):
        assert is_market_open(self._make_ist(15, 31)) is False

    def test_market_closed_on_weekend(self):
        assert is_market_open(self._make_ist(11, 0, weekday_offset=5)) is False

    def test_session_opening(self):
        assert get_session(self._make_ist(9, 20))  == "OPENING"

    def test_session_midday(self):
        assert get_session(self._make_ist(11, 0))  == "MIDDAY"

    def test_session_closing(self):
        assert get_session(self._make_ist(15, 0))  == "CLOSING"

    def test_session_pre_market(self):
        assert get_session(self._make_ist(9, 5))   == "PRE_MARKET"

    def test_nearest_expiry_is_thursday(self):
        dt = self._make_ist(10, 0)
        assert nearest_expiry("NIFTY", dt).weekday() == 3
