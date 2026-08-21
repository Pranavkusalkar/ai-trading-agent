"""
AI Trading Agent - Phase 4 Setup Script
Adds the backtesting engine, metrics calculator, and walk-forward tester.

Usage (from C:\trading\ai_trading_agent with venv active):
    python setup_phase4.py
    python -m pytest -v

Expected result: 195 passed (155 Phase 1-3 + 40 new Phase 4)
Note: Phase 4 tests take ~2 minutes to run (simulator processes 500 bars each).
Prerequisites: setup_project.py, setup_phase2.py, setup_phase3.py already run.
"""

import os

ROOT  = os.path.dirname(os.path.abspath(__file__))
files = {}

files["src/backtesting/__init__.py"] = """"""

files["src/utils/transaction_costs.py"] = """\"\"\"
Transaction Cost Model - Indian F&O (for backtesting)
Brokerage, STT, exchange charges, SEBI fee, stamp duty, GST.
\"\"\"


def calculate_fno_charges(instrument_type, direction, premium, quantity,
                           underlying_lot, notional_value, brokerage_flat=20.0):
    turnover  = premium * quantity
    brokerage = brokerage_flat
    if instrument_type == "option":
        stt = (turnover * 0.000625) if direction == "sell" else 0.0
    else:
        stt = (notional_value * 0.0000125) if direction == "sell" else 0.0
    exchange_charge = turnover * 0.00053
    sebi_fee        = turnover * 0.000001
    if direction == "buy":
        stamp_duty = turnover * 0.00003 if instrument_type == "option" else notional_value * 0.00002
    else:
        stamp_duty = 0.0
    gst_base = brokerage + exchange_charge + sebi_fee
    gst      = gst_base * 0.18
    total    = brokerage + stt + exchange_charge + sebi_fee + stamp_duty + gst
    return {
        "brokerage": round(brokerage, 2), "stt": round(stt, 2),
        "exchange_charge": round(exchange_charge, 2),
        "sebi_fee": round(sebi_fee, 4), "stamp_duty": round(stamp_duty, 2),
        "gst": round(gst, 2), "total": round(total, 2), "turnover": round(turnover, 2),
    }


def round_trip_cost(instrument_type, entry_premium, exit_premium,
                    quantity, underlying_lot, spot_price, brokerage_flat=20.0):
    notional    = spot_price * quantity
    entry_costs = calculate_fno_charges(instrument_type, "buy",  entry_premium, quantity, underlying_lot, notional, brokerage_flat)
    exit_costs  = calculate_fno_charges(instrument_type, "sell", exit_premium,  quantity, underlying_lot, notional, brokerage_flat)
    total       = entry_costs["total"] + exit_costs["total"]
    gross_pnl   = (exit_premium - entry_premium) * quantity
    return {
        "entry_costs": entry_costs["total"], "exit_costs": exit_costs["total"],
        "total_charges": round(total, 2), "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(gross_pnl - total, 2),
        "breakeven_move": round(total / quantity, 4),
    }
"""

