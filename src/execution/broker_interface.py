"""
Broker Abstraction Layer
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import logging

log = logging.getLogger(__name__)


@dataclass
class OrderRequest:
    symbol:        str
    exchange:      str
    order_type:    str
    direction:     str
    quantity:      int
    price:         float = 0.0
    trigger_price: float = 0.0
    product:       str = "MIS"
    validity:      str = "DAY"
    tag:           str = ""


@dataclass
class OrderResponse:
    success:         bool
    order_id:        str = ""
    broker_order_id: str = ""
    status:          str = ""
    message:         str = ""
    filled_price:    float = 0.0
    filled_qty:      int = 0


@dataclass
class Position:
    symbol:        str
    direction:     str
    quantity:      int
    average_price: float
    ltp:           float
    pnl:           float
    product:       str


class BrokerInterface(ABC):
    @abstractmethod
    def connect(self): pass
    @abstractmethod
    def disconnect(self): pass
    @abstractmethod
    def is_connected(self): pass
    @abstractmethod
    def get_ltp(self, symbol, exchange): pass
    @abstractmethod
    def get_positions(self): pass
    @abstractmethod
    def get_orders(self): pass
    @abstractmethod
    def get_balance(self): pass
    @abstractmethod
    def place_order(self, order): pass
    @abstractmethod
    def modify_order(self, broker_order_id, price, trigger_price=0.0, quantity=0): pass
    @abstractmethod
    def cancel_order(self, broker_order_id): pass
    @abstractmethod
    def close_position(self, symbol, exchange, quantity, direction): pass
    @abstractmethod
    def get_option_chain(self, symbol, expiry): pass
    @abstractmethod
    def get_historical_candles(self, symbol, exchange, timeframe, from_date, to_date): pass


class PaperBroker(BrokerInterface):
    def __init__(self, initial_capital=500000):
        self.capital    = initial_capital
        self.positions  = {}
        self.orders     = []
        self._connected = True
        self._ltp_cache = {}
        log.info(f"PaperBroker initialised | capital={initial_capital:,.0f}")

    def connect(self):
        self._connected = True
        return True
    def disconnect(self):
        self._connected = False
    def is_connected(self):
        return self._connected
    def get_ltp(self, symbol, exchange):
        return self._ltp_cache.get(symbol)
    def update_ltp(self, symbol, price):
        self._ltp_cache[symbol] = price
    def get_positions(self):
        return list(self.positions.values())
    def get_orders(self):
        return self.orders
    def get_balance(self):
        return {"capital": self.capital, "available_margin": self.capital, "used_margin": 0}

    def place_order(self, order):
        import uuid
        oid = str(uuid.uuid4())[:8]
        fill_price = self._ltp_cache.get(order.symbol, order.price or 0)
        self.orders.append({"order_id": oid, "symbol": order.symbol,
                            "direction": order.direction, "quantity": order.quantity,
                            "price": fill_price, "status": "FILLED"})
        return OrderResponse(success=True, order_id=oid, broker_order_id=oid,
                             status="FILLED", filled_price=fill_price, filled_qty=order.quantity)

    def modify_order(self, broker_order_id, price, trigger_price=0.0, quantity=0):
        return OrderResponse(success=True, order_id=broker_order_id, status="MODIFIED")
    def cancel_order(self, broker_order_id):
        return OrderResponse(success=True, order_id=broker_order_id, status="CANCELLED")
    def close_position(self, symbol, exchange, quantity, direction):
        close_dir = "SELL" if direction == "BUY" else "BUY"
        return self.place_order(OrderRequest(symbol=symbol, exchange=exchange,
                                             order_type="MARKET", direction=close_dir, quantity=quantity))
    def get_option_chain(self, symbol, expiry): return []
    def get_historical_candles(self, symbol, exchange, timeframe, from_date, to_date): return []


class BrokerFactory:
    @staticmethod
    def create(broker_name, config, capital):
        name = broker_name.lower()
        if name == "paper":
            return PaperBroker(initial_capital=capital)
        raise ValueError(f"Unknown broker: {broker_name}")
