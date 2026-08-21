"""
Dashboard Data Provider
Aggregates all live system state into clean dicts
that the Streamlit UI reads every refresh cycle.
Keeps the dashboard code clean — no business logic in the UI layer.
"""

import datetime
import logging
import json
import os
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class DashboardDataProvider:
    """
    Single source of truth for the dashboard.
    Reads from the live engine components if running,
    or from session log files if the engine is stopped.
    """

    def __init__(
        self,
        broker          = None,
        position_mgr    = None,
        order_mgr       = None,
        signal_engine   = None,
        risk_manager    = None,
        log_dir:  str   = "logs",
        data_provider   = None,
    ):
        self.broker       = broker
        self.pos_mgr      = position_mgr
        self.order_mgr    = order_mgr
        self.sig_engine   = signal_engine
        self.risk_mgr     = risk_manager
        self.log_dir      = log_dir
        self.data_prov    = data_provider
        self._signal_history: list[dict] = []
        self._last_signals:   dict[str, dict] = {}

    # ── Account ───────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        if self.broker and self.broker.is_connected():
            try:
                return self.broker.get_balance()
            except Exception:
                pass
        return {
            "capital":          500_000,
            "available_margin": 500_000,
            "used_margin":      0,
            "session_pnl":      0,
            "unrealised_pnl":   0,
            "open_positions":   0,
        }

    # ── Positions ─────────────────────────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        if self.pos_mgr:
            return self.pos_mgr.get_all_positions()
        if self.broker and self.broker.is_connected():
            try:
                return self.broker.get_positions()
            except Exception:
                pass
        return []

    def get_closed_trades(self) -> list[dict]:
        if self.broker and hasattr(self.broker, "get_closed_trades"):
            return self.broker.get_closed_trades()
        return []

    # ── Orders ────────────────────────────────────────────────────────────────

    def get_orders(self) -> list[dict]:
        if self.order_mgr:
            return [
                {
                    "order_id":    o.order_id,
                    "symbol":      o.symbol,
                    "direction":   o.direction,
                    "quantity":    o.quantity,
                    "state":       o.state,
                    "filled_price":o.filled_price,
                    "timestamp":   o.created_at,
                }
                for o in self.order_mgr.get_all_orders()
            ]
        return []

    # ── Signals ───────────────────────────────────────────────────────────────

    def record_signal(self, signal: dict):
        signal["recorded_at"] = datetime.datetime.now(IST).isoformat()
        self._signal_history.append(signal)
        sym = signal.get("underlying", "UNKNOWN")
        self._last_signals[sym] = signal
        # Keep last 100
        if len(self._signal_history) > 100:
            self._signal_history = self._signal_history[-100:]

    def get_last_signal(self, symbol: str) -> Optional[dict]:
        return self._last_signals.get(symbol)

    def get_signal_history(self, limit: int = 20) -> list[dict]:
        return self._signal_history[-limit:]

    # ── Risk ──────────────────────────────────────────────────────────────────

    def get_risk_state(self) -> dict:
        if self.risk_mgr:
            return self.risk_mgr.get_state_summary()
        return {
            "daily_pnl":          0,
            "trades_today":       0,
            "consecutive_losses": 0,
            "open_positions":     0,
            "is_halted":          False,
            "halt_reason":        "",
            "broker_connected":   self.broker.is_connected() if self.broker else False,
        }

    # ── Performance ───────────────────────────────────────────────────────────

    def get_session_summary(self) -> dict:
        if self.broker and hasattr(self.broker, "get_session_summary"):
            return self.broker.get_session_summary()
        return {"trades": 0, "win_rate": 0, "session_pnl": 0}

    def get_equity_curve(self) -> list[float]:
        """Returns equity curve from closed trades."""
        trades  = self.get_closed_trades()
        capital = 500_000.0
        curve   = [capital]
        for t in trades:
            capital += t.get("net_pnl", 0)
            curve.append(round(capital, 2))
        return curve

    # ── System health ─────────────────────────────────────────────────────────

    def get_system_status(self) -> dict:
        now = datetime.datetime.now(IST)
        return {
            "timestamp":       now.isoformat(),
            "time_ist":        now.strftime("%H:%M:%S"),
            "broker_connected":self.broker.is_connected() if self.broker else False,
            "trading_mode":    os.getenv("TRADING_MODE", "paper").upper(),
            "live_enabled":    os.getenv("ENABLE_LIVE_TRADING", "false") == "true",
            "market_open":     self._is_market_open(now),
            "session_active":  True,
        }

    # ── Session log loader (for offline review) ───────────────────────────────

    def load_latest_session_log(self) -> Optional[dict]:
        """Load the most recent paper session JSON log."""
        try:
            logs = sorted([
                f for f in os.listdir(self.log_dir)
                if f.startswith("paper_session") and f.endswith(".json")
            ])
            if not logs:
                return None
            with open(os.path.join(self.log_dir, logs[-1])) as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def _is_market_open(dt: datetime.datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        t = dt.time()
        return datetime.time(9, 15) <= t < datetime.time(15, 30)