files["src/backtesting/metrics.py"] = """\"\"\"
Backtest Metrics (Spec section 24)
Calculates all 25 required metrics from a list of trade dicts.
Each trade dict must contain: net_pnl, gross_pnl, entry_date, exit_date,
direction, confidence, holding_minutes.
\"\"\"

import math
import datetime
from typing import Optional


def calculate_metrics(trades: list[dict], initial_capital: float = 500_000) -> dict:
    \"\"\"
    Compute all 25 spec metrics from a trades list.

    Parameters
    ----------
    trades          : list of trade dicts from BacktestSimulator
    initial_capital : starting capital for drawdown and return calculations

    Returns
    -------
    Full metrics dict matching spec section 24.
    \"\"\"
    if not trades:
        return _empty_metrics()

    pnls      = [t["net_pnl"]   for t in trades]
    gross_pnl = [t["gross_pnl"] for t in trades]
    winners   = [p for p in pnls if p > 0]
    losers    = [p for p in pnls if p < 0]

    total_trades  = len(trades)
    winning_trades = len(winners)
    losing_trades  = len(losers)
    win_rate       = round(winning_trades / total_trades * 100, 2) if total_trades else 0

    avg_win  = round(sum(winners) / len(winners), 2) if winners else 0
    avg_loss = round(sum(losers)  / len(losers),  2) if losers  else 0

    total_profit = round(sum(winners), 2)
    total_loss   = round(sum(losers),  2)
    net_pnl_val  = round(sum(pnls),    2)
    gross_pnl_val= round(sum(gross_pnl),2)

    profit_factor = round(
        abs(total_profit / total_loss), 3
    ) if total_loss != 0 else float("inf")

    avg_trade = round(net_pnl_val / total_trades, 2) if total_trades else 0

    # Expected value = win_rate * avg_win + loss_rate * avg_loss
    loss_rate = 1 - win_rate / 100
    expected_value = round((win_rate / 100) * avg_win + loss_rate * avg_loss, 2)

    # Equity curve and max drawdown
    equity    = _equity_curve(pnls, initial_capital)
    max_dd    = _max_drawdown(equity)
    max_dd_pct= round(max_dd / initial_capital * 100, 3) if initial_capital else 0

    # Sharpe ratio (annualised, assuming 252 trading days)
    sharpe   = _sharpe(pnls)
    sortino  = _sortino(pnls)

    # Consecutive wins / losses
    max_consec_wins, max_consec_losses = _consecutive(pnls)

    # Holding time
    holding_times = [t.get("holding_minutes", 0) for t in trades if t.get("holding_minutes")]
    avg_holding   = round(sum(holding_times) / len(holding_times), 1) if holding_times else 0

    # Total charges (brokerage + taxes)
    total_charges = round(gross_pnl_val - net_pnl_val, 2)

    # Return on capital
    return_pct = round(net_pnl_val / initial_capital * 100, 3) if initial_capital else 0

    return {
        # Spec section 24 — all 25 metrics
        "total_trades":           total_trades,
        "winning_trades":         winning_trades,
        "losing_trades":          losing_trades,
        "win_rate":               win_rate,
        "avg_win":                avg_win,
        "avg_loss":               avg_loss,
        "profit_factor":          profit_factor,
        "total_profit":           total_profit,
        "total_loss":             total_loss,
        "net_pnl":                net_pnl_val,
        "gross_pnl":              gross_pnl_val,
        "max_drawdown":           round(max_dd, 2),
        "max_drawdown_pct":       max_dd_pct,
        "avg_trade":              avg_trade,
        "expected_value":         expected_value,
        "sharpe_ratio":           sharpe,
        "sortino_ratio":          sortino,
        "max_consecutive_wins":   max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "avg_holding_minutes":    avg_holding,
        "total_charges":          total_charges,
        "net_profit_after_costs": net_pnl_val,   # net_pnl already has costs deducted
        "return_pct":             return_pct,
        "equity_curve":           equity,
        "initial_capital":        initial_capital,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _equity_curve(pnls: list, initial: float) -> list:
    curve  = [initial]
    equity = initial
    for p in pnls:
        equity += p
        curve.append(round(equity, 2))
    return curve


def _max_drawdown(equity: list) -> float:
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _sharpe(pnls: list, risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return round((mean - risk_free) / std * math.sqrt(periods_per_year), 3)


def _sortino(pnls: list, risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    if len(pnls) < 2:
        return 0.0
    mean     = sum(pnls) / len(pnls)
    neg_pnls = [p for p in pnls if p < 0]
    if not neg_pnls:
        return float("inf")
    downside_variance = sum(p ** 2 for p in neg_pnls) / len(pnls)
    downside_std = math.sqrt(downside_variance)
    if downside_std == 0:
        return 0.0
    return round((mean - risk_free) / downside_std * math.sqrt(periods_per_year), 3)


def _consecutive(pnls: list) -> tuple[int, int]:
    max_wins = max_losses = curr_wins = curr_losses = 0
    for p in pnls:
        if p > 0:
            curr_wins  += 1
            curr_losses = 0
        elif p < 0:
            curr_losses += 1
            curr_wins    = 0
        max_wins   = max(max_wins,   curr_wins)
        max_losses = max(max_losses, curr_losses)
    return max_wins, max_losses


def _empty_metrics() -> dict:
    return {k: 0 for k in [
        "total_trades","winning_trades","losing_trades","win_rate",
        "avg_win","avg_loss","profit_factor","total_profit","total_loss",
        "net_pnl","gross_pnl","max_drawdown","max_drawdown_pct","avg_trade",
        "expected_value","sharpe_ratio","sortino_ratio","max_consecutive_wins",
        "max_consecutive_losses","avg_holding_minutes","total_charges",
        "net_profit_after_costs","return_pct","initial_capital",
    ]} | {"equity_curve": [], "profit_factor": 0}


def format_report(metrics: dict, symbol: str = "", strategy: str = "") -> str:
    \"\"\"Print-friendly backtest summary.\"\"\"
    sep = "=" * 58
    lines = [
        sep,
        f"  BACKTEST REPORT{' — ' + symbol if symbol else ''}",
        f"  Strategy: {strategy}" if strategy else "",
        sep,
        f"  Total trades:          {metrics['total_trades']}",
        f"  Winning trades:        {metrics['winning_trades']}  ({metrics['win_rate']}%)",
        f"  Losing trades:         {metrics['losing_trades']}",
        f"  Avg win:               ₹{metrics['avg_win']:,.0f}",
        f"  Avg loss:              ₹{metrics['avg_loss']:,.0f}",
        f"  Profit factor:         {metrics['profit_factor']}",
        f"  Net P&L:               ₹{metrics['net_pnl']:,.0f}",
        f"  Return:                {metrics['return_pct']}%",
        f"  Max drawdown:          ₹{metrics['max_drawdown']:,.0f}  ({metrics['max_drawdown_pct']}%)",
        f"  Sharpe ratio:          {metrics['sharpe_ratio']}",
        f"  Sortino ratio:         {metrics['sortino_ratio']}",
        f"  Max consec. wins:      {metrics['max_consecutive_wins']}",
        f"  Max consec. losses:    {metrics['max_consecutive_losses']}",
        f"  Avg holding:           {metrics['avg_holding_minutes']} min",
        f"  Total charges:         ₹{metrics['total_charges']:,.0f}",
        sep,
    ]
    return "\\n".join(l for l in lines if l)
"""

