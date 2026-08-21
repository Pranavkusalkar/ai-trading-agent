"""
Angel One SmartAPI Broker Adapter (Phase 6)
Implements BrokerInterface for Angel One's SmartAPI.

Requirements:
    pip install smartapi-python pyotp

Setup (.env):
    ANGEL_API_KEY=your_api_key
    ANGEL_CLIENT_ID=your_client_id
    ANGEL_PASSWORD=your_mpin
    ANGEL_TOTP_SECRET=your_totp_secret   (from SmartAPI app setup)

Get credentials:
    1. Open account at angelone.in
    2. Visit smartapi.angelbroking.com → Create App
    3. Note your API key
    4. Enable TOTP in Angel One app → Settings → Security

IMPORTANT: This adapter is for PAPER/LIVE trading in Phase 8+.
           During paper trading (Phase 5-7), PaperBroker is used instead.
           Never enable live trading without thorough paper testing first.
"""

import logging
import os
import json
import datetime
import time
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


# ── SmartAPI response codes ───────────────────────────────────────────────────
SUCCESS_CODE = "SUCCESS"

# ── Exchange / segment mappings ───────────────────────────────────────────────
EXCHANGE_MAP = {
    "NSE":  "NSE",
    "BSE":  "BSE",
    "NFO":  "NFO",   # F&O
    "MCX":  "MCX",
}

# ── Timeframe mappings (our format → SmartAPI format) ────────────────────────
TIMEFRAME_MAP = {
    "1min":  "ONE_MINUTE",
    "5min":  "FIVE_MINUTE",
    "15min": "FIFTEEN_MINUTE",
    "30min": "THIRTY_MINUTE",
    "1hour": "ONE_HOUR",
    "day":   "ONE_DAY",
}

# ── Product type mappings ─────────────────────────────────────────────────────
PRODUCT_MAP = {
    "MIS":  "INTRADAY",
    "NRML": "CARRYFORWARD",
    "CNC":  "DELIVERY",
}


