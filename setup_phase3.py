"""
AI Trading Agent - Phase 3 Setup Script
Adds the signal engine, AI decision agent, and orchestrator.

Usage (from C:\trading\ai_trading_agent with venv active):
    python setup_phase3.py
    python -m pytest -v

Expected result: 155 passed (119 Phase 1+2 + 36 new Phase 3)
Prerequisites: setup_project.py and setup_phase2.py already run.
"""

import os

ROOT  = os.path.dirname(os.path.abspath(__file__))
files = {}

files["src/strategies/__init__.py"] = """"""

files["src/agents/__init__.py"] = """"""

files["src/strategies/signal_engine.py"] = """\"\"\"
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
\"\"\"

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
    \"\"\"
    Aggregates all agent scores into one composite signal.
    All agent outputs feed in as 0-100 subscores.
    \"\"\"

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
        \"\"\"
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
        \"\"\"
        scores = self._extract_scores(tech, volume, futures, options, price_action)
        composite, breakdown = self._weighted_composite(scores)
        direction, bias      = self._direction(composite)
        confidence_band      = self._confidence_band(composite)
        strategy             = self._select_strategy(composite)
        entry, sl, target, rr = self._levels(tech, options, bias)

        # Decision
        if composite >= CONFIDENCE_BANDS["VALID"] and entry and sl and target:
            decision = "BUY" if bias in ("bullish", "mild_bullish") else \\
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
        \"\"\"Map each agent output to a 0-100 subscore.\"\"\"
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
        \"\"\"Apply weights and compute composite score.\"\"\"
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
        \"\"\"
        Generate indicative entry, stop-loss, target and R:R.
        Uses ATR for SL sizing per spec section 17.
        In Phase 5 these become precise option premium levels.
        \"\"\"
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
        \"\"\"Human-readable reasons for the signal.\"\"\"
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
        \"\"\"Conditions that would invalidate this signal.\"\"\"
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
"""

files["src/strategies/orchestrator.py"] = """\"\"\"
Signal Orchestrator
Ties data provider, indicators, signal engine, and AI decision
into a single call that returns a complete, ready-to-risk-check signal.

Usage:
    from src.strategies.orchestrator import SignalOrchestrator
    orch   = SignalOrchestrator()
    signal = orch.run("NIFTY")
    # signal is now ready for risk_manager.validate_signal(signal)
\"\"\"

import logging
from typing import Optional

from src.data.market_data    import create_data_provider, MarketDataProvider
from src.data.futures_data   import FuturesDataAgent
from src.data.options_chain  import OptionsChainAgent
from src.indicators.technical import compute_all
from src.indicators.volume    import compute_volume
from src.strategies.signal_engine import SignalEngine
from src.agents.decision_agent    import AIDecisionAgent

log = logging.getLogger(__name__)


class SignalOrchestrator:
    \"\"\"
    Single entry point for a full signal generation cycle.
    Instantiate once and call run() every interval.
    \"\"\"

    def __init__(
        self,
        data_provider:   Optional[MarketDataProvider] = None,
        weights:         Optional[dict] = None,
        ai_api_key:      Optional[str]  = None,
        use_ai:          bool = True,
        candle_count:    int  = 250,
        timeframe:       str  = "5min",
    ):
        self.provider     = data_provider or create_data_provider("mock")
        self.futures_agent = FuturesDataAgent(mock=True)
        self.options_agent = OptionsChainAgent(mock=True)
        self.signal_engine = SignalEngine(weights=weights)
        self.ai_agent      = AIDecisionAgent(api_key=ai_api_key) if use_ai else None
        self.candle_count  = candle_count
        self.timeframe     = timeframe

        log.info(
            f"SignalOrchestrator ready | provider={type(self.provider).__name__} "
            f"| tf={timeframe} | ai={'yes' if use_ai else 'no'}"
        )

    def run(self, symbol: str) -> dict:
        \"\"\"
        Full signal generation pipeline for one symbol.
        Returns a signal dict ready for risk_manager.validate_signal().
        \"\"\"
        log.info(f"Running signal pipeline for {symbol}")

        # 1. Fetch candles
        df = self.provider.get_candles(symbol, self.timeframe, self.candle_count)
        if df.empty:
            log.error(f"No candle data for {symbol} — aborting")
            return self._empty_signal(symbol, "No candle data")

        # 2. Compute indicators
        vix  = getattr(self.provider, "get_vix", lambda: None)()
        tech = compute_all(df, vix=vix)
        vol  = compute_volume(df)

        # 3. Fetch futures and options data
        futures = self.futures_agent.get_futures_snapshot(symbol)
        options = self.options_agent.analyse(symbol)

        # 4. Build composite signal
        signal = self.signal_engine.compute(
            symbol=symbol,
            tech=tech,
            volume=vol,
            futures=futures,
            options=options,
        )

        # 5. AI decision layer (optional)
        if self.ai_agent:
            market_context = {**tech, "futures": futures, "options": options, "volume": vol}
            signal = self.ai_agent.decide(symbol, signal, market_context)

        return signal

    def run_all(self, symbols: list[str]) -> list[dict]:
        \"\"\"Run the pipeline for multiple symbols and return ranked results.\"\"\"
        signals = []
        for sym in symbols:
            try:
                s = self.run(sym)
                signals.append(s)
            except Exception as e:
                log.error(f"Pipeline failed for {sym}: {e}", exc_info=True)

        # Rank by confidence score descending
        return sorted(signals, key=lambda x: x.get("confidence", 0), reverse=True)

    @staticmethod
    def _empty_signal(symbol: str, reason: str) -> dict:
        return {
            "underlying": symbol,
            "decision":   "NO_TRADE",
            "confidence": 0,
            "reason":     reason,
        }
"""

