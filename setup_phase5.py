"""
AI Trading Agent - Phase 5 Setup Script
Adds paper trading engine, order manager, position manager, and alerts.

Usage (from C:\trading\ai_trading_agent with venv active):
    python setup_phase5.py
    python -m pytest -v

Expected: 196 passed (155 Phase 1-3 + 40 Phase 4 + 41 Phase 5)
Note: Phase 4 tests take ~2 min. Total run ~2-3 min.
Prerequisites: all previous setup scripts already run.
"""

import os

ROOT  = os.path.dirname(os.path.abspath(__file__))
files = {}

files["src/execution/__init__.py"] = """"""

files["src/monitoring/__init__.py"] = """"""

files["src/execution/paper_broker.py"] = """\"\"\"
Paper Broker (Spec section 26)
Simulates order execution without sending real orders.
Tracks virtual positions, P&L, and order history in memory.
Used during TRADING_MODE=paper.
\"\"\"

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
    \"\"\"
    Simulates a broker for paper trading.
    All orders are filled at the current market price with configurable slippage.
    \"\"\"

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
        \"\"\"Called by the data engine every tick/bar to keep prices fresh.\"\"\"
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
        \"\"\"Place a paper order. Market orders fill immediately at LTP ± slippage.\"\"\"
        oid = str(uuid.uuid4())[:8]
        ltp = self._ltp.get(symbol, price or 0)

        if order_type == "MARKET":
            fill_price = ltp * (1 + self.slippage_pct) if direction == "BUY" \\
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
"""

files["src/execution/order_manager.py"] = """\"\"\"
Order Manager (Spec section 27)
Manages the full order lifecycle:
CREATED → PENDING → FILLED → COMPLETED
              ↓         ↓
          CANCELLED  REJECTED

Sits between the signal engine and the broker.
Risk Manager validates before any order reaches here.
\"\"\"

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
    \"\"\"
    Manages all orders for a trading session.
    Validates state transitions and maintains a complete audit trail.
    \"\"\"

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
        \"\"\"Create and submit an order through the broker.\"\"\"
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
"""

files["src/execution/position_manager.py"] = """\"\"\"
Position Manager
Tracks all open paper positions, monitors SL/target,
applies trailing stops, and triggers exits.
\"\"\"

import logging
import datetime
import uuid
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class PositionManager:
    \"\"\"
    Monitors open positions every time a new price arrives.
    Calls back into the broker to close positions when conditions are met.
    \"\"\"

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
        \"\"\"Register a new open position for monitoring.\"\"\"
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
        \"\"\"
        Call this every bar/tick with the latest price.
        Returns list of exit events that occurred.
        \"\"\"
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
        \"\"\"Close all open positions — used at end of day.\"\"\"
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
"""

