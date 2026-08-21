"""
AI Trading Agent — Windows Setup Script
Run this once from inside C:\trading\ai_trading_agent with venv active.
It creates every project file with correct content and folder structure.

Usage:
    python setup_project.py
"""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))

files = {}

# ── config/settings.yaml ─────────────────────────────────────────────────────
files["config/settings.yaml"] = """\
app:
  name: AI Trading Agent - NSE F&O
  version: "1.0.0"
  environment: development
  trading_mode: paper
  enable_live_trading: false

instruments:
  - symbol: NIFTY
    exchange: NSE
    segment: INDEX
    futures_symbol: NIFTY-FUT
    lot_size: 50
    tick_size: 0.05
  - symbol: BANKNIFTY
    exchange: NSE
    segment: INDEX
    futures_symbol: BANKNIFTY-FUT
    lot_size: 15
    tick_size: 0.05

timeframes:
  primary: "5min"
  secondary: "15min"
  confirmation: "1min"

market_hours:
  pre_market_start: "09:00"
  market_open: "09:15"
  avoid_open_minutes: 15
  midday_start: "11:30"
  closing_start: "14:45"
  market_close: "15:30"
  expiry_special_rules: true

data:
  candle_history_days: 365
  options_chain_depth: 10
  refresh_interval_seconds: 60
  stale_data_threshold_seconds: 120
"""

# ── config/risk.yaml ──────────────────────────────────────────────────────────
files["config/risk.yaml"] = """\
risk:
  max_risk_per_trade: 0.005
  max_daily_loss: 0.02
  max_weekly_loss: 0.05
  max_trades_per_day: 10
  max_consecutive_losses: 3
  max_open_positions: 3
  min_risk_reward: 1.5
  min_confidence: 70

position_sizing:
  method: fixed_risk
  default_capital: 500000

stop_loss:
  method: atr_based
  atr_multiplier: 1.5
  min_sl_points: 20
  max_sl_points: 150

targets:
  method: fixed_rr
  default_rr: 2.0
  trail_after_r: 1.0

filters:
  max_spread_pct: 0.5
  min_option_volume: 500
  min_option_oi: 1000
  max_iv_percentile: 80
"""

# ── config/strategy.yaml ──────────────────────────────────────────────────────
files["config/strategy.yaml"] = """\
strategy:
  active: vwap_ema_price_action
  min_confidence: 70

  signal_weights:
    trend: 20
    price_action: 20
    vwap: 10
    momentum: 10
    volume: 10
    futures_oi: 10
    options_oi: 10
    iv: 5
    market_regime: 5

  confidence_thresholds:
    strong: 80
    valid: 70
    weak: 60
    no_trade: 0

  market_regime:
    adx_strong_trend: 25
    adx_weak_trend: 15
    rsi_overbought: 70
    rsi_oversold: 30

  time_rules:
    avoid_first_minutes: 15
    avoid_last_minutes: 15
    expiry_day_caution: true

  indicators:
    ema_fast: 9
    ema_mid: 21
    ema_slow: 50
    ema_trend: 200
    rsi_period: 14
    atr_period: 14
    bb_period: 20
    bb_std: 2.0
    adx_period: 14
    macd_fast: 12
    macd_slow: 26
    macd_signal: 9
    supertrend_period: 10
    supertrend_multiplier: 3.0
"""

# ── src/__init__.py ───────────────────────────────────────────────────────────
files["src/__init__.py"] = ""

# ── src/config/__init__.py ────────────────────────────────────────────────────
files["src/config/__init__.py"] = ""

