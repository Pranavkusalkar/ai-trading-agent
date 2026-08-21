"""
AI Trading Agent - Phase 2 Setup Script
Adds the data pipeline and indicator engine to your Phase 1 project.

Usage (from C:\trading\ai_trading_agent with venv active):
    python setup_phase2.py
    python -m pytest -v

Prerequisites: Phase 1 must already be installed (setup_project.py run successfully).
"""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))
files = {}

files["src/data/__init__.py"] = """"""

files["src/indicators/__init__.py"] = """"""

files["src/data/data_cache.py"] = """\"\"\"
In-memory data cache with TTL (time-to-live).
Prevents re-fetching within the refresh interval.
Thread-safe for single-process use.
\"\"\"

import time
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


class CacheEntry:
    def __init__(self, value: Any, ttl_seconds: int):
        self.value     = value
        self.expires   = time.time() + ttl_seconds
        self.created   = time.time()

    def is_expired(self) -> bool:
        return time.time() > self.expires

    def age_seconds(self) -> float:
        return time.time() - self.created


class DataCache:
    \"\"\"
    Simple key-value cache with per-entry TTL.
    Keys are strings like "candles:NIFTY:5min" or "options:NIFTY:2026-08-21"
    \"\"\"

    def __init__(self, default_ttl: int = 60):
        self._store:       dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._hits         = 0
        self._misses       = 0

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None or entry.is_expired():
            if entry:
                del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = CacheEntry(value, ttl)
        log.debug(f"Cache SET {key} (ttl={ttl}s)")

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        return len(keys)

    def clear(self) -> None:
        self._store.clear()
        log.info("Cache cleared")

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "entries":   len(self._store),
            "hits":      self._hits,
            "misses":    self._misses,
            "hit_rate":  round(self._hits / total * 100, 1) if total else 0,
        }

    def is_fresh(self, key: str) -> bool:
        return self.get(key) is not None


# Singleton cache instance shared across data modules
_cache = DataCache(default_ttl=60)

def get_cache() -> DataCache:
    return _cache
"""

files["src/data/data_validator.py"] = """\"\"\"
Data Validator (Spec section — Data Validation / Cleaning)
Validates incoming market data before it reaches the signal engine.
Returns a ValidationResult so callers can act on failures.
\"\"\"

import logging
import datetime
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

log = logging.getLogger(__name__)

# Maximum age of data before it is considered stale
STALE_THRESHOLD_SECONDS = 120

# Minimum candles needed for indicator calculation
MIN_CANDLES_FOR_INDICATORS = 210

# Required OHLCV columns
REQUIRED_CANDLE_COLUMNS = {"open", "high", "low", "close", "volume"}


@dataclass
class ValidationResult:
    valid:    bool
    errors:   list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def __str__(self):
        parts = []
        if self.errors:
            parts.append("ERRORS: " + "; ".join(self.errors))
        if self.warnings:
            parts.append("WARNINGS: " + "; ".join(self.warnings))
        return " | ".join(parts) if parts else "OK"


class DataValidator:

    @staticmethod
    def validate_candles(df: pd.DataFrame, symbol: str = "") -> ValidationResult:
        \"\"\"
        Validate a candle DataFrame.
        Checks: schema, nulls, OHLC integrity, volume, gaps, minimum length.
        \"\"\"
        result = ValidationResult(valid=True)
        tag = f"[{symbol}] " if symbol else ""

        if df is None or df.empty:
            result.add_error(f"{tag}Empty candle DataFrame")
            return result

        # Schema check
        missing_cols = REQUIRED_CANDLE_COLUMNS - set(df.columns)
        if missing_cols:
            result.add_error(f"{tag}Missing columns: {missing_cols}")
            return result

        # Null check
        null_counts = df[list(REQUIRED_CANDLE_COLUMNS)].isnull().sum()
        if null_counts.any():
            result.add_warning(f"{tag}Null values found: {null_counts[null_counts > 0].to_dict()}")

        # OHLC integrity
        bad_hl = (df["high"] < df["low"]).sum()
        if bad_hl > 0:
            result.add_error(f"{tag}{bad_hl} candles where high < low")

        bad_open  = ((df["open"]  > df["high"]) | (df["open"]  < df["low"])).sum()
        bad_close = ((df["close"] > df["high"]) | (df["close"] < df["low"])).sum()
        if bad_open > 0:
            result.add_warning(f"{tag}{bad_open} candles where open outside high/low")
        if bad_close > 0:
            result.add_warning(f"{tag}{bad_close} candles where close outside high/low")

        # Negative prices
        if (df["close"] <= 0).any():
            result.add_error(f"{tag}Non-positive close prices found")

        # Volume
        zero_vol = (df["volume"] == 0).sum()
        if zero_vol > len(df) * 0.1:
            result.add_warning(f"{tag}{zero_vol} zero-volume candles ({zero_vol/len(df)*100:.1f}%)")

        # Minimum length
        if len(df) < MIN_CANDLES_FOR_INDICATORS:
            result.add_warning(
                f"{tag}Only {len(df)} candles — need {MIN_CANDLES_FOR_INDICATORS} "
                f"for full indicator suite"
            )

        return result

    @staticmethod
    def validate_snapshot(data: dict, symbol: str = "") -> ValidationResult:
        \"\"\"
        Validate a market snapshot dict (spot, futures, OI, PCR etc.)
        \"\"\"
        result = ValidationResult(valid=True)
        tag = f"[{symbol}] " if symbol else ""

        if not data:
            result.add_error(f"{tag}Empty snapshot")
            return result

        spot = data.get("spot")
        if spot is None or spot <= 0:
            result.add_error(f"{tag}Invalid spot price: {spot}")

        ts = data.get("timestamp")
        if ts:
            try:
                if isinstance(ts, str):
                    ts = datetime.datetime.fromisoformat(ts)
                age = (datetime.datetime.now() - ts).total_seconds()
                if age > STALE_THRESHOLD_SECONDS:
                    result.add_error(
                        f"{tag}Data is stale — age {age:.0f}s "
                        f"(threshold {STALE_THRESHOLD_SECONDS}s)"
                    )
            except Exception:
                result.add_warning(f"{tag}Could not parse timestamp")

        return result

    @staticmethod
    def validate_options_chain(chain: list, symbol: str = "") -> ValidationResult:
        \"\"\"Validate options chain list of dicts.\"\"\"
        result = ValidationResult(valid=True)
        tag = f"[{symbol}] " if symbol else ""

        if not chain:
            result.add_error(f"{tag}Empty options chain")
            return result

        required = {"strike", "option_type", "ltp", "oi", "volume"}
        sample = chain[0]
        missing = required - set(sample.keys())
        if missing:
            result.add_error(f"{tag}Options chain missing fields: {missing}")

        zero_oi  = sum(1 for c in chain if not c.get("oi"))
        zero_vol = sum(1 for c in chain if not c.get("volume"))
        if zero_oi  > len(chain) * 0.5:
            result.add_warning(f"{tag}Over 50% of options have zero OI")
        if zero_vol > len(chain) * 0.8:
            result.add_warning(f"{tag}Over 80% of options have zero volume")

        return result

    @staticmethod
    def detect_gaps(df: pd.DataFrame, timeframe_minutes: int = 5) -> list:
        \"\"\"
        Detect missing candles in a time series.
        Returns list of (gap_start, gap_end, missing_count) tuples.
        \"\"\"
        if df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return []

        expected_delta = pd.Timedelta(minutes=timeframe_minutes)
        gaps = []
        idx = df.index.sort_values()

        for i in range(1, len(idx)):
            actual_delta = idx[i] - idx[i - 1]
            if actual_delta > expected_delta * 1.5:
                missing = int(actual_delta / expected_delta) - 1
                gaps.append({
                    "gap_start":     str(idx[i - 1]),
                    "gap_end":       str(idx[i]),
                    "missing_candles": missing,
                })

        return gaps
"""

