"""Signal history tracking and accuracy measurement.

Queries historical signals from the database and evaluates whether
buy/sell signals were correct based on subsequent price movement.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict

from sqlalchemy import and_
from sqlalchemy.orm import Session

from db.models import Signal, Price


class SignalHistory:
    """Evaluate historical signal accuracy.

    Args:
        session: SQLAlchemy database session.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_accuracy(
        self, market: str, days_back: int = 90
    ) -> Dict[str, float | int]:
        """Calculate buy/sell signal accuracy over the last *days_back* days.

        For each signal, checks whether the price moved in the expected
        direction within the subsequent 10 trading days.

        Returns
        -------
        dict
            Keys: buy_accuracy (float 0-100), sell_accuracy (float 0-100),
            buy_total (int), sell_total (int).
        """
        cutoff = date.today() - timedelta(days=days_back)

        signals = (
            self.session.query(Signal)
            .filter(
                and_(
                    Signal.market == market,
                    Signal.date >= cutoff,
                    Signal.signal_type.in_(["buy", "sell"]),
                )
            )
            .all()
        )

        buy_correct = 0
        buy_total = 0
        sell_correct = 0
        sell_total = 0

        for sig in signals:
            if sig.signal_type == "buy":
                buy_total += 1
                if self._was_correct(sig, "buy"):
                    buy_correct += 1
            elif sig.signal_type == "sell":
                sell_total += 1
                if self._was_correct(sig, "sell"):
                    sell_correct += 1

        buy_accuracy = (buy_correct / buy_total * 100.0) if buy_total > 0 else 0.0
        sell_accuracy = (sell_correct / sell_total * 100.0) if sell_total > 0 else 0.0

        return {
            "buy_accuracy": buy_accuracy,
            "sell_accuracy": sell_accuracy,
            "buy_total": buy_total,
            "sell_total": sell_total,
        }

    def _was_correct(
        self, signal: Signal, signal_type: str, check_days: int = 10
    ) -> bool:
        """Check if a signal's expected move materialised within *check_days*.

        A buy signal is correct if any closing price in the window is
        above the signal price. A sell signal is correct if any closing
        price is below the signal price.
        """
        prices = (
            self.session.query(Price)
            .filter(
                and_(
                    Price.symbol == signal.symbol,
                    Price.date > signal.date,
                )
            )
            .order_by(Price.date)
            .limit(check_days)
            .all()
        )

        if not prices:
            return False

        for p in prices:
            if signal_type == "buy" and p.close > signal.price:
                return True
            if signal_type == "sell" and p.close < signal.price:
                return True

        return False
