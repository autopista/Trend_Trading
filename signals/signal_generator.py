"""Signal generation with confidence scoring and priority ordering.

Combines outputs from MarketKey, PivotDetector, and VolumeAnalyzer
to produce actionable buy/sell/watch signals with confidence scores.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd


class SignalGenerator:
    """Generate trading signals from combined engine results.

    Args:
        min_confidence: Minimum confidence score (0-100) required to
            emit a buy or sell signal. Below this threshold the signal
            becomes a 'watch'.
    """

    def __init__(
        self,
        min_confidence: float = 60.0,
        confirm_days: int = 2,
    ) -> None:
        self.min_confidence = min_confidence
        # Recent-window size for finding a freshly confirmed pivot. The last
        # (confirm_days) rows of the pivot frame are structurally unable to
        # carry confirmed=True, so widen the search by that amount.
        self.pivot_lookback = confirm_days + 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        symbol: str,
        results: Dict[str, object],
        market_direction: str,
    ) -> List[dict]:
        """Generate signals for *symbol* from combined engine results.

        Parameters
        ----------
        symbol : str
            Stock ticker symbol.
        results : dict
            Keys: market_key (DataFrame), pivots (DataFrame),
            volume (DataFrame), price (float), rsi (float).
        market_direction : str
            Overall market direction: "up", "down", or "neutral".

        Returns
        -------
        list[dict]
            Each dict has keys: symbol, signal_type, price, confidence,
            reason, target_price, stop_price, volume_ratio.
        """
        mk: pd.DataFrame = results["market_key"]
        pivots: pd.DataFrame = results["pivots"]
        vol: pd.DataFrame = results["volume"]
        price: float = results["price"]
        rsi: float = results["rsi"]

        # Use last row for market key / volume (reflects current state).
        mk_row = mk.iloc[-1]
        vol_row = vol.iloc[-1]

        # Pivot row: search recent window for a confirmed breakout/breakdown.
        # Today's row can never carry confirmed=True because the confirmation
        # window (confirm_days forward bars) isn't complete yet.
        window = min(len(pivots), self.pivot_lookback)
        recent = pivots.tail(window)
        recent_confirmed = recent[
            recent["confirmed"]
            & recent["pivot_type"].isin(["breakout", "breakdown"])
        ]
        if not recent_confirmed.empty:
            pivot_row = recent_confirmed.iloc[-1]
            # Use the volume surge recorded on the breakout day itself.
            pivot_date = pivot_row["date"]
            vol_on_pivot = vol[vol["date"] == pivot_date]
            if not vol_on_pivot.empty:
                vol_row = vol_on_pivot.iloc[0]
        else:
            pivot_row = pivots.iloc[-1]

        # Determine raw signal type
        is_breakout = pivot_row["pivot_type"] == "breakout"
        is_breakdown = pivot_row["pivot_type"] == "breakdown"
        confirmed = bool(pivot_row["confirmed"])
        volume_surge = bool(vol_row["volume_surge"])

        buy_allowed = mk_row["trend_direction"] in ("up", "neutral")
        sell_allowed = mk_row["trend_direction"] in ("down", "neutral")

        rsi_ok_buy = rsi <= 70.0

        if is_breakout and confirmed and volume_surge and buy_allowed and rsi_ok_buy:
            signal_type = "buy"
        elif is_breakdown and confirmed and volume_surge and sell_allowed:
            signal_type = "sell"
        else:
            signal_type = "watch"

        # In a down market, never emit buy signals
        if market_direction == "down" and signal_type == "buy":
            signal_type = "watch"

        confidence = self._calculate_confidence(
            pivot_row, vol_row, mk_row, market_direction, rsi
        )

        # Demote to watch if confidence is below threshold
        if signal_type in ("buy", "sell") and confidence < self.min_confidence:
            signal_type = "watch"

        reason = self._build_reason(pivot_row, vol_row, mk_row, signal_type)

        # Target / stop prices
        resistance = float(pivot_row["resistance"])
        support = float(pivot_row["support"])
        if signal_type == "buy":
            target_price = round(price * 1.10, 2)  # +10 %
            stop_price = support
        elif signal_type == "sell":
            target_price = round(price * 0.90, 2)  # -10 %
            stop_price = resistance
        else:
            target_price = None
            stop_price = None

        volume_ratio = float(vol_row["volume_ratio"])

        return [
            {
                "symbol": symbol,
                "signal_type": signal_type,
                "price": price,
                "confidence": confidence,
                "reason": reason,
                "target_price": target_price,
                "stop_price": stop_price,
                "volume_ratio": volume_ratio,
            }
        ]

    def prioritize(self, signals: List[dict]) -> List[dict]:
        """Sort signals by descending confidence, then descending volume_ratio."""
        return sorted(
            signals,
            key=lambda s: (-s["confidence"], -s["volume_ratio"]),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self,
        pivot: pd.Series,
        vol: pd.Series,
        mk: pd.Series,
        market_direction: str,
        rsi: float,
    ) -> float:
        """Calculate a 0-100 confidence score from multiple factors.

        Factor breakdown:
            Pivot clarity:        0-25
            Volume:               0-20
            Market alignment:     0-20
            Livermore strength:    0-15
            RSI:                  0-10
            Consolidation/time:   0-10
        """
        # 1. Pivot clarity (0-25)
        if bool(pivot["confirmed"]):
            pivot_score = 25.0
        elif pivot["pivot_type"] in ("breakout", "breakdown"):
            pivot_score = 10.0
        else:
            pivot_score = 0.0

        # 2. Volume (0-20): volume_ratio * 8, capped at 20
        vol_ratio = float(vol["volume_ratio"])
        volume_score = min(vol_ratio * 8.0, 20.0)

        # 3. Market alignment (0-20)
        direction = mk["trend_direction"]
        if direction in ("up", "down"):
            market_score = 20.0
        elif direction == "neutral":
            market_score = 10.0
        else:
            market_score = 0.0

        # 4. Livermore strength (0-15): strength * 0.15
        strength = float(mk["trend_strength"])
        livermore_score = min(strength * 0.15, 15.0)

        # 5. RSI (0-10)
        if 30.0 <= rsi <= 70.0:
            rsi_score = 10.0
        elif 20.0 <= rsi <= 80.0:
            rsi_score = 5.0
        else:
            rsi_score = 0.0

        # 6. Consolidation / time (0-10): consolidation_days * 1.0
        consolidation = float(pivot["consolidation_days"])
        consolidation_score = min(consolidation * 1.0, 10.0)

        total = (
            pivot_score
            + volume_score
            + market_score
            + livermore_score
            + rsi_score
            + consolidation_score
        )
        return min(max(total, 0.0), 100.0)

    @staticmethod
    def _build_reason(
        pivot: pd.Series,
        vol: pd.Series,
        mk: pd.Series,
        signal_type: str,
    ) -> str:
        """Build a Korean-language reason string for the signal."""
        parts: list[str] = []

        # Pivot type description
        ptype = pivot["pivot_type"]
        if ptype == "breakout":
            parts.append("저항선 돌파")
        elif ptype == "breakdown":
            parts.append("지지선 이탈")
        else:
            parts.append("피벗 미감지")

        # Confirmation
        if bool(pivot["confirmed"]):
            parts.append("확인 완료")
        else:
            parts.append("미확인")

        # Volume
        if bool(vol["volume_surge"]):
            parts.append(f"거래량 급증(x{float(vol['volume_ratio']):.1f})")

        # Livermore state
        state = mk["column_state"]
        state_map = {
            "upward_trend": "상승 추세",
            "downward_trend": "하락 추세",
            "natural_reaction": "자연 조정",
            "natural_rally": "자연 반등",
            "secondary_rally": "2차 반등",
            "secondary_reaction": "2차 조정",
            "neutral": "중립",
        }
        parts.append(state_map.get(state, state))

        return " | ".join(parts)
