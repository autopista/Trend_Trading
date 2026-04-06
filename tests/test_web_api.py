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


class TestSignalsWithDate:
    def test_filter_by_date(self, client):
        resp = client.get("/api/us/signals?date=2026-04-03")
        data = resp.get_json()
        assert len(data) == 2  # AAPL + MSFT on that date
        assert all(s["date"] == "2026-04-03" for s in data)

    def test_without_date_returns_latest(self, client):
        """No date param → returns signals from most recent date only."""
        resp = client.get("/api/us/signals")
        data = resp.get_json()
        assert len(data) == 2
        assert all(s["date"] == "2026-04-06" for s in data)

    def test_invalid_date_returns_empty(self, client):
        resp = client.get("/api/us/signals?date=2026-12-31")
        data = resp.get_json()
        assert data == []

    def test_sorted_by_confidence_desc(self, client):
        resp = client.get("/api/us/signals?date=2026-04-06")
        data = resp.get_json()
        confs = [s["confidence"] for s in data]
        assert confs == sorted(confs, reverse=True)


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


class TestSignalsSummaryWithDate:
    def test_summary_for_specific_date(self, client):
        resp = client.get("/api/us/signals/summary?date=2026-04-03")
        data = resp.get_json()
        assert data["buy"] == 1
        assert data["watch"] == 1
        assert data["sell"] == 0

    def test_summary_without_date_uses_latest(self, client):
        resp = client.get("/api/us/signals/summary")
        data = resp.get_json()
        assert data["buy"] == 1
        assert data["watch"] == 1

    def test_summary_for_empty_date(self, client):
        resp = client.get("/api/us/signals/summary?date=2099-01-01")
        data = resp.get_json()
        assert data == {"buy": 0, "sell": 0, "watch": 0}


class TestDateFilterIntegration:
    def test_dates_and_signals_consistent(self, client):
        """Signals returned for a date should match that date in dates list."""
        dates_resp = client.get("/api/us/signals/dates")
        dates = dates_resp.get_json()["dates"]

        for d in dates:
            signals_resp = client.get(f"/api/us/signals?date={d}")
            signals = signals_resp.get_json()
            assert len(signals) > 0, f"Date {d} in dates list but no signals"
            assert all(s["date"] == d for s in signals)

    def test_summary_matches_signals(self, client):
        """Summary counts should match actual signal counts."""
        for d in ["2026-04-06", "2026-04-03"]:
            signals = client.get(f"/api/us/signals?date={d}").get_json()
            summary = client.get(f"/api/us/signals/summary?date={d}").get_json()

            actual = {"buy": 0, "sell": 0, "watch": 0}
            for s in signals:
                if s["signal_type"] in actual:
                    actual[s["signal_type"]] += 1
            assert summary == actual
