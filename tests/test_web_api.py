"""Tests for web API endpoints."""

from __future__ import annotations

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Base, Signal
import web.app as app_module


@pytest.fixture
def client(monkeypatch):
    """Flask test client with in-memory SQLite DB and test signals."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = Session(engine)

    # Insert test signals across 3 dates, each with 2 signals
    test_dates = [date(2026, 4, 6), date(2026, 4, 3), date(2026, 4, 1)]
    for d in test_dates:
        session.add(Signal(
            symbol="AAPL",
            market="us",
            date=d,
            signal_type="buy",
            price=170.0,
            confidence=85.0,
            reason="Strong uptrend",
        ))
        session.add(Signal(
            symbol="MSFT",
            market="us",
            date=d,
            signal_type="watch",
            price=420.0,
            confidence=40.0,
            reason="Consolidating",
        ))
    session.commit()

    # Patch web.app.get_session to return our test session
    monkeypatch.setattr(app_module, "get_session", lambda: session)

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c

    session.close()
    engine.dispose()


class TestSignalDates:
    def test_returns_dates_descending(self, client):
        """GET /api/us/signals/dates returns dates in descending order."""
        resp = client.get("/api/us/signals/dates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dates" in data
        dates = data["dates"]
        assert len(dates) == 3
        # Verify descending order
        assert dates == sorted(dates, reverse=True)
        assert dates[0] == "2026-04-06"
        assert dates[1] == "2026-04-03"
        assert dates[2] == "2026-04-01"

    def test_returns_empty_for_unknown_market(self, client):
        """GET /api/xx/signals/dates returns empty list for unknown market."""
        resp = client.get("/api/xx/signals/dates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"dates": []}

    def test_limited_to_90_days(self, client):
        """All test dates within 90 days should appear in results."""
        resp = client.get("/api/us/signals/dates")
        assert resp.status_code == 200
        data = resp.get_json()
        dates = data["dates"]
        # All 3 test dates are within 90 days of 2026-04-06
        assert "2026-04-06" in dates
        assert "2026-04-03" in dates
        assert "2026-04-01" in dates
