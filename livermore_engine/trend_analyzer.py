"""Top-down trend analysis using Livermore Market Key on market index data.

Determines overall market context (up/down/neutral) to filter individual
stock signals — only take buy signals in uptrends, sell signals in downtrends,
and require higher confidence in neutral markets.
"""

from dataclasses import dataclass

import pandas as pd

from livermore_engine.market_key import MarketKey


@dataclass
class MarketContext:
    """Snapshot of the current market regime."""

    trend_direction: str  # "up", "down", "neutral"
    trend_state: str  # Livermore 6-state name
    trend_strength: float  # 0-100
    allow_buy: bool
    allow_sell: bool


class TrendAnalyzer:
    """Applies Livermore Market Key to a market index for top-down filtering.

    Args:
        pivot_threshold_pct: Threshold passed to MarketKey for state transitions.
        min_strength_for_neutral: Minimum signal confidence required to act
            in a neutral (trendless) market.
    """

    def __init__(
        self,
        pivot_threshold_pct: float = 5.0,
        min_strength_for_neutral: float = 70.0,
    ):
        self.market_key = MarketKey(pivot_threshold_pct=pivot_threshold_pct)
        self.min_strength_for_neutral = min_strength_for_neutral

    def analyze_market(self, market_ohlcv: pd.DataFrame) -> MarketContext:
        """Run MarketKey on index data and return current market context.

        Args:
            market_ohlcv: DataFrame with columns [date, open, high, low, close, volume]
                representing a broad market index (e.g. KOSPI, S&P 500).

        Returns:
            MarketContext describing the latest trend state and allowed actions.
        """
        result = self.market_key.analyze(market_ohlcv)

        if len(result) == 0:
            return MarketContext(
                trend_direction="neutral",
                trend_state="neutral",
                trend_strength=0.0,
                allow_buy=True,
                allow_sell=True,
            )

        last = result.iloc[-1]
        direction = last["trend_direction"]
        state = last["column_state"]
        strength = float(last["trend_strength"])

        if direction == "up":
            allow_buy, allow_sell = True, False
        elif direction == "down":
            allow_buy, allow_sell = False, True
        else:  # neutral
            allow_buy, allow_sell = True, True

        return MarketContext(
            trend_direction=direction,
            trend_state=state,
            trend_strength=strength,
            allow_buy=allow_buy,
            allow_sell=allow_sell,
        )

    def filter_signal(
        self,
        signal_type: str,
        confidence: float,
        market_ctx: MarketContext,
    ) -> bool:
        """Decide whether a trading signal should be acted on.

        Args:
            signal_type: "buy" or "sell".
            confidence: Signal confidence / strength (0-100).
            market_ctx: Current MarketContext from analyze_market().

        Returns:
            True if the signal is allowed, False if it should be filtered out.
        """
        if signal_type == "buy" and not market_ctx.allow_buy:
            return False
        if signal_type == "sell" and not market_ctx.allow_sell:
            return False

        # In neutral markets, require higher confidence
        if market_ctx.trend_direction == "neutral":
            return confidence >= self.min_strength_for_neutral

        return True
