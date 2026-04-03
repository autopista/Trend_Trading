"""Livermore Market Key 6-state analysis engine.

Implements Jesse Livermore's Market Key method, tracking price movements
through 6 states plus neutral to identify trend direction and strength.
"""

import pandas as pd
import numpy as np


# States grouped by trend direction
_UP_STATES = {"upward_trend", "natural_reaction", "secondary_rally"}
_DOWN_STATES = {"downward_trend", "natural_rally", "secondary_reaction"}


class MarketKey:
    """Livermore Market Key 6-state trend analysis.

    Tracks price through six states:
    - upward_trend: price broke above previous pivot high
    - natural_rally: temporary bounce during downtrend
    - secondary_rally: bounce from natural_reaction, not reaching upward_trend
    - downward_trend: price broke below previous pivot low
    - natural_reaction: temporary pullback during uptrend
    - secondary_reaction: pullback from natural_rally, not reaching downward_trend

    Args:
        pivot_threshold_pct: Percentage threshold for major trend transitions.
            Half this value is used for secondary transitions.
    """

    def __init__(self, pivot_threshold_pct: float = 5.0):
        self.pivot_threshold_pct = pivot_threshold_pct
        self.half_threshold_pct = pivot_threshold_pct / 2.0

    def analyze(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Analyze OHLCV data and assign Livermore Market Key states.

        Args:
            ohlcv: DataFrame with columns [date, open, high, low, close, volume].

        Returns:
            DataFrame with columns [date, column_state, reference_pivot_price,
            trend_direction, trend_strength, trend_duration_days].
        """
        n = len(ohlcv)
        closes = ohlcv["close"].values.astype(float)

        states = ["neutral"] * n
        ref_pivots = np.full(n, np.nan)
        directions = ["neutral"] * n
        strengths = np.zeros(n)
        durations = np.zeros(n, dtype=int)

        if n == 0:
            return self._build_result(ohlcv, states, ref_pivots, directions, strengths, durations)

        # Initialize
        state = "neutral"
        ref_pivot = closes[0]
        trend_start_idx = 0
        high_since_pivot = closes[0]
        low_since_pivot = closes[0]

        for i in range(n):
            price = closes[i]
            high_since_pivot = max(high_since_pivot, price)
            low_since_pivot = min(low_since_pivot, price)

            pct_from_pivot = ((price - ref_pivot) / ref_pivot) * 100.0 if ref_pivot != 0 else 0.0
            pct_from_high = ((price - high_since_pivot) / high_since_pivot) * 100.0 if high_since_pivot != 0 else 0.0
            pct_from_low = ((price - low_since_pivot) / low_since_pivot) * 100.0 if low_since_pivot != 0 else 0.0

            new_state = self._next_state(
                state, pct_from_pivot, pct_from_high, pct_from_low, price, ref_pivot
            )

            # Update reference pivot on major state changes
            if new_state != state:
                if new_state in ("upward_trend", "downward_trend"):
                    if state == "neutral" or self._is_major_transition(state, new_state):
                        ref_pivot = price
                        trend_start_idx = i
                        high_since_pivot = price
                        low_since_pivot = price
                elif new_state in ("natural_reaction", "secondary_reaction"):
                    # Keep the high as reference pivot for pullbacks
                    ref_pivot = high_since_pivot
                    high_since_pivot = price
                    low_since_pivot = price
                elif new_state in ("natural_rally", "secondary_rally"):
                    # Keep the low as reference pivot for bounces
                    ref_pivot = low_since_pivot
                    high_since_pivot = price
                    low_since_pivot = price

            state = new_state

            # Record state
            states[i] = state
            ref_pivots[i] = ref_pivot
            directions[i] = self._get_direction(state)

            # Calculate duration (days in current trend direction)
            if i == 0:
                durations[i] = 0
            elif directions[i] == directions[i - 1] and directions[i] != "neutral":
                durations[i] = durations[i - 1] + 1
            elif directions[i] != "neutral":
                durations[i] = 1
            else:
                durations[i] = 0

            # Calculate strength (0-100)
            strengths[i] = self._calc_strength(price, ref_pivot, durations[i])

        return self._build_result(ohlcv, states, ref_pivots, directions, strengths, durations)

    def _next_state(
        self,
        current: str,
        pct_from_pivot: float,
        pct_from_high: float,
        pct_from_low: float,
        price: float,
        ref_pivot: float,
    ) -> str:
        """Determine the next state based on transition rules."""
        threshold = self.pivot_threshold_pct
        half = self.half_threshold_pct

        if current == "neutral":
            if pct_from_pivot >= threshold:
                return "upward_trend"
            elif pct_from_pivot <= -threshold:
                return "downward_trend"
            return "neutral"

        elif current == "upward_trend":
            # Check for pullback -> natural_reaction
            if pct_from_high <= -half:
                return "natural_reaction"
            return "upward_trend"

        elif current == "downward_trend":
            # Check for bounce -> natural_rally
            if pct_from_low >= half:
                return "natural_rally"
            return "downward_trend"

        elif current == "natural_reaction":
            # If price recovers back to/above reference pivot -> upward_trend
            if price >= ref_pivot:
                return "upward_trend"
            # If price drops further -> secondary_reaction (deeper pullback)
            if pct_from_high <= -half:
                return "secondary_reaction"
            # If price bounces from reaction but not to pivot -> secondary_rally
            if pct_from_low >= half:
                return "secondary_rally"
            return "natural_reaction"

        elif current == "natural_rally":
            # If price drops back to/below reference pivot -> downward_trend
            if price <= ref_pivot:
                return "downward_trend"
            # If price rises further -> secondary_rally (deeper bounce)
            if pct_from_low >= half:
                return "secondary_rally"
            # If price pulls back from rally but not to pivot -> secondary_reaction
            if pct_from_high <= -half:
                return "secondary_reaction"
            return "natural_rally"

        elif current == "secondary_rally":
            # If price reaches/exceeds reference pivot -> upward_trend
            if price >= ref_pivot:
                return "upward_trend"
            # If pulls back again
            if pct_from_high <= -half:
                return "secondary_reaction"
            return "secondary_rally"

        elif current == "secondary_reaction":
            # If price drops to/below reference pivot -> downward_trend
            if price <= ref_pivot:
                return "downward_trend"
            # If bounces again
            if pct_from_low >= half:
                return "secondary_rally"
            return "secondary_reaction"

        return current

    @staticmethod
    def _is_major_transition(old_state: str, new_state: str) -> bool:
        """Check if this is a major trend transition."""
        return (
            (old_state in _DOWN_STATES and new_state == "upward_trend")
            or (old_state in _UP_STATES and new_state == "downward_trend")
            or old_state == "neutral"
        )

    @staticmethod
    def _get_direction(state: str) -> str:
        """Map state to trend direction."""
        if state in _UP_STATES:
            return "up"
        elif state in _DOWN_STATES:
            return "down"
        return "neutral"

    @staticmethod
    def _calc_strength(price: float, ref_pivot: float, duration: int) -> float:
        """Calculate trend strength 0-100 from price distance and duration.

        Combines price distance from pivot (70% weight) and duration (30% weight).
        """
        if ref_pivot == 0:
            return 0.0

        # Price distance component (0-100), capped at 20% move
        price_pct = abs((price - ref_pivot) / ref_pivot) * 100.0
        price_score = min(price_pct / 20.0 * 100.0, 100.0)

        # Duration component (0-100), capped at 60 days
        duration_score = min(duration / 60.0 * 100.0, 100.0)

        strength = price_score * 0.7 + duration_score * 0.3
        return min(max(strength, 0.0), 100.0)

    @staticmethod
    def _build_result(
        ohlcv: pd.DataFrame,
        states: list,
        ref_pivots: np.ndarray,
        directions: list,
        strengths: np.ndarray,
        durations: np.ndarray,
    ) -> pd.DataFrame:
        """Build the output DataFrame."""
        return pd.DataFrame({
            "date": ohlcv["date"].values,
            "column_state": states,
            "reference_pivot_price": ref_pivots,
            "trend_direction": directions,
            "trend_strength": strengths,
            "trend_duration_days": durations,
        })