# ── src/config/loader.py ──────────────────────────────────────────────────────
files["src/config/loader.py"] = '''\
"""
Config Loader
Loads settings.yaml, risk.yaml, strategy.yaml and merges
with environment variables from .env
"""

import os
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(filename):
    path = ROOT / "config" / filename
    if not path.exists():
        log.warning(f"Config file not found: {path}")
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config():
    load_dotenv(ROOT / ".env", override=False)
    cfg = {}
    cfg.update(_load_yaml("settings.yaml"))
    cfg["risk"]     = _load_yaml("risk.yaml").get("risk", {})
    cfg["strategy"] = _load_yaml("strategy.yaml").get("strategy", {})

    env_map = {
        "TRADING_MODE":           ("app", "trading_mode"),
        "ENABLE_LIVE_TRADING":    ("app", "enable_live_trading"),
        "ENVIRONMENT":            ("app", "environment"),
        "DATABASE_URL":           ("database", "url"),
        "MAX_RISK_PER_TRADE":     ("risk", "max_risk_per_trade"),
        "MAX_DAILY_LOSS":         ("risk", "max_daily_loss"),
        "MAX_TRADES_PER_DAY":     ("risk", "max_trades_per_day"),
        "MAX_CONSECUTIVE_LOSSES": ("risk", "max_consecutive_losses"),
    }

    for env_key, (section, field) in env_map.items():
        val = os.getenv(env_key)
        if val is not None:
            if section not in cfg:
                cfg[section] = {}
            if val.lower() in ("true", "false"):
                val = val.lower() == "true"
            else:
                try:
                    val = float(val) if "." in val else int(val)
                except ValueError:
                    pass
            cfg[section][field] = val

    if "database" not in cfg:
        cfg["database"] = {}
    cfg["database"].setdefault(
        "url",
        os.getenv("DATABASE_URL", f"sqlite:///{ROOT}/data/trading.db")
    )
    return cfg


_config = None

def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config
'''

# ── src/database/__init__.py ──────────────────────────────────────────────────
files["src/database/__init__.py"] = ""

