"""
Angel One Data Provider
Wraps AngelOneBroker to provide OHLCV candles and snapshots
in the same format as MockDataProvider.

Usage:
    from src.execution.brokers.angel_data import AngelOneDataProvider
    provider = AngelOneDataProvider(broker=angel_broker)
    df = provider.get_candles("NIFTY", "5min", count=250)
"""

import logging
import datetime
import pandas as pd
import pytz
from typing import Optional

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN  = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)


class AngelOneDataProvider:
    """
    Live market data from Angel One SmartAPI.
    Drop-in replacement for MockDataProvider.
    """

    def __init__(self, broker):
        self._broker = broker
        log.info("AngelOneDataProvider ready")

    def get_spot(self, symbol: str) -> Optional[float]:
        exchange = "NFO" if "FUT" in symbol or "CE" in symbol or "PE" in symbol else "NSE"
        return self._broker.get_ltp(symbol, exchange)

    def get_candles(
        self, symbol: str, timeframe: str = "5min", count: int = 250
    ) -> pd.DataFrame:
        """Fetch historical candles and return as DataFrame."""
        today     = datetime.date.today()
        days_back = max(10, count // 75 + 5)
        from_date = (today - datetime.timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date   = today.strftime("%Y-%m-%d")

        raw = self._broker.get_historical_candles(
            symbol    = symbol,
            exchange  = "NSE",
            timeframe = timeframe,
            from_date = from_date,
            to_date   = to_date,
        )

        if not raw:
            log.warning(f"No candle data returned for {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df.index = pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
        df = df[["open", "high", "low", "close", "volume"]].tail(count)
        df["vwap"] = (df["high"] + df["low"] + df["close"]) / 3
        df = df.sort_index()

        log.debug(f"Fetched {len(df)} candles for {symbol} ({timeframe})")
        return df

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
            "data_quality": 100 if spot else 0,
        }

    def is_market_open(self) -> bool:
        now = datetime.datetime.now(IST)
        if now.weekday() >= 5:
            return False
        return MARKET_OPEN <= now.time() < MARKET_CLOSE

    def get_data_quality(self, symbol: str) -> int:
        spot = self.get_spot(symbol)
        return 100 if spot and spot > 0 else 0
