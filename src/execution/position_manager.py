"""
Position Manager
Tracks all open paper positions, monitors SL/target,
applies trailing stops, and triggers exits.
"""

import logging
import datetime
import uuid
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class PositionManager:
    """
    Monitors open positions every time a new price arrives.
    Calls back into the broker to close positions when conditions are met.
    """

    def __init__(self, broker, risk_manager=None, alert_fn=None):
        self.broker       = broker
        self.risk_manager = risk_manager
        self.alert_fn     = alert_fn   # callable(event_type, message, data)
        self._positions   = {}         # trade_id → position config dict

    def register(
        self,
        trade_id:    str,
        symbol:      str,
        direction:   str,
        quantity:    int,
        entry_price: float,
        stop_loss:   float,
        target:      float,
        trail_after_r: float = 1.0,
        option_type: str    = "CE",
        strike:      float  = 0.0,
        expiry:      str    = "",
        confidence:  float  = 0.0,
    ):
        """Register a new open position for monitoring."""
        risk_per_unit  = abs(entry_price - stop_loss)
        self._positions[trade_id] = {
            "trade_id":      trade_id,
            "symbol":        symbol,
            "direction":     direction,
            "quantity":      quantity,
            "entry_price":   entry_price,
            "stop_loss":     stop_loss,
            "original_sl":   stop_loss,
            "target":        target,
            "risk_per_unit": risk_per_unit,
            "trail_after_r": trail_after_r,
            "be_applied":    False,    # break-even applied
            "option_type":   option_type,
            "strike":        strike,
            "expiry":        expiry,
            "confidence":    confidence,
            "opened_at":     datetime.datetime.now(IST).isoformat(),
        }
        log.info(
            f"[POSITION] Registered {direction} {quantity} {symbol} "
            f"| SL={stop_loss:.2f} TGT={target:.2f}"
        )

    def on_price_update(self, symbol: str, price: float) -> list[dict]:
        """
        Call this every bar/tick with the latest price.
        Returns list of exit events that occurred.
        """
        exits = []
        for tid, pos in list(self._positions.items()):
            if pos["symbol"] != symbol:
                continue

            self.broker.update_ltp(symbol, price)
            event = self._check_exit(tid, pos, price)
            if event:
                exits.append(event)

        return exits

    def modify_stop(self, trade_id: str, new_sl: float) -> bool:
        pos = self._positions.get(trade_id)
        if not pos:
            return False
        pos["stop_loss"] = round(new_sl, 2)
        log.info(f"[POSITION] SL modified for {trade_id} → {new_sl:.2f}")
        return True

    def get_position(self, trade_id: str) -> Optional[dict]:
        return self._positions.get(trade_id)

    def get_all_positions(self) -> list[dict]:
        return list(self._positions.values())

    def get_count(self) -> int:
        return len(self._positions)

    def force_close_all(self, reason: str = "EOD"):
        """Close all open positions — used at end of day."""
        for tid in list(self._positions.keys()):
            pos   = self._positions[tid]
            price = self.broker.get_ltp(pos["symbol"]) or pos["entry_price"]
            self._exit(tid, pos, price, reason)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _check_exit(self, trade_id: str, pos: dict, price: float) -> Optional[dict]:
        direction  = pos["direction"]
        sl         = pos["stop_loss"]
        target     = pos["target"]
        entry      = pos["entry_price"]
        risk       = pos["risk_per_unit"]
        trail_r    = pos["trail_after_r"]

        # Apply trailing break-even
        if not pos["be_applied"] and risk > 0:
            gain = (price - entry) if direction == "LONG" else (entry - price)
            if gain >= risk * trail_r:
                new_sl = entry   # break-even
                if direction == "LONG":
                    new_sl = max(sl, entry)
                else:
                    new_sl = min(sl, entry)
                pos["stop_loss"]  = round(new_sl, 2)
                pos["be_applied"] = True
                log.info(f"[TRAIL] Break-even applied for {trade_id} SL → {new_sl:.2f}")
                if self.alert_fn:
                    self.alert_fn("STOP_MODIFIED", f"Break-even SL applied: {pos['symbol']}", pos)

        # Check exits
        if direction == "LONG":
            if price <= pos["stop_loss"]:
                return self._exit(trade_id, pos, pos["stop_loss"], "STOP_LOSS")
            if price >= target:
                return self._exit(trade_id, pos, target, "TARGET")
        else:
            if price >= pos["stop_loss"]:
                return self._exit(trade_id, pos, pos["stop_loss"], "STOP_LOSS")
            if price <= target:
                return self._exit(trade_id, pos, target, "TARGET")

        return None

    def _exit(self, trade_id: str, pos: dict, exit_price: float, reason: str) -> dict:
        record = self.broker.close_position(trade_id, exit_price, reason)
        self._positions.pop(trade_id, None)

        if self.risk_manager:
            pnl = record["net_pnl"] if record else 0
            self.risk_manager.on_trade_closed(pnl)

        if self.alert_fn and record:
            self.alert_fn(reason, f"{pos['symbol']} {reason}", record)

        return record or {}
