"""
Options Chain Agent (Spec section 8, 9, 10)
Fetches option chain, calculates PCR variants, identifies
support/resistance zones from OI, and classifies IV environment.
"""

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
    """
    Provides options chain analysis for NIFTY / BANKNIFTY.
    Mock mode generates realistic synthetic chain data.
    """

    STRIKE_GAPS = {"NIFTY": 50, "BANKNIFTY": 100}

    def __init__(self, mock: bool = True):
        self._mock = mock
        self._rng  = random.Random(77)

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_chain(self, symbol: str, expiry: str = None, depth: int = 10) -> list[dict]:
        """
        Returns list of option dicts for `depth` strikes each side of ATM.
        Each dict: strike, option_type, ltp, bid, ask, oi, change_in_oi,
                   volume, iv, delta, gamma, theta, vega
        """
        cache_key = f"chain:{symbol}:{expiry}:{depth}"
        cached    = cache.get(cache_key)
        if cached:
            return cached

        chain = self._mock_chain(symbol, depth) if self._mock else []
        cache.set(cache_key, chain, ttl=60)
        return chain

    def analyse(self, symbol: str, depth: int = 10) -> dict:
        """
        Full options analysis dict consumed by the signal engine.
        Returns: pcr_oi, pcr_volume, pcr_change_oi,
                 max_call_oi_strike, max_put_oi_strike,
                 call_resistance, put_support,
                 atm_iv, iv_environment,
                 oi_score (0-100 for signal engine)
        """
        cache_key = f"analysis:{symbol}:{depth}"
        cached    = cache.get(cache_key)
        if cached:
            return cached

        chain  = self.get_chain(symbol, depth=depth)
        result = self._analyse_chain(symbol, chain)
        cache.set(cache_key, result, ttl=60)
        return result

    def get_oi_score(self, symbol: str) -> float:
        """0-100 score for signal engine. >50 = bullish options flow."""
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
        """
        PCR < 0.7 = too bullish (contrarian bearish) → score ~35
        PCR 0.7-1.0 = mild bullish → score 55-65
        PCR 1.0-1.3 = neutral → score 50
        PCR > 1.3 = too bearish (contrarian bullish) → score ~65
        Note: PCR alone is never a standalone signal per spec.
        """
        if pcr is None:
            return 50.0
        if pcr < 0.7:   return 35.0
        if pcr < 1.0:   return 55.0 + (1.0 - pcr) * 33
        if pcr < 1.3:   return 50.0
        return 65.0
