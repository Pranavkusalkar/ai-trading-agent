"""
Signal Engine (Spec section 12)
Combines all agent outputs into a 100-point composite score.
Maps score to confidence band and selects options strategy.

Score weights (from config/strategy.yaml):
  trend        20 pts
  price_action 20 pts
  vwap         10 pts
  momentum     10 pts
  volume       10 pts
  futures_oi   10 pts
  options_oi   10 pts
  iv            5 pts
  market_regime 5 pts
  TOTAL       100 pts
"""

import logging
import datetime
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# ── Default weights (overridden by config/strategy.yaml) ─────────────────────
DEFAULT_WEIGHTS = {
    "trend":         20,
    "price_action":  20,
    "vwap":          10,
    "momentum":      10,
    "volume":        10,
    "futures_oi":    10,
    "options_oi":    10,
    "iv":             5,
    "market_regime":  5,
}

# ── Confidence bands (spec section 12) ───────────────────────────────────────
CONFIDENCE_BANDS = {
    "STRONG": 80,
    "VALID":  70,
    "WEAK":   60,
}

# ── Strategy map by score and direction ──────────────────────────────────────
STRATEGY_MAP = [
    (75, 100, "bullish",      "Long call / Bull call spread"),
    (55,  75, "mild_bullish", "Bull put spread / Cash-secured put"),
    (45,  55, "neutral",      "Iron condor / Short strangle"),
    (25,  45, "mild_bearish", "Bear call spread / Long put"),
    (0,   25, "bearish",      "Long put / Bear put spread"),
]


