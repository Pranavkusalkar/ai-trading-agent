"""
Order Manager (Spec section 27)
Manages the full order lifecycle:
CREATED → PENDING → FILLED → COMPLETED
              ↓         ↓
          CANCELLED  REJECTED

Sits between the signal engine and the broker.
Risk Manager validates before any order reaches here.
"""

import logging
import uuid
import datetime
from dataclasses import dataclass, field
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class OrderState:
    CREATED          = "CREATED"
    PENDING          = "PENDING"
    OPEN             = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED           = "FILLED"
    MODIFIED         = "MODIFIED"
    CANCELLED        = "CANCELLED"
    REJECTED         = "REJECTED"
    COMPLETED        = "COMPLETED"


@dataclass
class ManagedOrder:
    order_id:      str
    trade_id:      str
    symbol:        str
    direction:     str
    quantity:      int
    order_type:    str
    price:         float
    trigger_price: float
    state:         str = OrderState.CREATED
    filled_price:  float = 0.0
    filled_qty:    int   = 0
    broker_order_id: str = ""
    reject_reason:   str = ""
    created_at:    str   = ""
    updated_at:    str   = ""
    tag:           str   = ""


class OrderManager:
    """
    Manages all orders for a trading session.
    Validates state transitions and maintains a complete audit trail.
    """

    # Valid state transitions
    TRANSITIONS = {
        OrderState.CREATED:          {OrderState.PENDING, OrderState.REJECTED},
        OrderState.PENDING:          {OrderState.OPEN, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED},
        OrderState.OPEN:             {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.MODIFIED},
        OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCELLED},
        OrderState.FILLED:           {OrderState.COMPLETED},
        OrderState.MODIFIED:         {OrderState.OPEN, OrderState.CANCELLED},
        OrderState.CANCELLED:        set(),
        OrderState.REJECTED:         set(),
        OrderState.COMPLETED:        set(),
    }

    def __init__(self, broker):
        self._broker  = broker
        self._orders: dict[str, ManagedOrder] = {}
        self._trade_orders: dict[str, list[str]] = {}   # trade_id → [order_ids]

    def submit(
        self,
        trade_id:      str,
        symbol:        str,
        direction:     str,
        quantity:      int,
        order_type:    str   = "MARKET",
        price:         float = 0.0,
        trigger_price: float = 0.0,
        tag:           str   = "",
    ) -> ManagedOrder:
        """Create and submit an order through the broker."""
        oid   = str(uuid.uuid4())[:8]
        now   = datetime.datetime.now(IST).isoformat()
        order = ManagedOrder(
            order_id      = oid,
            trade_id      = trade_id,
            symbol        = symbol,
            direction     = direction,
            quantity      = quantity,
            order_type    = order_type,
            price         = price,
            trigger_price = trigger_price,
            state         = OrderState.CREATED,
            created_at    = now,
            updated_at    = now,
            tag           = tag,
        )
        self._orders[oid] = order
        self._trade_orders.setdefault(trade_id, []).append(oid)

        # Submit to broker
        try:
            broker_order = self._broker.place_order(
                symbol        = symbol,
                direction     = direction,
                quantity      = quantity,
                order_type    = order_type,
                price         = price,
                trigger_price = trigger_price,
                tag           = tag,
            )
            order.broker_order_id = broker_order.order_id
            order.filled_price    = broker_order.filled_price
            order.filled_qty      = broker_order.filled_qty

                # CREATED → PENDING → FILLED (two hops needed)
            self._transition(order, OrderState.PENDING)
            if broker_order.status == "FILLED":
                self._transition(order, OrderState.FILLED)

        except Exception as e:
            log.error(f"Order submission failed: {e}")
            self._transition(order, OrderState.REJECTED)
            order.reject_reason = str(e)

        log.info(
            f"[ORDER] {direction} {quantity} {symbol} | "
            f"id={oid} state={order.state} fill=₹{order.filled_price:.2f}"
        )
        return order

    def cancel(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False
        if order.state in (OrderState.PENDING, OrderState.OPEN):
            success = self._broker.cancel_order(order.broker_order_id)
            if success:
                self._transition(order, OrderState.CANCELLED)
            return success
        return False

    def complete(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.state == OrderState.FILLED:
            self._transition(order, OrderState.COMPLETED)
            return True
        return False

    def get_order(self, order_id: str) -> Optional[ManagedOrder]:
        return self._orders.get(order_id)

    def get_trade_orders(self, trade_id: str) -> list[ManagedOrder]:
        ids = self._trade_orders.get(trade_id, [])
        return [self._orders[i] for i in ids if i in self._orders]

    def get_all_orders(self) -> list[ManagedOrder]:
        return list(self._orders.values())

    def get_open_orders(self) -> list[ManagedOrder]:
        return [o for o in self._orders.values()
                if o.state in (OrderState.PENDING, OrderState.OPEN)]

    def session_summary(self) -> dict:
        orders = list(self._orders.values())
        return {
            "total":     len(orders),
            "filled":    sum(1 for o in orders if o.state == OrderState.FILLED),
            "pending":   sum(1 for o in orders if o.state == OrderState.PENDING),
            "cancelled": sum(1 for o in orders if o.state == OrderState.CANCELLED),
            "rejected":  sum(1 for o in orders if o.state == OrderState.REJECTED),
        }

    def _transition(self, order: ManagedOrder, new_state: str):
        valid = self.TRANSITIONS.get(order.state, set())
        if new_state not in valid:
            log.warning(
                f"Invalid state transition {order.state} → {new_state} "
                f"for order {order.order_id}"
            )
            return
        order.state      = new_state
        order.updated_at = datetime.datetime.now(IST).isoformat()