# ── src/database/models.py ────────────────────────────────────────────────────
files["src/database/models.py"] = '''\
"""
Database Models (SQLAlchemy) - All 16 tables
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Boolean,
    DateTime, Text, JSON, ForeignKey, Index,
    create_engine
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Instrument(Base):
    __tablename__ = "instruments"
    id             = Column(Integer, primary_key=True)
    symbol         = Column(String(20), nullable=False, unique=True)
    exchange       = Column(String(10), nullable=False)
    segment        = Column(String(20), nullable=False)
    futures_symbol = Column(String(30))
    lot_size       = Column(Integer, nullable=False)
    tick_size      = Column(Float,   nullable=False)
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


class Candle(Base):
    __tablename__ = "candles"
    id        = Column(Integer, primary_key=True)
    symbol    = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    timestamp = Column(DateTime,   nullable=False)
    open      = Column(Float, nullable=False)
    high      = Column(Float, nullable=False)
    low       = Column(Float, nullable=False)
    close     = Column(Float, nullable=False)
    volume    = Column(Float, nullable=False)
    vwap      = Column(Float)
    __table_args__ = (
        Index("ix_candles_symbol_tf_ts", "symbol", "timeframe", "timestamp", unique=True),
    )


class MarketData(Base):
    __tablename__ = "market_data"
    id            = Column(Integer, primary_key=True)
    timestamp     = Column(DateTime, nullable=False, index=True)
    symbol        = Column(String(20), nullable=False)
    spot          = Column(Float)
    futures_price = Column(Float)
    basis         = Column(Float)
    volume        = Column(Float)
    market_status = Column(String(10))
    data_quality  = Column(Integer, default=100)


class FuturesData(Base):
    __tablename__ = "futures_data"
    id           = Column(Integer, primary_key=True)
    timestamp    = Column(DateTime, nullable=False)
    symbol       = Column(String(20), nullable=False)
    expiry       = Column(String(12))
    price        = Column(Float)
    volume       = Column(Float)
    oi           = Column(Float)
    change_in_oi = Column(Float)
    basis        = Column(Float)
    oi_signal    = Column(String(20))


class OptionsChain(Base):
    __tablename__ = "options_chain"
    id           = Column(Integer, primary_key=True)
    timestamp    = Column(DateTime, nullable=False)
    symbol       = Column(String(20), nullable=False)
    expiry       = Column(String(12), nullable=False)
    strike       = Column(Float, nullable=False)
    option_type  = Column(String(2), nullable=False)
    ltp          = Column(Float)
    bid          = Column(Float)
    ask          = Column(Float)
    volume       = Column(Float)
    oi           = Column(Float)
    change_in_oi = Column(Float)
    iv           = Column(Float)
    delta        = Column(Float)
    gamma        = Column(Float)
    theta        = Column(Float)
    vega         = Column(Float)


class Signal(Base):
    __tablename__ = "signals"
    id              = Column(Integer, primary_key=True)
    timestamp       = Column(DateTime, nullable=False, index=True)
    underlying      = Column(String(20))
    direction       = Column(String(10))
    decision        = Column(String(10))
    instrument_type = Column(String(10))
    option_type     = Column(String(2))
    strike          = Column(Float)
    expiry          = Column(String(12))
    entry           = Column(Float)
    stop_loss       = Column(Float)
    target          = Column(Float)
    risk_reward     = Column(Float)
    confidence      = Column(Float)
    market_regime   = Column(String(20))
    score_breakdown = Column(JSON)
    reasons         = Column(JSON)
    invalidation    = Column(JSON)
    strategy        = Column(String(50))
    acted_on        = Column(Boolean, default=False)


class Trade(Base):
    __tablename__ = "trades"
    id              = Column(Integer, primary_key=True)
    trade_id        = Column(String(36), unique=True)
    signal_id       = Column(Integer, ForeignKey("signals.id"))
    timestamp       = Column(DateTime, nullable=False)
    instrument      = Column(String(20))
    symbol          = Column(String(40))
    expiry          = Column(String(12))
    strike          = Column(Float)
    option_type     = Column(String(2))
    direction       = Column(String(10))
    entry_price     = Column(Float)
    exit_price      = Column(Float)
    quantity        = Column(Integer)
    stop_loss       = Column(Float)
    target          = Column(Float)
    gross_pnl       = Column(Float)
    brokerage       = Column(Float, default=0)
    charges         = Column(Float, default=0)
    slippage        = Column(Float, default=0)
    net_pnl         = Column(Float)
    strategy        = Column(String(50))
    confidence      = Column(Float)
    market_regime   = Column(String(20))
    exit_reason     = Column(String(50))
    holding_minutes = Column(Integer)
    mode            = Column(String(10))


class Order(Base):
    __tablename__ = "orders"
    id              = Column(Integer, primary_key=True)
    order_id        = Column(String(36), unique=True)
    trade_id        = Column(String(36))
    timestamp       = Column(DateTime, nullable=False)
    symbol          = Column(String(40))
    order_type      = Column(String(20))
    direction       = Column(String(10))
    quantity        = Column(Integer)
    price           = Column(Float)
    trigger_price   = Column(Float)
    status          = Column(String(20))
    filled_price    = Column(Float)
    filled_qty      = Column(Integer)
    broker_order_id = Column(String(50))
    reject_reason   = Column(Text)
    updated_at      = Column(DateTime)


class Position(Base):
    __tablename__ = "positions"
    id              = Column(Integer, primary_key=True)
    trade_id        = Column(String(36), unique=True)
    symbol          = Column(String(40))
    direction       = Column(String(10))
    quantity        = Column(Integer)
    entry_price     = Column(Float)
    current_price   = Column(Float)
    stop_loss       = Column(Float)
    target          = Column(Float)
    unrealised_pnl  = Column(Float)
    status          = Column(String(20), default="OPEN")
    opened_at       = Column(DateTime)
    updated_at      = Column(DateTime)


class RiskEvent(Base):
    __tablename__ = "risk_events"
    id           = Column(Integer, primary_key=True)
    timestamp    = Column(DateTime, nullable=False)
    event_type   = Column(String(50))
    description  = Column(Text)
    action_taken = Column(String(50))
    value        = Column(Float)
    threshold    = Column(Float)


class Performance(Base):
    __tablename__ = "performance"
    id                     = Column(Integer, primary_key=True)
    date                   = Column(String(10), unique=True)
    total_trades           = Column(Integer, default=0)
    winning_trades         = Column(Integer, default=0)
    losing_trades          = Column(Integer, default=0)
    win_rate               = Column(Float)
    avg_win                = Column(Float)
    avg_loss               = Column(Float)
    profit_factor          = Column(Float)
    gross_pnl              = Column(Float, default=0)
    net_pnl                = Column(Float, default=0)
    max_drawdown           = Column(Float)
    sharpe_ratio           = Column(Float)
    sortino_ratio          = Column(Float)
    max_consecutive_wins   = Column(Integer)
    max_consecutive_losses = Column(Integer)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id           = Column(Integer, primary_key=True)
    run_id       = Column(String(36), unique=True)
    started_at   = Column(DateTime)
    completed_at = Column(DateTime)
    strategy     = Column(String(50))
    symbol       = Column(String(20))
    from_date    = Column(String(12))
    to_date      = Column(String(12))
    timeframe    = Column(String(10))
    parameters   = Column(JSON)
    results      = Column(JSON)
    status       = Column(String(20))


class NewsEvent(Base):
    __tablename__ = "news_events"
    id           = Column(Integer, primary_key=True)
    timestamp    = Column(DateTime, nullable=False)
    event_type   = Column(String(50))
    title        = Column(Text)
    impact       = Column(String(10))
    source       = Column(String(50))
    action_taken = Column(String(50))


class SystemLog(Base):
    __tablename__ = "system_logs"
    id         = Column(Integer, primary_key=True)
    timestamp  = Column(DateTime, default=datetime.utcnow)
    level      = Column(String(10))
    event_type = Column(String(50))
    module     = Column(String(50))
    message    = Column(Text)
    extra      = Column(JSON)


class StrategyRun(Base):
    __tablename__ = "strategy_runs"
    id              = Column(Integer, primary_key=True)
    run_id          = Column(String(36), unique=True)
    strategy        = Column(String(50))
    started_at      = Column(DateTime)
    stopped_at      = Column(DateTime)
    mode            = Column(String(10))
    status          = Column(String(20))
    config_snapshot = Column(JSON)


class Account(Base):
    __tablename__ = "accounts"
    id               = Column(Integer, primary_key=True)
    broker           = Column(String(30))
    initial_capital  = Column(Float)
    current_capital  = Column(Float)
    available_margin = Column(Float)
    used_margin      = Column(Float)
    realised_pnl     = Column(Float, default=0)
    unrealised_pnl   = Column(Float, default=0)
    updated_at       = Column(DateTime)
'''

