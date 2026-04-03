"""Tests for the PivotDetector pivot point detection engine."""

import pytest
import pandas as pd
import numpy as np
from datetime import date

from livermore_engine.pivot_points import PivotDetector


def _make_ohlcv(closes, volumes=None, start="2026-01-05"):
    """Create an OHLCV DataFrame from a list of close prices."""
    n = len(closes)
    dates = pd.bdate_range(start=start, periods=n)
    if volumes is None:
        volumes = [1_000_000] * n

    closes = np.array(closes, dtype=float)
    data = {
        "date": dates.date,
        "open": closes * 0.999,
        "high": closes * 1.005,
        "low": closes * 0.995,
        "close": closes,
        "volume": volumes,
    }
    return pd.DataFrame(data)


class TestPivotDetector:
    """Test suite for PivotDetector."""

    def test_no_pivot_in_flat_market(self):
        """Flat prices produce no breakout or breakdown pivots."""
        closes = [100.0] * 30
        df = _make_ohlcv(closes)
        detector = PivotDetector(lookback_days=10, volume_surge_ratio=1.5)
        result = detector.detect(df)
        pivot_rows = result[result["pivot_type"] != "none"]
        assert len(pivot_rows) == 0

    def test_breakout_pivot_detected(self):
        """Price above resistance with volume surge triggers a breakout."""
        # 20 days of flat, then a sharp rise with volume surge
        closes = [100.0] * 20 + [120.0]
        volumes = [1_000_000] * 20 + [3_000_000]
        df = _make_ohlcv(closes, volumes)
        detector = PivotDetector(lookback_days=20, volume_surge_ratio=1.5)
        result = detector.detect(df)
        breakouts = result[result["pivot_type"] == "breakout"]
        assert len(breakouts) >= 1
        assert breakouts.iloc[-1]["pivot_price"] == pytest.approx(120.0, rel=0.01)

    def test_breakdown_pivot_detected(self):
        """Price below support with volume surge triggers a breakdown."""
        closes = [100.0] * 20 + [80.0]
        volumes = [1_000_000] * 20 + [3_000_000]
        df = _make_ohlcv(closes, volumes)
        detector = PivotDetector(lookback_days=20, volume_surge_ratio=1.5)
        result = detector.detect(df)
        breakdowns = result[result["pivot_type"] == "breakdown"]
        assert len(breakdowns) >= 1
        assert breakdowns.iloc[-1]["pivot_price"] == pytest.approx(80.0, rel=0.01)

    def test_no_pivot_without_volume_surge(self):
        """Breakout price but normal volume does not trigger a pivot."""
        closes = [100.0] * 20 + [120.0]
        volumes = [1_000_000] * 21  # no surge
        df = _make_ohlcv(closes, volumes)
        detector = PivotDetector(lookback_days=20, volume_surge_ratio=1.5)
        result = detector.detect(df)
        pivots = result[result["pivot_type"] != "none"]
        assert len(pivots) == 0

    def test_false_breakout_filter(self):
        """Breakout then price falls back results in confirmed=False."""
        # Breakout on day 21, then price falls back below pivot on days 22-23
        closes = [100.0] * 20 + [120.0, 95.0, 90.0]
        volumes = [1_000_000] * 20 + [3_000_000, 1_000_000, 1_000_000]
        df = _make_ohlcv(closes, volumes)
        detector = PivotDetector(lookback_days=20, volume_surge_ratio=1.5, confirm_days=2)
        result = detector.detect(df)
        breakouts = result[result["pivot_type"] == "breakout"]
        assert len(breakouts) >= 1
        assert breakouts.iloc[-1]["confirmed"] == False  # noqa: E712

    def test_confirmed_breakout(self):
        """Breakout then price holds for confirm_days results in confirmed=True."""
        closes = [100.0] * 20 + [120.0, 125.0, 130.0]
        volumes = [1_000_000] * 20 + [3_000_000, 1_500_000, 1_500_000]
        df = _make_ohlcv(closes, volumes)
        detector = PivotDetector(lookback_days=20, volume_surge_ratio=1.5, confirm_days=2)
        result = detector.detect(df)
        breakouts = result[result["pivot_type"] == "breakout"]
        assert len(breakouts) >= 1
        assert breakouts.iloc[-1]["confirmed"] == True  # noqa: E712

    def test_consolidation_days_tracked(self):
        """consolidation_days column exists and contains non-negative integers."""
        closes = [100.0] * 30
        df = _make_ohlcv(closes)
        detector = PivotDetector(lookback_days=10)
        result = detector.detect(df)
        assert "consolidation_days" in result.columns
        assert (result["consolidation_days"] >= 0).all()

    def test_output_columns(self):
        """Output DataFrame has exactly the required 8 columns."""
        closes = [100.0] * 25
        df = _make_ohlcv(closes)
        detector = PivotDetector(lookback_days=10)
        result = detector.detect(df)
        expected_columns = [
            "date",
            "pivot_type",
            "pivot_price",
            "resistance",
            "support",
            "volume_ratio",
            "confirmed",
            "consolidation_days",
        ]
        assert list(result.columns) == expected_columns
