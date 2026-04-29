"""CRUD repository functions for the Trend Trading database."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from db.models import (
    Price, MarketIndex, LivermoreState, Signal, Trade,
)


# ── Price ────────────────────────────────────────────────────────────────

def upsert_prices(session: Session, df: pd.DataFrame, symbol: str, market: str):
    """Insert or update price rows from a DataFrame.

    DataFrame must have columns: date, open, high, low, close, volume.
    Existing rows matching (symbol, date) are updated; new rows are inserted.
    """
    for _, row in df.iterrows():
        existing = session.execute(
            select(Price).where(Price.symbol == symbol, Price.date == row["date"])
        ).scalar_one_or_none()

        if existing:
            existing.open = float(row["open"])
            existing.high = float(row["high"])
            existing.low = float(row["low"])
            existing.close = float(row["close"])
            existing.volume = int(row["volume"])
        else:
            session.add(Price(
                symbol=symbol,
                market=market,
                date=row["date"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            ))
    session.commit()


def get_prices(
    session: Session, symbol: str, start: date, end: date
) -> Sequence[Price]:
    """Return Price rows for a symbol between start and end dates (inclusive)."""
    stmt = (
        select(Price)
        .where(Price.symbol == symbol, Price.date >= start, Price.date <= end)
        .order_by(Price.date)
    )
    return session.execute(stmt).scalars().all()


def get_all_symbols(session: Session, market: str) -> list[str]:
    """Return all distinct symbols for a given market from the prices table."""
    from sqlalchemy import distinct
    stmt = select(distinct(Price.symbol)).where(Price.market == market)
    return [row[0] for row in session.execute(stmt).all()]


# ── MarketIndex ──────────────────────────────────────────────────────────

def upsert_market_index(
    session: Session,
    index_name: str,
    market: str,
    dt: date,
    value: float,
    change_pct: Optional[float] = None,
    trend_state: Optional[str] = None,
):
    """Insert or update a single MarketIndex row."""
    existing = session.execute(
        select(MarketIndex).where(
            MarketIndex.index_name == index_name, MarketIndex.date == dt
        )
    ).scalar_one_or_none()

    if existing:
        existing.value = value
        existing.change_pct = change_pct
        existing.trend_state = trend_state
    else:
        session.add(MarketIndex(
            index_name=index_name,
            market=market,
            date=dt,
            value=value,
            change_pct=change_pct,
            trend_state=trend_state,
        ))
    session.commit()


# ── LivermoreState ───────────────────────────────────────────────────────

def upsert_livermore_state(
    session: Session,
    symbol: str,
    market: str,
    dt: date,
    column_state: str,
    reference_pivot_price: float,
    trend_direction: str,
    trend_strength: float,
    trend_duration_days: int,
):
    """Insert or update a LivermoreState row for (symbol, date)."""
    existing = session.execute(
        select(LivermoreState).where(
            LivermoreState.symbol == symbol, LivermoreState.date == dt
        )
    ).scalar_one_or_none()

    if existing:
        existing.column_state = column_state
        existing.reference_pivot_price = reference_pivot_price
        existing.trend_direction = trend_direction
        existing.trend_strength = trend_strength
        existing.trend_duration_days = trend_duration_days
    else:
        session.add(LivermoreState(
            symbol=symbol,
            market=market,
            date=dt,
            column_state=column_state,
            reference_pivot_price=reference_pivot_price,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            trend_duration_days=trend_duration_days,
        ))
    session.commit()


def get_latest_livermore_state(
    session: Session, symbol: str
) -> Optional[LivermoreState]:
    """Return the most recent LivermoreState for a symbol."""
    stmt = (
        select(LivermoreState)
        .where(LivermoreState.symbol == symbol)
        .order_by(LivermoreState.date.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


# ── Signal ───────────────────────────────────────────────────────────────

def save_signal(session: Session, signal: Signal) -> Signal:
    """Insert or update a Signal (upsert on symbol+market+date+signal_type)."""
    created_at = signal.created_at or datetime.utcnow()
    notified = bool(signal.notified) if signal.notified is not None else False
    stmt = sqlite_insert(Signal).values(
        symbol=signal.symbol,
        market=signal.market,
        date=signal.date,
        signal_type=signal.signal_type,
        price=signal.price,
        target_price=signal.target_price,
        stop_price=signal.stop_price,
        reason=signal.reason,
        confidence=signal.confidence,
        notified=notified,
        created_at=created_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "market", "date", "signal_type"],
        set_={
            "price": stmt.excluded.price,
            "target_price": stmt.excluded.target_price,
            "stop_price": stmt.excluded.stop_price,
            "reason": stmt.excluded.reason,
            "confidence": stmt.excluded.confidence,
            "created_at": stmt.excluded.created_at,
        },
    )
    session.execute(stmt)
    session.commit()

    refreshed = session.execute(
        select(Signal).where(
            Signal.symbol == signal.symbol,
            Signal.market == signal.market,
            Signal.date == signal.date,
            Signal.signal_type == signal.signal_type,
        )
    ).scalar_one()
    return refreshed


def get_signals_by_date(
    session: Session, dt: date, market: Optional[str] = None
) -> Sequence[Signal]:
    """Return all signals for a given date, optionally filtered by market."""
    stmt = select(Signal).where(Signal.date == dt)
    if market is not None:
        stmt = stmt.where(Signal.market == market)
    stmt = stmt.order_by(Signal.symbol)
    return session.execute(stmt).scalars().all()


# ── Trade ────────────────────────────────────────────────────────────────

def get_open_trades(
    session: Session, market: Optional[str] = None
) -> Sequence[Trade]:
    """Return all trades with status='open', optionally filtered by market."""
    stmt = select(Trade).where(Trade.status == "open")
    if market is not None:
        stmt = stmt.where(Trade.market == market)
    stmt = stmt.order_by(Trade.entry_date)
    return session.execute(stmt).scalars().all()