# ── src/database/connection.py ────────────────────────────────────────────────
files["src/database/connection.py"] = '''\
"""
Database Connection
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.database.models import Base
from src.config.loader import get_config

log = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def _get_engine():
    global _engine
    if _engine is None:
        cfg = get_config()
        url = cfg.get("database", {}).get(
            "url",
            f"sqlite:///{Path(__file__).parents[2]}/data/trading.db"
        )
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            from sqlalchemy import event as sa_event
            @sa_event.listens_for(_engine, "connect")
            def set_wal(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        log.info(f"Database engine created")
    return _engine


def init_db():
    engine = _get_engine()
    Base.metadata.create_all(engine)
    log.info("Database tables initialised.")


def get_session():
    return _session_context()


@contextmanager
def _session_context():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health_check():
    try:
        with _get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error(f"Database health check failed: {e}")
        return False
'''

# ── src/monitoring/__init__.py ────────────────────────────────────────────────
files["src/monitoring/__init__.py"] = ""

# ── src/monitoring/logger.py ─────────────────────────────────────────────────
files["src/monitoring/logger.py"] = '''\
"""
Logger
"""

import logging
import logging.handlers
import datetime
import os
from pathlib import Path

try:
    from colorama import Fore, Style, init as _init
    _init(autoreset=True)
    _HAS_COLOR = True
except ImportError:
    _HAS_COLOR = False
    class Fore:
        GREEN = RED = YELLOW = CYAN = WHITE = MAGENTA = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


class Event:
    SYSTEM_START     = "SYSTEM_START"
    SYSTEM_STOP      = "SYSTEM_STOP"
    SYSTEM_ERROR     = "SYSTEM_ERROR"
    DATA_RECEIVED    = "DATA_RECEIVED"
    DATA_STALE       = "DATA_STALE"
    DATA_ERROR       = "DATA_ERROR"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    SIGNAL_REJECTED  = "SIGNAL_REJECTED"
    RISK_VALIDATION  = "RISK_VALIDATION"
    RISK_BREACH      = "RISK_BREACH"
    ORDER_SUBMITTED  = "ORDER_SUBMITTED"
    ORDER_FILLED     = "ORDER_FILLED"
    ORDER_REJECTED   = "ORDER_REJECTED"
    ORDER_CANCELLED  = "ORDER_CANCELLED"
    STOP_MODIFIED    = "STOP_MODIFIED"
    POSITION_OPENED  = "POSITION_OPENED"
    POSITION_CLOSED  = "POSITION_CLOSED"
    STOP_HIT         = "STOP_HIT"
    TARGET_HIT       = "TARGET_HIT"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_ERROR     = "BROKER_ERROR"
    BACKTEST_START   = "BACKTEST_START"
    BACKTEST_COMPLETE= "BACKTEST_COMPLETE"
    PAPER_TRADE      = "PAPER_TRADE"
    ALERT_SENT       = "ALERT_SENT"


def setup_logging(level="INFO"):
    numeric = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)
    if root.handlers:
        root.handlers.clear()
    ch = logging.StreamHandler()
    ch.setLevel(numeric)
    ch.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S"
    ))
    root.addHandler(ch)
    today = datetime.date.today().strftime("%Y%m%d")
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / f"trading_{today}.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=14,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(fh)


def log_event(logger, event_type, message, level="INFO", **kwargs):
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    full_msg = f"[{event_type}] {message}"
    if extra:
        full_msg += f" | {extra}"
    getattr(logger, level.lower(), logger.info)(full_msg)
'''

