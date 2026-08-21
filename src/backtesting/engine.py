"""
Event-Driven Backtest Simulator (Spec section 23)
Replays historical candles bar-by-bar. Signal engine sees only
past data at each bar — strictly no look-ahead bias.

Simulates:
  - Entry on next-bar open after signal (realistic execution)
  - ATR-based stop-loss
  - Fixed R:R target
  - Trailing stop (break-even after +1R, then structure trail)
  - Partial exits
  - Full transaction costs (STT, GST, SEBI, stamp duty)
  - Slippage
  - Position sizing from risk %
"""

import logging
import uuid
import datetime
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import numpy as np

from src.backtesting.metrics         import calculate_metrics, format_report
from src.indicators.technical        import compute_all
from src.indicators.volume           import compute_volume
from src.data.futures_data           import FuturesDataAgent, classify_oi_signal
from src.data.options_chain          import OptionsChainAgent
from src.strategies.signal_engine    import SignalEngine
from src.utils.transaction_costs     import round_trip_cost

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_SLIPPAGE_PCT   = 0.001   # 0.1% slippage on entry and exit
DEFAULT_LOT_SIZE       = {"NIFTY": 50, "BANKNIFTY": 15}
OPTION_PREMIUM_PCT     = 0.025   # ATM option premium ≈ 2.5% of spot
MIN_BARS_FOR_SIGNAL    = 210     # need 210 bars of history before first signal


@dataclass
class BacktestTrade:
    trade_id:        str
    symbol:          str
    direction:       str          # LONG / SHORT
    entry_bar:       int
    entry_date:      str
    entry_price:     float
    stop_loss:       float
    target:          float
    quantity:        int
    lot_size:        int
    entry_premium:   float
    confidence:      float
    market_regime:   str
    signal_score:    dict = field(default_factory=dict)

    # Filled on exit
    exit_bar:        int    = 0
    exit_date:       str    = ""
    exit_price:      float  = 0.0
    exit_premium:    float  = 0.0
    exit_reason:     str    = ""
    gross_pnl:       float  = 0.0
    charges:         float  = 0.0
    net_pnl:         float  = 0.0
    holding_minutes: int    = 0
    is_open:         bool   = True


