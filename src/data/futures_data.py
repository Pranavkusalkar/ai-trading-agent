"""
Futures Data Agent (Spec section 7)
Fetches futures price, OI, change-in-OI and classifies:
  LONG_BUILDUP    — price up + OI up
  SHORT_BUILDUP   — price down + OI up
  LONG_UNWINDING  — price down + OI down
  SHORT_COVERING  — price up + OI down
"""

import logging
import random
import datetime
from typing import Optional
import pytz

from src.data.data_cache import get_cache

log   = logging.getLogger(__name__)
IST   = pytz.timezone("Asia/Kolkata")
cache = get_cache()


def classify_oi_signal(
    price_change: float, oi_change: float
) -> str:
    """
    Classify futures OI signal per spec section 7.
    price_change and oi_change are floats (positive = increase).
    """
    price_up = price_change >= 0
    oi_up    = oi_change    >= 0

    if price_up  and oi_up:   return "LONG_BUILDUP"
    if not price_up and oi_up: return "SHORT_BUILDUP"
    if not price_up and not oi_up: return "LONG_UNWINDING"
    return "SHORT_COVERING"


def describe_oi_signal(signal: str) -> str:
    descriptions = {
        "LONG_BUILDUP":    "Fresh longs being added — bullish",
        "SHORT_BUILDUP":   "Fresh shorts being added — bearish",
        "LONG_UNWINDING":  "Longs exiting — bearish",
        "SHORT_COVERING":  "Shorts exiting — mild bullish",
    }
    return descriptions.get(signal, "Unknown")


class FuturesDataAgent:
    """
    Provides futures market data.
    In mock mode, generates realistic synthetic OI/price data.
    In broker mode, fetches from the connected broker.
    """

    def __init__(self, data_provider=None, mock: bool = True):
        self._provider = data_provider
        self._mock     = mock
        self._rng      = random.Random(99)

        # Synthetic state for mock
        self._mock_state = {
            "NIFTY":     {"oi": 12_500_000, "prev_oi": 12_300_000, "price": 24500.0, "prev_price": 24450.0},
            "BANKNIFTY": {"oi":  4_200_000, "prev_oi":  4_100_000, "price": 52000.0, "prev_price": 51800.0},
        }

    def get_futures_snapshot(self, symbol: str) -> dict:
        """
        Returns:
          symbol, expiry, price, prev_price, price_change_pct,
          oi, prev_oi, change_in_oi, change_in_oi_pct,
          basis, oi_signal, oi_signal_description
        """
        cache_key = f"futures:{symbol}"
        cached    = cache.get(cache_key)
        if cached:
            return cached

        if self._mock:
            data = self._mock_futures(symbol)
        else:
            data = self._live_futures(symbol)

        cache.set(cache_key, data, ttl=60)
        return data

    def _mock_futures(self, symbol: str) -> dict:
        sym   = symbol.upper()
        state = self._mock_state.get(sym, {"oi": 10_000_000, "prev_oi": 9_800_000,
                                           "price": 20000.0, "prev_price": 19950.0})

        # Random walk
        price_change_pct = self._rng.gauss(0.0002, 0.001)
        oi_change_pct    = self._rng.gauss(0.002,  0.01)

        new_price = round(state["price"] * (1 + price_change_pct), 2)
        new_oi    = int(state["oi"]      * (1 + oi_change_pct))

        state["prev_price"] = state["price"]
        state["prev_oi"]    = state["oi"]
        state["price"]      = new_price
        state["oi"]         = new_oi

        spot  = new_price * 0.9995   # mock spot slightly below futures
        basis = round(new_price - spot, 2)

        oi_signal = classify_oi_signal(
            price_change_pct, oi_change_pct
        )

        expiry = _next_expiry(sym)

        return {
            "timestamp":              datetime.datetime.now(IST).isoformat(),
            "symbol":                 sym,
            "expiry":                 expiry,
            "price":                  new_price,
            "prev_price":             state["prev_price"],
            "price_change_pct":       round(price_change_pct * 100, 3),
            "oi":                     new_oi,
            "prev_oi":                state["prev_oi"],
            "change_in_oi":           new_oi - state["prev_oi"],
            "change_in_oi_pct":       round(oi_change_pct * 100, 3),
            "basis":                  basis,
            "oi_signal":              oi_signal,
            "oi_signal_description":  describe_oi_signal(oi_signal),
            "volume":                 self._rng.randint(200_000, 800_000),
        }

    def _live_futures(self, symbol: str) -> dict:
        """Stub for real broker integration in Phase 8."""
        log.warning(f"Live futures data not yet implemented for {symbol}")
        return {}

    def get_oi_buildup_score(self, symbol: str) -> float:
        """
        Convert OI signal to a 0-100 score for the signal engine.
        LONG_BUILDUP = 80, SHORT_COVERING = 65,
        LONG_UNWINDING = 35, SHORT_BUILDUP = 20
        """
        snap  = self.get_futures_snapshot(symbol)
        signal = snap.get("oi_signal", "")
        scores = {
            "LONG_BUILDUP":   80.0,
            "SHORT_COVERING": 65.0,
            "LONG_UNWINDING": 35.0,
            "SHORT_BUILDUP":  20.0,
        }
        return scores.get(signal, 50.0)


def _next_expiry(symbol: str) -> str:
    """Return the next weekly expiry date string."""
    today = datetime.date.today()
    days_to_thursday = (3 - today.weekday()) % 7
    if days_to_thursday == 0:
        days_to_thursday = 7
    expiry = today + datetime.timedelta(days=days_to_thursday)
    return expiry.isoformat()