files["src/execution/paper_engine.py"] = """\"\"\"
Paper Trading Engine (Spec section 26)
Runs the full signal pipeline on live/mock market data,
simulates execution, monitors positions, and logs everything.
No real orders are sent.

Usage:
    engine = PaperTradingEngine(symbols=["NIFTY","BANKNIFTY"])
    engine.run_session()     # blocking — runs until market close
    # or for testing:
    engine.run_bars(n=10)    # process n bars then stop
\"\"\"

import logging
import time
import datetime
import uuid
import json
import os
from typing import Optional
import pytz

from src.data.market_data         import create_data_provider
from src.data.futures_data        import FuturesDataAgent
from src.data.options_chain       import OptionsChainAgent
from src.indicators.technical     import compute_all
from src.indicators.volume        import compute_volume
from src.strategies.signal_engine import SignalEngine
from src.execution.paper_broker   import PaperBroker
from src.execution.order_manager  import OrderManager
from src.execution.position_manager import PositionManager
from src.monitoring.alerts        import AlertSystem

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN  = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)


class PaperTradingEngine:
    \"\"\"
    Full paper trading session manager.
    Fetches data → generates signals → validates → executes paper orders →
    monitors positions → logs results → sends alerts.
    \"\"\"

    def __init__(
        self,
        symbols:         list[str]    = None,
        capital:         float        = 500_000,
        min_confidence:  float        = 70.0,
        max_positions:   int          = 3,
        risk_pct:        float        = 0.005,
        refresh_seconds: int          = 300,    # 5 min between signal checks
        candle_count:    int          = 250,
        timeframe:       str          = "5min",
        log_dir:         str          = "logs",
        data_mode:       str          = "mock",
        telegram_token:  Optional[str]= None,
        telegram_chat_id:Optional[str]= None,
    ):
        self.symbols          = symbols or ["NIFTY", "BANKNIFTY"]
        self.capital          = capital
        self.min_confidence   = min_confidence
        self.max_positions    = max_positions
        self.risk_pct         = risk_pct
        self.refresh_seconds  = refresh_seconds
        self.candle_count     = candle_count
        self.timeframe        = timeframe
        self.log_dir          = log_dir
        self._running         = False
        self._bars_processed  = 0
        self._signals_log:    list[dict] = []

        os.makedirs(log_dir, exist_ok=True)

        # Initialise components
        self.provider      = create_data_provider(data_mode)
        self.futures_agent = FuturesDataAgent(mock=(data_mode == "mock"))
        self.options_agent = OptionsChainAgent(mock=(data_mode == "mock"))
        self.signal_engine = SignalEngine()
        self.broker        = PaperBroker(initial_capital=capital)
        self.order_manager = OrderManager(self.broker)
        self.alerts        = AlertSystem(telegram_token, telegram_chat_id)
        self.position_mgr  = PositionManager(
            broker       = self.broker,
            alert_fn     = self.alerts.send,
        )

        self.broker.connect()
        log.info(
            f"PaperTradingEngine ready | symbols={self.symbols} "
            f"| capital=₹{capital:,.0f} | min_conf={min_confidence}"
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_session(self):
        \"\"\"
        Run until market close. Blocks the calling thread.
        Checks signals every refresh_seconds.
        \"\"\"
        self._running = True
        self.alerts.send("SESSION_START", f"Paper session started | {', '.join(self.symbols)}")
        log.info("Paper trading session started")

        try:
            while self._running:
                now = datetime.datetime.now(IST)
                if self._is_market_open(now):
                    self._process_cycle()
                    time.sleep(self.refresh_seconds)
                elif now.time() >= MARKET_CLOSE:
                    log.info("Market closed — ending session")
                    break
                else:
                    log.info("Market not open yet — waiting...")
                    time.sleep(60)
        except KeyboardInterrupt:
            log.info("Session interrupted by user")
        finally:
            self._end_session()

    def run_bars(self, n: int = 10) -> dict:
        \"\"\"
        Process n signal cycles and return session summary.
        Used for testing and development without waiting for market hours.
        \"\"\"
        self._running = True
        self.alerts.send("SESSION_START", f"Paper test session | {n} bars | {', '.join(self.symbols)}")

        for i in range(n):
            if not self._running:
                break
            self._process_cycle()
            self._bars_processed += 1

        return self._end_session()

    def stop(self):
        self._running = False

    # ── Core cycle ────────────────────────────────────────────────────────────

    def _process_cycle(self):
        \"\"\"One full signal-check cycle across all symbols.\"\"\"
        for symbol in self.symbols:
            try:
                self._process_symbol(symbol)
            except Exception as e:
                log.error(f"Cycle failed for {symbol}: {e}", exc_info=True)

        # Update all positions with latest prices
        for symbol in self.symbols:
            ltp = self.provider.get_spot(symbol)
            if ltp:
                exits = self.position_mgr.on_price_update(symbol, ltp)
                for exit_record in exits:
                    if exit_record:
                        self.alerts.send_trade_closed(exit_record)

    def _process_symbol(self, symbol: str):
        \"\"\"Full signal pipeline for one symbol.\"\"\"
        # 1. Fetch data
        df = self.provider.get_candles(symbol, self.timeframe, self.candle_count)
        if df.empty:
            log.warning(f"No candle data for {symbol}")
            return

        ltp = self.provider.get_spot(symbol)
        if ltp:
            self.broker.update_ltp(symbol, ltp)

        # 2. Compute indicators
        vix     = getattr(self.provider, "get_vix", lambda: None)()
        tech    = compute_all(df, vix=vix)
        vol     = compute_volume(df)
        futures = self.futures_agent.get_futures_snapshot(symbol)
        options = self.options_agent.analyse(symbol)

        # 3. Signal engine
        signal = self.signal_engine.compute(symbol, tech, vol, futures, options)
        self._signals_log.append(signal)

        confidence = signal.get("confidence", 0)
        decision   = signal.get("decision", "NO_TRADE")

        log.info(
            f"[{symbol}] score={confidence:.1f} decision={decision} "
            f"regime={signal.get('market_regime')}"
        )

        # 4. Send signal alert regardless of decision
        self.alerts.send_signal(signal)

        # 5. Check if we can enter
        if decision == "NO_TRADE" or confidence < self.min_confidence:
            return

        if self.position_mgr.get_count() >= self.max_positions:
            log.info(f"Max positions reached ({self.max_positions}) — skipping {symbol}")
            return

        # 6. Execute paper trade
        self._enter_trade(symbol, signal, tech)

    def _enter_trade(self, symbol: str, signal: dict, tech: dict):
        \"\"\"Open a paper position based on the signal.\"\"\"
        trade_id    = str(uuid.uuid4())[:8]
        direction   = signal.get("direction", "NEUTRAL")
        entry_price = tech.get("ema", {}).get("price", 0)
        atr         = tech.get("atr", {}).get("atr", entry_price * 0.005)

        if not entry_price or direction == "NEUTRAL":
            return

        # Position sizing
        risk_amount  = self.capital * self.risk_pct
        sl_dist      = atr * 1.5
        lot_size     = 50 if "BANK" not in symbol else 15
        lots         = max(1, int(risk_amount / (sl_dist * lot_size)))
        quantity     = lots * lot_size

        if direction == "LONG":
            sl     = round(entry_price - sl_dist, 2)
            target = round(entry_price + sl_dist * 2.0, 2)
            opt_type = "CE"
        else:
            sl     = round(entry_price + sl_dist, 2)
            target = round(entry_price - sl_dist * 2.0, 2)
            opt_type = "PE"

        # Place paper order
        order = self.order_manager.submit(
            trade_id   = trade_id,
            symbol     = symbol,
            direction  = "BUY",
            quantity   = quantity,
            order_type = "MARKET",
            tag        = f"paper_{signal.get('confidence', 0):.0f}",
        )

        if order.state != "FILLED":
            log.warning(f"Order not filled for {symbol}")
            return

        # Open position for monitoring
        self.broker.open_position(
            trade_id    = trade_id,
            symbol      = symbol,
            direction   = direction,
            quantity    = quantity,
            entry_price = order.filled_price or entry_price,
            stop_loss   = sl,
            target      = target,
            option_type = opt_type,
            expiry      = signal.get("expiry", ""),
        )

        self.position_mgr.register(
            trade_id    = trade_id,
            symbol      = symbol,
            direction   = direction,
            quantity    = quantity,
            entry_price = order.filled_price or entry_price,
            stop_loss   = sl,
            target      = target,
            option_type = opt_type,
            confidence  = signal.get("confidence", 0),
        )

        trade_info = {
            "trade_id":    trade_id,
            "symbol":      symbol,
            "direction":   direction,
            "entry_price": order.filled_price or entry_price,
            "stop_loss":   sl,
            "target":      target,
            "quantity":    quantity,
        }
        self.alerts.send_trade_opened(trade_info)
        log.info(
            f"[PAPER ENTRY] {symbol} {direction} {quantity} units "
            f"@ ₹{entry_price:.2f} | SL={sl:.2f} TGT={target:.2f}"
        )

    # ── Session end ───────────────────────────────────────────────────────────

    def _end_session(self) -> dict:
        \"\"\"Close all positions and produce session report.\"\"\"
        self.position_mgr.force_close_all("EOD")

        summary = self.broker.get_session_summary()
        order_summary = self.order_manager.session_summary()
        balance = self.broker.get_balance()

        session_report = {
            "session_date":   datetime.date.today().isoformat(),
            "symbols":        self.symbols,
            "bars_processed": self._bars_processed,
            "signals_generated": len(self._signals_log),
            "trade_summary":  summary,
            "order_summary":  order_summary,
            "balance":        balance,
        }

        # Save session log
        os.makedirs(self.log_dir, exist_ok=True)
        log_path = os.path.join(
            self.log_dir,
            f"paper_session_{datetime.date.today().isoformat()}.json"
        )
        with open(log_path, "w") as f:
            json.dump(session_report, f, indent=2, default=str)
        log.info(f"Session log saved: {log_path}")

        self.alerts.send_session_summary(summary)
        self._running = False
        return session_report

    @staticmethod
    def _is_market_open(dt: datetime.datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        return MARKET_OPEN <= dt.time() < MARKET_CLOSE
"""

