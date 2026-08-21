"""
Angel One Live Data Provider for Dashboard
Fetches real NIFTY/BANKNIFTY prices, option chain, and candles
using SmartAPI. Falls back to yfinance for US markets.
"""

import os, time, logging, datetime, threading
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# Shared state — background thread writes, UI reads
_state = {
    "prices":     {},
    "candles":    {},
    "option_chain": {},
    "connected":  False,
    "last_update": 0,
    "error":      "",
}
_lock   = threading.Lock()
_smart  = None


def get_state():
    with _lock:
        return dict(_state)


def _connect():
    global _smart
    try:
        from SmartApi import SmartConnect
        import pyotp
        api_key   = os.getenv("ANGEL_API_KEY", "")
        client_id = os.getenv("ANGEL_CLIENT_ID", "")
        password  = os.getenv("ANGEL_PASSWORD", "")
        totp_sec  = os.getenv("ANGEL_TOTP_SECRET", "")
        if not all([api_key, client_id, password, totp_sec]):
            with _lock:
                _state["error"] = "Missing Angel One credentials in .env"
            return False
        _smart = SmartConnect(api_key=api_key)
        totp   = pyotp.TOTP(totp_sec).now()
        data   = _smart.generateSession(client_id, password, totp)
        if not data.get("status"):
            with _lock:
                _state["error"] = f"Login failed: {data.get('message','')}"
            return False
        with _lock:
            _state["connected"] = True
            _state["error"]     = ""
        log.info("Angel One connected successfully")
        return True
    except ImportError:
        with _lock:
            _state["error"] = "smartapi-python not installed. Run: pip install smartapi-python pyotp"
        return False
    except Exception as e:
        with _lock:
            _state["error"] = f"Connection error: {str(e)}"
        return False


def _fetch_ltp(symbol, token, exchange="NSE"):
    global _smart
    try:
        data = _smart.ltpData(exchange, symbol, token)
        if data and data.get("status"):
            return float(data["data"]["ltp"])
    except Exception as e:
        log.warning(f"LTP fetch failed for {symbol}: {e}")
    return None


def _fetch_candles(symbol, token, exchange="NSE", tf="FIVE_MINUTE"):
    global _smart
    try:
        today = datetime.date.today()
        from_dt = f"{today} 09:15"
        to_dt   = f"{today} 15:30"
        params  = {
            "exchange":    exchange,
            "symboltoken": token,
            "interval":    tf,
            "fromdate":    from_dt,
            "todate":      to_dt,
        }
        data = _smart.getCandleData(params)
        if data and data.get("status") and data.get("data"):
            rows = data["data"]
            return {
                "time":  [r[0] for r in rows],
                "open":  [float(r[1]) for r in rows],
                "high":  [float(r[2]) for r in rows],
                "low":   [float(r[3]) for r in rows],
                "close": [float(r[4]) for r in rows],
                "vol":   [float(r[5]) for r in rows],
            }
    except Exception as e:
        log.warning(f"Candle fetch failed for {symbol}: {e}")
    return None


def _fetch_us_markets():
    """Fetch US market prices via yfinance."""
    try:
        import yfinance as yf
        tickers = {"S&P 500":"^GSPC","NASDAQ":"^IXIC","DOW JONES":"^DJI"}
        result  = {}
        for name, ticker in tickers.items():
            try:
                t = yf.Ticker(ticker)
                h = t.history(period="2d", interval="5m")
                if not h.empty:
                    last = float(h["Close"].iloc[-1])
                    prev = float(h["Close"].iloc[0])
                    chg  = round((last-prev)/prev*100, 2)
                    result[name] = {
                        "price": round(last, 2),
                        "chg":   chg,
                        "high":  round(float(h["High"].max()), 2),
                        "low":   round(float(h["Low"].min()),  2),
                        "candles": {
                            "time":  [str(i) for i in h.index.tolist()],
                            "open":  h["Open"].tolist(),
                            "high":  h["High"].tolist(),
                            "low":   h["Low"].tolist(),
                            "close": h["Close"].tolist(),
                            "vol":   h["Volume"].tolist(),
                        }
                    }
            except Exception:
                pass
        return result
    except ImportError:
        return {}


# NSE instrument tokens
NSE_TOKENS = {
    "NIFTY 50":   ("Nifty 50",   "99926000", "NSE"),
    "BANKNIFTY":  ("Nifty Bank", "99926009", "NSE"),
    "INDIA VIX":  ("India VIX",  "99919000", "NSE"),
}


def _fetch_loop():
    """Background thread — fetches data every 5 seconds."""
    global _smart
    connected = _connect()
    while True:
        try:
            if not connected:
                time.sleep(30)
                connected = _connect()
                continue

            prices = {}

            # Indian markets via Angel One
            for name, (sym, token, exch) in NSE_TOKENS.items():
                ltp = _fetch_ltp(sym, token, exch)
                if ltp:
                    prev = _state["prices"].get(name, {}).get("price", ltp)
                    chg  = round((ltp - prev) / prev * 100, 2) if prev else 0
                    candles = _fetch_candles(sym, token, exch)
                    if candles and len(candles["close"]) > 1:
                        open_p = candles["open"][0]
                        chg    = round((ltp - open_p) / open_p * 100, 2)
                        hi     = max(candles["high"])
                        lo     = min(candles["low"])
                    else:
                        hi = ltp * 1.005
                        lo = ltp * 0.995
                    prices[name] = {
                        "price":   round(ltp, 2),
                        "chg":     chg,
                        "chg_abs": round(ltp - (candles["open"][0] if candles else ltp), 2),
                        "high":    round(hi, 2),
                        "low":     round(lo, 2),
                        "candles": candles,
                    }

            # US markets via yfinance
            us = _fetch_us_markets()
            prices.update(us)

            with _lock:
                _state["prices"]      = prices
                _state["last_update"] = time.time()
                _state["connected"]   = True
                _state["error"]       = ""

        except Exception as e:
            log.error(f"Fetch loop error: {e}")
            with _lock:
                _state["error"]     = str(e)
                _state["connected"] = False
            connected = False

        time.sleep(5)


def start(interval=5):
    """Start the background data fetch thread."""
    t = threading.Thread(target=_fetch_loop, daemon=True)
    t.start()
    log.info("Angel One live data thread started")
