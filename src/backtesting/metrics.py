"""
Backtest Metrics (Spec section 24)
Calculates all 25 required metrics from a list of trade dicts.
Each trade dict must contain: net_pnl, gross_pnl, entry_date, exit_date,
direction, confidence, holding_minutes.
"""

import math
import datetime
from typing import Optional


def calculate_metrics(trades: list[dict], initial_capital: float = 500_000) -> dict:
    """
    Compute all 25 spec metrics from a trades list.

    Parameters
    ----------
    trades          : list of trade dicts from BacktestSimulator
    initial_capital : starting capital for drawdown and return calculations

    Returns
    -------
    Full metrics dict matching spec section 24.
    """
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
    """Print-friendly backtest summary."""
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
    return "\n".join(l for l in lines if l)