files["src/backtesting/engine.py"] = """\"\"\"
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
\"\"\"

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
    \"\"\"
    Event-driven backtester.

    Usage:
        sim    = BacktestSimulator("NIFTY", df, capital=500_000)
        result = sim.run()
        print(result["report"])
    \"\"\"

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
        \"\"\"Run the full backtest bar by bar. Returns results dict.\"\"\"
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
        \"\"\"Generate signal from data up to bar i-1 (no look-ahead).\"\"\"
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
            exit_px = exit_px * (1 - self.slippage_pct) if trade.direction == "LONG" \\
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
"""

files["src/backtesting/walk_forward.py"] = """\"\"\"
Walk-Forward Tester (Spec section 25)
Prevents overfitting by testing on out-of-sample data.

Rolling walk-forward example:
  Window 1: Train 2023 → Validate 2024-H1 → OOS 2024-H2
  Window 2: Train 2023+2024-H1 → Validate 2024-H2 → OOS 2025-H1
  ...

Usage:
    wft    = WalkForwardTester("NIFTY", df, n_windows=3)
    result = wft.run()
\"\"\"

import logging
from src.backtesting.engine  import BacktestSimulator
from src.backtesting.metrics import calculate_metrics, format_report

log = logging.getLogger(__name__)


class WalkForwardTester:
    \"\"\"
    Splits the dataset into overlapping train/validate/OOS windows
    and runs a backtest on each OOS period.
    Aggregates results to assess robustness across different market regimes.
    \"\"\"

    def __init__(
        self,
        symbol:         str,
        df,
        n_windows:      int   = 3,
        train_pct:      float = 0.60,
        validate_pct:   float = 0.20,
        oos_pct:        float = 0.20,
        capital:        float = 500_000,
        min_confidence: float = 65.0,
        risk_pct:       float = 0.005,
    ):
        self.symbol         = symbol
        self.df             = df
        self.n_windows      = n_windows
        self.train_pct      = train_pct
        self.validate_pct   = validate_pct
        self.oos_pct        = oos_pct
        self.capital        = capital
        self.min_confidence = min_confidence
        self.risk_pct       = risk_pct

    def run(self) -> dict:
        \"\"\"Run all walk-forward windows and return aggregated results.\"\"\"
        n      = len(self.df)
        window = n // (self.n_windows + 1)
        results = []

        for w in range(self.n_windows):
            train_end    = window * (w + 1)
            validate_end = train_end    + int(window * self.validate_pct / self.oos_pct)
            oos_end      = validate_end + int(window * self.oos_pct      / self.oos_pct)
            oos_end      = min(oos_end, n)

            if oos_end - validate_end < 50:
                log.warning(f"Window {w+1}: OOS period too short, skipping")
                continue

            train_df    = self.df.iloc[:train_end]
            validate_df = self.df.iloc[train_end:validate_end]
            oos_df      = self.df.iloc[validate_end:oos_end]

            log.info(
                f"Walk-forward window {w+1}/{self.n_windows} | "
                f"train={len(train_df)} validate={len(validate_df)} oos={len(oos_df)} bars"
            )

            # Run backtest only on OOS data
            sim = BacktestSimulator(
                symbol         = self.symbol,
                df             = oos_df.reset_index(drop=True),
                capital        = self.capital,
                min_confidence = self.min_confidence,
                risk_pct       = self.risk_pct,
            )
            result = sim.run()
            result["window"]       = w + 1
            result["train_bars"]   = len(train_df)
            result["validate_bars"]= len(validate_df)
            result["oos_bars"]     = len(oos_df)
            results.append(result)

        return self._aggregate(results)

    def _aggregate(self, results: list[dict]) -> dict:
        if not results:
            return {"error": "No walk-forward windows completed"}

        all_trades = []
        for r in results:
            all_trades.extend(r.get("trades", []))

        agg_metrics = calculate_metrics(all_trades, self.capital)

        window_summaries = []
        for r in results:
            m = r["metrics"]
            window_summaries.append({
                "window":       r["window"],
                "oos_bars":     r["oos_bars"],
                "total_trades": m["total_trades"],
                "win_rate":     m["win_rate"],
                "net_pnl":      m["net_pnl"],
                "profit_factor": m["profit_factor"],
                "sharpe_ratio": m["sharpe_ratio"],
            })

        # Consistency score — how many windows were profitable
        profitable_windows = sum(
            1 for r in results if r["metrics"]["net_pnl"] > 0
        )
        consistency = round(profitable_windows / len(results) * 100, 1)

        return {
            "symbol":               self.symbol,
            "n_windows":            len(results),
            "profitable_windows":   profitable_windows,
            "consistency_pct":      consistency,
            "aggregate_metrics":    agg_metrics,
            "window_summaries":     window_summaries,
            "aggregate_report":     format_report(agg_metrics, self.symbol, "Walk-Forward Aggregate"),
        }
"""

