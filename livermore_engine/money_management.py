"""Livermore-style money management and position sizing.

Implements split-buy entries (pyramiding) and stop-loss management based on
pivot reference prices, following Jesse Livermore's principle of scaling into
positions only as the trade proves correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PositionPlan:
    """Computed position sizing plan for a trade."""

    total_shares: int
    splits: list[int] = field(default_factory=list)  # shares per split
    stop_price: float = 0.0
    max_investment: float = 0.0


class MoneyManager:
    """Position sizing and risk management.

    Args:
        max_position_pct: Maximum percentage of portfolio to allocate to a
            single position (default 20%).
        split_buy_ratio: How to split the total position across entries.
            Default [50, 30, 20] means 50% on first buy, 30% on confirmation,
            20% on final add.
        stop_loss_pct: Percentage below the pivot price to set the stop loss.
    """

    def __init__(
        self,
        max_position_pct: float = 20.0,
        split_buy_ratio: Optional[list[int]] = None,
        stop_loss_pct: float = 5.0,
    ):
        self.max_position_pct = max_position_pct
        self.split_buy_ratio = split_buy_ratio if split_buy_ratio is not None else [50, 30, 20]
        self.stop_loss_pct = stop_loss_pct

    def calculate_position(
        self,
        total_portfolio: float,
        price: float,
        pivot_price: float,
    ) -> PositionPlan:
        """Calculate a position plan with split entries and stop price.

        Args:
            total_portfolio: Total portfolio value in currency.
            price: Current stock price.
            pivot_price: Reference pivot price for stop-loss calculation.

        Returns:
            PositionPlan with share counts per split and stop price.
        """
        max_investment = total_portfolio * (self.max_position_pct / 100.0)
        total_shares = int(max_investment / price) if price > 0 else 0

        # Distribute shares across splits according to ratio
        ratio_sum = sum(self.split_buy_ratio)
        splits: list[int] = []
        allocated = 0
        for i, ratio in enumerate(self.split_buy_ratio):
            if i == len(self.split_buy_ratio) - 1:
                # Last split gets remainder to avoid rounding gaps
                shares = total_shares - allocated
            else:
                shares = int(total_shares * ratio / ratio_sum)
            splits.append(shares)
            allocated += shares

        stop_price = pivot_price * (1.0 - self.stop_loss_pct / 100.0)

        return PositionPlan(
            total_shares=total_shares,
            splits=splits,
            stop_price=stop_price,
            max_investment=max_investment,
        )

    @staticmethod
    def should_stop_loss(current_price: float, stop_price: float) -> bool:
        """Check whether the current price has breached the stop-loss level.

        Args:
            current_price: Latest market price.
            stop_price: Pre-calculated stop-loss price.

        Returns:
            True if stop-loss is triggered.
        """
        return current_price <= stop_price

    @staticmethod
    def calculate_target_price(
        entry_price: float,
        risk_reward_ratio: float = 2.0,
        stop_price: float = 0.0,
    ) -> float:
        """Calculate a profit-taking target price based on risk/reward.

        target = entry + (entry - stop) * risk_reward_ratio

        Args:
            entry_price: Price at which the position was entered.
            risk_reward_ratio: Desired reward-to-risk multiple (default 2.0).
            stop_price: Stop-loss price.

        Returns:
            Target price for taking profits.
        """
        risk = entry_price - stop_price
        return entry_price + risk * risk_reward_ratio