files["src/monitoring/alerts.py"] = """\"\"\"
Alert System (Spec section 32)
Sends alerts via Telegram and console.
Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
Console alerts always work with no config needed.
\"\"\"

import logging
import datetime
import os
import json
import urllib.request
import urllib.parse
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class AlertSystem:
    \"\"\"
    Multi-channel alert dispatcher.
    Channels: console (always), Telegram (if configured).
    \"\"\"

    EMOJI = {
        "SIGNAL_GENERATED":  "📊",
        "BUY":               "🟢",
        "SELL":              "🔴",
        "TARGET":            "🎯",
        "STOP_LOSS":         "🛑",
        "STOP_MODIFIED":     "✏️",
        "DAILY_LOSS_LIMIT":  "⚠️",
        "BROKER_ERROR":      "❌",
        "DATA_ERROR":        "⚠️",
        "SYSTEM_ERROR":      "🆘",
        "SESSION_START":     "🔔",
        "SESSION_END":       "📋",
        "NO_TRADE":          "⏸️",
        "PAPER_TRADE":       "📝",
    }

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        console: bool = True,
    ):
        self.token    = telegram_token   or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id  = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID",   "")
        self.console  = console
        self._telegram_enabled = bool(self.token and self.chat_id)

        if self._telegram_enabled:
            log.info("AlertSystem: Telegram enabled")
        else:
            log.info("AlertSystem: Console only (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID for Telegram)")

    def send(self, event_type: str, message: str, data: dict = None) -> bool:
        \"\"\"Send an alert. Returns True if at least one channel succeeded.\"\"\"
        emoji    = self.EMOJI.get(event_type, "📌")
        ts       = datetime.datetime.now(IST).strftime("%H:%M:%S")
        full_msg = f"{emoji} [{ts}] {event_type}\\n{message}"

        if data:
            # Append key fields
            extra = []
            for k in ["symbol","direction","confidence","net_pnl","exit_reason","market_regime"]:
                if k in data:
                    val = data[k]
                    if isinstance(val, float):
                        val = f"{val:,.2f}"
                    extra.append(f"  {k}: {val}")
            if extra:
                full_msg += "\\n" + "\\n".join(extra)

        success = False
        if self.console:
            self._console_alert(event_type, full_msg)
            success = True
        if self._telegram_enabled:
            success = self._telegram_alert(full_msg) or success

        return success

    def send_signal(self, signal: dict) -> bool:
        \"\"\"Formatted alert for a new trading signal.\"\"\"
        sym  = signal.get("underlying", "")
        dec  = signal.get("decision", "")
        conf = signal.get("confidence", 0)
        strat= signal.get("strategy", "")
        reg  = signal.get("market_regime", "")
        sl   = signal.get("stop_loss")
        tgt  = signal.get("target")
        rr   = signal.get("risk_reward", 0)

        msg = (
            f"{sym} | {dec} | conf={conf:.0f}%\\n"
            f"Strategy: {strat}\\n"
            f"Regime: {reg}\\n"
        )
        if sl and tgt:
            msg += f"SL: {sl:.0f}  TGT: {tgt:.0f}  R:R 1:{rr}\\n"

        reasons = signal.get("reasons", [])
        if reasons:
            msg += "Reasons:\\n" + "\\n".join(f"  • {r}" for r in reasons[:3])

        return self.send("SIGNAL_GENERATED", msg)

    def send_trade_opened(self, trade: dict) -> bool:
        msg = (
            f"{trade.get('symbol')} {trade.get('direction')}\\n"
            f"Entry: ₹{trade.get('entry_price', 0):,.2f}\\n"
            f"SL: ₹{trade.get('stop_loss', 0):,.2f}  "
            f"TGT: ₹{trade.get('target', 0):,.2f}"
        )
        return self.send("PAPER_TRADE", msg, trade)

    def send_trade_closed(self, trade: dict) -> bool:
        pnl    = trade.get("net_pnl", 0)
        reason = trade.get("exit_reason", "")
        event  = "TARGET" if reason == "TARGET" else "STOP_LOSS" if reason == "STOP_LOSS" else "PAPER_TRADE"
        msg    = (
            f"{trade.get('symbol')} CLOSED | {reason}\\n"
            f"P&L: ₹{pnl:+,.0f}"
        )
        return self.send(event, msg, trade)

    def send_session_summary(self, summary: dict) -> bool:
        msg = (
            f"Session complete\\n"
            f"Trades:   {summary.get('trades', 0)}\\n"
            f"Win rate: {summary.get('win_rate', 0)}%\\n"
            f"P&L:      ₹{summary.get('session_pnl', 0):+,.0f}"
        )
        return self.send("SESSION_END", msg)

    def send_risk_alert(self, reason: str) -> bool:
        return self.send("DAILY_LOSS_LIMIT", reason)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _console_alert(self, event_type: str, message: str):
        emoji = self.EMOJI.get(event_type, "📌")
        border = "─" * 50
        print(f"\\n{border}")
        print(message)
        print(border)

    def _telegram_alert(self, message: str) -> bool:
        try:
            url     = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = json.dumps({
                "chat_id":    self.chat_id,
                "text":       message,
                "parse_mode": "HTML",
            }).encode("utf-8")
            req  = urllib.request.Request(url, data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            log.warning(f"Telegram alert failed: {e}")
            return False
"""

