"""
Risk Management Engine
"""

import logging
import datetime
from dataclasses import dataclass, field
from typing import Optional
from src.monitoring.logger import log_event, Event

log = logging.getLogger(__name__)


@dataclass
class RiskState:
    daily_pnl:           float = 0.0
    weekly_pnl:          float = 0.0
    trades_today:        int   = 0
    consecutive_losses:  int   = 0
    open_positions:      int   = 0
    is_trading_halted:   bool  = False
    halt_reason:         str   = ""
    data_last_received:  Optional[datetime.datetime] = None
    broker_connected:    bool  = False


@dataclass
class RiskValidationResult:
    approved:     bool
    reason:       str
    adjusted_qty: Optional[int] = None
    warnings:     list = field(default_factory=list)


class RiskManager:
    def __init__(self, config, capital):
        self.cfg     = config.get("risk", {})
        self.capital = capital
        self.state   = RiskState()
        self.max_risk_pct      = self.cfg.get("max_risk_per_trade", 0.005)
        self.max_daily_loss    = self.cfg.get("max_daily_loss", 0.02)
        self.max_weekly_loss   = self.cfg.get("max_weekly_loss", 0.05)
        self.max_trades_day    = self.cfg.get("max_trades_per_day", 10)
        self.max_consec_losses = self.cfg.get("max_consecutive_losses", 3)
        self.max_positions     = self.cfg.get("max_open_positions", 3)
        self.min_rr            = self.cfg.get("min_risk_reward", 1.5)
        self.min_confidence    = self.cfg.get("min_confidence", 70)
        self.stale_threshold   = 120

    def validate_signal(self, signal):
        warnings = []
        if self.state.is_trading_halted:
            return self._reject(f"Trading halted: {self.state.halt_reason}")
        daily_loss_pct = abs(self.state.daily_pnl) / self.capital
        if self.state.daily_pnl < 0 and daily_loss_pct >= self.max_daily_loss:
            self._halt(f"Daily loss limit hit ({daily_loss_pct*100:.1f}%)")
            return self._reject(f"Daily loss limit reached: {self.state.daily_pnl:,.0f}")
        weekly_loss_pct = abs(self.state.weekly_pnl) / self.capital
        if self.state.weekly_pnl < 0 and weekly_loss_pct >= self.max_weekly_loss:
            return self._reject(f"Weekly loss limit reached")
        if self.state.trades_today >= self.max_trades_day:
            return self._reject(f"Max trades per day reached ({self.state.trades_today})")
        if self.state.consecutive_losses >= self.max_consec_losses:
            self._halt(f"Consecutive losses: {self.state.consecutive_losses}")
            return self._reject(f"Consecutive loss limit reached ({self.state.consecutive_losses})")
        if self.state.open_positions >= self.max_positions:
            return self._reject(f"Max open positions reached ({self.state.open_positions})")
        if not self._check_data_freshness():
            return self._reject("Market data is stale - not safe to trade")
        if not self.state.broker_connected:
            return self._reject("Broker not connected")
        confidence = signal.get("confidence", 0)
        if confidence < self.min_confidence:
            return self._reject(f"Confidence {confidence} below minimum {self.min_confidence}")
        rr = signal.get("risk_reward", 0)
        if rr < self.min_rr:
            return self._reject(f"R:R {rr:.2f} below minimum {self.min_rr}")
        for f in ("entry", "stop_loss", "target"):
            if not signal.get(f):
                return self._reject(f"Missing field: {f}")
        log_event(log, Event.RISK_VALIDATION, "Signal approved",
                  confidence=confidence, rr=rr)
        return RiskValidationResult(approved=True, reason="All checks passed", warnings=warnings)

    def calculate_position_size(self, entry, stop_loss, lot_size):
        risk_amount   = self.capital * self.max_risk_pct
        risk_per_unit = abs(entry - stop_loss)
        if risk_per_unit <= 0:
            return {"lots": 0, "quantity": 0, "error": "SL equals entry"}
        raw_qty  = risk_amount / risk_per_unit
        lots     = max(1, int(raw_qty / lot_size))
        quantity = lots * lot_size
        actual_risk = quantity * risk_per_unit
        return {
            "lots":        lots,
            "quantity":    quantity,
            "risk_amount": round(actual_risk, 2),
            "risk_pct":    round(actual_risk / self.capital * 100, 3),
        }

    def on_trade_opened(self):
        self.state.trades_today   += 1
        self.state.open_positions += 1

    def on_trade_closed(self, pnl):
        self.state.open_positions = max(0, self.state.open_positions - 1)
        self.state.daily_pnl     += pnl
        self.state.weekly_pnl    += pnl
        if pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

    def on_data_received(self):
        self.state.data_last_received = datetime.datetime.now()

    def set_broker_connected(self, connected):
        self.state.broker_connected = connected

    def reset_daily(self):
        self.state.daily_pnl    = 0.0
        self.state.trades_today = 0
        if "daily loss" in self.state.halt_reason.lower():
            self.state.is_trading_halted = False
            self.state.halt_reason = ""

    def get_state_summary(self):
        return {
            "daily_pnl":          self.state.daily_pnl,
            "weekly_pnl":         self.state.weekly_pnl,
            "trades_today":       self.state.trades_today,
            "consecutive_losses": self.state.consecutive_losses,
            "open_positions":     self.state.open_positions,
            "is_halted":          self.state.is_trading_halted,
            "halt_reason":        self.state.halt_reason,
            "broker_connected":   self.state.broker_connected,
        }

    def _reject(self, reason):
        log_event(log, Event.RISK_BREACH, reason, level="warning")
        return RiskValidationResult(approved=False, reason=reason)

    def _halt(self, reason):
        self.state.is_trading_halted = True
        self.state.halt_reason = reason
        log_event(log, Event.RISK_BREACH, f"TRADING HALTED: {reason}", level="error")

    def _check_data_freshness(self):
        if self.state.data_last_received is None:
            return False
        age = (datetime.datetime.now() - self.state.data_last_received).total_seconds()
        if age > self.stale_threshold:
            return False
        return True
