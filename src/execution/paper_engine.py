"""
Paper Trading Engine (Spec section 26)
Runs the full signal pipeline on live/mock market data,
simulates execution, monitors positions, and logs everything.
No real orders are sent.

Usage:
    engine = PaperTradingEngine(symbols=["NIFTY","BANKNIFTY"])
    engine.run_session()     # blocking — runs until market close
    # or for testing:
    engine.run_bars(n=10)    # process n bars then stop
"""

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
    """
    Full paper trading session manager.
    Fetches data → generates signals → validates → executes paper orders →
    monitors positions → logs results → sends alerts.
    """

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
        """
        Run until market close. Blocks the calling thread.
        Checks signals every refresh_seconds.
        """
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
        """
        Process n signal cycles and return session summary.
        Used for testing and development without waiting for market hours.
        """
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
        """One full signal-check cycle across all symbols."""
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
        """Full signal pipeline for one symbol."""
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
        """Open a paper position based on the signal."""
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
        """Close all positions and produce session report."""
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