class AngelOneBroker:
    """
    Angel One SmartAPI adapter.
    Implements the same interface as PaperBroker so the rest of the
    system works identically in paper and live mode.
    """

    def __init__(self, config: dict = None):
        self.api_key     = os.getenv("ANGEL_API_KEY",     config.get("angel_api_key",     "") if config else "")
        self.client_id   = os.getenv("ANGEL_CLIENT_ID",   config.get("angel_client_id",   "") if config else "")
        self.password    = os.getenv("ANGEL_PASSWORD",     config.get("angel_password",    "") if config else "")
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET", config.get("angel_totp_secret", "") if config else "")

        self._smart_api  = None
        self._auth_token = None
        self._feed_token = None
        self._connected  = False
        self._session_ts: Optional[datetime.datetime] = None

        # Token symbol cache: symbol → token mapping needed by SmartAPI
        self._symbol_tokens: dict[str, str] = {
            "NIFTY":     "26000",
            "BANKNIFTY": "26009",
            "NIFTY-FUT": "NIFTY-FUT",
        }

        log.info("AngelOneBroker initialised (not yet connected)")

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Authenticate with SmartAPI using API key + MPIN + TOTP.
        Returns True on success.
        """
        try:
            from SmartApi import SmartConnect
            import pyotp
        except ImportError:
            log.error(
                "smartapi-python or pyotp not installed.\n"
                "Run: pip install smartapi-python pyotp"
            )
            return False

        if not all([self.api_key, self.client_id, self.password]):
            log.error(
                "Missing Angel One credentials. Set in .env:\n"
                "  ANGEL_API_KEY\n  ANGEL_CLIENT_ID\n  ANGEL_PASSWORD\n  ANGEL_TOTP_SECRET"
            )
            return False

        try:
            self._smart_api = SmartConnect(api_key=self.api_key)

            # Generate TOTP
            totp = pyotp.TOTP(self.totp_secret).now() if self.totp_secret else ""

            data = self._smart_api.generateSession(
                self.client_id, self.password, totp
            )

            if data.get("status") is False:
                log.error(f"Angel One login failed: {data.get('message')}")
                return False

            self._auth_token = data["data"]["jwtToken"]
            self._feed_token = self._smart_api.getfeedToken()
            self._connected  = True
            self._session_ts = datetime.datetime.now(IST)

            log.info(
                f"Angel One connected | client={self.client_id} "
                f"| session={self._session_ts.strftime('%H:%M:%S IST')}"
            )
            return True

        except Exception as e:
            log.error(f"Angel One connection failed: {e}")
            return False

    def disconnect(self) -> None:
        if self._smart_api and self._connected:
            try:
                self._smart_api.terminateSession(self.client_id)
            except Exception:
                pass
        self._connected  = False
        self._smart_api  = None
        log.info("Angel One disconnected")

    def is_connected(self) -> bool:
        return self._connected and self._smart_api is not None

    def reconnect_if_needed(self) -> bool:
        """Re-authenticate if session is older than 8 hours."""
        if not self._session_ts:
            return self.connect()
        age_hours = (datetime.datetime.now(IST) - self._session_ts).seconds / 3600
        if age_hours > 8:
            log.info("Session expired — reconnecting")
            return self.connect()
        return True

    # ── Market data ───────────────────────────────────────────────────────────

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Optional[float]:
        """Last traded price."""
        self._require_connection()
        try:
            token  = self._get_token(symbol)
            params = {"exchange": exchange, "tradingsymbol": symbol, "symboltoken": token}
            data   = self._smart_api.ltpData(exchange, symbol, token)
            if data.get("status"):
                return float(data["data"]["ltp"])
        except Exception as e:
            log.error(f"get_ltp failed for {symbol}: {e}")
        return None

    def get_historical_candles(
        self,
        symbol:    str,
        exchange:  str,
        timeframe: str,
        from_date: str,
        to_date:   str,
    ) -> list[dict]:
        """
        Fetch OHLCV candles from SmartAPI.
        from_date / to_date format: "YYYY-MM-DD HH:MM"
        """
        self._require_connection()
        try:
            token  = self._get_token(symbol)
            tf     = TIMEFRAME_MAP.get(timeframe, "FIVE_MINUTE")
            params = {
                "exchange":     exchange,
                "symboltoken":  token,
                "interval":     tf,
                "fromdate":     from_date + " 09:15",
                "todate":       to_date   + " 15:30",
            }
            data = self._smart_api.getCandleData(params)
            if not data.get("status"):
                log.warning(f"getCandleData returned error: {data.get('message')}")
                return []

            candles = []
            for row in data.get("data", []):
                # SmartAPI returns [timestamp, open, high, low, close, volume]
                candles.append({
                    "timestamp": row[0],
                    "open":      float(row[1]),
                    "high":      float(row[2]),
                    "low":       float(row[3]),
                    "close":     float(row[4]),
                    "volume":    float(row[5]),
                })
            return candles

        except Exception as e:
            log.error(f"get_historical_candles failed: {e}")
            return []

    def get_option_chain(self, symbol: str, expiry: str) -> list[dict]:
        """
        Fetch live options chain.
        expiry format: "DDMMMYYYY" e.g. "21AUG2026"
        """
        self._require_connection()
        try:
            data = self._smart_api.getOptionChainDetails(
                exchange="NFO",
                tradingsymbol=symbol,
                expiry=expiry,
                strikePrice="",
                productType="OPTIDX",
            )
            if not data.get("status"):
                return []

            chain = []
            for row in data.get("data", []):
                chain.append({
                    "strike":        row.get("strikePrice"),
                    "option_type":   row.get("optionType"),   # CE / PE
                    "ltp":           row.get("ltp"),
                    "bid":           row.get("bidPrice"),
                    "ask":           row.get("askPrice"),
                    "oi":            row.get("openInterest"),
                    "change_in_oi":  row.get("changeinOpenInterest"),
                    "volume":        row.get("totalTradedVolume"),
                    "iv":            row.get("impliedVolatility"),
                    "delta":         row.get("delta"),
                    "gamma":         row.get("gamma"),
                    "theta":         row.get("theta"),
                    "vega":          row.get("vega"),
                })
            return chain

        except Exception as e:
            log.error(f"get_option_chain failed: {e}")
            return []

    # ── Account ───────────────────────────────────────────────────────────────

    def get_balance(self) -> dict:
        """Available funds and margin details."""
        self._require_connection()
        try:
            data = self._smart_api.rmsLimit()
            if data.get("status"):
                d = data["data"]
                return {
                    "capital":          float(d.get("availablecash",    0)),
                    "available_margin": float(d.get("net",              0)),
                    "used_margin":      float(d.get("utiliseddebits",   0)),
                }
        except Exception as e:
            log.error(f"get_balance failed: {e}")
        return {"capital": 0, "available_margin": 0, "used_margin": 0}

    def get_positions(self) -> list[dict]:
        """All open positions from Angel One (source of truth after crash)."""
        self._require_connection()
        try:
            data = self._smart_api.position()
            if data.get("status") and data.get("data"):
                positions = []
                for p in data["data"]:
                    positions.append({
                        "symbol":        p.get("tradingsymbol"),
                        "direction":     "LONG" if int(p.get("netqty", 0)) > 0 else "SHORT",
                        "quantity":      abs(int(p.get("netqty", 0))),
                        "average_price": float(p.get("netprice", 0)),
                        "ltp":           float(p.get("ltp", 0)),
                        "pnl":           float(p.get("unrealised", 0)),
                        "product":       p.get("producttype"),
                    })
                return positions
        except Exception as e:
            log.error(f"get_positions failed: {e}")
        return []

    def get_orders(self) -> list[dict]:
        """All orders for current session."""
        self._require_connection()
        try:
            data = self._smart_api.orderBook()
            if data.get("status") and data.get("data"):
                return data["data"]
        except Exception as e:
            log.error(f"get_orders failed: {e}")
        return []

    # ── Order placement ───────────────────────────────────────────────────────

    def place_order(
        self,
        symbol:        str,
        exchange:      str,
        order_type:    str,
        direction:     str,       # BUY / SELL
        quantity:      int,
        price:         float = 0.0,
        trigger_price: float = 0.0,
        product:       str   = "MIS",
        variety:       str   = "NORMAL",
        tag:           str   = "",
    ) -> dict:
        """
        Place a live order.
        Returns order dict with order_id and status.

        SAFETY: This method is disabled unless ENABLE_LIVE_TRADING=true
        and TRADING_MODE=live in .env. Use PaperBroker for paper trading.
        """
        self._require_live_enabled()
        self._require_connection()

        token    = self._get_token(symbol)
        order_params = {
            "variety":          variety,
            "tradingsymbol":    symbol,
            "symboltoken":      token,
            "transactiontype":  direction,
            "exchange":         exchange,
            "ordertype":        self._map_order_type(order_type),
            "producttype":      PRODUCT_MAP.get(product, "INTRADAY"),
            "duration":         "DAY",
            "price":            str(price),
            "triggerprice":     str(trigger_price),
            "quantity":         str(quantity),
            "ordertag":         tag,
        }

        try:
            data = self._smart_api.placeOrder(order_params)
            if data.get("status"):
                order_id = data["data"]["orderid"]
                log.info(
                    f"[LIVE ORDER] {direction} {quantity} {symbol} "
                    f"@ ₹{price:.2f} | order_id={order_id}"
                )
                return {
                    "order_id":    order_id,
                    "status":      "PLACED",
                    "symbol":      symbol,
                    "direction":   direction,
                    "quantity":    quantity,
                    "price":       price,
                }
            else:
                log.error(f"Order placement failed: {data.get('message')}")
                return {"order_id": "", "status": "REJECTED", "message": data.get("message")}
        except Exception as e:
            log.error(f"place_order exception: {e}")
            return {"order_id": "", "status": "ERROR", "message": str(e)}

    def modify_order(
        self,
        order_id:      str,
        price:         float,
        trigger_price: float = 0.0,
        quantity:      int   = 0,
    ) -> dict:
        """Modify an existing open order."""
        self._require_live_enabled()
        self._require_connection()
        try:
            data = self._smart_api.modifyOrder({
                "variety":      "NORMAL",
                "orderid":      order_id,
                "price":        str(price),
                "triggerprice": str(trigger_price),
                "quantity":     str(quantity),
            })
            return {"status": "MODIFIED" if data.get("status") else "FAILED"}
        except Exception as e:
            log.error(f"modify_order failed: {e}")
            return {"status": "ERROR", "message": str(e)}

    def cancel_order(self, order_id: str, variety: str = "NORMAL") -> dict:
        """Cancel an open order."""
        self._require_live_enabled()
        self._require_connection()
        try:
            data = self._smart_api.cancelOrder(variety, order_id)
            return {"status": "CANCELLED" if data.get("status") else "FAILED"}
        except Exception as e:
            log.error(f"cancel_order failed: {e}")
            return {"status": "ERROR", "message": str(e)}

    def close_position(
        self, symbol: str, exchange: str, quantity: int, direction: str
    ) -> dict:
        """Market-close an open position."""
        close_dir = "SELL" if direction in ("BUY", "LONG") else "BUY"
        return self.place_order(
            symbol=symbol, exchange=exchange,
            order_type="MARKET", direction=close_dir,
            quantity=quantity, product="MIS",
        )

    # ── Crash recovery ────────────────────────────────────────────────────────

    def reconcile_positions(self, local_positions: dict) -> dict:
        """
        Spec section 49 — after crash/restart, fetch broker positions
        and compare against local state. Broker is source of truth.

        Returns:
          { "matched": [...], "missing_locally": [...], "extra_locally": [...] }
        """
        broker_positions = {p["symbol"]: p for p in self.get_positions()}
        local_symbols    = set(local_positions.keys())
        broker_symbols   = set(broker_positions.keys())

        return {
            "matched":          list(local_symbols & broker_symbols),
            "missing_locally":  list(broker_symbols - local_symbols),
            "extra_locally":    list(local_symbols  - broker_symbols),
            "broker_positions": broker_positions,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_token(self, symbol: str) -> str:
        """Return the SmartAPI symbol token. Add more symbols as needed."""
        return self._symbol_tokens.get(symbol.upper(), symbol)

    def _map_order_type(self, order_type: str) -> str:
        mapping = {
            "MARKET": "MARKET",
            "LIMIT":  "LIMIT",
            "SL":     "STOPLOSS_LIMIT",
            "SL-M":   "STOPLOSS_MARKET",
        }
        return mapping.get(order_type.upper(), "MARKET")

    def _require_connection(self):
        if not self.is_connected():
            raise RuntimeError(
                "AngelOneBroker not connected. Call connect() first."
            )

    def _require_live_enabled(self):
        """
        Safety gate (spec section 37).
        Order placement is blocked unless both env vars are set.
        """
        trading_mode     = os.getenv("TRADING_MODE",      "paper").lower()
        live_enabled     = os.getenv("ENABLE_LIVE_TRADING","false").lower()

        if trading_mode != "live" or live_enabled != "true":
            raise RuntimeError(
                "LIVE ORDER BLOCKED.\n"
                "To enable live trading, set in .env:\n"
                "  TRADING_MODE=live\n"
                "  ENABLE_LIVE_TRADING=true\n"
                "Only do this after completing paper trading (Phase 7)."
            )
