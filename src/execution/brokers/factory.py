"""
Broker Factory (Spec section 28)
Creates the correct broker instance based on TRADING_MODE.

paper mode  → PaperBroker (no real orders, safe)
live mode   → AngelOneBroker (real orders, requires credentials + safety gates)

Usage:
    from src.execution.brokers.factory import create_broker
    broker = create_broker()
    broker.connect()
"""

import os
import logging

log = logging.getLogger(__name__)


def create_broker(config: dict = None):
    """
    Create the right broker based on TRADING_MODE env var.

    TRADING_MODE=paper  → PaperBroker (default, safe)
    TRADING_MODE=live   → AngelOneBroker (requires ENABLE_LIVE_TRADING=true)

    Returns a connected broker instance.
    """
    trading_mode = os.getenv("TRADING_MODE", "paper").lower()
    capital      = float(os.getenv("INITIAL_CAPITAL", "500000"))

    if trading_mode == "paper" or trading_mode == "backtest":
        from src.execution.paper_broker import PaperBroker
        log.info("BrokerFactory: creating PaperBroker (paper mode)")
        broker = PaperBroker(initial_capital=capital)
        broker.connect()
        return broker

    if trading_mode == "live":
        live_enabled = os.getenv("ENABLE_LIVE_TRADING", "false").lower()
        if live_enabled != "true":
            raise RuntimeError(
                "Cannot create live broker: ENABLE_LIVE_TRADING is not 'true'.\n"
                "Set ENABLE_LIVE_TRADING=true in .env only after completing paper trading."
            )

        broker_name = os.getenv("BROKER_NAME", "angel").lower()

        if broker_name == "angel":
            from src.execution.brokers.angel_one import AngelOneBroker
            log.warning("BrokerFactory: creating AngelOneBroker (LIVE MODE)")
            broker = AngelOneBroker(config)
            if not broker.connect():
                raise RuntimeError("AngelOneBroker connection failed. Check credentials.")
            return broker

        raise ValueError(
            f"Unknown broker: '{broker_name}'. "
            f"Supported: angel. Add more adapters in src/execution/brokers/"
        )

    raise ValueError(f"Unknown TRADING_MODE: '{trading_mode}'. Use: paper | live")


def get_broker_status(broker) -> dict:
    """Return a health status dict for the dashboard."""
    try:
        connected = broker.is_connected()
        balance   = broker.get_balance() if connected else {}
        return {
            "connected":        connected,
            "broker_type":      type(broker).__name__,
            "available_margin": balance.get("available_margin", 0),
            "used_margin":      balance.get("used_margin",      0),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}
