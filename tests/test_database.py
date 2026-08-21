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