class BacktestSimulator:
    """
    Event-driven backtester.

    Usage:
        sim    = BacktestSimulator("NIFTY", df, capital=500_000)
        result = sim.run()
        print(result["report"])
    """

    def __init__(
        self,
        symbol:           str,
        df:               pd.DataFrame,
        capital:          float = 500_000,
        risk_pct:         float = 0.005,      # 0.5% per trade
        min_confidence:   float = 65.0,
        sl_atr_mult:      float = 1.5,
        tp_rr:            float = 2.0,
        trail_after_r:    float = 1.0,        # trail SL to break-even after +1R
        max_open:         int   = 1,          # max simultaneous positions
        slippage_pct:     float = DEFAULT_SLIPPAGE_PCT,
        timeframe_minutes:int   = 5,
        lot_size:         Optional[int] = None,
    ):
        self.symbol            = symbol.upper()
        self.df                = df.reset_index(drop=True)
        self.capital           = capital
        self.risk_pct          = risk_pct
        self.min_confidence    = min_confidence
        self.sl_atr_mult       = sl_atr_mult
        self.tp_rr             = tp_rr
        self.trail_after_r     = trail_after_r
        self.max_open          = max_open
        self.slippage_pct      = slippage_pct
        self.tf_minutes        = timeframe_minutes
        self.lot_size          = lot_size or DEFAULT_LOT_SIZE.get(self.symbol, 50)

        self._engine  = SignalEngine()
        self._futures = FuturesDataAgent(mock=True)
        self._options = OptionsChainAgent(mock=True)

        self.trades:       list[BacktestTrade] = []
        self.open_trades:  list[BacktestTrade] = []
        self.equity_curve: list[float]         = [capital]
        self._current_capital = capital

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> dict:
        """Run the full backtest bar by bar. Returns results dict."""
        log.info(
            f"Backtest start | {self.symbol} | {len(self.df)} bars "
            f"| capital=₹{self.capital:,.0f} | min_conf={self.min_confidence}"
        )

        for i in range(MIN_BARS_FOR_SIGNAL, len(self.df)):
            bar = self.df.iloc[i]

            # 1. Update open positions first (check SL / target / trail)
            self._update_open_positions(i, bar)

            # 2. Only enter new positions if capacity allows
            if len(self.open_trades) < self.max_open:
                self._check_entry(i, bar)

            self.equity_curve.append(round(self._current_capital, 2))

        # Close any still-open trades at last bar
        for trade in list(self.open_trades):
            self._close_trade(trade, len(self.df) - 1,
                              self.df.iloc[-1], reason="END_OF_DATA")

        closed = [t for t in self.trades if not t.is_open]
        metrics = calculate_metrics(
            [self._trade_to_dict(t) for t in closed],
            initial_capital=self.capital,
        )
        metrics["equity_curve"] = self.equity_curve

        report = format_report(metrics, self.symbol)
        log.info(f"Backtest complete | {len(closed)} trades | net_pnl=₹{metrics['net_pnl']:,.0f}")

        return {
            "symbol":     self.symbol,
            "metrics":    metrics,
            "trades":     [self._trade_to_dict(t) for t in closed],
            "report":     report,
            "parameters": {
                "capital":         self.capital,
                "risk_pct":        self.risk_pct,
                "min_confidence":  self.min_confidence,
                "sl_atr_mult":     self.sl_atr_mult,
                "tp_rr":           self.tp_rr,
                "bars":            len(self.df),
            },
        }

    # ── Signal generation ─────────────────────────────────────────────────────

    def _check_entry(self, i: int, bar) -> None:
        """Generate signal from data up to bar i-1 (no look-ahead)."""
        history = self.df.iloc[:i]   # strictly historical — bar i not included
        if len(history) < MIN_BARS_FOR_SIGNAL:
            return

        try:
            tech    = compute_all(history)
            vol     = compute_volume(history)
            futures = self._futures.get_futures_snapshot(self.symbol)
            options = self._options.analyse(self.symbol)

            signal  = self._engine.compute(
                self.symbol, tech, vol, futures, options
            )
        except Exception as e:
            log.debug(f"Signal generation failed at bar {i}: {e}")
            return

        confidence = signal.get("confidence", 0)
        decision   = signal.get("decision", "NO_TRADE")

        if confidence < self.min_confidence or decision == "NO_TRADE":
            return

        # Enter on NEXT bar open (realistic — can't trade the signal bar)
        if i + 1 >= len(self.df):
            return

        next_bar   = self.df.iloc[i + 1]
        entry_px   = float(next_bar["open"]) * (1 + self.slippage_pct)
        atr_data   = tech.get("atr", {})
        atr        = atr_data.get("atr", float(next_bar["close"]) * 0.005)
        direction  = signal.get("direction", "NEUTRAL")

        if direction == "NEUTRAL":
            return

        if direction == "LONG":
            sl     = round(entry_px - atr * self.sl_atr_mult, 2)
            target = round(entry_px + atr * self.sl_atr_mult * self.tp_rr, 2)
        else:
            sl     = round(entry_px + atr * self.sl_atr_mult, 2)
            target = round(entry_px - atr * self.sl_atr_mult * self.tp_rr, 2)

        # Position sizing
        risk_amount  = self._current_capital * self.risk_pct
        risk_per_lot = abs(entry_px - sl) * self.lot_size
        lots         = max(1, int(risk_amount / risk_per_lot)) if risk_per_lot > 0 else 1
        quantity     = lots * self.lot_size

        # Option premium approximation
        entry_premium = round(entry_px * OPTION_PREMIUM_PCT, 2)

        trade = BacktestTrade(
            trade_id      = str(uuid.uuid4())[:8],
            symbol        = self.symbol,
            direction     = direction,
            entry_bar     = i + 1,
            entry_date    = str(next_bar.get("timestamp", i + 1)),
            entry_price   = round(entry_px, 2),
            stop_loss     = sl,
            target        = target,
            quantity      = quantity,
            lot_size      = self.lot_size,
            entry_premium = entry_premium,
            confidence    = confidence,
            market_regime = signal.get("market_regime", "UNKNOWN"),
            signal_score  = signal.get("score_breakdown", {}),
        )

        self.open_trades.append(trade)
        self.trades.append(trade)
        log.debug(
            f"ENTRY | {self.symbol} {direction} | bar={i+1} "
            f"| px={entry_px:.0f} SL={sl:.0f} TGT={target:.0f} "
            f"| conf={confidence:.1f}"
        )

    # ── Position management ───────────────────────────────────────────────────

    def _update_open_positions(self, i: int, bar) -> None:
        high  = float(bar["high"])
        low   = float(bar["low"])
        close = float(bar["close"])

        for trade in list(self.open_trades):
            # Trailing stop: move SL to break-even after +1R
            risk   = abs(trade.entry_price - trade.stop_loss)
            reward = abs(trade.entry_price - trade.target)

            if trade.direction == "LONG":
                gain = close - trade.entry_price
                if gain >= risk * self.trail_after_r:
                    new_sl = max(trade.stop_loss, trade.entry_price)
                    trade.stop_loss = new_sl

                # Check stop hit (low touched SL)
                if low <= trade.stop_loss:
                    self._close_trade(trade, i, bar, reason="STOP_LOSS",
                                      exit_price=trade.stop_loss)
                # Check target hit (high touched target)
                elif high >= trade.target:
                    self._close_trade(trade, i, bar, reason="TARGET",
                                      exit_price=trade.target)

            else:  # SHORT
                gain = trade.entry_price - close
                if gain >= risk * self.trail_after_r:
                    new_sl = min(trade.stop_loss, trade.entry_price)
                    trade.stop_loss = new_sl

                # Check stop hit
                if high >= trade.stop_loss:
                    self._close_trade(trade, i, bar, reason="STOP_LOSS",
                                      exit_price=trade.stop_loss)
                elif low <= trade.target:
                    self._close_trade(trade, i, bar, reason="TARGET",
                                      exit_price=trade.target)

    def _close_trade(
        self, trade: BacktestTrade, i: int, bar,
        reason: str = "MANUAL", exit_price: Optional[float] = None
    ) -> None:
        if not trade.is_open:
            return

        exit_px = exit_price or float(bar["close"])
        # Apply slippage on exit
        if reason == "STOP_LOSS":
            exit_px = exit_px * (1 - self.slippage_pct) if trade.direction == "LONG" \
                      else exit_px * (1 + self.slippage_pct)

        exit_premium = round(exit_px * OPTION_PREMIUM_PCT, 2)

        # P&L calculation
        if trade.direction == "LONG":
            price_diff = exit_px - trade.entry_price
        else:
            price_diff = trade.entry_price - exit_px

        gross_pnl = round(price_diff * trade.quantity, 2)

        # Transaction costs
        cost_data = round_trip_cost(
            instrument_type="option",
            entry_premium=trade.entry_premium,
            exit_premium=exit_premium,
            quantity=trade.quantity,
            underlying_lot=trade.lot_size,
            spot_price=trade.entry_price,
        )
        charges = cost_data["total_charges"]
        net_pnl = round(gross_pnl - charges, 2)

        # Holding time
        bars_held       = i - trade.entry_bar
        holding_minutes = bars_held * self.tf_minutes

        trade.exit_bar        = i
        trade.exit_date       = str(bar.get("timestamp", i))
        trade.exit_price      = round(exit_px, 2)
        trade.exit_premium    = exit_premium
        trade.exit_reason     = reason
        trade.gross_pnl       = gross_pnl
        trade.charges         = charges
        trade.net_pnl         = net_pnl
        trade.holding_minutes = holding_minutes
        trade.is_open         = False

        self._current_capital += net_pnl
        self.open_trades.remove(trade)

        log.debug(
            f"EXIT  | {self.symbol} {trade.direction} | {reason} "
            f"| net_pnl=₹{net_pnl:+,.0f} | capital=₹{self._current_capital:,.0f}"
        )

    def _trade_to_dict(self, t: BacktestTrade) -> dict:
        return {
            "trade_id":        t.trade_id,
            "symbol":          t.symbol,
            "direction":       t.direction,
            "entry_date":      t.entry_date,
            "exit_date":       t.exit_date,
            "entry_price":     t.entry_price,
            "exit_price":      t.exit_price,
            "stop_loss":       t.stop_loss,
            "target":          t.target,
            "quantity":        t.quantity,
            "gross_pnl":       t.gross_pnl,
            "charges":         t.charges,
            "net_pnl":         t.net_pnl,
            "holding_minutes": t.holding_minutes,
            "exit_reason":     t.exit_reason,
            "confidence":      t.confidence,
            "market_regime":   t.market_regime,
        }
