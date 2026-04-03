"""Shared test fixtures for Trend Trading test suite."""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Base


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_ohlcv_data():
    """Generate 20 business days of sample OHLCV data as a DataFrame."""
    np.random.seed(42)
    start_date = date(2026, 3, 1)
    dates = pd.bdate_range(start=start_date, periods=20)

    base_price = 100.0
    closes = base_price + np.cumsum(np.random.randn(20) * 2)

    data = {
        "date": dates.date,
        "open": closes - np.random.rand(20) * 1.5,
        "high": closes + np.random.rand(20) * 2.0,
        "low": closes - np.random.rand(20) * 2.0,
        "close": closes,
        "volume": np.random.randint(100_000, 10_000_000, size=20),
    }
    df = pd.DataFrame(data)
    df["symbol"] = "005930"
    df["market"] = "KR"
    return df