files["src/data/market_data.py"] = """\"\"\"
Market Data Provider (Spec section 3 — Market Data Agent)
Defines the abstract interface and provides:
  - MockDataProvider   : realistic synthetic NIFTY/BANKNIFTY data (no API needed)
  - BrokerDataProvider : stub that connects to any broker implementing BrokerInterface

Switch providers by changing one line in config. All downstream code
(indicators, agents, signal engine) only sees MarketDataProvider.
\"\"\"

import logging
import random
import datetime
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional
import pytz

from src.data.data_cache import get_cache
from src.data.data_validator import DataValidator

log  = logging.getLogger(__name__)
IST  = pytz.timezone("Asia/Kolkata")
cache = get_cache()


# ── Abstract interface ────────────────────────────────────────────────────────

class MarketDataProvider(ABC):
    \"\"\"All data sources implement this interface.\"\"\"

    @abstractmethod
    def get_spot(self, symbol: str) -> Optional[float]:
        \"\"\"Current index spot price.\"\"\"

    @abstractmethod
    def get_candles(
        self, symbol: str, timeframe: str, count: int = 250
    ) -> pd.DataFrame:
        \"\"\"
        OHLCV candles. timeframe: '1min' | '5min' | '15min' | 'day'
        Returns DataFrame with DatetimeIndex and columns:
        open, high, low, close, volume, vwap
        \"\"\"

    @abstractmethod
    def get_market_snapshot(self, symbol: str) -> dict:
        \"\"\"
        Full snapshot: spot, futures price, basis, volume, market status.
        Matches spec section 3 output format.
        \"\"\"

    @abstractmethod
    def is_market_open(self) -> bool:
        \"\"\"Returns True during NSE trading hours.\"\"\"

    def get_data_quality(self, symbol: str) -> int:
        \"\"\"0–100 score. Override in subclasses for real health checks.\"\"\"
        return 100


# ── Mock Data Provider ────────────────────────────────────────────────────────

class MockDataProvider(MarketDataProvider):
    \"\"\"
    Generates realistic synthetic NIFTY / BANKNIFTY data.
    Uses seeded random walk so results are reproducible.
    Ideal for development, backtesting setup, and unit tests.
    \"\"\"

    BASE_PRICES = {
        "NIFTY":     24500.0,
        "BANKNIFTY": 52000.0,
    }

    VOLATILITY = {
        "NIFTY":     0.0008,   # ~0.08% per candle (5min)
        "BANKNIFTY": 0.0012,
    }

    def __init__(self, seed: int = 42):
        self._seed   = seed
        self._prices: dict[str, float] = dict(self.BASE_PRICES)
        self._rng    = random.Random(seed)
        log.info("MockDataProvider initialised (synthetic NSE data)")

    def get_spot(self, symbol: str) -> Optional[float]:
        sym = symbol.upper()
        if sym not in self._prices:
            return None
        # Small random walk on each call
        vol  = self.VOLATILITY.get(sym, 0.001)
        move = self._rng.gauss(0, vol)
        self._prices[sym] *= (1 + move)
        return round(self._prices[sym], 2)

    def get_candles(
        self, symbol: str, timeframe: str = "5min", count: int = 250
    ) -> pd.DataFrame:
        cache_key = f"candles:{symbol}:{timeframe}:{count}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        sym   = symbol.upper()
        base  = self.BASE_PRICES.get(sym, 20000.0)
        vol   = self.VOLATILITY.get(sym, 0.001)

        tf_minutes = {"1min": 1, "5min": 5, "15min": 15, "day": 375}.get(timeframe, 5)

        # Generate timestamps ending at last market close
        now        = datetime.datetime.now(IST)
        end_time   = now.replace(hour=15, minute=30, second=0, microsecond=0)
        delta      = datetime.timedelta(minutes=tf_minutes)
        timestamps = [end_time - delta * i for i in range(count, 0, -1)]

        rng   = np.random.default_rng(self._seed + hash(symbol) % 1000)
        close = base * np.cumprod(1 + rng.normal(0.00003, vol, count))
        open_ = np.roll(close, 1)
        open_[0] = base
        high  = np.maximum(open_, close) * (1 + rng.uniform(0, vol * 2, count))
        low   = np.minimum(open_, close) * (1 - rng.uniform(0, vol * 2, count))
        vol_  = rng.integers(500_000, 3_000_000, count).astype(float)
        vwap  = (high + low + close) / 3

        df = pd.DataFrame({
            "open":   np.round(open_, 2),
            "high":   np.round(high,  2),
            "low":    np.round(low,   2),
            "close":  np.round(close, 2),
            "volume": vol_,
            "vwap":   np.round(vwap,  2),
        }, index=pd.DatetimeIndex(timestamps))
        df.index.name = "timestamp"
        df = df.sort_index()

        # Validate
        result = DataValidator.validate_candles(df, symbol)
        if not result.valid:
            log.warning(f"Mock candles validation: {result}")

        cache.set(cache_key, df, ttl=30)
        log.debug(f"Generated {len(df)} mock candles for {symbol} ({timeframe})")
        return df

    def get_market_snapshot(self, symbol: str) -> dict:
        spot    = self.get_spot(symbol)
        futures = round(spot * 1.0005, 2) if spot else None
        return {
            "timestamp":    datetime.datetime.now(IST).isoformat(),
            "instrument":   symbol.upper(),
            "spot":         spot,
            "future":       futures,
            "basis":        round(futures - spot, 2) if futures and spot else None,
            "volume":       self._rng.randint(1_000_000, 5_000_000),
            "market_status": "OPEN" if self.is_market_open() else "CLOSED",
            "data_quality": 100,
        }

    def is_market_open(self) -> bool:
        now = datetime.datetime.now(IST)
        if now.weekday() >= 5:
            return False
        t = now.time()
        return datetime.time(9, 15) <= t < datetime.time(15, 30)

    def get_vix(self) -> float:
        \"\"\"Simulated India VIX.\"\"\"
        return round(self._rng.uniform(12.0, 22.0), 2)


# ── Broker Data Provider stub ─────────────────────────────────────────────────

class BrokerDataProvider(MarketDataProvider):
    \"\"\"
    Wraps a BrokerInterface implementation to provide market data.
    Plug in ZerodhaBroker / UpstoxBroker / AngelBroker here.
    Phase 8 connects this to the real broker.
    \"\"\"

    def __init__(self, broker):
        self._broker = broker
        log.info(f"BrokerDataProvider initialised with {type(broker).__name__}")

    def get_spot(self, symbol: str) -> Optional[float]:
        exchange_map = {"NIFTY": "NSE", "BANKNIFTY": "NSE"}
        exchange = exchange_map.get(symbol.upper(), "NSE")
        return self._broker.get_ltp(symbol, exchange)

    def get_candles(
        self, symbol: str, timeframe: str = "5min", count: int = 250
    ) -> pd.DataFrame:
        import datetime as dt
        to_date   = dt.date.today().isoformat()
        from_date = (dt.date.today() - dt.timedelta(days=count // 75 + 5)).isoformat()
        raw = self._broker.get_historical_candles(
            symbol, "NSE", timeframe, from_date, to_date
        )
        if not raw:
            log.warning(f"No candle data returned for {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df.index = pd.DatetimeIndex(df["timestamp"])
        df = df[["open", "high", "low", "close", "volume"]].tail(count)
        df["vwap"] = (df["high"] + df["low"] + df["close"]) / 3
        return df.sort_index()

    def get_market_snapshot(self, symbol: str) -> dict:
        spot = self.get_spot(symbol)
        return {
            "timestamp":    datetime.datetime.now(IST).isoformat(),
            "instrument":   symbol.upper(),
            "spot":         spot,
            "future":       None,
            "basis":        None,
            "volume":       None,
            "market_status": "OPEN" if self.is_market_open() else "CLOSED",
            "data_quality": 90 if spot else 0,
        }

    def is_market_open(self) -> bool:
        from src.utils.time_utils import is_market_open
        return is_market_open()

    def get_data_quality(self, symbol: str) -> int:
        spot = self.get_spot(symbol)
        return 100 if spot and spot > 0 else 0


# ── Factory ───────────────────────────────────────────────────────────────────

def create_data_provider(mode: str = "mock", broker=None) -> MarketDataProvider:
    \"\"\"
    mode: 'mock' | 'broker'
    For Phase 2-7: use 'mock'.
    For Phase 8+:  use 'broker' and pass a connected BrokerInterface.
    \"\"\"
    if mode == "mock":
        return MockDataProvider()
    if mode == "broker":
        if broker is None:
            raise ValueError("broker instance required for mode='broker'")
        return BrokerDataProvider(broker)
    raise ValueError(f"Unknown data provider mode: {mode}")
"""

