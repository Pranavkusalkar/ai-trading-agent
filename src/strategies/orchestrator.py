"""
Signal Orchestrator
Ties data provider, indicators, signal engine, and AI decision
into a single call that returns a complete, ready-to-risk-check signal.

Usage:
    from src.strategies.orchestrator import SignalOrchestrator
    orch   = SignalOrchestrator()
    signal = orch.run("NIFTY")
    # signal is now ready for risk_manager.validate_signal(signal)
"""

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
    """
    Single entry point for a full signal generation cycle.
    Instantiate once and call run() every interval.
    """

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
        """
        Full signal generation pipeline for one symbol.
        Returns a signal dict ready for risk_manager.validate_signal().
        """
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
        """Run the pipeline for multiple symbols and return ranked results."""
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
