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
