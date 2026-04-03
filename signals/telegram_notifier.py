"""Telegram notification service for trading signals.

Sends formatted signal alerts and error messages to a configured
Telegram chat via the python-telegram-bot library.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trading signal notifications to Telegram.

    Reads ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` from
    environment variables.  If either is missing the notifier is
    disabled and all send calls become no-ops.
    """

    def __init__(self) -> None:
        self.token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.enabled: bool = bool(self.token and self.chat_id)

        if not self.enabled:
            logger.warning(
                "TelegramNotifier disabled — TELEGRAM_BOT_TOKEN or "
                "TELEGRAM_CHAT_ID not set"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_signal(self, signal: dict, market: str) -> None:
        """Format and send a trading signal message.

        Args:
            signal: Dict with keys symbol, signal_type, price,
                target_price, stop_price, confidence, reason.
            market: ``"kr"`` or ``"us"``.
        """
        text = self._format_message(signal, market)
        await self._send(text)

    async def send_error(self, message: str) -> None:
        """Send an error notification.

        Args:
            message: Human-readable error description.
        """
        text = f"⚠️ 오류 알림\n━━━━━━━━━━━━━━━━━━\n{message}"
        await self._send(text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_message(self, signal: dict, market: str) -> str:
        """Build a formatted Telegram message from a signal dict.

        Args:
            signal: Signal dictionary.
            market: ``"kr"`` or ``"us"``.

        Returns:
            Formatted message string with emoji and Korean text.
        """
        signal_type = signal.get("signal_type", "watch")
        symbol = signal.get("symbol", "???")
        price = signal.get("price", 0)
        target = signal.get("target_price")
        stop = signal.get("stop_price")
        confidence = signal.get("confidence", 0)
        reason = signal.get("reason", "")

        currency = "₩" if market.lower() == "kr" else "$"

        if signal_type == "buy":
            emoji = "🟢"
            label = "매수 시그널"
        elif signal_type == "sell":
            emoji = "🔴"
            label = "매도 시그널"
        else:
            emoji = "👀"
            label = "관찰 시그널"

        lines = [
            f"{emoji} {label} — {symbol}",
            "━━━━━━━━━━━━━━━━━━",
            f"💰 현재가: {currency}{price:,.2f}",
        ]

        if target is not None and price:
            target_pct = (target - price) / price * 100
            lines.append(
                f"🎯 목표가: {currency}{target:,.2f} ({target_pct:+.1f}%)"
            )

        if stop is not None and price:
            stop_pct = (stop - price) / price * 100
            lines.append(
                f"🛑 손절가: {currency}{stop:,.2f} ({stop_pct:+.1f}%)"
            )

        lines.append(f"📈 신뢰도: {confidence:.0f}%")
        lines.append(f"📋 사유: {reason}")

        return "\n".join(lines)

    async def _send(self, text: str) -> None:
        """Send *text* to the configured Telegram chat.

        Errors are logged but never re-raised so that notification
        failures do not crash the pipeline.
        """
        if not self.enabled:
            logger.debug("Telegram disabled; skipping message")
            return

        try:
            from telegram import Bot

            bot = Bot(token=self.token)
            await bot.send_message(chat_id=self.chat_id, text=text)
            logger.info("Telegram message sent (%d chars)", len(text))
        except Exception:
            logger.exception("Failed to send Telegram message")