# ── src/risk/__init__.py ──────────────────────────────────────────────────────
files["src/risk/__init__.py"] = ""

# ── src/risk/risk_manager.py ──────────────────────────────────────────────────
files["src/risk/risk_manager.py"] = '''\
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
'''

# ── src/execution/__init__.py ─────────────────────────────────────────────────
files["src/execution/__init__.py"] = ""

# ── src/execution/broker_interface.py ────────────────────────────────────────
files["src/execution/broker_interface.py"] = '''\
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
'''

# ── src/utils/__init__.py ─────────────────────────────────────────────────────
files["src/utils/__init__.py"] = ""

# ── src/utils/transaction_costs.py ───────────────────────────────────────────
files["src/utils/transaction_costs.py"] = '''\
"""
Transaction Cost Model - Indian F&O
"""


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
        "brokerage":       round(brokerage, 2),
        "stt":             round(stt, 2),
        "exchange_charge": round(exchange_charge, 2),
        "sebi_fee":        round(sebi_fee, 4),
        "stamp_duty":      round(stamp_duty, 2),
        "gst":             round(gst, 2),
        "total":           round(total, 2),
        "turnover":        round(turnover, 2),
    }


def round_trip_cost(instrument_type, entry_premium, exit_premium,
                    quantity, underlying_lot, spot_price, brokerage_flat=20.0):
    notional     = spot_price * quantity
    entry_costs  = calculate_fno_charges(instrument_type, "buy",  entry_premium, quantity, underlying_lot, notional, brokerage_flat)
    exit_costs   = calculate_fno_charges(instrument_type, "sell", exit_premium,  quantity, underlying_lot, notional, brokerage_flat)
    total        = entry_costs["total"] + exit_costs["total"]
    gross_pnl    = (exit_premium - entry_premium) * quantity
    return {
        "entry_costs":    entry_costs["total"],
        "exit_costs":     exit_costs["total"],
        "total_charges":  round(total, 2),
        "gross_pnl":      round(gross_pnl, 2),
        "net_pnl":        round(gross_pnl - total, 2),
        "breakeven_move": round(total / quantity, 4),
    }
'''

