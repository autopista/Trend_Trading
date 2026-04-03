"""Volume analysis with surge detection, price-volume divergence, and climax detection.

Analyzes volume patterns relative to historical averages to identify
volume surges, climax events, and bearish/bullish divergences between
price and volume trends.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


class VolumeAnalyzer:
    """Analyze volume patterns for surge, divergence, and climax signals.

    Parameters
    ----------
    lookback_days : int
        Number of prior days used to compute average volume.
    surge_ratio : float
        Minimum volume_ratio to flag a volume surge.
    climax_ratio : float
        Minimum volume_ratio to flag a volume climax (extreme volume).
    """

    def __init__(
        self,
        lookback_days: int = 20,
        surge_ratio: float = 1.5,
        climax_ratio: float = 3.0,
    ) -> None:
        self.lookback_days = lookback_days
        self.surge_ratio = surge_ratio
        self.climax_ratio = climax_ratio

    def analyze(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Analyze volume patterns in OHLCV data.

        Parameters
        ----------
        ohlcv : pd.DataFrame
            DataFrame with columns [date, open, high, low, close, volume].

        Returns
        -------
        pd.DataFrame
            DataFrame with columns [date, volume_ratio, volume_surge, divergence, climax].
        """
        df = ohlcv.copy()

        # Volume ratio: current volume / rolling average of lookback window
        avg_volume = df["volume"].rolling(window=self.lookback_days, min_periods=1).mean().shift(1)
        df["volume_ratio"] = df["volume"] / avg_volume
        # First row has no prior data; default to 1.0
        df["volume_ratio"] = df["volume_ratio"].fillna(1.0)

        # Volume surge
        df["volume_surge"] = df["volume_ratio"] >= self.surge_ratio

        # Climax
        df["climax"] = df["volume_ratio"] >= self.climax_ratio

        # Divergence detection
        df["divergence"] = "none"
        if len(df) >= 5:
            close_diff = df["close"].diff()
            volume_diff = df["volume"].diff()

            for i in range(4, len(df)):
                window = slice(i - 3, i + 1)  # 4 diffs cover 5 consecutive days
                price_diffs = close_diff.iloc[window]
                vol_diffs = volume_diff.iloc[window]

                prices_rising = (price_diffs > 0).all()
                prices_falling = (price_diffs < 0).all()
                volumes_declining = (vol_diffs < 0).all()

                if prices_rising and volumes_declining:
                    df.iloc[i, df.columns.get_loc("divergence")] = "bearish"
                elif prices_falling and volumes_declining:
                    df.iloc[i, df.columns.get_loc("divergence")] = "bullish"

        return df[["date", "volume_ratio", "volume_surge", "divergence", "climax"]]