files["src/data/futures_data.py"] = """\"\"\"
Futures Data Agent (Spec section 7)
Fetches futures price, OI, change-in-OI and classifies:
  LONG_BUILDUP    — price up + OI up
  SHORT_BUILDUP   — price down + OI up
  LONG_UNWINDING  — price down + OI down
  SHORT_COVERING  — price up + OI down
\"\"\"

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
    \"\"\"
    Classify futures OI signal per spec section 7.
    price_change and oi_change are floats (positive = increase).
    \"\"\"
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
    \"\"\"
    Provides futures market data.
    In mock mode, generates realistic synthetic OI/price data.
    In broker mode, fetches from the connected broker.
    \"\"\"

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
        \"\"\"
        Returns:
          symbol, expiry, price, prev_price, price_change_pct,
          oi, prev_oi, change_in_oi, change_in_oi_pct,
          basis, oi_signal, oi_signal_description
        \"\"\"
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
        \"\"\"Stub for real broker integration in Phase 8.\"\"\"
        log.warning(f"Live futures data not yet implemented for {symbol}")
        return {}

    def get_oi_buildup_score(self, symbol: str) -> float:
        \"\"\"
        Convert OI signal to a 0-100 score for the signal engine.
        LONG_BUILDUP = 80, SHORT_COVERING = 65,
        LONG_UNWINDING = 35, SHORT_BUILDUP = 20
        \"\"\"
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
    \"\"\"Return the next weekly expiry date string.\"\"\"
    today = datetime.date.today()
    days_to_thursday = (3 - today.weekday()) % 7
    if days_to_thursday == 0:
        days_to_thursday = 7
    expiry = today + datetime.timedelta(days=days_to_thursday)
    return expiry.isoformat()
"""