files["tests/test_paper_trading.py"] = """\"\"\"
Unit tests - Paper Trading Engine (Phase 5)
Tests: PaperBroker, OrderManager, PositionManager, AlertSystem, PaperTradingEngine.
\"\"\"

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.execution.paper_broker     import PaperBroker, PaperOrder, PaperPosition
from src.execution.order_manager    import OrderManager, OrderState
from src.execution.position_manager import PositionManager
from src.monitoring.alerts          import AlertSystem
from src.execution.paper_engine     import PaperTradingEngine


# ── PaperBroker tests ─────────────────────────────────────────────────────────

class TestPaperBroker:

    def setup_method(self):
        self.broker = PaperBroker(initial_capital=500_000)

    def test_connect_returns_true(self):
        assert self.broker.connect() is True

    def test_is_connected(self):
        assert self.broker.is_connected() is True

    def test_update_and_get_ltp(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        assert self.broker.get_ltp("NIFTY") == 24500.0

    def test_place_market_order_filled(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        order = self.broker.place_order("NIFTY", "BUY", 50, "MARKET")
        assert order.status       == "FILLED"
        assert order.filled_qty   == 50
        assert order.filled_price > 0

    def test_slippage_applied_on_buy(self):
        ltp = 24500.0
        self.broker.update_ltp("NIFTY", ltp)
        order = self.broker.place_order("NIFTY", "BUY", 50, "MARKET")
        assert order.filled_price > ltp   # buy price is slightly higher

    def test_slippage_applied_on_sell(self):
        ltp = 24500.0
        self.broker.update_ltp("NIFTY", ltp)
        order = self.broker.place_order("NIFTY", "SELL", 50, "MARKET")
        assert order.filled_price < ltp   # sell price is slightly lower

    def test_open_and_close_position(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        self.broker.open_position(
            "T001", "NIFTY", "LONG", 50,
            24500.0, 24350.0, 24800.0
        )
        assert len(self.broker.get_positions()) == 1
        record = self.broker.close_position("T001", 24700.0, "TARGET")
        assert record is not None
        assert record["net_pnl"] != 0
        assert len(self.broker.get_positions()) == 0

    def test_close_nonexistent_position_returns_none(self):
        result = self.broker.close_position("FAKE", 24500.0)
        assert result is None

    def test_get_balance_keys(self):
        bal = self.broker.get_balance()
        for k in ["capital","available_margin","session_pnl","open_positions"]:
            assert k in bal

    def test_session_summary_empty(self):
        s = self.broker.get_session_summary()
        assert s["trades"] == 0

    def test_session_summary_after_trade(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        self.broker.open_position("T001","NIFTY","LONG",50,24500,24350,24800)
        self.broker.close_position("T001", 24700.0, "TARGET")
        s = self.broker.get_session_summary()
        assert s["trades"] == 1

    def test_unrealised_pnl_updates(self):
        self.broker.update_ltp("NIFTY", 24500.0)
        self.broker.open_position("T001","NIFTY","LONG",50,24500,24350,24800)
        self.broker.update_ltp("NIFTY", 24600.0)
        pos = self.broker.get_positions()[0]
        assert pos.unrealised_pnl == pytest.approx(50 * 100.0, abs=5)

    def test_cancel_pending_order(self):
        order = self.broker.place_order("NIFTY","BUY",50,"LIMIT",price=24000)
        result = self.broker.cancel_order(order.order_id)
        # PaperBroker fills MARKET orders immediately; LIMIT stays pending
        # Just check no crash
        assert isinstance(result, bool)


# ── OrderManager tests ────────────────────────────────────────────────────────

class TestOrderManager:

    def setup_method(self):
        self.broker = PaperBroker(initial_capital=500_000)
        self.broker.update_ltp("NIFTY", 24500.0)
        self.om = OrderManager(self.broker)

    def test_submit_market_order_filled(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        assert order.state        == OrderState.FILLED
        assert order.filled_price  > 0

    def test_order_stored(self):
        self.om.submit("T001","NIFTY","BUY",50)
        assert len(self.om.get_all_orders()) == 1

    def test_get_order_by_id(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        found = self.om.get_order(order.order_id)
        assert found is not None
        assert found.order_id == order.order_id

    def test_get_trade_orders(self):
        self.om.submit("T001","NIFTY","BUY",50)
        self.om.submit("T001","NIFTY","SELL",50)
        orders = self.om.get_trade_orders("T001")
        assert len(orders) == 2

    def test_complete_filled_order(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        result = self.om.complete(order.order_id)
        assert result is True
        assert self.om.get_order(order.order_id).state == OrderState.COMPLETED

    def test_session_summary_keys(self):
        self.om.submit("T001","NIFTY","BUY",50)
        s = self.om.session_summary()
        for k in ["total","filled","pending","cancelled","rejected"]:
            assert k in s

    def test_invalid_state_transition_ignored(self):
        order = self.om.submit("T001","NIFTY","BUY",50)
        # Try invalid transition: FILLED → PENDING
        self.om._transition(order, OrderState.PENDING)
        assert order.state == OrderState.FILLED   # unchanged


# ── PositionManager tests ─────────────────────────────────────────────────────

class TestPositionManager:

    def setup_method(self):
        self.broker = PaperBroker(initial_capital=500_000)
        self.broker.update_ltp("NIFTY", 24500.0)
        self.events = []
        self.pm     = PositionManager(
            broker   = self.broker,
            alert_fn = lambda et, msg, data: self.events.append(et)
        )

    def _open_pos(self, direction="LONG", entry=24500, sl=24350, tgt=24800):
        tid = "T001"
        self.broker.open_position(tid,"NIFTY",direction,50,entry,sl,tgt)
        self.pm.register(tid,"NIFTY",direction,50,entry,sl,tgt)
        return tid

    def test_register_adds_position(self):
        self._open_pos()
        assert self.pm.get_count() == 1

    def test_get_position(self):
        tid = self._open_pos()
        pos = self.pm.get_position(tid)
        assert pos is not None
        assert pos["symbol"] == "NIFTY"

    def test_target_hit_closes_position(self):
        self._open_pos(entry=24500, sl=24350, tgt=24700)
        exits = self.pm.on_price_update("NIFTY", 24750.0)
        assert len(exits) > 0
        assert self.pm.get_count() == 0

    def test_stop_loss_hit_closes_position(self):
        self._open_pos(entry=24500, sl=24350, tgt=24800)
        exits = self.pm.on_price_update("NIFTY", 24300.0)
        assert len(exits) > 0
        assert self.pm.get_count() == 0

    def test_no_exit_between_sl_and_target(self):
        self._open_pos(entry=24500, sl=24350, tgt=24800)
        exits = self.pm.on_price_update("NIFTY", 24550.0)
        assert len(exits) == 0
        assert self.pm.get_count() == 1

    def test_modify_stop(self):
        tid = self._open_pos()
        result = self.pm.modify_stop(tid, 24450.0)
        assert result is True
        assert self.pm.get_position(tid)["stop_loss"] == 24450.0

    def test_force_close_all(self):
        self._open_pos()
        self.pm.force_close_all("EOD")
        assert self.pm.get_count() == 0

    def test_breakeven_applied_after_1r(self):
        # Entry 24500, SL 24350 (risk=150), target 24800
        tid = self._open_pos(entry=24500, sl=24350, tgt=24800)
        # Price moves +150 (1R) — should apply break-even
        self.pm.on_price_update("NIFTY", 24660.0)
        pos = self.pm.get_position(tid)
        if pos:   # if position still open
            assert pos["be_applied"] is True


# ── AlertSystem tests ─────────────────────────────────────────────────────────

class TestAlertSystem:

    def setup_method(self):
        # No Telegram credentials — console only
        self.alerts = AlertSystem(console=True)

    def test_send_returns_bool(self):
        result = self.alerts.send("SESSION_START", "Test alert")
        assert isinstance(result, bool)
        assert result is True

    def test_send_signal(self):
        signal = {
            "underlying": "NIFTY", "decision": "BUY",
            "confidence": 78.0, "strategy": "Long call",
            "market_regime": "BULL", "reasons": ["EMA bullish"],
            "stop_loss": 24350, "target": 24800, "risk_reward": 2.0,
        }
        result = self.alerts.send_signal(signal)
        assert result is True

    def test_send_trade_closed(self):
        result = self.alerts.send_trade_closed({
            "symbol": "NIFTY", "net_pnl": 1200.0, "exit_reason": "TARGET"
        })
        assert result is True

    def test_send_session_summary(self):
        result = self.alerts.send_session_summary({
            "trades": 5, "win_rate": 60.0, "session_pnl": 3500.0
        })
        assert result is True

    def test_no_telegram_no_crash(self):
        a = AlertSystem(telegram_token="", telegram_chat_id="", console=False)
        result = a.send("SESSION_START", "Test")
        assert result is False   # console disabled, telegram not configured


# ── PaperTradingEngine tests ──────────────────────────────────────────────────

class TestPaperTradingEngine:

    def setup_method(self):
        self.engine = PaperTradingEngine(
            symbols        = ["NIFTY"],
            capital        = 500_000,
            min_confidence = 60.0,
            data_mode      = "mock",
        )

    def test_run_bars_returns_dict(self):
        result = self.engine.run_bars(n=3)
        assert isinstance(result, dict)

    def test_run_bars_required_keys(self):
        result = self.engine.run_bars(n=3)
        for k in ["session_date","symbols","bars_processed",
                  "signals_generated","trade_summary","balance"]:
            assert k in result, f"Missing key: {k}"

    def test_signals_generated(self):
        result = self.engine.run_bars(n=5)
        assert result["signals_generated"] >= 5   # 1 per bar per symbol

    def test_balance_keys(self):
        result = self.engine.run_bars(n=2)
        bal    = result["balance"]
        for k in ["capital","available_margin","session_pnl"]:
            assert k in bal

    def test_session_log_saved(self):
        import os
        self.engine.log_dir = "logs_test"
        self.engine.run_bars(n=2)
        log_files = [f for f in os.listdir("logs_test") if f.endswith(".json")]
        assert len(log_files) >= 1
        # Cleanup
        import shutil
        shutil.rmtree("logs_test", ignore_errors=True)

    def test_multi_symbol(self):
        engine = PaperTradingEngine(
            symbols=["NIFTY","BANKNIFTY"], min_confidence=60.0, data_mode="mock"
        )
        result = engine.run_bars(n=2)
        assert "NIFTY"     in result["symbols"]
        assert "BANKNIFTY" in result["symbols"]

    def test_stop_works(self):
        self.engine.stop()
        assert self.engine._running is False

    def test_capital_preserved_structure(self):
        result = self.engine.run_bars(n=3)
        assert result["balance"]["capital"] == 500_000
"""


created = []
for rel_path, content in files.items():
    full_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(rel_path)

print(f"\n{'='*58}")
print(f"  Phase 5 setup complete  {len(created)} files written")
print(f"{'='*58}")
for p in created:
    print(f"  OK  {p}")
print(f"\nNow run:  python -m pytest -v")
print(f"Expected: 196 passed  (155 + 40 + 41 new)")
print(f"{'='*58}\n")
