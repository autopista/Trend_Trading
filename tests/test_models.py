"""Tests for database ORM models."""

import pytest
from datetime import date, datetime
from sqlalchemy.exc import IntegrityError

from db.models import Price, MarketIndex, LivermoreState, Signal, Trade, Portfolio


def test_create_price(db_session):
    """Test creating a Price record and reading it back."""
    price = Price(
        symbol="005930",
        market="KR",
        date=date(2026, 3, 2),
        open=70000.0,
        high=71500.0,
        low=69500.0,
        close=71000.0,
        volume=15_000_000,
    )
    db_session.add(price)
    db_session.commit()

    result = db_session.query(Price).filter_by(symbol="005930").first()
    assert result is not None
    assert result.close == 71000.0
    assert result.market == "KR"
    assert result.volume == 15_000_000


def test_create_livermore_state(db_session):
    """Test creating a LivermoreState record."""
    state = LivermoreState(
        symbol="005930",
        market="KR",
        date=date(2026, 3, 2),
        column_state="upward_trend",
        reference_pivot_price=70000.0,
        trend_direction="UP",
        trend_strength=0.85,
        trend_duration_days=12,
    )
    db_session.add(state)
    db_session.commit()

    result = db_session.query(LivermoreState).filter_by(symbol="005930").first()
    assert result is not None
    assert result.trend_direction == "UP"
    assert result.trend_strength == 0.85
    assert result.trend_duration_days == 12


def test_create_signal(db_session):
    """Test creating a Signal record."""
    signal = Signal(
        symbol="AAPL",
        market="US",
        date=date(2026, 3, 2),
        signal_type="BUY",
        price=178.50,
        target_price=195.0,
        stop_price=170.0,
        reason="Upward trend confirmed with strong volume",
        confidence=0.82,
    )
    db_session.add(signal)
    db_session.commit()

    result = db_session.query(Signal).filter_by(symbol="AAPL").first()
    assert result is not None
    assert result.signal_type == "BUY"
    assert result.confidence == 0.82
    assert result.notified is False
    assert result.created_at is not None


def test_create_trade_with_signal_fk(db_session):
    """Test creating a Trade linked to a Signal via foreign key."""
    signal = Signal(
        symbol="AAPL",
        market="US",
        date=date(2026, 3, 2),
        signal_type="BUY",
        price=178.50,
        reason="Trend breakout",
        confidence=0.80,
    )
    db_session.add(signal)
    db_session.flush()

    trade = Trade(
        symbol="AAPL",
        market="US",
        entry_date=date(2026, 3, 2),
        entry_price=178.50,
        quantity=100,
        signal_id=signal.id,
    )
    db_session.add(trade)
    db_session.commit()

    result = db_session.query(Trade).filter_by(symbol="AAPL").first()
    assert result is not None
    assert result.status == "open"
    assert result.exit_date is None
    assert result.signal_id == signal.id
    assert result.signal.signal_type == "BUY"


def test_create_portfolio_snapshot(db_session):
    """Test creating a Portfolio snapshot."""
    portfolio = Portfolio(
        market="US",
        date=date(2026, 3, 2),
        total_value=100000.0,
        cash=50000.0,
        invested=50000.0,
        daily_return=0.012,
        cumulative_return=0.05,
    )
    db_session.add(portfolio)
    db_session.commit()

    result = db_session.query(Portfolio).filter_by(market="US").first()
    assert result is not None
    assert result.total_value == 100000.0
    assert result.daily_return == 0.012


def test_price_unique_constraint(db_session):
    """Test that duplicate (symbol, date) raises IntegrityError."""
    price1 = Price(
        symbol="005930",
        market="KR",
        date=date(2026, 3, 2),
        open=70000.0,
        high=71500.0,
        low=69500.0,
        close=71000.0,
        volume=15_000_000,
    )
    db_session.add(price1)
    db_session.commit()

    price2 = Price(
        symbol="005930",
        market="KR",
        date=date(2026, 3, 2),
        open=70500.0,
        high=72000.0,
        low=70000.0,
        close=71500.0,
        volume=16_000_000,
    )
    db_session.add(price2)
    with pytest.raises(IntegrityError):
        db_session.commit()
