"""
Market Data Provider (Spec section 3 — Market Data Agent)
Defines the abstract interface and provides:
  - MockDataProvider   : realistic synthetic NIFTY/BANKNIFTY data (no API needed)
  - BrokerDataProvider : stub that connects to any broker implementing BrokerInterface

Switch providers by changing one line in config. All downstream code
(indicators, agents, signal engine) only sees MarketDataProvider.
"""

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
    """All data sources implement this interface."""

    @abstractmethod
    def get_spot(self, symbol: str) -> Optional[float]:
        """Current index spot price."""

    @abstractmethod
    def get_candles(
        self, symbol: str, timeframe: str, count: int = 250
    ) -> pd.DataFrame:
        """
        OHLCV candles. timeframe: '1min' | '5min' | '15min' | 'day'
        Returns DataFrame with DatetimeIndex and columns:
        open, high, low, close, volume, vwap
        """

    @abstractmethod
    def get_market_snapshot(self, symbol: str) -> dict:
        """
        Full snapshot: spot, futures price, basis, volume, market status.
        Matches spec section 3 output format.
        """

    @abstractmethod
    def is_market_open(self) -> bool:
        """Returns True during NSE trading hours."""

    def get_data_quality(self, symbol: str) -> int:
        """0–100 score. Override in subclasses for real health checks."""
        return 100


# ── Mock Data Provider ────────────────────────────────────────────────────────

class MockDataProvider(MarketDataProvider):
    """
    Generates realistic synthetic NIFTY / BANKNIFTY data.
    Uses seeded random walk so results are reproducible.
    Ideal for development, backtesting setup, and unit tests.
    """

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
        """Simulated India VIX."""
        return round(self._rng.uniform(12.0, 22.0), 2)


# ── Broker Data Provider stub ─────────────────────────────────────────────────

class BrokerDataProvider(MarketDataProvider):
    """
    Wraps a BrokerInterface implementation to provide market data.
    Plug in ZerodhaBroker / UpstoxBroker / AngelBroker here.
    Phase 8 connects this to the real broker.
    """

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
    """
    mode: 'mock' | 'broker'
    For Phase 2-7: use 'mock'.
    For Phase 8+:  use 'broker' and pass a connected BrokerInterface.
    """
    if mode == "mock":
        return MockDataProvider()
    if mode == "broker":
        if broker is None:
            raise ValueError("broker instance required for mode='broker'")
        return BrokerDataProvider(broker)
    raise ValueError(f"Unknown data provider mode: {mode}")
