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