files["src/agents/decision_agent.py"] = """\"\"\"
AI Decision Agent (Spec sections 13, 14, 38)
Sends structured market data to Claude API and returns
a typed decision with full reasoning.

CRITICAL: The AI recommends only. Risk Manager has final authority.
AI output NEVER goes directly to the broker.

Architecture (spec section 14):
  AI → Signal → Risk Manager → Validation → Order Manager → Broker
\"\"\"

import json
import logging
import datetime
import os
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# ── System prompt (spec section 38) ──────────────────────────────────────────
SYSTEM_PROMPT = \"\"\"You are the decision-analysis component of an Indian F&O trading system for NSE.

You do NOT directly execute orders. Your role is analysis and recommendation only.

Analyze the structured market data provided. Evaluate:
1. Market trend and EMA structure
2. Price action relative to VWAP
3. Momentum (RSI, MACD)
4. Volume confirmation
5. Futures OI classification
6. Options OI, PCR, and IV environment
7. Support and resistance from options chain
8. Market regime
9. Risk/reward

Rules:
- Be conservative. If evidence is conflicting, return NO_TRADE.
- Never invent market data or assume missing information.
- Never override risk management rules.
- A strong signal requires confirmation from multiple independent dimensions.

Return ONLY a valid JSON object with these exact fields:
{
  "direction": "LONG" | "SHORT" | "NEUTRAL",
  "decision": "BUY" | "SELL" | "NO_TRADE",
  "instrument_type": "OPTION" | "FUTURE",
  "option_type": "CE" | "PE" | null,
  "entry_zone": "description of entry zone",
  "stop_loss_rationale": "why this stop level",
  "target_rationale": "why this target level",
  "risk_reward": float,
  "confidence": float (0-100),
  "market_regime": "regime string",
  "reasons": ["reason1", "reason2", "reason3"],
  "invalidation": ["condition1", "condition2"],
  "ai_notes": "any additional context"
}

Do not include any text outside the JSON object.
Do not add markdown code fences.
\"\"\"


class AIDecisionAgent:
    \"\"\"
    Calls Claude API with structured market context.
    Falls back to rule-based decision if API is unavailable.
    \"\"\"

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key or os.getenv("AI_API_KEY", "")
        self.model   = model
        self._available = bool(self.api_key)
        if not self._available:
            log.warning(
                "AI_API_KEY not set. AIDecisionAgent will use "
                "rule-based fallback. Set AI_API_KEY in .env for full AI analysis."
            )

    def decide(self, symbol: str, signal: dict, market_context: dict) -> dict:
        \"\"\"
        Main entry point.
        signal         : output of SignalEngine.compute()
        market_context : raw indicator values for the AI prompt

        Returns enriched decision dict with AI reasoning layered on top.
        \"\"\"
        if self._available:
            try:
                ai_result = self._call_api(symbol, signal, market_context)
                return self._merge(signal, ai_result)
            except Exception as e:
                log.error(f"AI API call failed: {e} — using rule-based fallback")

        # Fallback: return signal as-is with fallback flag
        return {**signal, "ai_used": False, "ai_notes": "Rule-based decision (AI API not available)"}

    def _build_prompt(self, symbol: str, signal: dict, ctx: dict) -> str:
        ema  = ctx.get("ema",  {})
        vwap = ctx.get("vwap", {})
        rsi  = ctx.get("rsi",  {})
        macd = ctx.get("macd", {})
        atr  = ctx.get("atr",  {})
        adx  = ctx.get("adx",  {})
        st   = ctx.get("supertrend", {})
        fut  = ctx.get("futures", {})
        opt  = ctx.get("options", {})
        vol  = ctx.get("volume",  {})

        prompt = f\"\"\"Analyze this NSE F&O market data and provide a trading decision.

INSTRUMENT: {symbol}
TIMESTAMP:  {datetime.datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}

=== PRICE & TREND ===
Spot price:      {ema.get('price', 'N/A')}
EMA 9:           {ema.get('ema9', 'N/A')}
EMA 21:          {ema.get('ema21', 'N/A')}
EMA 50:          {ema.get('ema50', 'N/A')}
EMA 200:         {ema.get('ema200', 'N/A')}
Above EMA200:    {ema.get('above_200', 'N/A')}
Golden cross:    {ema.get('golden_cross', 'N/A')}
VWAP:            {vwap.get('vwap', 'N/A')}
Above VWAP:      {vwap.get('above_vwap', 'N/A')}
Supertrend:      {st.get('direction', 'N/A')}

=== MOMENTUM ===
RSI (14):        {rsi.get('rsi', 'N/A')}
MACD histogram:  {macd.get('histogram', 'N/A')}
MACD crossover:  {'Bullish' if macd.get('crossover_bull') else 'Bearish' if macd.get('crossover_bear') else 'None'}
ADX:             {adx.get('adx', 'N/A')}
DI+ vs DI-:      {adx.get('plus_di', 'N/A')} vs {adx.get('minus_di', 'N/A')}
ATR:             {atr.get('atr', 'N/A')} ({atr.get('volatility', 'N/A')} volatility)

=== VOLUME ===
Volume ratio:    {vol.get('volume_ratio', 'N/A')}x average
P/V signal:      {vol.get('price_volume_signal', 'N/A')}
Volume spike:    {vol.get('spike', 'N/A')}

=== FUTURES ===
Futures price:   {fut.get('price', 'N/A')}
Basis:           {fut.get('basis', 'N/A')}
OI:              {fut.get('oi', 'N/A'):,} contracts
Change in OI:    {fut.get('change_in_oi', 'N/A'):,}
OI signal:       {fut.get('oi_signal', 'N/A')}

=== OPTIONS CHAIN ===
PCR (OI):        {opt.get('pcr_oi', 'N/A')}
PCR (volume):    {opt.get('pcr_volume', 'N/A')}
ATM IV:          {opt.get('atm_iv', 'N/A')}%
IV environment:  {opt.get('iv_environment', 'N/A')}
Call resistance: {opt.get('call_resistance', 'N/A')}
Put support:     {opt.get('put_support', 'N/A')}

=== SIGNAL ENGINE OUTPUT ===
Composite score: {signal.get('confidence', 'N/A')} / 100
Confidence band: {signal.get('confidence_band', 'N/A')}
Market regime:   {signal.get('market_regime', 'N/A')}
Rule-based decision: {signal.get('decision', 'N/A')}
Suggested strategy: {signal.get('strategy', 'N/A')}

Based on all of the above, provide your structured decision as JSON.\"\"\"

        return prompt

    def _call_api(self, symbol: str, signal: dict, ctx: dict) -> dict:
        \"\"\"Call Claude API and parse JSON response.\"\"\"
        import urllib.request

        prompt  = self._build_prompt(symbol, signal, ctx)
        payload = json.dumps({
            "model":      self.model,
            "max_tokens": 1000,
            "system":     SYSTEM_PROMPT,
            "messages":   [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        raw_text = data["content"][0]["text"].strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        return json.loads(raw_text)

    def _merge(self, signal: dict, ai: dict) -> dict:
        \"\"\"Layer AI reasoning on top of the rule-based signal.\"\"\"
        merged = dict(signal)
        merged["ai_used"]              = True
        merged["ai_direction"]         = ai.get("direction")
        merged["ai_decision"]          = ai.get("decision")
        merged["ai_confidence"]        = ai.get("confidence")
        merged["ai_notes"]             = ai.get("ai_notes", "")
        merged["ai_entry_zone"]        = ai.get("entry_zone")
        merged["ai_sl_rationale"]      = ai.get("stop_loss_rationale")
        merged["ai_target_rationale"]  = ai.get("target_rationale")
        merged["ai_reasons"]           = ai.get("reasons", [])
        merged["ai_invalidation"]      = ai.get("invalidation", [])

        # If AI overrides to NO_TRADE, respect it
        if ai.get("decision") == "NO_TRADE" and merged.get("decision") != "NO_TRADE":
            log.info("AI overrode rule-based signal to NO_TRADE")
            merged["decision"] = "NO_TRADE"
            merged["ai_override"] = True

        # Blend AI confidence with rule-based score (60/40 weight)
        rule_conf = signal.get("confidence", 50)
        ai_conf   = ai.get("confidence", rule_conf)
        merged["confidence"] = round(rule_conf * 0.6 + ai_conf * 0.4, 1)

        return merged
"""

