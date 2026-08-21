"""
Data Validator (Spec section — Data Validation / Cleaning)
Validates incoming market data before it reaches the signal engine.
Returns a ValidationResult so callers can act on failures.
"""

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
        """
        Validate a candle DataFrame.
        Checks: schema, nulls, OHLC integrity, volume, gaps, minimum length.
        """
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
        """
        Validate a market snapshot dict (spot, futures, OI, PCR etc.)
        """
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
        """Validate options chain list of dicts."""
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
        """
        Detect missing candles in a time series.
        Returns list of (gap_start, gap_end, missing_count) tuples.
        """
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
