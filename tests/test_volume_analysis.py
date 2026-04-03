"""Tests for the VolumeAnalyzer volume analysis engine."""

import pytest
import pandas as pd
import numpy as np
from datetime import date

from livermore_engine.volume_analysis import VolumeAnalyzer


def _make_ohlcv(closes, volumes, start="2026-01-05"):
    """Create an OHLCV DataFrame from lists of close prices and volumes."""
    n = len(closes)
    dates = pd.bdate_range(start=start, periods=n)
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


class TestVolumeAnalyzer:
    """Test suite for VolumeAnalyzer."""

    def test_volume_surge_detected(self):
        """Last day volume 2x average triggers surge=True."""
        # 20 days of normal volume, then last day at 2x
        closes = [100.0] * 21
        volumes = [1_000_000] * 20 + [2_000_000]
        df = _make_ohlcv(closes, volumes)
        analyzer = VolumeAnalyzer(lookback_days=20, surge_ratio=1.5)
        result = analyzer.analyze(df)
        assert result.iloc[-1]["volume_surge"] == True  # noqa: E712

    def test_no_surge_below_threshold(self):
        """Flat volume does not trigger surge."""
        closes = [100.0] * 21
        volumes = [1_000_000] * 21
        df = _make_ohlcv(closes, volumes)
        analyzer = VolumeAnalyzer(lookback_days=20, surge_ratio=1.5)
        result = analyzer.analyze(df)
        assert result.iloc[-1]["volume_surge"] == False  # noqa: E712

    def test_price_volume_divergence_bearish(self):
        """Prices rising for 5 days while volumes declining yields bearish divergence."""
        # 20 days of base data, then 5 days of rising prices + declining volumes
        base_closes = [100.0] * 20
        rising_closes = [101.0, 102.0, 103.0, 104.0, 105.0]
        closes = base_closes + rising_closes

        base_volumes = [1_000_000] * 20
        declining_volumes = [900_000, 800_000, 700_000, 600_000, 500_000]
        volumes = base_volumes + declining_volumes

        df = _make_ohlcv(closes, volumes)
        analyzer = VolumeAnalyzer(lookback_days=20)
        result = analyzer.analyze(df)
        assert result.iloc[-1]["divergence"] == "bearish"

    def test_climax_volume(self):
        """Volume at 5x average triggers climax=True."""
        closes = [100.0] * 21
        volumes = [1_000_000] * 20 + [5_000_000]
        df = _make_ohlcv(closes, volumes)
        analyzer = VolumeAnalyzer(lookback_days=20, climax_ratio=3.0)
        result = analyzer.analyze(df)
        assert result.iloc[-1]["climax"] == True  # noqa: E712

    def test_output_columns(self):
        """Output DataFrame has exactly the 5 required columns."""
        closes = [100.0] * 25
        volumes = [1_000_000] * 25
        df = _make_ohlcv(closes, volumes)
        analyzer = VolumeAnalyzer(lookback_days=20)
        result = analyzer.analyze(df)
        expected_columns = ["date", "volume_ratio", "volume_surge", "divergence", "climax"]
        assert list(result.columns) == expected_columns
