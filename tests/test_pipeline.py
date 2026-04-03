"""Integration tests for the main pipeline (update_all.py).

Uses an in-memory SQLite database to verify that:
- Phase 2 produces LivermoreState rows from inserted price data.
- Phase 3 produces signals from the full analysis chain.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db.models import Base, LivermoreState, Price, Signal
from db.repository import upsert_prices
from update_all import run_phase2, run_phase3
from signals.telegram_notifier import TelegramNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_session() -> tuple[Session, object]:
    """Create an in-memory SQLite engine + session with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = Session(engine)
    return session, engine


def _insert_test_prices(session: Session, symbol: str = "005930", market: str = "kr") -> None:
    """Insert 60 days of synthetic OHLCV data into the prices table."""
    np.random.seed(42)
    start = date(2026, 1, 5)
    dates = pd.bdate_range(start=start, periods=60)

    base = 50000.0
    closes = base + np.cumsum(np.random.randn(60) * 500)

    df = pd.DataFrame({
        "date": [d.date() for d in dates],
        "open": closes - np.random.rand(60) * 200,
        "high": closes + np.random.rand(60) * 300,
        "low": closes - np.random.rand(60) * 300,
        "close": closes,
        "volume": np.random.randint(500_000, 5_000_000, size=60),
    })

    upsert_prices(session, df, symbol, market)


def _make_config() -> dict:
    return {
        "markets": {
            "kr": {
                "watchlist": ["005930"],
                "indices": ["KOSPI"],
            },
            "us": {
                "watchlist": ["AAPL"],
                "indices": ["^GSPC"],
            },
        },
        "livermore": {
            "pivot_threshold_pct": 5.0,
            "volume_surge_ratio": 1.5,
            "lookback_days": 20,
            "false_breakout_confirm_days": 2,
        },
        "signals": {
            "min_confidence": 60,
        },
        "money_management": {
            "max_position_pct": 20,
            "split_buy_ratio": [50, 30, 20],
            "stop_loss_pct": 5.0,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPhase2:
    """Phase 2: Livermore analysis should produce LivermoreState rows."""

    def test_phase2_produces_livermore_states(self):
        session, engine = _create_test_session()
        _insert_test_prices(session, symbol="005930", market="kr")

        config = _make_config()
        start_date = date(2026, 1, 5).isoformat()
        end_date = date(2026, 4, 1).isoformat()

        # Patch get_session so pipeline uses our in-memory session
        with patch("update_all.get_session", return_value=session):
            run_phase2(config, "kr", start_date, end_date)

        states = session.execute(select(LivermoreState)).scalars().all()
        assert len(states) > 0, "Phase 2 should produce at least one LivermoreState"

        # All states should belong to our test symbol
        for s in states:
            assert s.symbol == "005930"
            assert s.market == "kr"
            assert s.column_state in {
                "neutral", "upward_trend", "downward_trend",
                "natural_reaction", "natural_rally",
                "secondary_rally", "secondary_reaction",
            }
            assert 0 <= s.trend_strength <= 100

        session.close()
        engine.dispose()


class TestPhase3:
    """Phase 3: Signal generation from analysis chain."""

    def test_phase3_produces_signals(self):
        session, engine = _create_test_session()
        _insert_test_prices(session, symbol="005930", market="kr")

        config = _make_config()
        start_date = date(2026, 1, 5).isoformat()
        end_date = date(2026, 4, 1).isoformat()

        notifier = TelegramNotifier()  # disabled — no env vars set

        with patch("update_all.get_session", return_value=session):
            # Run phase 2 first to populate states
            run_phase2(config, "kr", start_date, end_date)
            # Run phase 3
            signals = run_phase3(config, "kr", start_date, end_date, notifier)

        # Should return a list of signal dicts
        assert isinstance(signals, list)
        assert len(signals) > 0, "Phase 3 should produce at least one signal"

        for sig in signals:
            assert "symbol" in sig
            assert "signal_type" in sig
            assert sig["signal_type"] in ("buy", "sell", "watch")
            assert "confidence" in sig
            assert 0 <= sig["confidence"] <= 100

        # Signals should also be persisted in DB
        db_signals = session.execute(select(Signal)).scalars().all()
        assert len(db_signals) > 0

        session.close()
        engine.dispose()
