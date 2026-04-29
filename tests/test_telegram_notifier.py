"""Unit tests for ``TelegramNotifier`` formatting helpers."""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

from signals.telegram_notifier import TelegramNotifier


def _make_notifier(name_map: dict | None = None) -> TelegramNotifier:
    notifier = TelegramNotifier(name_map=name_map or {})
    notifier.enabled = True
    notifier._send = AsyncMock()  # type: ignore[method-assign]
    return notifier


def test_notify_pipeline_complete_counts_signal_types() -> None:
    notifier = _make_notifier()
    signals = (
        [{"signal_type": "buy"}] * 2
        + [{"signal_type": "sell"}] * 1
        + [{"signal_type": "watch"}] * 5
    )
    asyncio.run(
        notifier.notify_pipeline_complete("kr", signals, run_date=date(2026, 4, 29))
    )

    sent = notifier._send.await_args.args[0]
    assert "🇰🇷 KR 점검 완료 — 2026-04-29" in sent
    assert "매수 2" in sent
    assert "매도 1" in sent
    assert "관찰 5" in sent


def test_notify_pipeline_complete_zero_signals() -> None:
    notifier = _make_notifier()
    asyncio.run(
        notifier.notify_pipeline_complete("us", [], run_date=date(2026, 4, 29))
    )

    sent = notifier._send.await_args.args[0]
    assert "🇺🇸 US 점검 완료 — 2026-04-29" in sent
    assert "매수 0" in sent
    assert "매도 0" in sent
    assert "관찰 0" in sent


def test_notify_pipeline_complete_ignores_unknown_signal_types() -> None:
    notifier = _make_notifier()
    signals = [
        {"signal_type": "buy"},
        {"signal_type": "noise"},  # unknown — should be ignored
        {},  # missing signal_type — defaults to "watch"
    ]
    asyncio.run(
        notifier.notify_pipeline_complete("kr", signals, run_date=date(2026, 4, 29))
    )

    sent = notifier._send.await_args.args[0]
    assert "매수 1" in sent
    assert "매도 0" in sent
    assert "관찰 1" in sent  # the empty dict counted as watch