# ── src/utils/time_utils.py ───────────────────────────────────────────────────
files["src/utils/time_utils.py"] = '''\
"""
Market Time Utilities - NSE
"""

import datetime
import pytz
from typing import Optional

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN  = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)
PRE_MARKET   = datetime.time(9, 0)

NIFTY_EXPIRY_DAY     = 3
BANKNIFTY_EXPIRY_DAY = 3


def now_ist():
    return datetime.datetime.now(IST)


def is_market_open(dt=None):
    dt = dt or now_ist()
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return MARKET_OPEN <= t < MARKET_CLOSE


def is_pre_market(dt=None):
    dt = dt or now_ist()
    t = dt.time()
    return PRE_MARKET <= t < MARKET_OPEN


def get_session(dt=None):
    dt = dt or now_ist()
    t = dt.time()
    if t < PRE_MARKET:
        return "AFTER_HOURS"
    if t < MARKET_OPEN:
        return "PRE_MARKET"
    if t < datetime.time(9, 30):
        return "OPENING"
    if t < datetime.time(14, 45):
        return "MIDDAY"
    if t < MARKET_CLOSE:
        return "CLOSING"
    return "AFTER_HOURS"


def is_expiry_day(symbol, dt=None):
    dt = dt or now_ist()
    if symbol.upper() == "BANKNIFTY":
        return dt.weekday() == BANKNIFTY_EXPIRY_DAY
    return dt.weekday() == NIFTY_EXPIRY_DAY


def minutes_to_close(dt=None):
    dt = dt or now_ist()
    close = dt.replace(hour=15, minute=30, second=0, microsecond=0)
    delta = (close - dt).total_seconds() / 60
    return max(0, int(delta))


def nearest_expiry(symbol, dt=None):
    dt = dt or now_ist()
    expiry_weekday = BANKNIFTY_EXPIRY_DAY if symbol.upper() == "BANKNIFTY" else NIFTY_EXPIRY_DAY
    days_ahead = (expiry_weekday - dt.weekday()) % 7
    if days_ahead == 0 and dt.time() > MARKET_CLOSE:
        days_ahead = 7
    return (dt + datetime.timedelta(days=days_ahead)).date()
'''

# ── src/data/__init__.py ──────────────────────────────────────────────────────
for d in ["src/data", "src/indicators", "src/agents", "src/strategies",
          "src/backtesting", "src/api", "src/dashboard"]:
    files[f"{d}/__init__.py"] = ""

# ── tests/__init__.py ─────────────────────────────────────────────────────────
files["tests/__init__.py"] = ""

# ── tests/test_risk.py ────────────────────────────────────────────────────────
files["tests/test_risk.py"] = '''\
"""
Unit tests - Risk Manager
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.risk.risk_manager import RiskManager

CAPITAL  = 500_000
BASE_CFG = {
    "risk": {
        "max_risk_per_trade":     0.005,
        "max_daily_loss":         0.02,
        "max_weekly_loss":        0.05,
        "max_trades_per_day":     5,
        "max_consecutive_losses": 3,
        "max_open_positions":     3,
        "min_risk_reward":        1.5,
        "min_confidence":         70,
    }
}

VALID_SIGNAL = {
    "confidence":  80,
    "risk_reward": 2.0,
    "entry":       19000.0,
    "stop_loss":   18800.0,
    "target":      19400.0,
}


def make_rm():
    rm = RiskManager(BASE_CFG, CAPITAL)
    rm.state.broker_connected = True
    import datetime
    rm.state.data_last_received = datetime.datetime.now()
    return rm


class TestSignalValidation:
    def test_valid_signal_approved(self):
        rm = make_rm()
        assert rm.validate_signal(VALID_SIGNAL).approved is True

    def test_low_confidence_rejected(self):
        rm = make_rm()
        r = rm.validate_signal({**VALID_SIGNAL, "confidence": 60})
        assert r.approved is False
        assert "Confidence" in r.reason

    def test_low_rr_rejected(self):
        rm = make_rm()
        r = rm.validate_signal({**VALID_SIGNAL, "risk_reward": 1.0})
        assert r.approved is False
        assert "R:R" in r.reason

    def test_missing_stoploss_rejected(self):
        rm = make_rm()
        sig = {**VALID_SIGNAL}
        del sig["stop_loss"]
        assert rm.validate_signal(sig).approved is False

    def test_broker_disconnected_rejected(self):
        rm = make_rm()
        rm.state.broker_connected = False
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "Broker" in r.reason

    def test_stale_data_rejected(self):
        import datetime
        rm = make_rm()
        rm.state.data_last_received = datetime.datetime.now() - datetime.timedelta(seconds=300)
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "stale" in r.reason.lower()

    def test_no_data_received_rejected(self):
        rm = make_rm()
        rm.state.data_last_received = None
        assert rm.validate_signal(VALID_SIGNAL).approved is False


class TestDailyLimits:
    def test_daily_loss_limit_halts_trading(self):
        rm = make_rm()
        rm.state.daily_pnl = -(CAPITAL * 0.021)
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert rm.state.is_trading_halted is True

    def test_max_trades_per_day_rejected(self):
        rm = make_rm()
        rm.state.trades_today = 5
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "trades" in r.reason.lower()

    def test_consecutive_losses_halts(self):
        rm = make_rm()
        rm.state.consecutive_losses = 3
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert rm.state.is_trading_halted is True

    def test_max_positions_rejected(self):
        rm = make_rm()
        rm.state.open_positions = 3
        r = rm.validate_signal(VALID_SIGNAL)
        assert r.approved is False
        assert "positions" in r.reason.lower()


class TestPositionSizing:
    def test_basic_sizing(self):
        rm = make_rm()
        r = rm.calculate_position_size(entry=200.0, stop_loss=180.0, lot_size=50)
        assert r["lots"] >= 1
        assert r["risk_pct"] <= rm.max_risk_pct * 100 * 2

    def test_zero_risk_returns_error(self):
        rm = make_rm()
        r = rm.calculate_position_size(entry=200.0, stop_loss=200.0, lot_size=50)
        assert "error" in r

    def test_quantity_is_multiple_of_lot(self):
        rm = make_rm()
        r = rm.calculate_position_size(entry=250.0, stop_loss=220.0, lot_size=50)
        assert r["quantity"] % 50 == 0


class TestStateTransitions:
    def test_winning_trade_resets_consecutive_losses(self):
        rm = make_rm()
        rm.state.consecutive_losses = 2
        rm.on_trade_closed(pnl=1000)
        assert rm.state.consecutive_losses == 0

    def test_losing_trade_increments_consecutive_losses(self):
        rm = make_rm()
        rm.on_trade_closed(pnl=-500)
        assert rm.state.consecutive_losses == 1

    def test_daily_reset(self):
        rm = make_rm()
        rm.state.daily_pnl    = -12000
        rm.state.trades_today = 4
        rm._halt("daily loss")
        rm.reset_daily()
        assert rm.state.daily_pnl    == 0
        assert rm.state.trades_today == 0
        assert rm.state.is_trading_halted is False
'''

