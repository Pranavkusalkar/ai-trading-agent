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