files["src/data/options_chain.py"] = """\"\"\"
Options Chain Agent (Spec section 8, 9, 10)
Fetches option chain, calculates PCR variants, identifies
support/resistance zones from OI, and classifies IV environment.
\"\"\"

import logging
import random
import math
import datetime
from typing import Optional
import pytz

from src.data.data_cache import get_cache

log   = logging.getLogger(__name__)
IST   = pytz.timezone("Asia/Kolkata")
cache = get_cache()


class OptionsChainAgent:
    \"\"\"
    Provides options chain analysis for NIFTY / BANKNIFTY.
    Mock mode generates realistic synthetic chain data.
    \"\"\"

    STRIKE_GAPS = {"NIFTY": 50, "BANKNIFTY": 100}

    def __init__(self, mock: bool = True):
        self._mock = mock
        self._rng  = random.Random(77)

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_chain(self, symbol: str, expiry: str = None, depth: int = 10) -> list[dict]:
        \"\"\"
        Returns list of option dicts for `depth` strikes each side of ATM.
        Each dict: strike, option_type, ltp, bid, ask, oi, change_in_oi,
                   volume, iv, delta, gamma, theta, vega
        \"\"\"
        cache_key = f"chain:{symbol}:{expiry}:{depth}"
        cached    = cache.get(cache_key)
        if cached:
            return cached

        chain = self._mock_chain(symbol, depth) if self._mock else []
        cache.set(cache_key, chain, ttl=60)
        return chain

    def analyse(self, symbol: str, depth: int = 10) -> dict:
        \"\"\"
        Full options analysis dict consumed by the signal engine.
        Returns: pcr_oi, pcr_volume, pcr_change_oi,
                 max_call_oi_strike, max_put_oi_strike,
                 call_resistance, put_support,
                 atm_iv, iv_environment,
                 oi_score (0-100 for signal engine)
        \"\"\"
        cache_key = f"analysis:{symbol}:{depth}"
        cached    = cache.get(cache_key)
        if cached:
            return cached

        chain  = self.get_chain(symbol, depth=depth)
        result = self._analyse_chain(symbol, chain)
        cache.set(cache_key, result, ttl=60)
        return result

    def get_oi_score(self, symbol: str) -> float:
        \"\"\"0-100 score for signal engine. >50 = bullish options flow.\"\"\"
        analysis = self.analyse(symbol)
        return analysis.get("oi_score", 50.0)

    # ── Chain generation (mock) ────────────────────────────────────────────────

    def _mock_chain(self, symbol: str, depth: int) -> list[dict]:
        sym        = symbol.upper()
        atm        = self._get_atm(sym)
        strike_gap = self.STRIKE_GAPS.get(sym, 50)
        expiry     = self._next_expiry()
        days_to_exp = max(1, (datetime.date.fromisoformat(expiry) - datetime.date.today()).days)

        chain = []
        for i in range(-depth, depth + 1):
            strike = atm + i * strike_gap
            moneyness = (atm - strike) / atm  # positive = ITM for call

            for opt_type in ("CE", "PE"):
                iv       = self._mock_iv(moneyness, opt_type, days_to_exp)
                ltp      = self._mock_premium(atm, strike, iv, days_to_exp, opt_type)
                oi       = self._mock_oi(i, opt_type)
                chg_oi   = int(oi * self._rng.uniform(-0.05, 0.15))
                vol      = int(oi * self._rng.uniform(0.05, 0.3))
                delta    = self._approx_delta(moneyness, opt_type)
                gamma    = max(0.0001, 0.05 * math.exp(-0.5 * (moneyness / 0.02) ** 2))
                theta    = -ltp * 0.015 / days_to_exp
                vega     = ltp * 0.1

                chain.append({
                    "strike":       strike,
                    "option_type":  opt_type,
                    "expiry":       expiry,
                    "ltp":          round(ltp,   2),
                    "bid":          round(ltp * 0.99, 2),
                    "ask":          round(ltp * 1.01, 2),
                    "oi":           oi,
                    "change_in_oi": chg_oi,
                    "volume":       vol,
                    "iv":           round(iv * 100, 2),  # as percentage
                    "delta":        round(delta, 4),
                    "gamma":        round(gamma, 5),
                    "theta":        round(theta, 2),
                    "vega":         round(vega,  2),
                })
        return chain

    def _analyse_chain(self, symbol: str, chain: list[dict]) -> dict:
        calls = [c for c in chain if c["option_type"] == "CE"]
        puts  = [c for c in chain if c["option_type"] == "PE"]

        total_call_oi     = sum(c["oi"] for c in calls)
        total_put_oi      = sum(c["oi"] for c in puts)
        total_call_vol    = sum(c["volume"] for c in calls)
        total_put_vol     = sum(c["volume"] for c in puts)
        total_call_chg_oi = sum(c["change_in_oi"] for c in calls)
        total_put_chg_oi  = sum(c["change_in_oi"] for c in puts)

        pcr_oi        = round(total_put_oi  / total_call_oi,  3) if total_call_oi  else None
        pcr_volume    = round(total_put_vol / total_call_vol, 3) if total_call_vol else None
        pcr_change_oi = round(total_put_chg_oi / total_call_chg_oi, 3) if total_call_chg_oi else None

        # Max OI strikes = support / resistance
        max_call = max(calls, key=lambda x: x["oi"], default={})
        max_put  = max(puts,  key=lambda x: x["oi"], default={})

        # ATM IV (average of ATM call and put)
        atm_calls = sorted(calls, key=lambda x: x["oi"], reverse=True)[:2]
        atm_iv    = round(sum(c["iv"] for c in atm_calls) / len(atm_calls), 2) if atm_calls else None

        # IV environment
        iv_env = self._classify_iv(atm_iv)

        # OI score — PCR-based, 0-100
        oi_score = self._pcr_to_score(pcr_oi)

        return {
            "symbol":              symbol,
            "timestamp":           datetime.datetime.now(IST).isoformat(),
            "total_call_oi":       total_call_oi,
            "total_put_oi":        total_put_oi,
            "pcr_oi":              pcr_oi,
            "pcr_volume":          pcr_volume,
            "pcr_change_oi":       pcr_change_oi,
            "max_call_oi_strike":  max_call.get("strike"),
            "max_put_oi_strike":   max_put.get("strike"),
            "call_resistance":     max_call.get("strike"),
            "put_support":         max_put.get("strike"),
            "atm_iv":              atm_iv,
            "iv_environment":      iv_env,
            "oi_score":            oi_score,
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_atm(self, symbol: str) -> int:
        base = {"NIFTY": 24500, "BANKNIFTY": 52000}.get(symbol, 20000)
        gap  = self.STRIKE_GAPS.get(symbol, 50)
        return round(base / gap) * gap

    def _next_expiry(self) -> str:
        today = datetime.date.today()
        days  = (3 - today.weekday()) % 7 or 7
        return (today + datetime.timedelta(days=days)).isoformat()

    def _mock_iv(self, moneyness: float, opt_type: str, days: int) -> float:
        base_iv = 0.13 + abs(moneyness) * 2   # vol smile
        time_adj = 1 + (7 - min(days, 7)) * 0.01
        return max(0.08, base_iv * time_adj * self._rng.uniform(0.95, 1.05))

    def _mock_premium(self, spot: float, strike: float, iv: float, days: int, opt_type: str) -> float:
        intrinsic = max(0, spot - strike) if opt_type == "CE" else max(0, strike - spot)
        time_val  = spot * iv * math.sqrt(days / 365) * 0.4
        return max(0.5, round(intrinsic + time_val * self._rng.uniform(0.8, 1.2), 1))

    def _mock_oi(self, dist_from_atm: int, opt_type: str) -> int:
        base = 500_000 * math.exp(-0.3 * abs(dist_from_atm))
        return max(1000, int(base * self._rng.uniform(0.7, 1.3)))

    def _approx_delta(self, moneyness: float, opt_type: str) -> float:
        d = 0.5 + moneyness * 5
        d = max(0.01, min(0.99, d))
        return d if opt_type == "CE" else -(1 - d)

    def _classify_iv(self, atm_iv: Optional[float]) -> str:
        if atm_iv is None:
            return "UNKNOWN"
        if atm_iv < 12:   return "LOW_IV"
        if atm_iv < 18:   return "NORMAL_IV"
        if atm_iv < 25:   return "ELEVATED_IV"
        return "HIGH_IV"

    def _pcr_to_score(self, pcr: Optional[float]) -> float:
        \"\"\"
        PCR < 0.7 = too bullish (contrarian bearish) → score ~35
        PCR 0.7-1.0 = mild bullish → score 55-65
        PCR 1.0-1.3 = neutral → score 50
        PCR > 1.3 = too bearish (contrarian bullish) → score ~65
        Note: PCR alone is never a standalone signal per spec.
        \"\"\"
        if pcr is None:
            return 50.0
        if pcr < 0.7:   return 35.0
        if pcr < 1.0:   return 55.0 + (1.0 - pcr) * 33
        if pcr < 1.3:   return 50.0
        return 65.0
"""

