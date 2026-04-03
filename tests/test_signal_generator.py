"""Tests for SignalGenerator signal generation and prioritization."""

import pytest
import pandas as pd
import numpy as np
from datetime import date

from signals.signal_generator import SignalGenerator


def _make_engine_results(
    column_state="upward_trend",
    confirmed=True,
    volume_surge=True,
    price=72500.0,
    rsi=62.0,
    trend_direction="up",
    trend_strength=65.0,
    volume_ratio=2.0,
    consolidation_days=8,
    pivot_type="breakout",
):
    """Create mock engine results dict mimicking real pipeline output."""
    mk_df = pd.DataFrame(
        [
            {
                "date": date(2026, 3, 20),
                "column_state": column_state,
                "reference_pivot_price": 70000.0,
                "trend_direction": trend_direction,
                "trend_strength": trend_strength,
                "trend_duration_days": 12,
            }
        ]
    )

    pivots_df = pd.DataFrame(
        [
            {
                "date": date(2026, 3, 20),
                "pivot_type": pivot_type,
                "pivot_price": price,
                "resistance": 72000.0,
                "support": 68000.0,
                "volume_ratio": volume_ratio,
                "confirmed": confirmed,
                "consolidation_days": consolidation_days,
            }
        ]
    )

    vol_df = pd.DataFrame(
        [
            {
                "date": date(2026, 3, 20),
                "volume_ratio": volume_ratio,
                "volume_surge": volume_surge,
                "divergence": "none",
                "climax": False,
            }
        ]
    )

    return {
        "market_key": mk_df,
        "pivots": pivots_df,
        "volume": vol_df,
        "price": price,
        "rsi": rsi,
    }


class TestSignalGenerator:
    """Test suite for SignalGenerator."""

    def test_buy_signal_generated(self):
        """Good conditions (breakout, confirmed, volume surge, RSI<=70) produce a buy signal with confidence >= 60."""
        gen = SignalGenerator(min_confidence=60.0)
        results = _make_engine_results()
        signals = gen.generate("005930", results, market_direction="up")

        buy_signals = [s for s in signals if s["signal_type"] == "buy"]
        assert len(buy_signals) == 1
        assert buy_signals[0]["confidence"] >= 60.0
        assert buy_signals[0]["symbol"] == "005930"
        assert buy_signals[0]["price"] == 72500.0

    def test_watch_signal_when_unconfirmed(self):
        """Unconfirmed pivot results in a watch signal, not buy."""
        gen = SignalGenerator(min_confidence=60.0)
        results = _make_engine_results(confirmed=False)
        signals = gen.generate("005930", results, market_direction="up")

        signal_types = [s["signal_type"] for s in signals]
        assert "buy" not in signal_types
        assert "watch" in signal_types

    def test_no_buy_in_down_market(self):
        """In a down market, no buy signals should be emitted."""
        gen = SignalGenerator(min_confidence=60.0)
        results = _make_engine_results()
        signals = gen.generate("005930", results, market_direction="down")

        buy_signals = [s for s in signals if s["signal_type"] == "buy"]
        assert len(buy_signals) == 0

    def test_watch_when_rsi_overbought(self):
        """RSI > 70 should result in a watch signal even with good breakout conditions."""
        gen = SignalGenerator(min_confidence=60.0)
        results = _make_engine_results(rsi=75.0)
        signals = gen.generate("005930", results, market_direction="up")

        signal_types = [s["signal_type"] for s in signals]
        assert "buy" not in signal_types
        assert "watch" in signal_types

    def test_confidence_calculation(self):
        """Confidence score must be between 0 and 100."""
        gen = SignalGenerator(min_confidence=0.0)
        results = _make_engine_results()
        signals = gen.generate("005930", results, market_direction="up")

        for s in signals:
            assert 0.0 <= s["confidence"] <= 100.0

    def test_signal_priority_ordering(self):
        """prioritize() sorts signals by descending confidence, then descending volume_ratio."""
        gen = SignalGenerator(min_confidence=0.0)
        signals = [
            {"signal_type": "buy", "confidence": 70.0, "volume_ratio": 1.5},
            {"signal_type": "buy", "confidence": 85.0, "volume_ratio": 2.0},
            {"signal_type": "watch", "confidence": 85.0, "volume_ratio": 3.0},
            {"signal_type": "sell", "confidence": 60.0, "volume_ratio": 1.0},
        ]
        ordered = gen.prioritize(signals)
        # First two have confidence 85 — higher volume_ratio first
        assert ordered[0]["confidence"] == 85.0
        assert ordered[0]["volume_ratio"] == 3.0
        assert ordered[1]["confidence"] == 85.0
        assert ordered[1]["volume_ratio"] == 2.0
        assert ordered[2]["confidence"] == 70.0
        assert ordered[3]["confidence"] == 60.0