class SignalEngine:
    """
    Aggregates all agent scores into one composite signal.
    All agent outputs feed in as 0-100 subscores.
    """

    def __init__(self, weights: dict = None):
        self.weights = weights or DEFAULT_WEIGHTS
        total = sum(self.weights.values())
        if abs(total - 100) > 1:
            log.warning(f"Signal weights sum to {total}, expected 100")

    def compute(
        self,
        symbol:          str,
        tech:            dict,       # from indicators.technical.compute_all()
        volume:          dict,       # from indicators.volume.compute_volume()
        futures:         dict,       # from data.futures_data.FuturesDataAgent
        options:         dict,       # from data.options_chain.OptionsChainAgent.analyse()
        price_action:    dict = None,
        extra:           dict = None,
    ) -> dict:
        """
        Build the full signal dict.

        Parameters
        ----------
        symbol       : e.g. "NIFTY"
        tech         : output of compute_all() — contains ema, vwap, rsi, macd, adx, supertrend etc.
        volume       : output of compute_volume()
        futures      : output of FuturesDataAgent.get_futures_snapshot()
        options      : output of OptionsChainAgent.analyse()
        price_action : optional price action dict (Phase 4)
        extra        : any additional override scores

        Returns
        -------
        Full signal dict matching spec section 39 JSON format.
        """
        scores = self._extract_scores(tech, volume, futures, options, price_action)
        composite, breakdown = self._weighted_composite(scores)
        direction, bias      = self._direction(composite)
        confidence_band      = self._confidence_band(composite)
        strategy             = self._select_strategy(composite)
        entry, sl, target, rr = self._levels(tech, options, bias)

        # Decision
        if composite >= CONFIDENCE_BANDS["VALID"] and entry and sl and target:
            decision = "BUY" if bias in ("bullish", "mild_bullish") else \
                       "SELL" if bias in ("bearish", "mild_bearish") else "NO_TRADE"
        else:
            decision = "NO_TRADE"

        reasons      = self._reasons(tech, volume, futures, options, scores)
        invalidation = self._invalidation(tech, options, bias)

        signal = {
            "timestamp":       datetime.datetime.now(IST).isoformat(),
            "underlying":      symbol,
            "direction":       direction,
            "decision":        decision,
            "instrument_type": "OPTION",
            "option_type":     "CE" if bias in ("bullish", "mild_bullish") else "PE",
            "strike":          options.get("max_put_oi_strike") if "bear" in bias else options.get("max_call_oi_strike"),
            "expiry":          futures.get("expiry"),
            "entry":           entry,
            "stop_loss":       sl,
            "target":          target,
            "risk_reward":     rr,
            "confidence":      composite,
            "confidence_band": confidence_band,
            "market_regime":   tech.get("market_regime", "UNKNOWN"),
            "strategy":        strategy,
            "score_breakdown": breakdown,
            "reasons":         reasons,
            "invalidation":    invalidation,
        }

        log.info(
            f"[SIGNAL] {symbol} | {decision} | score={composite} "
            f"| band={confidence_band} | regime={signal['market_regime']}"
        )
        return signal

    # ── Score extraction ──────────────────────────────────────────────────────

    def _extract_scores(self, tech, volume, futures, options, price_action) -> dict:
        """Map each agent output to a 0-100 subscore."""
        ema_score  = tech.get("ema",        {}).get("score", 50)
        vwap_score = tech.get("vwap",       {}).get("score", 50)
        rsi_score  = tech.get("rsi",        {}).get("score", 50)
        macd_score = tech.get("macd",       {}).get("score", 50)
        adx_score  = tech.get("adx",        {}).get("score", 50)
        st_score   = tech.get("supertrend", {}).get("score", 50)
        bb_score   = tech.get("bollinger",  {}).get("score", 50)
        vol_score  = volume.get("score", 50)

        # Trend = average of EMA + ADX + Supertrend
        trend_score = (ema_score + adx_score + st_score) / 3

        # Momentum = RSI + MACD
        momentum_score = (rsi_score + macd_score) / 2

        # Futures OI score
        oi_signal = futures.get("oi_signal", "")
        futures_score = {
            "LONG_BUILDUP":   80.0,
            "SHORT_COVERING": 65.0,
            "LONG_UNWINDING": 35.0,
            "SHORT_BUILDUP":  20.0,
        }.get(oi_signal, 50.0)

        # Options OI score
        options_score = options.get("oi_score", 50.0)

        # IV score — penalise extreme IV expansion
        atm_iv = options.get("atm_iv", 15)
        if atm_iv is None:
            iv_score = 50.0
        elif atm_iv < 12:
            iv_score = 55.0   # low IV — options cheap, slight bullish
        elif atm_iv < 20:
            iv_score = 60.0   # normal
        elif atm_iv < 28:
            iv_score = 45.0   # elevated — caution
        else:
            iv_score = 30.0   # high IV expansion — avoid buying

        # Market regime score
        regime = tech.get("market_regime", "RANGE")
        regime_score = {
            "STRONG_BULL":     90.0,
            "BULL":            75.0,
            "WEAK_BULL":       62.0,
            "RANGE":           50.0,
            "WEAK_BEAR":       38.0,
            "BEAR":            25.0,
            "STRONG_BEAR":     10.0,
            "HIGH_VOLATILITY": 40.0,
            "LOW_VOLATILITY":  55.0,
        }.get(regime, 50.0)

        # Price action score (Phase 4 — default neutral)
        pa_score = price_action.get("score", 50) if price_action else 50.0

        return {
            "trend":         round(trend_score,   1),
            "price_action":  round(pa_score,       1),
            "vwap":          round(vwap_score,     1),
            "momentum":      round(momentum_score, 1),
            "volume":        round(vol_score,      1),
            "futures_oi":    round(futures_score,  1),
            "options_oi":    round(options_score,  1),
            "iv":            round(iv_score,       1),
            "market_regime": round(regime_score,   1),
        }

    def _weighted_composite(self, scores: dict) -> tuple[float, dict]:
        """Apply weights and compute composite score."""
        total   = 0.0
        breakdown = {}
        for key, weight in self.weights.items():
            raw   = scores.get(key, 50.0)
            contrib = raw * weight / 100
            total  += contrib
            breakdown[key] = {
                "raw_score":    raw,
                "weight":       weight,
                "contribution": round(contrib, 2),
            }
        return round(total, 1), breakdown

    def _direction(self, composite: float) -> tuple[str, str]:
        if composite >= 65:   return "LONG",  "bullish"
        if composite >= 55:   return "LONG",  "mild_bullish"
        if composite <= 35:   return "SHORT", "bearish"
        if composite <= 45:   return "SHORT", "mild_bearish"
        return "NEUTRAL", "neutral"

    def _confidence_band(self, composite: float) -> str:
        if composite >= CONFIDENCE_BANDS["STRONG"]: return "STRONG"
        if composite >= CONFIDENCE_BANDS["VALID"]:  return "VALID"
        if composite >= CONFIDENCE_BANDS["WEAK"]:   return "WEAK"
        return "NO_TRADE"

    def _select_strategy(self, composite: float) -> str:
        for lo, hi, bias, strategy in STRATEGY_MAP:
            if lo <= composite <= hi:
                return strategy
        return "No trade — unclear signal"

    def _levels(self, tech: dict, options: dict, bias: str) -> tuple:
        """
        Generate indicative entry, stop-loss, target and R:R.
        Uses ATR for SL sizing per spec section 17.
        In Phase 5 these become precise option premium levels.
        """
        atr_data = tech.get("atr", {})
        atr      = atr_data.get("atr", 0)
        price    = tech.get("ema", {}).get("price", 0)

        if not price or not atr:
            return None, None, None, None

        if "bull" in bias:
            entry  = round(price, 2)
            sl     = round(price - atr * 1.5, 2)
            target = round(price + atr * 3.0, 2)
        elif "bear" in bias:
            entry  = round(price, 2)
            sl     = round(price + atr * 1.5, 2)
            target = round(price - atr * 3.0, 2)
        else:
            return None, None, None, None

        risk   = abs(entry - sl)
        reward = abs(entry - target)
        rr     = round(reward / risk, 2) if risk > 0 else 0

        return entry, sl, target, rr

    def _reasons(self, tech, volume, futures, options, scores) -> list[str]:
        """Human-readable reasons for the signal."""
        reasons = []
        ema = tech.get("ema", {})
        if ema.get("golden_cross"):
            reasons.append("Golden cross: EMA50 above EMA200")
        if ema.get("above_200"):
            reasons.append("Price above 200 EMA — long-term uptrend")
        if tech.get("vwap", {}).get("above_vwap"):
            reasons.append("Price above VWAP — intraday bullish bias")
        rsi_val = tech.get("rsi", {}).get("rsi", 50)
        if rsi_val < 35:
            reasons.append(f"RSI oversold at {rsi_val:.1f} — reversal opportunity")
        elif rsi_val > 65:
            reasons.append(f"RSI overbought at {rsi_val:.1f} — momentum strong")
        if tech.get("adx", {}).get("trending"):
            reasons.append(f"ADX {tech['adx']['adx']:.1f} — strong trend")
        if tech.get("supertrend", {}).get("direction") == "BULLISH":
            reasons.append("Supertrend bullish")
        oi_sig = futures.get("oi_signal", "")
        if oi_sig:
            reasons.append(f"Futures OI: {oi_sig.replace('_', ' ').title()}")
        pcr = options.get("pcr_oi")
        if pcr:
            reasons.append(f"PCR OI: {pcr:.2f}")
        if volume.get("spike"):
            reasons.append("Volume spike detected — conviction move")
        regime = tech.get("market_regime", "")
        if regime:
            reasons.append(f"Market regime: {regime.replace('_', ' ').title()}")
        return reasons[:6]   # cap at 6 reasons

    def _invalidation(self, tech, options, bias) -> list[str]:
        """Conditions that would invalidate this signal."""
        inv = []
        vwap = tech.get("vwap", {}).get("vwap")
        if vwap:
            if "bull" in bias:
                inv.append(f"Price breaks below VWAP ({vwap:.0f})")
            else:
                inv.append(f"Price reclaims VWAP ({vwap:.0f})")
        ema200 = tech.get("ema", {}).get("ema200")
        if ema200:
            if "bull" in bias:
                inv.append(f"Price closes below EMA200 ({ema200:.0f})")
            else:
                inv.append(f"Price closes above EMA200 ({ema200:.0f})")
        call_res = options.get("call_resistance")
        put_sup  = options.get("put_support")
        if "bull" in bias and call_res:
            inv.append(f"Call OI wall at {call_res} acts as resistance")
        if "bear" in bias and put_sup:
            inv.append(f"Put OI wall at {put_sup} acts as support")
        inv.append("Market regime shifts to HIGH_VOLATILITY or opposite direction")
        return inv