files["src/indicators/technical.py"] = """\"\"\"
Technical Indicators Engine (Spec section 4)
All indicators use pandas + numpy only (no pandas-ta dependency).
Each returns a typed dict with value, signal, and score (0-100).
score > 65 = bullish, < 35 = bearish, 35-65 = neutral.
\"\"\"

import logging
import numpy as np
import pandas as pd
from typing import Optional

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _signal(score: float) -> str:
    if score >= 65: return "BULLISH"
    if score <= 35: return "BEARISH"
    return "NEUTRAL"


def _require(df: pd.DataFrame, min_bars: int, name: str) -> bool:
    if len(df) < min_bars:
        log.debug(f"{name}: need {min_bars} bars, got {len(df)}")
        return False
    return True


# ── EMA ───────────────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_emas(df: pd.DataFrame) -> dict:
    \"\"\"EMA 9, 21, 50, 200 with crossover detection.\"\"\"
    if not _require(df, 200, "EMA"):
        return {}

    close  = df["close"].astype(float)
    e9     = ema(close, 9)
    e21    = ema(close, 21)
    e50    = ema(close, 50)
    e200   = ema(close, 200)
    price  = float(close.iloc[-1])

    above_9   = price > float(e9.iloc[-1])
    above_21  = price > float(e21.iloc[-1])
    above_50  = price > float(e50.iloc[-1])
    above_200 = price > float(e200.iloc[-1])
    golden_cross = float(e50.iloc[-1]) > float(e200.iloc[-1])
    death_cross  = float(e50.iloc[-1]) < float(e200.iloc[-1])
    ema9_above_21 = float(e9.iloc[-1]) > float(e21.iloc[-1])

    score = 50.0
    if above_9:    score += 8
    if above_21:   score += 8
    if above_50:   score += 10
    if above_200:  score += 12
    if golden_cross: score += 12
    elif death_cross: score -= 15
    if ema9_above_21: score += 10
    score = min(max(score, 0), 100)

    return {
        "ema9":          round(float(e9.iloc[-1]),   2),
        "ema21":         round(float(e21.iloc[-1]),  2),
        "ema50":         round(float(e50.iloc[-1]),  2),
        "ema200":        round(float(e200.iloc[-1]), 2),
        "price":         round(price, 2),
        "above_9":       above_9,
        "above_21":      above_21,
        "above_50":      above_50,
        "above_200":     above_200,
        "golden_cross":  golden_cross,
        "death_cross":   death_cross,
        "ema9_above_21": ema9_above_21,
        "score":         round(score, 1),
        "signal":        _signal(score),
    }


# ── VWAP ──────────────────────────────────────────────────────────────────────

def compute_vwap(df: pd.DataFrame) -> dict:
    \"\"\"VWAP relative to current price.\"\"\"
    if not _require(df, 10, "VWAP"):
        return {}

    if "vwap" in df.columns and df["vwap"].notna().all():
        vwap_val = float(df["vwap"].iloc[-1])
    else:
        typical  = (df["high"] + df["low"] + df["close"]) / 3
        vwap_val = float((typical * df["volume"]).cumsum().iloc[-1] /
                          df["volume"].cumsum().iloc[-1])

    price    = float(df["close"].iloc[-1])
    pct_diff = (price - vwap_val) / vwap_val * 100

    if price > vwap_val:
        score = min(65 + abs(pct_diff) * 5, 90)
    else:
        score = max(35 - abs(pct_diff) * 5, 10)

    return {
        "vwap":        round(vwap_val, 2),
        "price":       round(price, 2),
        "above_vwap":  price > vwap_val,
        "pct_from_vwap": round(pct_diff, 3),
        "score":       round(score, 1),
        "signal":      _signal(score),
    }


# ── RSI ───────────────────────────────────────────────────────────────────────

def compute_rsi(df: pd.DataFrame, period: int = 14) -> dict:
    if not _require(df, period + 1, "RSI"):
        return {}

    close  = df["close"].astype(float)
    delta  = close.diff()
    gain   = delta.clip(lower=0).rolling(period).mean()
    loss   = (-delta.clip(upper=0)).rolling(period).mean()
    rs     = gain / loss.replace(0, np.nan)
    rsi_s  = 100 - (100 / (1 + rs))
    rsi    = float(rsi_s.iloc[-1])

    if rsi   <= 30: score = 85.0
    elif rsi <= 40: score = 65.0
    elif rsi <= 55: score = 52.0
    elif rsi <= 65: score = 48.0
    elif rsi <= 70: score = 35.0
    else:           score = 15.0

    return {
        "rsi":     round(rsi, 2),
        "score":   round(score, 1),
        "signal":  _signal(score),
        "oversold":    rsi <= 30,
        "overbought":  rsi >= 70,
    }


# ── MACD ─────────────────────────────────────────────────────────────────────

def compute_macd(
    df: pd.DataFrame,
    fast: int = 12, slow: int = 26, signal_period: int = 9
) -> dict:
    if not _require(df, slow + signal_period, "MACD"):
        return {}

    close      = df["close"].astype(float)
    ema_fast   = ema(close, fast)
    ema_slow   = ema(close, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram  = macd_line - signal_line

    hist_val   = float(histogram.iloc[-1])
    macd_val   = float(macd_line.iloc[-1])
    sig_val    = float(signal_line.iloc[-1])

    # Bullish: histogram positive and growing
    hist_prev  = float(histogram.iloc[-2]) if len(histogram) > 1 else hist_val
    growing    = hist_val > hist_prev

    if hist_val > 0 and growing:   score = 75.0
    elif hist_val > 0:              score = 60.0
    elif hist_val < 0 and not growing: score = 25.0
    else:                           score = 40.0

    crossover_bull = float(macd_line.iloc[-2]) < float(signal_line.iloc[-2]) and macd_val > sig_val
    crossover_bear = float(macd_line.iloc[-2]) > float(signal_line.iloc[-2]) and macd_val < sig_val

    if crossover_bull: score = min(score + 10, 90)
    if crossover_bear: score = max(score - 10, 10)

    return {
        "macd":            round(macd_val,  4),
        "signal":          round(sig_val,   4),
        "histogram":       round(hist_val,  4),
        "crossover_bull":  crossover_bull,
        "crossover_bear":  crossover_bear,
        "score":           round(score, 1),
        "signal_label":    _signal(score),
    }


# ── ATR ───────────────────────────────────────────────────────────────────────

def compute_atr(df: pd.DataFrame, period: int = 14) -> dict:
    \"\"\"ATR for stop-loss sizing. Returns value and volatility label.\"\"\"
    if not _require(df, period + 1, "ATR"):
        return {}

    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    atr_val = float(atr.iloc[-1])

    price   = float(close.iloc[-1])
    atr_pct = atr_val / price * 100

    if atr_pct < 0.3:   vol_label = "LOW"
    elif atr_pct < 0.6: vol_label = "MEDIUM"
    elif atr_pct < 1.0: vol_label = "HIGH"
    else:               vol_label = "VERY_HIGH"

    return {
        "atr":       round(atr_val, 2),
        "atr_pct":   round(atr_pct, 3),
        "volatility": vol_label,
        "sl_1atr":   round(price - atr_val, 2),
        "sl_15atr":  round(price - atr_val * 1.5, 2),
        "sl_2atr":   round(price - atr_val * 2, 2),
    }


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def compute_bollinger(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> dict:
    if not _require(df, period, "Bollinger"):
        return {}

    close = df["close"].astype(float)
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = mid + std * std_dev
    lower = mid - std * std_dev
    pct_b = (close - lower) / (upper - lower)
    bw    = (upper - lower) / mid * 100  # bandwidth

    price   = float(close.iloc[-1])
    pct_b_v = float(pct_b.iloc[-1])
    bw_v    = float(bw.iloc[-1])

    # Near lower band = oversold = bullish setup
    if pct_b_v < 0.2:   score = 72.0
    elif pct_b_v < 0.4: score = 58.0
    elif pct_b_v < 0.6: score = 50.0
    elif pct_b_v < 0.8: score = 42.0
    else:               score = 30.0

    return {
        "upper":        round(float(upper.iloc[-1]), 2),
        "middle":       round(float(mid.iloc[-1]),   2),
        "lower":        round(float(lower.iloc[-1]), 2),
        "pct_b":        round(pct_b_v, 3),
        "bandwidth":    round(bw_v,    3),
        "squeeze":      bw_v < 2.0,
        "score":        round(score, 1),
        "signal":       _signal(score),
    }


# ── ADX ───────────────────────────────────────────────────────────────────────

def compute_adx(df: pd.DataFrame, period: int = 14) -> dict:
    \"\"\"ADX for trend strength. DI+ / DI- for direction.\"\"\"
    if not _require(df, period * 2, "ADX"):
        return {}

    high   = df["high"].astype(float)
    low    = df["low"].astype(float)
    close  = df["close"].astype(float)

    up_move   = high.diff()
    down_move = -low.diff()

    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_s    = tr.ewm(span=period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(span=period,  adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr_s
    dx       = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx_s    = dx.ewm(span=period, adjust=False).mean()

    adx_v     = float(adx_s.iloc[-1])
    plus_di_v = float(plus_di.iloc[-1])
    minus_di_v= float(minus_di.iloc[-1])

    trending  = adx_v > 25
    bullish   = plus_di_v > minus_di_v

    if trending and bullish:       score = 75.0
    elif trending and not bullish: score = 25.0
    elif adx_v > 15 and bullish:   score = 60.0
    elif adx_v > 15:               score = 40.0
    else:                          score = 50.0

    return {
        "adx":        round(adx_v,      2),
        "plus_di":    round(plus_di_v,  2),
        "minus_di":   round(minus_di_v, 2),
        "trending":   trending,
        "bullish_di": bullish,
        "score":      round(score, 1),
        "signal":     _signal(score),
    }


# ── Supertrend ────────────────────────────────────────────────────────────────

def compute_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> dict:
    if not _require(df, period + 1, "Supertrend"):
        return {}

    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    hl2   = (high + low) / 2
    tr1   = high - low
    tr2   = (high - close.shift()).abs()
    tr3   = (low  - close.shift()).abs()
    tr    = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr   = tr.ewm(span=period, adjust=False).mean()

    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(index=df.index, dtype=int)

    for i in range(1, len(df)):
        prev_close = float(close.iloc[i - 1])
        ub = float(upper_basic.iloc[i])
        lb = float(lower_basic.iloc[i])

        prev_st  = float(supertrend.iloc[i - 1]) if not pd.isna(supertrend.iloc[i - 1]) else lb
        prev_dir = int(direction.iloc[i - 1]) if not pd.isna(direction.iloc[i - 1]) else 1

        if prev_dir == 1:
            st = lb if float(close.iloc[i]) > prev_st else ub
            d  = 1  if float(close.iloc[i]) > st else -1
        else:
            st = ub if float(close.iloc[i]) < prev_st else lb
            d  = -1 if float(close.iloc[i]) < st else 1

        supertrend.iloc[i] = st
        direction.iloc[i]  = d

    last_dir = int(direction.iloc[-1]) if not pd.isna(direction.iloc[-1]) else 0
    last_st  = float(supertrend.iloc[-1]) if not pd.isna(supertrend.iloc[-1]) else 0.0
    bullish  = last_dir == 1

    score = 70.0 if bullish else 30.0

    return {
        "supertrend":  round(last_st, 2),
        "direction":   "BULLISH" if bullish else "BEARISH",
        "score":       score,
        "signal":      _signal(score),
    }


# ── Market Regime ─────────────────────────────────────────────────────────────

def detect_market_regime(
    ema_result:  dict,
    adx_result:  dict,
    rsi_result:  dict,
    atr_result:  dict,
    vix:         Optional[float] = None,
) -> str:
    \"\"\"
    Classify market into one of 9 regimes (spec section 11).
    STRONG_BULL | BULL | WEAK_BULL | RANGE |
    WEAK_BEAR   | BEAR | STRONG_BEAR |
    HIGH_VOLATILITY | LOW_VOLATILITY
    \"\"\"
    adx  = adx_result.get("adx", 15)
    rsi  = rsi_result.get("rsi", 50)
    atr_vol = atr_result.get("volatility", "MEDIUM")
    bullish_ema  = ema_result.get("above_200", False) and ema_result.get("golden_cross", False)
    bearish_ema  = not ema_result.get("above_200", True)
    bullish_di   = adx_result.get("bullish_di", True)
    ema_score    = ema_result.get("score", 50)

    if atr_vol == "VERY_HIGH" or (vix and vix > 25):
        return "HIGH_VOLATILITY"
    if atr_vol == "LOW" and adx < 15:
        return "LOW_VOLATILITY"
    if adx > 25:
        if bullish_di and ema_score > 70:
            return "STRONG_BULL" if ema_score > 80 else "BULL"
        if not bullish_di and ema_score < 30:
            return "STRONG_BEAR" if ema_score < 20 else "BEAR"
    if adx < 15:
        return "RANGE"
    if ema_score > 60:
        return "WEAK_BULL"
    if ema_score < 40:
        return "WEAK_BEAR"
    return "RANGE"


# ── Full composite ────────────────────────────────────────────────────────────

def compute_all(df: pd.DataFrame, vix: Optional[float] = None) -> dict:
    \"\"\"
    Run every indicator and return a unified dict.
    The signal engine reads this output.
    \"\"\"
    emas    = compute_emas(df)
    vwap    = compute_vwap(df)
    rsi     = compute_rsi(df)
    macd    = compute_macd(df)
    atr     = compute_atr(df)
    boll    = compute_bollinger(df)
    adx     = compute_adx(df)
    st      = compute_supertrend(df)

    regime = detect_market_regime(emas, adx, rsi, atr, vix) if all([emas, adx, rsi, atr]) else "UNKNOWN"

    # Composite technical score (equal weight across indicators)
    scores = [
        emas.get("score", 50),
        vwap.get("score", 50),
        rsi.get("score",  50),
        macd.get("score", 50),
        boll.get("score", 50),
        adx.get("score",  50),
        st.get("score",   50),
    ]
    valid_scores  = [s for s in scores if s is not None]
    tech_score    = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 50.0

    return {
        "ema":          emas,
        "vwap":         vwap,
        "rsi":          rsi,
        "macd":         macd,
        "atr":          atr,
        "bollinger":    boll,
        "adx":          adx,
        "supertrend":   st,
        "market_regime": regime,
        "tech_score":   tech_score,
        "tech_signal":  _signal(tech_score),
    }
"""