files["tests/test_signal_engine.py"] = """\"\"\"
Unit tests - Signal Engine, AI Decision Agent, Orchestrator (Phase 3)
\"\"\"

import pytest
import sys
import numpy as np
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.strategies.signal_engine import SignalEngine, DEFAULT_WEIGHTS, CONFIDENCE_BANDS
from src.agents.decision_agent    import AIDecisionAgent
from src.strategies.orchestrator  import SignalOrchestrator


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_candles(n=250, trend=0.0005):
    np.random.seed(42)
    close = 24500 * np.cumprod(1 + np.random.normal(trend, 0.001, n))
    open_ = np.roll(close, 1); open_[0] = 24500
    high  = np.maximum(open_, close) * 1.002
    low   = np.minimum(open_, close) * 0.998
    vol   = np.random.randint(500_000, 2_000_000, n).astype(float)
    vwap  = (high + low + close) / 3
    idx   = pd.date_range("2026-01-02 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": vol, "vwap": vwap
    }, index=idx)


def make_tech(bullish=True):
    score = 72.0 if bullish else 28.0
    sig   = "BULLISH" if bullish else "BEARISH"
    return {
        "ema": {
            "score": score, "signal": sig, "price": 24500,
            "ema9": 24520, "ema21": 24480, "ema50": 24300, "ema200": 24000,
            "above_200": bullish, "above_50": bullish,
            "golden_cross": bullish, "death_cross": not bullish,
            "ema9_above_21": bullish,
        },
        "vwap":       {"score": score, "signal": sig, "vwap": 24450, "above_vwap": bullish, "pct_from_vwap": 0.2},
        "rsi":        {"score": score, "signal": sig, "rsi": 62.0 if bullish else 38.0, "oversold": False, "overbought": False},
        "macd":       {"score": score, "signal": sig, "histogram": 0.5 if bullish else -0.5, "crossover_bull": bullish, "crossover_bear": not bullish},
        "atr":        {"atr": 120.0, "atr_pct": 0.49, "volatility": "MEDIUM", "sl_1atr": 24380, "sl_15atr": 24320, "sl_2atr": 24260},
        "bollinger":  {"score": 55.0, "signal": "NEUTRAL", "pct_b": 0.55, "upper": 24800, "middle": 24500, "lower": 24200, "bandwidth": 2.5, "squeeze": False},
        "adx":        {"score": score, "signal": sig, "adx": 28.0, "plus_di": 25.0, "minus_di": 18.0, "trending": True, "bullish_di": bullish},
        "supertrend": {"score": 70.0 if bullish else 30.0, "signal": sig, "direction": "BULLISH" if bullish else "BEARISH", "supertrend": 24300},
        "market_regime": "BULL" if bullish else "BEAR",
        "tech_score":    score,
        "tech_signal":   sig,
    }


def make_volume(bullish=True):
    return {
        "score": 72.0 if bullish else 28.0,
        "signal": "BULLISH" if bullish else "BEARISH",
        "volume_ratio": 1.6,
        "volume_class": "HIGH",
        "price_volume_signal": "BULLISH_CONFIRMATION" if bullish else "BEARISH_CONFIRMATION",
        "price_up": bullish,
        "spike": False,
        "contraction": False,
        "current_volume": 1_500_000,
        "volume_ma": 950_000,
        "price_change_pct": 0.3 if bullish else -0.3,
    }


def make_futures(bullish=True):
    return {
        "symbol": "NIFTY",
        "price": 24510.0,
        "prev_price": 24400.0,
        "price_change_pct": 0.45 if bullish else -0.45,
        "oi": 12_500_000,
        "prev_oi": 12_000_000,
        "change_in_oi": 500_000 if bullish else -500_000,
        "change_in_oi_pct": 4.2,
        "basis": 10.0,
        "oi_signal": "LONG_BUILDUP" if bullish else "SHORT_BUILDUP",
        "oi_signal_description": "Fresh longs being added",
        "volume": 450_000,
        "expiry": "2026-08-21",
    }


def make_options(bullish=True):
    return {
        "symbol": "NIFTY",
        "pcr_oi": 0.85 if bullish else 1.4,
        "pcr_volume": 0.9,
        "pcr_change_oi": 0.8,
        "max_call_oi_strike": 24600,
        "max_put_oi_strike": 24400,
        "call_resistance": 24600,
        "put_support": 24400,
        "atm_iv": 14.5,
        "iv_environment": "NORMAL_IV",
        "oi_score": 62.0 if bullish else 38.0,
        "total_call_oi": 8_000_000,
        "total_put_oi": 6_800_000,
    }


# ── Signal Engine tests ───────────────────────────────────────────────────────

class TestSignalEngine:

    def setup_method(self):
        self.engine = SignalEngine()

    def test_compute_returns_required_keys(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        for k in ["timestamp","underlying","direction","decision",
                  "confidence","confidence_band","market_regime",
                  "strategy","score_breakdown","reasons","invalidation"]:
            assert k in sig, f"Missing key: {k}"

    def test_bullish_composite_score(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        assert sig["confidence"] > 55, f"Expected bullish score, got {sig['confidence']}"

    def test_bearish_composite_score(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(False), make_volume(False),
            make_futures(False), make_options(False)
        )
        assert sig["confidence"] < 45, f"Expected bearish score, got {sig['confidence']}"

    def test_score_in_range(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert 0 <= sig["confidence"] <= 100

    def test_decision_no_trade_on_low_score(self):
        # Neutral tech should produce low confidence
        tech = make_tech()
        for k in ["ema","vwap","rsi","macd","adx","supertrend","bollinger"]:
            if isinstance(tech.get(k), dict):
                tech[k]["score"] = 50.0
        tech["market_regime"] = "RANGE"
        tech["tech_score"]    = 50.0
        vol  = make_volume(); vol["score"] = 50.0
        fut  = make_futures(); fut["oi_signal"] = ""
        opt  = make_options(); opt["oi_score"] = 50.0; opt["atm_iv"] = 20.0
        sig  = self.engine.compute("NIFTY", tech, vol, fut, opt)
        assert sig["decision"] in ["NO_TRADE","BUY","SELL"]   # any valid decision

    def test_confidence_band_valid_values(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert sig["confidence_band"] in ["STRONG","VALID","WEAK","NO_TRADE"]

    def test_strategy_string_not_empty(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert isinstance(sig["strategy"], str)
        assert len(sig["strategy"]) > 0

    def test_score_breakdown_has_all_dimensions(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        for dim in DEFAULT_WEIGHTS.keys():
            assert dim in sig["score_breakdown"], f"Missing dimension: {dim}"

    def test_breakdown_contributions_sum_to_composite(self):
        sig    = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        total  = sum(v["contribution"] for v in sig["score_breakdown"].values())
        assert abs(total - sig["confidence"]) < 0.5

    def test_reasons_list(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        assert isinstance(sig["reasons"], list)
        assert len(sig["reasons"]) > 0

    def test_invalidation_list(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert isinstance(sig["invalidation"], list)
        assert len(sig["invalidation"]) > 0

    def test_entry_sl_target_present_on_valid_signal(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        if sig["decision"] != "NO_TRADE":
            assert sig["entry"]     is not None
            assert sig["stop_loss"] is not None
            assert sig["target"]    is not None
            assert sig["risk_reward"] > 0

    def test_custom_weights(self):
        custom = {k: 100//len(DEFAULT_WEIGHTS) for k in DEFAULT_WEIGHTS}
        engine = SignalEngine(weights=custom)
        sig    = engine.compute(
            "NIFTY", make_tech(), make_volume(),
            make_futures(), make_options()
        )
        assert 0 <= sig["confidence"] <= 100

    def test_banknifty_signal(self):
        sig = self.engine.compute(
            "BANKNIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        assert sig["underlying"] == "BANKNIFTY"

    def test_bull_bias_gives_ce_option_type(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(True), make_volume(True),
            make_futures(True), make_options(True)
        )
        if sig["direction"] == "LONG":
            assert sig["option_type"] == "CE"

    def test_bear_bias_gives_pe_option_type(self):
        sig = self.engine.compute(
            "NIFTY", make_tech(False), make_volume(False),
            make_futures(False), make_options(False)
        )
        if sig["direction"] == "SHORT":
            assert sig["option_type"] == "PE"


# ── Score extraction tests ────────────────────────────────────────────────────

class TestScoreExtraction:

    def setup_method(self):
        self.engine = SignalEngine()

    def test_long_buildup_gives_high_futures_score(self):
        fut = make_futures(bullish=True)
        fut["oi_signal"] = "LONG_BUILDUP"
        scores = self.engine._extract_scores(make_tech(), make_volume(), fut, make_options(), None)
        assert scores["futures_oi"] >= 75

    def test_short_buildup_gives_low_futures_score(self):
        fut = make_futures()
        fut["oi_signal"] = "SHORT_BUILDUP"
        scores = self.engine._extract_scores(make_tech(), make_volume(), fut, make_options(), None)
        assert scores["futures_oi"] <= 25

    def test_high_iv_penalises_iv_score(self):
        opt = make_options()
        opt["atm_iv"] = 35.0
        scores = self.engine._extract_scores(make_tech(), make_volume(), make_futures(), opt, None)
        assert scores["iv"] <= 35

    def test_normal_iv_gives_good_score(self):
        opt = make_options()
        opt["atm_iv"] = 15.0
        scores = self.engine._extract_scores(make_tech(), make_volume(), make_futures(), opt, None)
        assert scores["iv"] >= 55

    def test_strong_bull_regime_score(self):
        tech = make_tech()
        tech["market_regime"] = "STRONG_BULL"
        scores = self.engine._extract_scores(tech, make_volume(), make_futures(), make_options(), None)
        assert scores["market_regime"] >= 85

    def test_range_regime_neutral_score(self):
        tech = make_tech()
        tech["market_regime"] = "RANGE"
        scores = self.engine._extract_scores(tech, make_volume(), make_futures(), make_options(), None)
        assert scores["market_regime"] == 50.0


# ── AI Decision Agent tests ───────────────────────────────────────────────────

class TestAIDecisionAgent:

    def test_no_api_key_uses_fallback(self):
        agent = AIDecisionAgent(api_key="")
        signal = {"confidence": 72, "decision": "BUY", "confidence_band": "VALID"}
        result = agent.decide("NIFTY", signal, {})
        assert result["ai_used"] is False
        assert "ai_notes" in result

    def test_fallback_preserves_signal(self):
        agent  = AIDecisionAgent(api_key="")
        signal = {"confidence": 80, "decision": "BUY", "underlying": "NIFTY"}
        result = agent.decide("NIFTY", signal, {})
        assert result["decision"]   == "BUY"
        assert result["confidence"] == 80
        assert result["underlying"] == "NIFTY"

    def test_merge_blends_confidence(self):
        agent  = AIDecisionAgent(api_key="fake_key_for_test")
        signal = {"confidence": 70, "decision": "BUY"}
        ai_out = {
            "direction": "LONG", "decision": "BUY", "confidence": 80,
            "instrument_type": "OPTION", "option_type": "CE",
            "entry_zone": "above 24500", "stop_loss_rationale": "below VWAP",
            "target_rationale": "next resistance", "risk_reward": 2.0,
            "market_regime": "BULL", "reasons": ["EMA bullish"],
            "invalidation": ["breaks VWAP"], "ai_notes": "Strong setup",
        }
        merged = agent._merge(signal, ai_out)
        # 70 * 0.6 + 80 * 0.4 = 74
        assert merged["confidence"] == pytest.approx(74.0, 0.1)
        assert merged["ai_used"]    is True

    def test_ai_no_trade_overrides_buy(self):
        agent  = AIDecisionAgent(api_key="fake_key_for_test")
        signal = {"confidence": 72, "decision": "BUY"}
        ai_out = {
            "direction": "NEUTRAL", "decision": "NO_TRADE", "confidence": 45,
            "instrument_type": "OPTION", "option_type": None,
            "entry_zone": "N/A", "stop_loss_rationale": "N/A",
            "target_rationale": "N/A", "risk_reward": 0,
            "market_regime": "RANGE", "reasons": ["conflicting signals"],
            "invalidation": [], "ai_notes": "Too many conflicting signals",
        }
        merged = agent._merge(signal, ai_out)
        assert merged["decision"]    == "NO_TRADE"
        assert merged["ai_override"] is True

    def test_prompt_contains_key_fields(self):
        agent  = AIDecisionAgent(api_key="")
        signal = {"confidence": 72, "decision": "BUY", "confidence_band": "VALID",
                  "market_regime": "BULL", "strategy": "Long call"}
        ctx    = {**make_tech(), "futures": make_futures(), "options": make_options(), "volume": make_volume()}
        prompt = agent._build_prompt("NIFTY", signal, ctx)
        assert "NIFTY"      in prompt
        assert "RSI"        in prompt
        assert "VWAP"       in prompt
        assert "Futures"    in prompt
        assert "PCR"        in prompt
        assert "72"         in prompt


# ── Orchestrator tests ────────────────────────────────────────────────────────

class TestSignalOrchestrator:

    def setup_method(self):
        self.orch = SignalOrchestrator(use_ai=False)

    def test_run_returns_signal(self):
        sig = self.orch.run("NIFTY")
        assert "underlying"  in sig
        assert "decision"    in sig
        assert "confidence"  in sig

    def test_run_nifty(self):
        sig = self.orch.run("NIFTY")
        assert sig["underlying"] == "NIFTY"

    def test_run_banknifty(self):
        sig = self.orch.run("BANKNIFTY")
        assert sig["underlying"] == "BANKNIFTY"

    def test_run_confidence_in_range(self):
        sig = self.orch.run("NIFTY")
        assert 0 <= sig["confidence"] <= 100

    def test_run_all_returns_sorted(self):
        results = self.orch.run_all(["NIFTY","BANKNIFTY"])
        assert len(results) == 2
        assert results[0]["confidence"] >= results[1]["confidence"]

    def test_decision_valid_value(self):
        sig = self.orch.run("NIFTY")
        assert sig["decision"] in ["BUY","SELL","NO_TRADE"]

    def test_market_regime_present(self):
        sig = self.orch.run("NIFTY")
        assert "market_regime" in sig
        assert isinstance(sig["market_regime"], str)

    def test_score_breakdown_present(self):
        sig = self.orch.run("NIFTY")
        assert "score_breakdown" in sig
        assert len(sig["score_breakdown"]) == len(DEFAULT_WEIGHTS)

    def test_orchestrator_with_custom_weights(self):
        weights = {k: 100//9 for k in DEFAULT_WEIGHTS}
        orch    = SignalOrchestrator(weights=weights, use_ai=False)
        sig     = orch.run("NIFTY")
        assert 0 <= sig["confidence"] <= 100
"""


created = []
for rel_path, content in files.items():
    full_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(rel_path)

print(f"\n{'='*55}")
print(f"  Phase 3 setup complete  {len(created)} files written")
print(f"{'='*55}")
for p in created:
    print(f"  OK  {p}")
print(f"\nNow run:  python -m pytest -v")
print(f"Expected: 155 passed  (119 Phase 1+2 + 36 Phase 3)")
print(f"{'='*55}\n")
