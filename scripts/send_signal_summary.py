"""Send a summary of today's signals to Telegram."""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / "config" / ".env")

from db.database import get_session
from db.models import Signal
from signals.telegram_notifier import TelegramNotifier


def _fetch_today(market: str, today: date) -> list[Signal]:
    with get_session() as session:
        stmt = (
            select(Signal)
            .where(Signal.market == market, Signal.date == today)
            .order_by(Signal.signal_type, Signal.confidence.desc())
        )
        return list(session.scalars(stmt).all())


def _format_summary(
    market: str,
    signals: list[Signal],
    today: date,
    notifier: TelegramNotifier,
) -> str:
    currency = "₩" if market == "kr" else "$"
    flag = "🇰🇷" if market == "kr" else "🇺🇸"

    buys = [s for s in signals if s.signal_type == "buy"]
    sells = [s for s in signals if s.signal_type == "sell"]
    watches = [s for s in signals if s.signal_type == "watch"]

    lines = [
        f"{flag} {market.upper()} 시그널 요약 — {today}",
        "━━━━━━━━━━━━━━━━━━",
        f"🟢 매수 {len(buys)}  🔴 매도 {len(sells)}  👀 관찰 {len(watches)}",
        "",
    ]

    def _block(label: str, emoji: str, items: list[Signal], limit: int = 10) -> None:
        if not items:
            return
        lines.append(f"{emoji} {label} TOP {min(limit, len(items))}")
        for s in items[:limit]:
            lines.append(
                f"  • {notifier.display_symbol(s.symbol)} — "
                f"{currency}{s.price:,.2f} (신뢰도 {s.confidence:.0f}%)"
            )
        lines.append("")

    _block("매수", "🟢", buys)
    _block("매도", "🔴", sells)

    return "\n".join(lines).rstrip()


async def main() -> None:
    today = date.today()
    notifier = TelegramNotifier()
    if not notifier.enabled:
        print("TelegramNotifier disabled — check TELEGRAM_BOT_TOKEN/CHAT_ID")
        return

    for market in ("kr", "us"):
        signals = _fetch_today(market, today)
        if not signals:
            print(f"No {market} signals for {today}")
            continue
        text = _format_summary(market, signals, today, notifier)
        await notifier._send(text)
        print(f"Sent {market} summary ({len(signals)} signals)")


if __name__ == "__main__":
    asyncio.run(main())
