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
