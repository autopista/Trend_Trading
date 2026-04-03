"""Tests for the Livermore Market Key 6-state analysis engine."""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from livermore_engine.market_key import MarketKey


def _make_ohlcv(prices, volumes=None):
    """Create an OHLCV DataFrame from a list of close prices."""
    n = len(prices)
    dates = pd.bdate_range(start=date(2026, 1, 5), periods=n)
    if volumes is None:
        volumes = [1_000_000] * n

    closes = np.array(prices, dtype=float)
    data = {
        "date": dates.date,
        "open": closes * 0.999,
        "high": closes * 1.005,
        "low": closes * 0.995,
        "close": closes,
        "volume": volumes,
    }
    return pd.DataFrame(data)


class TestMarketKey:
    """Tests for MarketKey engine."""

    def test_initial_state_is_neutral(self):
        """Flat prices should produce neutral state."""
        prices = [100.0] * 10
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)
        assert result["column_state"].iloc[0] == "neutral"
        assert all(result["column_state"] == "neutral")

    def test_upward_trend_on_breakout(self):
        """Steady rise >5% should produce upward_trend with direction 'up'."""
        # Start at 100, rise to ~108 over several days
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108]
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)

        states = result["column_state"].tolist()
        assert "upward_trend" in states

        # Where upward_trend appears, direction should be "up"
        up_rows = result[result["column_state"] == "upward_trend"]
        assert all(up_rows["trend_direction"] == "up")

    def test_downward_trend_on_breakdown(self):
        """Steady drop >5% should produce downward_trend with direction 'down'."""
        prices = [100, 99, 98, 97, 96, 95, 94, 93, 92]
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)

        states = result["column_state"].tolist()
        assert "downward_trend" in states

        down_rows = result[result["column_state"] == "downward_trend"]
        assert all(down_rows["trend_direction"] == "down")

    def test_natural_reaction_during_uptrend(self):
        """Rise then pullback should produce natural_reaction in states."""
        # Rise enough for upward_trend, then pull back > half_threshold (2.5%)
        prices = [100, 102, 104, 106, 108, 110, 107, 105, 104]
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)

        states = result["column_state"].tolist()
        assert "natural_reaction" in states

    def test_natural_rally_during_downtrend(self):
        """Drop then bounce should produce natural_rally in states."""
        # Drop enough for downward_trend, then bounce > half_threshold (2.5%)
        prices = [100, 98, 96, 94, 92, 90, 93, 95, 96]
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)

        states = result["column_state"].tolist()
        assert "natural_rally" in states

    def test_trend_duration_increments(self):
        """Rising prices should show increasing trend_duration_days."""
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)

        # Once a trend is established, duration should increase
        up_rows = result[result["column_state"] == "upward_trend"]
        if len(up_rows) > 1:
            durations = up_rows["trend_duration_days"].tolist()
            assert durations == sorted(durations), "Duration should be non-decreasing"
            assert durations[-1] > durations[0], "Duration should increase over time"

    def test_trend_strength_calculated(self):
        """All trend_strength values should be between 0 and 100."""
        prices = [100, 102, 104, 106, 108, 110, 107, 105, 103, 101, 99]
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)

        assert all(result["trend_strength"] >= 0)
        assert all(result["trend_strength"] <= 100)

    def test_output_columns(self):
        """Output should have exactly 6 columns."""
        prices = [100, 101, 102, 103, 104]
        ohlcv = _make_ohlcv(prices)
        mk = MarketKey(pivot_threshold_pct=5.0)
        result = mk.analyze(ohlcv)

        expected_columns = [
            "date",
            "column_state",
            "reference_pivot_price",
            "trend_direction",
            "trend_strength",
            "trend_duration_days",
        ]
        assert list(result.columns) == expected_columns
