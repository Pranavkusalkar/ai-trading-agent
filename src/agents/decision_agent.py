"""
AI Decision Agent (Spec sections 13, 14, 38)
Sends structured market data to Claude API and returns
a typed decision with full reasoning.

CRITICAL: The AI recommends only. Risk Manager has final authority.
AI output NEVER goes directly to the broker.

Architecture (spec section 14):
  AI → Signal → Risk Manager → Validation → Order Manager → Broker
"""

import json
import logging
import datetime
import os
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# ── System prompt (spec section 38) ──────────────────────────────────────────
SYSTEM_PROMPT = """You are the decision-analysis component of an Indian F&O trading system for NSE.

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
"""


class AIDecisionAgent:
    """
    Calls Claude API with structured market context.
    Falls back to rule-based decision if API is unavailable.
    """

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
        """
        Main entry point.
        signal         : output of SignalEngine.compute()
        market_context : raw indicator values for the AI prompt

        Returns enriched decision dict with AI reasoning layered on top.
        """
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

        prompt = f"""Analyze this NSE F&O market data and provide a trading decision.

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

Based on all of the above, provide your structured decision as JSON."""

        return prompt

    def _call_api(self, symbol: str, signal: dict, ctx: dict) -> dict:
        """Call Claude API and parse JSON response."""
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
        """Layer AI reasoning on top of the rule-based signal."""
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
