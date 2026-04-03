"""Pivot point detection with false breakout filtering.

Detects breakout and breakdown pivots based on price exceeding
resistance/support levels with accompanying volume surges.
Includes confirmation logic and consolidation day tracking.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


class PivotDetector:
    """Detect pivot points (breakouts/breakdowns) with false breakout filtering.

    Parameters
    ----------
    lookback_days : int
        Number of prior days used to compute resistance and support levels.
    volume_surge_ratio : float
        Minimum ratio of current volume to average volume required to
        qualify a pivot signal.
    confirm_days : int
        Number of subsequent days the price must hold above (breakout)
        or below (breakdown) the pivot price to be confirmed.
    """

    def __init__(
        self,
        lookback_days: int = 20,
        volume_surge_ratio: float = 1.5,
        confirm_days: int = 2,
    ) -> None:
        self.lookback_days = lookback_days
        self.volume_surge_ratio = volume_surge_ratio
        self.confirm_days = confirm_days

    def detect(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Detect pivot points in OHLCV data.

        Parameters
        ----------
        ohlcv : pd.DataFrame
            Must contain columns: date, open, high, low, close, volume.

        Returns
        -------
        pd.DataFrame
            Columns: date, pivot_type, pivot_price, resistance, support,
            volume_ratio, confirmed, consolidation_days.
        """
        n = len(ohlcv)
        dates = ohlcv["date"].values
        highs = ohlcv["high"].values.astype(float)
        lows = ohlcv["low"].values.astype(float)
        closes = ohlcv["close"].values.astype(float)
        volumes = ohlcv["volume"].values.astype(float)

        out_date = []
        out_pivot_type = []
        out_pivot_price = []
        out_resistance = []
        out_support = []
        out_volume_ratio = []
        out_confirmed = []
        out_consolidation = []

        # Track breakout/breakdown events for confirmation
        # Each entry: (row_index_in_output, pivot_price, pivot_type)
        pending_pivots: list[tuple[int, float, str]] = []

        for i in range(self.lookback_days, n):
            window_start = i - self.lookback_days
            window_highs = highs[window_start:i]
            window_lows = lows[window_start:i]
            window_volumes = volumes[window_start:i]

            resistance = float(np.max(window_highs))
            support = float(np.min(window_lows))
            avg_volume = float(np.mean(window_volumes))

            current_close = closes[i]
            current_volume = volumes[i]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0

            pivot_type = "none"
            pivot_price = current_close

            if (
                current_close > resistance
                and current_volume >= avg_volume * self.volume_surge_ratio
            ):
                pivot_type = "breakout"
            elif (
                current_close < support
                and current_volume >= avg_volume * self.volume_surge_ratio
            ):
                pivot_type = "breakdown"

            # Consolidation days: count days in lookback where close
            # stayed within [support, resistance]
            window_closes = closes[window_start:i]
            consolidation_days = int(
                np.sum((window_closes >= support) & (window_closes <= resistance))
            )

            row_idx = len(out_date)
            out_date.append(dates[i])
            out_pivot_type.append(pivot_type)
            out_pivot_price.append(pivot_price)
            out_resistance.append(resistance)
            out_support.append(support)
            out_volume_ratio.append(volume_ratio)
            out_confirmed.append(False)
            out_consolidation.append(consolidation_days)

            if pivot_type in ("breakout", "breakdown"):
                pending_pivots.append((row_idx, pivot_price, pivot_type))

        # False breakout filter: check confirmation
        for row_idx, pprice, ptype in pending_pivots:
            # Find position of this pivot in the original ohlcv
            # row_idx is the index in our output arrays
            # The corresponding ohlcv index is row_idx + lookback_days
            ohlcv_idx = row_idx + self.lookback_days

            # Check the next confirm_days after the pivot
            confirm_end = min(ohlcv_idx + 1 + self.confirm_days, n)
            subsequent = closes[ohlcv_idx + 1 : confirm_end]

            if len(subsequent) < self.confirm_days:
                # Not enough data to confirm
                out_confirmed[row_idx] = False
                continue

            if ptype == "breakout":
                # All subsequent closes must stay above pivot price
                out_confirmed[row_idx] = bool(np.all(subsequent >= pprice))
            elif ptype == "breakdown":
                # All subsequent closes must stay below pivot price
                out_confirmed[row_idx] = bool(np.all(subsequent <= pprice))

        result = pd.DataFrame(
            {
                "date": out_date,
                "pivot_type": out_pivot_type,
                "pivot_price": out_pivot_price,
                "resistance": out_resistance,
                "support": out_support,
                "volume_ratio": out_volume_ratio,
                "confirmed": out_confirmed,
                "consolidation_days": out_consolidation,
            }
        )
        return result
