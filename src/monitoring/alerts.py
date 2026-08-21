"""
Alert System (Spec section 32)
Sends alerts via Telegram and console.
Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
Console alerts always work with no config needed.
"""

import logging
import datetime
import os
import json
import urllib.request
import urllib.parse
from typing import Optional
import pytz

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class AlertSystem:
    """
    Multi-channel alert dispatcher.
    Channels: console (always), Telegram (if configured).
    """

    EMOJI = {
        "SIGNAL_GENERATED":  "📊",
        "BUY":               "🟢",
        "SELL":              "🔴",
        "TARGET":            "🎯",
        "STOP_LOSS":         "🛑",
        "STOP_MODIFIED":     "✏️",
        "DAILY_LOSS_LIMIT":  "⚠️",
        "BROKER_ERROR":      "❌",
        "DATA_ERROR":        "⚠️",
        "SYSTEM_ERROR":      "🆘",
        "SESSION_START":     "🔔",
        "SESSION_END":       "📋",
        "NO_TRADE":          "⏸️",
        "PAPER_TRADE":       "📝",
    }

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        console: bool = True,
    ):
        self.token    = telegram_token   or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id  = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID",   "")
        self.console  = console
        self._telegram_enabled = bool(self.token and self.chat_id)

        if self._telegram_enabled:
            log.info("AlertSystem: Telegram enabled")
        else:
            log.info("AlertSystem: Console only (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID for Telegram)")

    def send(self, event_type: str, message: str, data: dict = None) -> bool:
        """Send an alert. Returns True if at least one channel succeeded."""
        emoji    = self.EMOJI.get(event_type, "📌")
        ts       = datetime.datetime.now(IST).strftime("%H:%M:%S")
        full_msg = f"{emoji} [{ts}] {event_type}\n{message}"

        if data:
            # Append key fields
            extra = []
            for k in ["symbol","direction","confidence","net_pnl","exit_reason","market_regime"]:
                if k in data:
                    val = data[k]
                    if isinstance(val, float):
                        val = f"{val:,.2f}"
                    extra.append(f"  {k}: {val}")
            if extra:
                full_msg += "\n" + "\n".join(extra)

        success = False
        if self.console:
            self._console_alert(event_type, full_msg)
            success = True
        if self._telegram_enabled:
            success = self._telegram_alert(full_msg) or success

        return success

    def send_signal(self, signal: dict) -> bool:
        """Formatted alert for a new trading signal."""
        sym  = signal.get("underlying", "")
        dec  = signal.get("decision", "")
        conf = signal.get("confidence", 0)
        strat= signal.get("strategy", "")
        reg  = signal.get("market_regime", "")
        sl   = signal.get("stop_loss")
        tgt  = signal.get("target")
        rr   = signal.get("risk_reward", 0)

        msg = (
            f"{sym} | {dec} | conf={conf:.0f}%\n"
            f"Strategy: {strat}\n"
            f"Regime: {reg}\n"
        )
        if sl and tgt:
            msg += f"SL: {sl:.0f}  TGT: {tgt:.0f}  R:R 1:{rr}\n"

        reasons = signal.get("reasons", [])
        if reasons:
            msg += "Reasons:\n" + "\n".join(f"  • {r}" for r in reasons[:3])

        return self.send("SIGNAL_GENERATED", msg)

    def send_trade_opened(self, trade: dict) -> bool:
        msg = (
            f"{trade.get('symbol')} {trade.get('direction')}\n"
            f"Entry: ₹{trade.get('entry_price', 0):,.2f}\n"
            f"SL: ₹{trade.get('stop_loss', 0):,.2f}  "
            f"TGT: ₹{trade.get('target', 0):,.2f}"
        )
        return self.send("PAPER_TRADE", msg, trade)

    def send_trade_closed(self, trade: dict) -> bool:
        pnl    = trade.get("net_pnl", 0)
        reason = trade.get("exit_reason", "")
        event  = "TARGET" if reason == "TARGET" else "STOP_LOSS" if reason == "STOP_LOSS" else "PAPER_TRADE"
        msg    = (
            f"{trade.get('symbol')} CLOSED | {reason}\n"
            f"P&L: ₹{pnl:+,.0f}"
        )
        return self.send(event, msg, trade)

    def send_session_summary(self, summary: dict) -> bool:
        msg = (
            f"Session complete\n"
            f"Trades:   {summary.get('trades', 0)}\n"
            f"Win rate: {summary.get('win_rate', 0)}%\n"
            f"P&L:      ₹{summary.get('session_pnl', 0):+,.0f}"
        )
        return self.send("SESSION_END", msg)

    def send_risk_alert(self, reason: str) -> bool:
        return self.send("DAILY_LOSS_LIMIT", reason)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _console_alert(self, event_type: str, message: str):
        emoji = self.EMOJI.get(event_type, "📌")
        border = "─" * 50
        print(f"\n{border}")
        print(message)
        print(border)

    def _telegram_alert(self, message: str) -> bool:
        try:
            url     = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = json.dumps({
                "chat_id":    self.chat_id,
                "text":       message,
                "parse_mode": "HTML",
            }).encode("utf-8")
            req  = urllib.request.Request(url, data=payload,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            log.warning(f"Telegram alert failed: {e}")
            return False