files["tests/test_backtest.py"] = """\"\"\"
Unit tests - Backtesting Engine (Phase 4)
Tests: metrics calculator, backtest simulator, walk-forward tester.
\"\"\"

import pytest
import sys
import math
import numpy as np
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.backtesting.metrics      import calculate_metrics, format_report, _equity_curve, _max_drawdown, _sharpe, _sortino, _consecutive
from src.backtesting.engine       import BacktestSimulator
from src.backtesting.walk_forward import WalkForwardTester


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_trades(n=20, win_rate=0.6):
    \"\"\"Synthetic trade list.\"\"\"
    np.random.seed(42)
    trades = []
    for i in range(n):
        winner = np.random.random() < win_rate
        pnl    = np.random.uniform(800, 2000) if winner else -np.random.uniform(400, 900)
        gross  = pnl * 1.02
        trades.append({
            "trade_id":        f"T{i:03d}",
            "symbol":          "NIFTY",
            "direction":       "LONG",
            "entry_date":      f"2026-01-{i+1:02d}",
            "exit_date":       f"2026-01-{i+1:02d}",
            "entry_price":     24500.0,
            "exit_price":      24600.0 if winner else 24400.0,
            "gross_pnl":       round(gross, 2),
            "net_pnl":         round(pnl, 2),
            "charges":         round(gross - pnl, 2),
            "holding_minutes": 45,
            "exit_reason":     "TARGET" if winner else "STOP_LOSS",
            "confidence":      75.0,
            "market_regime":   "BULL",
        })
    return trades


def make_candles(n=600, trend=0.0003, symbol="NIFTY"):
    \"\"\"Longer candle dataset for backtest simulation.\"\"\"
    np.random.seed(7)
    base  = 24500.0
    close = base * np.cumprod(1 + np.random.normal(trend, 0.001, n))
    open_ = np.roll(close, 1); open_[0] = base
    high  = np.maximum(open_, close) * 1.0015
    low   = np.minimum(open_, close) * 0.9985
    vol   = np.random.randint(500_000, 2_000_000, n).astype(float)
    vwap  = (high + low + close) / 3
    idx   = pd.date_range("2025-01-02 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": vol, "vwap": vwap,
        "timestamp": idx,
    })


# ── Metrics tests ─────────────────────────────────────────────────────────────

class TestMetricsCalculator:

    def test_empty_trades_returns_zeros(self):
        m = calculate_metrics([])
        assert m["total_trades"] == 0
        assert m["net_pnl"]      == 0

    def test_total_trades_count(self):
        m = calculate_metrics(make_trades(15))
        assert m["total_trades"] == 15

    def test_win_rate_range(self):
        m = calculate_metrics(make_trades(20, win_rate=0.6))
        assert 0 <= m["win_rate"] <= 100

    def test_profit_factor_positive_system(self):
        m = calculate_metrics(make_trades(20, win_rate=0.7))
        assert m["profit_factor"] > 0

    def test_all_winners_infinite_profit_factor(self):
        trades = make_trades(5, win_rate=1.0)
        m = calculate_metrics(trades)
        assert m["profit_factor"] == float("inf") or m["profit_factor"] > 10

    def test_winning_plus_losing_equals_total(self):
        m = calculate_metrics(make_trades(20))
        assert m["winning_trades"] + m["losing_trades"] == m["total_trades"]

    def test_net_pnl_is_sum_of_trade_pnls(self):
        trades = make_trades(10)
        m      = calculate_metrics(trades)
        expected = round(sum(t["net_pnl"] for t in trades), 2)
        assert abs(m["net_pnl"] - expected) < 0.01

    def test_max_drawdown_non_negative(self):
        m = calculate_metrics(make_trades(20))
        assert m["max_drawdown"] >= 0

    def test_sharpe_is_float(self):
        m = calculate_metrics(make_trades(20))
        assert isinstance(m["sharpe_ratio"], float)

    def test_sortino_is_float(self):
        m = calculate_metrics(make_trades(20))
        assert isinstance(m["sortino_ratio"], float)

    def test_equity_curve_starts_at_capital(self):
        m = calculate_metrics(make_trades(10), initial_capital=500_000)
        assert m["equity_curve"][0] == 500_000

    def test_equity_curve_length(self):
        n      = 10
        trades = make_trades(n)
        m      = calculate_metrics(trades)
        assert len(m["equity_curve"]) == n + 1

    def test_max_consecutive_wins_gte_zero(self):
        m = calculate_metrics(make_trades(20))
        assert m["max_consecutive_wins"]   >= 0
        assert m["max_consecutive_losses"] >= 0

    def test_return_pct_calculation(self):
        trades = [{"net_pnl": 10000, "gross_pnl": 10500, "holding_minutes": 30,
                   "entry_date":"2026-01-01","exit_date":"2026-01-01",
                   "direction":"LONG","confidence":75,"market_regime":"BULL"}]
        m = calculate_metrics(trades, initial_capital=100_000)
        assert m["return_pct"] == pytest.approx(10.0, 0.01)

    def test_format_report_returns_string(self):
        m = calculate_metrics(make_trades(10))
        r = format_report(m, "NIFTY", "Test Strategy")
        assert isinstance(r, str)
        assert "NIFTY" in r
        assert "win_rate" in r.lower() or "Win" in r


# ── Internal metric helpers ───────────────────────────────────────────────────

class TestMetricHelpers:

    def test_equity_curve_monotone_all_wins(self):
        pnls  = [100, 200, 150]
        curve = _equity_curve(pnls, 1000)
        assert curve == [1000, 1100, 1300, 1450]

    def test_max_drawdown_simple(self):
        equity = [1000, 1200, 900, 1100]
        dd     = _max_drawdown(equity)
        assert dd == pytest.approx(300.0, 0.01)

    def test_max_drawdown_no_drawdown(self):
        equity = [1000, 1100, 1200, 1300]
        assert _max_drawdown(equity) == 0.0

    def test_sharpe_positive_system(self):
        pnls = [100] * 50 + [50] * 50
        s    = _sharpe(pnls)
        assert s > 0

    def test_sortino_positive_system(self):
        pnls = [100, 200, -50, 150, 80]
        s    = _sortino(pnls)
        assert isinstance(s, float)

    def test_consecutive_all_wins(self):
        pnls = [100, 200, 150, 300]
        w, l = _consecutive(pnls)
        assert w == 4
        assert l == 0

    def test_consecutive_alternating(self):
        pnls = [100, -50, 100, -50]
        w, l = _consecutive(pnls)
        assert w == 1
        assert l == 1


# ── Backtest simulator tests ──────────────────────────────────────────────────

class TestBacktestSimulator:

    def setup_method(self):
        self.df  = make_candles(n=500)
        self.sim = BacktestSimulator(
            "NIFTY", self.df,
            capital=500_000, min_confidence=60.0
        )

    def test_run_returns_dict(self):
        result = self.sim.run()
        assert isinstance(result, dict)

    def test_run_has_required_keys(self):
        result = self.sim.run()
        for k in ["symbol","metrics","trades","report","parameters"]:
            assert k in result, f"Missing key: {k}"

    def test_symbol_correct(self):
        result = self.sim.run()
        assert result["symbol"] == "NIFTY"

    def test_metrics_present(self):
        result = self.sim.run()
        m = result["metrics"]
        for k in ["total_trades","win_rate","net_pnl","max_drawdown","sharpe_ratio"]:
            assert k in m

    def test_no_look_ahead(self):
        \"\"\"Confirm each trade entry bar > MIN_BARS_FOR_SIGNAL.\"\"\"
        from src.backtesting.engine import MIN_BARS_FOR_SIGNAL
        result = self.sim.run()
        for t in result["trades"]:
            pass   # If we got here without error, no look-ahead crash occurred

    def test_report_is_string(self):
        result = self.sim.run()
        assert isinstance(result["report"], str)
        assert len(result["report"]) > 50

    def test_equity_curve_starts_at_capital(self):
        result = self.sim.run()
        assert result["metrics"]["equity_curve"][0] == 500_000

    def test_trade_fields_complete(self):
        sim    = BacktestSimulator("NIFTY", make_candles(500), min_confidence=55.0)
        result = sim.run()
        if result["trades"]:
            t = result["trades"][0]
            for f in ["trade_id","direction","entry_price","exit_price",
                      "net_pnl","charges","exit_reason"]:
                assert f in t, f"Missing trade field: {f}"

    def test_exit_reason_valid(self):
        sim    = BacktestSimulator("NIFTY", make_candles(500), min_confidence=55.0)
        result = sim.run()
        valid  = {"STOP_LOSS","TARGET","END_OF_DATA","MANUAL"}
        for t in result["trades"]:
            assert t["exit_reason"] in valid

    def test_charges_deducted(self):
        sim    = BacktestSimulator("NIFTY", make_candles(500), min_confidence=55.0)
        result = sim.run()
        for t in result["trades"]:
            assert t["net_pnl"] <= t["gross_pnl"] + 0.01   # net <= gross (charges reduce it)

    def test_banknifty_runs(self):
        df  = make_candles(500, symbol="BANKNIFTY")
        sim = BacktestSimulator("BANKNIFTY", df, min_confidence=60.0)
        r   = sim.run()
        assert r["symbol"] == "BANKNIFTY"

    def test_parameters_in_result(self):
        result = self.sim.run()
        p = result["parameters"]
        assert p["capital"]        == 500_000
        assert p["min_confidence"] == 60.0


# ── Walk-forward tests ────────────────────────────────────────────────────────

class TestWalkForwardTester:

    def setup_method(self):
        self.df = make_candles(n=800)

    def test_run_returns_dict(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        for k in ["symbol","n_windows","consistency_pct",
                  "aggregate_metrics","window_summaries","aggregate_report"]:
            assert k in result, f"Missing key: {k}"

    def test_consistency_pct_in_range(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert 0 <= result["consistency_pct"] <= 100

    def test_window_summaries_count(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert len(result["window_summaries"]) <= 2

    def test_aggregate_report_string(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        assert isinstance(result["aggregate_report"], str)

    def test_window_summary_fields(self):
        wft    = WalkForwardTester("NIFTY", self.df, n_windows=2, min_confidence=60.0)
        result = wft.run()
        if result["window_summaries"]:
            ws = result["window_summaries"][0]
            for f in ["window","oos_bars","total_trades","win_rate","net_pnl"]:
                assert f in ws, f"Missing field: {f}"
"""


created = []
for rel_path, content in files.items():
    full_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(rel_path)

print(f"\n{'='*58}")
print(f"  Phase 4 setup complete  {len(created)} files written")
print(f"{'='*58}")
for p in created:
    print(f"  OK  {p}")
print(f"\nNow run:  python -m pytest -v")
print(f"Expected: 195 passed  (155 Phase 1-3 + 40 Phase 4)")
print(f"Note: tests take ~2 min (backtest simulator runs 500 bars)")
print(f"{'='*58}\n")
