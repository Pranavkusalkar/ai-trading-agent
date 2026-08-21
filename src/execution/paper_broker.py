"""
Paper Broker (Spec section 26)
Simulates order execution without sending real orders.
Tracks virtual positions, P&L, and order history in memory.
Used during TRADING_MODE=paper.
"""

import logging
import uuid
import datetime
from dataclasses import dataclass, field
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


@dataclass
class PaperOrder:
    order_id:    str
    symbol:      str
    direction:   str       # BUY / SELL
    quantity:    int
    order_type:  str       # MARKET / LIMIT / SL
    price:       float
    trigger_price: float
    status:      str       # PENDING / FILLED / CANCELLED / REJECTED
    filled_price: float    = 0.0
    filled_qty:  int       = 0
    timestamp:   str       = ""
    product:     str       = "MIS"


@dataclass
class PaperPosition:
    trade_id:      str
    symbol:        str
    direction:     str
    quantity:      int
    entry_price:   float
    current_price: float
    stop_loss:     float
    target:        float
    entry_time:    str
    option_type:   str       = "CE"
    strike:        float     = 0.0
    expiry:        str       = ""
    unrealised_pnl: float    = 0.0
    status:        str       = "OPEN"


class PaperBroker:
    """
    Simulates a broker for paper trading.
    All orders are filled at the current market price with configurable slippage.
    """

    def __init__(
        self,
        initial_capital: float = 500_000,
        slippage_pct:    float = 0.001,
    ):
        self.capital          = initial_capital
        self.available_margin = initial_capital
        self.used_margin      = 0.0
        self.slippage_pct     = slippage_pct
        self._ltp:    dict[str, float]   = {}
        self._orders: list[PaperOrder]   = []
        self._positions: dict[str, PaperPosition] = {}
        self._closed_trades: list[dict]  = []
        self._connected       = True
        self.session_pnl      = 0.0

        log.info(f"PaperBroker ready | capital=₹{initial_capital:,.0f}")

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        self._connected = True
        log.info("PaperBroker connected")
        return True

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self):
        self._connected = False

    # ── Price feed ────────────────────────────────────────────────────────────

    def update_ltp(self, symbol: str, price: float):
        """Called by the data engine every tick/bar to keep prices fresh."""
        self._ltp[symbol] = price
        self._update_unrealised_pnl(symbol, price)

    def get_ltp(self, symbol: str) -> Optional[float]:
        return self._ltp.get(symbol)

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol:        str,
        direction:     str,
        quantity:      int,
        order_type:    str   = "MARKET",
        price:         float = 0.0,
        trigger_price: float = 0.0,
        product:       str   = "MIS",
        tag:           str   = "",
    ) -> PaperOrder:
        """Place a paper order. Market orders fill immediately at LTP ± slippage."""
        oid = str(uuid.uuid4())[:8]
        ltp = self._ltp.get(symbol, price or 0)

        if order_type == "MARKET":
            fill_price = ltp * (1 + self.slippage_pct) if direction == "BUY" \
                         else ltp * (1 - self.slippage_pct)
            fill_price = round(fill_price, 2)
            status     = "FILLED"
        else:
            fill_price = 0.0
            status     = "PENDING"

        order = PaperOrder(
            order_id      = oid,
            symbol        = symbol,
            direction     = direction,
            quantity      = quantity,
            order_type    = order_type,
            price         = price,
            trigger_price = trigger_price,
            status        = status,
            filled_price  = fill_price,
            filled_qty    = quantity if status == "FILLED" else 0,
            timestamp     = datetime.datetime.now(IST).isoformat(),
            product       = product,
        )
        self._orders.append(order)

        if status == "FILLED":
            cost = fill_price * quantity
            if direction == "BUY":
                self.available_margin -= cost
                self.used_margin      += cost
            log.info(
                f"[PAPER ORDER] {direction} {quantity} {symbol} "
                f"@ ₹{fill_price:.2f} | id={oid}"
            )

        return order

    def cancel_order(self, order_id: str) -> bool:
        for o in self._orders:
            if o.order_id == order_id and o.status == "PENDING":
                o.status = "CANCELLED"
                return True
        return False

    # ── Positions ─────────────────────────────────────────────────────────────

    def open_position(
        self,
        trade_id:    str,
        symbol:      str,
        direction:   str,
        quantity:    int,
        entry_price: float,
        stop_loss:   float,
        target:      float,
        option_type: str   = "CE",
        strike:      float = 0.0,
        expiry:      str   = "",
    ) -> PaperPosition:
        pos = PaperPosition(
            trade_id      = trade_id,
            symbol        = symbol,
            direction     = direction,
            quantity      = quantity,
            entry_price   = round(entry_price, 2),
            current_price = round(entry_price, 2),
            stop_loss     = round(stop_loss, 2),
            target        = round(target, 2),
            entry_time    = datetime.datetime.now(IST).isoformat(),
            option_type   = option_type,
            strike        = strike,
            expiry        = expiry,
        )
        self._positions[trade_id] = pos
        log.info(
            f"[PAPER POSITION] OPEN {direction} {quantity} {symbol} "
            f"@ ₹{entry_price:.2f} | SL={stop_loss:.2f} TGT={target:.2f}"
        )
        return pos

    def close_position(
        self,
        trade_id:   str,
        exit_price: float,
        reason:     str = "MANUAL",
    ) -> Optional[dict]:
        pos = self._positions.pop(trade_id, None)
        if not pos:
            return None

        exit_px = round(exit_price * (1 - self.slippage_pct)
                        if pos.direction == "LONG"
                        else exit_price * (1 + self.slippage_pct), 2)

        if pos.direction in ("LONG", "BUY"):
            gross_pnl = (exit_px - pos.entry_price) * pos.quantity
        else:
            gross_pnl = (pos.entry_price - exit_px) * pos.quantity

        # Approximate charges
        charges   = pos.entry_price * pos.quantity * 0.002   # ~0.2% round trip
        net_pnl   = round(gross_pnl - charges, 2)

        self.session_pnl      += net_pnl
        self.available_margin += pos.entry_price * pos.quantity + net_pnl
        self.used_margin       = max(0, self.used_margin - pos.entry_price * pos.quantity)

        trade_record = {
            "trade_id":     trade_id,
            "symbol":       pos.symbol,
            "direction":    pos.direction,
            "quantity":     pos.quantity,
            "entry_price":  pos.entry_price,
            "exit_price":   exit_px,
            "entry_time":   pos.entry_time,
            "exit_time":    datetime.datetime.now(IST).isoformat(),
            "gross_pnl":    round(gross_pnl, 2),
            "charges":      round(charges,   2),
            "net_pnl":      net_pnl,
            "exit_reason":  reason,
            "option_type":  pos.option_type,
            "strike":       pos.strike,
        }
        self._closed_trades.append(trade_record)

        log.info(
            f"[PAPER POSITION] CLOSE {pos.direction} {pos.symbol} "
            f"@ ₹{exit_px:.2f} | {reason} | net_pnl=₹{net_pnl:+,.0f}"
        )
        return trade_record

    def get_positions(self) -> list[PaperPosition]:
        return list(self._positions.values())

    def get_closed_trades(self) -> list[dict]:
        return self._closed_trades

    def get_balance(self) -> dict:
        total_unrealised = sum(
            p.unrealised_pnl for p in self._positions.values()
        )
        return {
            "capital":          self.capital,
            "available_margin": round(self.available_margin, 2),
            "used_margin":      round(self.used_margin, 2),
            "session_pnl":      round(self.session_pnl, 2),
            "unrealised_pnl":   round(total_unrealised, 2),
            "open_positions":   len(self._positions),
        }

    def get_session_summary(self) -> dict:
        closed = self._closed_trades
        if not closed:
            return {"trades": 0, "session_pnl": 0, "win_rate": 0}
        winners  = [t for t in closed if t["net_pnl"] > 0]
        return {
            "trades":       len(closed),
            "winners":      len(winners),
            "losers":       len(closed) - len(winners),
            "win_rate":     round(len(winners) / len(closed) * 100, 1),
            "session_pnl":  round(self.session_pnl, 2),
            "gross_pnl":    round(sum(t["gross_pnl"] for t in closed), 2),
            "charges":      round(sum(t["charges"]   for t in closed), 2),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _update_unrealised_pnl(self, symbol: str, price: float):
        for pos in self._positions.values():
            if pos.symbol == symbol:
                if pos.direction in ("LONG", "BUY"):
                    pos.unrealised_pnl = round(
                        (price - pos.entry_price) * pos.quantity, 2
                    )
                else:
                    pos.unrealised_pnl = round(
                        (pos.entry_price - price) * pos.quantity, 2
                    )
                pos.current_price = price