# ── tests/test_database.py ────────────────────────────────────────────────────
files["tests/test_database.py"] = '''\
"""
Unit tests - Database models
"""

import pytest
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from src.database.models import (
    Base, Instrument, Candle, Signal, Trade, RiskEvent, Account
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


class TestInstrumentModel:
    def test_create_instrument(self, session):
        inst = Instrument(symbol="NIFTY", exchange="NSE", segment="INDEX",
                          futures_symbol="NIFTY-FUT", lot_size=50, tick_size=0.05)
        session.add(inst)
        session.commit()
        result = session.query(Instrument).filter_by(symbol="NIFTY").first()
        assert result is not None
        assert result.lot_size == 50

    def test_unique_symbol_constraint(self, session):
        from sqlalchemy.exc import IntegrityError
        i1 = Instrument(symbol="NIFTY", exchange="NSE", segment="INDEX", lot_size=50, tick_size=0.05)
        i2 = Instrument(symbol="NIFTY", exchange="NSE", segment="INDEX", lot_size=50, tick_size=0.05)
        session.add(i1)
        session.commit()
        session.add(i2)
        with pytest.raises(IntegrityError):
            session.commit()


class TestCandleModel:
    def test_create_candle(self, session):
        candle = Candle(symbol="NIFTY", timeframe="5min",
                        timestamp=datetime.datetime(2026, 8, 16, 10, 0),
                        open=19000, high=19050, low=18980, close=19030, volume=1500000)
        session.add(candle)
        session.commit()
        result = session.query(Candle).first()
        assert result.close == 19030

    def test_multiple_candles(self, session):
        candles = [
            Candle(symbol="NIFTY", timeframe="5min",
                   timestamp=datetime.datetime(2026, 8, 16, 9, i*5),
                   open=19000+i, high=19010+i, low=18990+i, close=19005+i, volume=100000)
            for i in range(5)
        ]
        session.add_all(candles)
        session.commit()
        assert session.query(Candle).count() == 5


class TestSignalModel:
    def test_create_signal(self, session):
        sig = Signal(
            timestamp=datetime.datetime(2026, 8, 16, 10, 30),
            underlying="NIFTY", direction="LONG", decision="BUY",
            instrument_type="OPTION", option_type="CE", strike=19000,
            entry=200.0, stop_loss=160.0, target=280.0,
            risk_reward=2.0, confidence=82.0, market_regime="BULL",
        )
        session.add(sig)
        session.commit()
        result = session.query(Signal).first()
        assert result.confidence == 82.0
        assert result.decision   == "BUY"


class TestAccountModel:
    def test_create_account(self, session):
        acc = Account(broker="paper", initial_capital=500000,
                      current_capital=500000, available_margin=500000, used_margin=0)
        session.add(acc)
        session.commit()
        assert session.query(Account).first().initial_capital == 500000


class TestRiskEventModel:
    def test_create_risk_event(self, session):
        ev = RiskEvent(
            timestamp=datetime.datetime(2026, 8, 16, 10, 0),
            event_type="DAILY_LOSS_LIMIT", description="2% reached",
            action_taken="HALT_TRADING", value=10000, threshold=10000
        )
        session.add(ev)
        session.commit()
        assert session.query(RiskEvent).first().event_type == "DAILY_LOSS_LIMIT"
'''