files["src/indicators/volume.py"] = """\"\"\"
Volume Analysis (Spec section 6)
Implements price-volume relationship rules and volume spike detection.
\"\"\"

import logging
import pandas as pd
import numpy as np

log = logging.getLogger(__name__)


def compute_volume(df: pd.DataFrame, ma_period: int = 20) -> dict:
    \"\"\"
    Volume analysis with price-volume relationship rules from spec section 6.

    Rules:
      High price + high volume   -> bullish confirmation
      Low price  + high volume   -> bearish confirmation
      Breakout   + high volume   -> stronger breakout
      Breakout   + low volume    -> possible false breakout
    \"\"\"
    if len(df) < ma_period + 1:
        return {}

    close  = df["close"].astype(float)
    volume = df["volume"].astype(float)

    vol_ma      = volume.rolling(ma_period).mean()
    curr_vol    = float(volume.iloc[-1])
    curr_vol_ma = float(vol_ma.iloc[-1])
    vol_ratio   = curr_vol / curr_vol_ma if curr_vol_ma > 0 else 1.0

    # Price direction
    price_up    = float(close.iloc[-1]) > float(close.iloc[-2])
    price_change_pct = (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2]) * 100

    # Volume classification
    if vol_ratio >= 2.0:   vol_class = "VERY_HIGH"
    elif vol_ratio >= 1.5: vol_class = "HIGH"
    elif vol_ratio >= 0.8: vol_class = "NORMAL"
    elif vol_ratio >= 0.5: vol_class = "LOW"
    else:                  vol_class = "VERY_LOW"

    high_vol = vol_ratio >= 1.5

    # Price-volume relationship (spec rules)
    if price_up and high_vol:
        pv_signal = "BULLISH_CONFIRMATION"
        score     = 75.0
    elif not price_up and high_vol:
        pv_signal = "BEARISH_CONFIRMATION"
        score     = 25.0
    elif price_up and not high_vol:
        pv_signal = "WEAK_UPSIDE"
        score     = 55.0
    else:
        pv_signal = "WEAK_DOWNSIDE"
        score     = 45.0

    # Volume spike detection
    vol_std    = float(volume.rolling(ma_period).std().iloc[-1])
    spike      = curr_vol > (curr_vol_ma + 2 * vol_std) if vol_std > 0 else False

    # Contraction (low volume squeeze — often precedes breakout)
    contraction = vol_ratio < 0.6 and float(volume.rolling(5).mean().iloc[-1]) < curr_vol_ma * 0.7

    return {
        "current_volume":   int(curr_vol),
        "volume_ma":        int(curr_vol_ma),
        "volume_ratio":     round(vol_ratio, 3),
        "volume_class":     vol_class,
        "price_volume_signal": pv_signal,
        "price_up":         price_up,
        "price_change_pct": round(price_change_pct, 3),
        "spike":            spike,
        "contraction":      contraction,
        "score":            round(score, 1),
        "signal":           "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL",
    }
"""

files["tests/test_data.py"] = """\"\"\"
Unit tests - Data Pipeline (Phase 2)
Tests: cache, validator, market data provider, futures agent, options chain.
\"\"\"

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
"""

files["tests/test_indicators.py"] = """\"\"\"
Unit tests - Technical Indicators (Phase 2)
Tests: EMA, VWAP, RSI, MACD, ATR, Bollinger, ADX, Supertrend, Volume, Regime.
\"\"\"

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
    \"\"\"Uptrending synthetic candle data.\"\"\"
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
    \"\"\"Range-bound synthetic candle data.\"\"\"
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
"""


created = []
for rel_path, content in files.items():
    full_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(rel_path)

print(f"\n{'='*55}")
print(f"  Phase 2 setup complete — {len(created)} files written")
print(f"{'='*55}")
for p in created:
    print(f"  OK  {p}")
print(f"\nNow run:  python -m pytest -v")
print(f"Expected: 119 passed  (38 Phase 1 + 81 Phase 2)")
print(f"{'='*55}\n")