# ── tests/test_utils.py ───────────────────────────────────────────────────────
files["tests/test_utils.py"] = '''\
"""
Unit tests - Transaction costs and time utilities
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.utils.transaction_costs import calculate_fno_charges, round_trip_cost
from src.utils.time_utils import is_market_open, get_session, nearest_expiry
import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")


class TestTransactionCosts:
    def test_option_buy_no_stt(self):
        costs = calculate_fno_charges("option", "buy", 100, 50, 50, 950000)
        assert costs["stt"]       == 0.0
        assert costs["brokerage"] == 20.0
        assert costs["gst"]       > 0
        assert costs["total"]     > 0

    def test_option_sell_has_stt(self):
        costs = calculate_fno_charges("option", "sell", 150, 50, 50, 950000)
        assert costs["stt"] > 0

    def test_total_is_sum_of_components(self):
        costs = calculate_fno_charges("option", "sell", 200, 50, 50, 1000000)
        component_sum = (costs["brokerage"] + costs["stt"] + costs["exchange_charge"] +
                         costs["sebi_fee"]  + costs["stamp_duty"] + costs["gst"])
        assert abs(costs["total"] - component_sum) < 0.01

    def test_round_trip_net_pnl(self):
        result = round_trip_cost("option", 100, 150, 50, 50, 19000)
        assert result["gross_pnl"]     == 2500.0
        assert result["net_pnl"]       < result["gross_pnl"]
        assert result["total_charges"] > 0

    def test_round_trip_losing_trade(self):
        result = round_trip_cost("option", 200, 100, 50, 50, 19000)
        assert result["gross_pnl"] == -5000.0
        assert result["net_pnl"]   < result["gross_pnl"]


class TestTimeUtils:
    def _make_ist(self, hour, minute, weekday_offset=0):
        base = datetime.datetime(2026, 8, 17, hour, minute, 0)
        base += datetime.timedelta(days=weekday_offset)
        return IST.localize(base)

    def test_market_open_during_session(self):
        assert is_market_open(self._make_ist(10, 30)) is True

    def test_market_closed_before_open(self):
        assert is_market_open(self._make_ist(9, 0)) is False

    def test_market_closed_after_close(self):
        assert is_market_open(self._make_ist(15, 31)) is False

    def test_market_closed_on_weekend(self):
        assert is_market_open(self._make_ist(11, 0, weekday_offset=5)) is False

    def test_session_opening(self):
        assert get_session(self._make_ist(9, 20))  == "OPENING"

    def test_session_midday(self):
        assert get_session(self._make_ist(11, 0))  == "MIDDAY"

    def test_session_closing(self):
        assert get_session(self._make_ist(15, 0))  == "CLOSING"

    def test_session_pre_market(self):
        assert get_session(self._make_ist(9, 5))   == "PRE_MARKET"

    def test_nearest_expiry_is_thursday(self):
        dt = self._make_ist(10, 0)
        assert nearest_expiry("NIFTY", dt).weekday() == 3
'''


# ── Write all files ───────────────────────────────────────────────────────────
created = []
skipped = []

for rel_path, content in files.items():
    full_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(rel_path)

print(f"\n{'='*55}")
print(f"  Setup complete — {len(created)} files written")
print(f"{'='*55}")
for p in created:
    print(f"  OK  {p}")
print(f"\nRun:  python -m pytest -v")
print(f"{'='*55}\n")
