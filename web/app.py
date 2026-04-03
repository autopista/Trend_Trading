"""Flask web application with API endpoints for the Trend Trading dashboard.

Routes:
    GET /                              → redirect to /kr/dashboard
    GET /<market>/dashboard            → render index.html
    GET /<market>/performance          → render performance.html
    GET /api/<market>/indices          → market indices for today
    GET /api/<market>/signals          → signals from last 7 days
    GET /api/<market>/signals/summary  → buy/sell/watch counts for today
    GET /api/<market>/chart/<symbol>   → OHLCV + Livermore states
    GET /api/<market>/performance      → trade stats and signal accuracy
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml
from flask import Flask, jsonify, redirect, render_template, request, url_for
from sqlalchemy import and_, select, func

from db.database import get_session, init_db
from db.models import LivermoreState, MarketIndex, Price, Signal, Trade
from signals.signal_history import SignalHistory

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).parent

app = Flask(
    __name__,
    template_folder=str(_BASE_DIR / "templates"),
    static_folder=str(_BASE_DIR / "static"),
)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Redirect root to Korean market dashboard."""
    return redirect(url_for("dashboard", market="kr"))


@app.route("/<market>/dashboard")
def dashboard(market: str):
    """Render the main dashboard page."""
    return render_template("index.html", market=market)


@app.route("/<market>/performance")
def performance(market: str):
    """Render the performance tracking page."""
    return render_template("performance.html", market=market)


# ---------------------------------------------------------------------------
# API — Market Indices
# ---------------------------------------------------------------------------

@app.route("/api/<market>/indices")
def api_indices(market: str):
    """Return latest value for each market index."""
    session = get_session()
    try:
        # Get all distinct index names for this market
        names = [row[0] for row in session.execute(
            select(MarketIndex.index_name).where(MarketIndex.market == market).distinct()
        ).all()]

        result = []
        for name in names:
            # Latest row for this index
            r = session.execute(
                select(MarketIndex)
                .where(MarketIndex.index_name == name)
                .order_by(MarketIndex.date.desc())
                .limit(1)
            ).scalar_one_or_none()
            if not r:
                continue

            # Calculate change_pct from previous day
            change_pct = r.change_pct
            if change_pct is None:
                prev = session.execute(
                    select(MarketIndex)
                    .where(MarketIndex.index_name == name,
                           MarketIndex.date < r.date)
                    .order_by(MarketIndex.date.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if prev and prev.value:
                    change_pct = round((r.value - prev.value) / prev.value * 100, 2)

            result.append({
                "index_name": r.index_name,
                "date": r.date.isoformat(),
                "value": r.value,
                "change_pct": change_pct,
                "trend_state": r.trend_state,
            })
        return jsonify(result)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API — Signals
# ---------------------------------------------------------------------------

@app.route("/api/<market>/signals")
def api_signals(market: str):
    """Return signals from the last 7 days, sorted by confidence descending."""
    session = get_session()
    try:
        cutoff = date.today() - timedelta(days=7)
        stmt = (
            select(Signal)
            .where(Signal.market == market, Signal.date >= cutoff)
            .order_by(Signal.confidence.desc())
        )
        rows = session.execute(stmt).scalars().all()

        return jsonify([
            {
                "id": r.id,
                "symbol": r.symbol,
                "date": r.date.isoformat(),
                "signal_type": r.signal_type,
                "price": r.price,
                "target_price": r.target_price,
                "stop_price": r.stop_price,
                "reason": r.reason,
                "confidence": r.confidence,
            }
            for r in rows
        ])
    finally:
        session.close()


@app.route("/api/<market>/signals/summary")
def api_signals_summary(market: str):
    """Return buy/sell/watch counts for the latest signal date."""
    session = get_session()
    try:
        # Find the most recent signal date for this market
        latest_row = session.execute(
            select(Signal.date)
            .where(Signal.market == market)
            .order_by(Signal.date.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not latest_row:
            return jsonify({"buy": 0, "sell": 0, "watch": 0})

        stmt = select(Signal).where(Signal.market == market, Signal.date == latest_row)
        rows = session.execute(stmt).scalars().all()

        counts = {"buy": 0, "sell": 0, "watch": 0}
        for r in rows:
            if r.signal_type in counts:
                counts[r.signal_type] += 1

        return jsonify(counts)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API — Chart Data
# ---------------------------------------------------------------------------

@app.route("/api/<market>/chart/<symbol>")
def api_chart(market: str, symbol: str):
    """Return OHLCV data and Livermore states for a symbol.

    Query params:
        days: number of days of history (default 90)
    """
    days = request.args.get("days", 90, type=int)
    session = get_session()
    try:
        start = date.today() - timedelta(days=days)
        end = date.today()

        # OHLCV
        price_stmt = (
            select(Price)
            .where(
                Price.symbol == symbol,
                Price.market == market,
                Price.date >= start,
                Price.date <= end,
            )
            .order_by(Price.date)
        )
        prices = session.execute(price_stmt).scalars().all()

        ohlcv = [
            {
                "date": p.date.isoformat(),
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": p.volume,
            }
            for p in prices
        ]

        # Livermore states
        state_stmt = (
            select(LivermoreState)
            .where(
                LivermoreState.symbol == symbol,
                LivermoreState.market == market,
                LivermoreState.date >= start,
                LivermoreState.date <= end,
            )
            .order_by(LivermoreState.date)
        )
        states = session.execute(state_stmt).scalars().all()

        livermore_states = [
            {
                "date": s.date.isoformat(),
                "column_state": s.column_state,
                "trend_direction": s.trend_direction,
                "trend_strength": s.trend_strength,
                "trend_duration_days": s.trend_duration_days,
            }
            for s in states
        ]

        return jsonify({
            "ohlcv": ohlcv,
            "livermore_states": livermore_states,
        })
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API — Performance
# ---------------------------------------------------------------------------

@app.route("/api/<market>/performance")
def api_performance(market: str):
    """Return trade statistics, signal accuracy, and recent trades."""
    session = get_session()
    try:
        # Signal accuracy
        history = SignalHistory(session)
        accuracy = history.get_accuracy(market, days_back=90)

        # Trade stats
        all_trades_stmt = select(Trade).where(Trade.market == market)
        all_trades = session.execute(all_trades_stmt).scalars().all()

        closed = [t for t in all_trades if t.status == "closed"]
        open_trades = [t for t in all_trades if t.status == "open"]

        total_pnl = sum(t.pnl or 0 for t in closed)
        win_count = sum(1 for t in closed if (t.pnl or 0) > 0)
        loss_count = sum(1 for t in closed if (t.pnl or 0) <= 0)
        win_rate = (win_count / len(closed) * 100) if closed else 0.0

        recent_trades = sorted(
            all_trades, key=lambda t: t.entry_date, reverse=True
        )[:20]

        return jsonify({
            "signal_accuracy": accuracy,
            "trade_stats": {
                "total_trades": len(all_trades),
                "open_trades": len(open_trades),
                "closed_trades": len(closed),
                "total_pnl": total_pnl,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": win_rate,
            },
            "recent_trades": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "entry_date": t.entry_date.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_date": t.exit_date.isoformat() if t.exit_date else None,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "status": t.status,
                }
                for t in recent_trades
            ],
        })
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API — Symbol Names
# ---------------------------------------------------------------------------

def _load_settings() -> dict:
    """Load settings.yaml and cache the result."""
    config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.route("/api/<market>/symbol-names")
def api_symbol_names(market: str):
    """Return ``{ticker: display_name}`` mapping for watchlist and indices.

    This allows the frontend to show human-readable names next to ticker codes.
    """
    config = _load_settings()
    market_cfg = config.get("markets", {}).get(market, {})

    names: dict[str, str] = {}
    for section in ("watchlist", "indices"):
        for item in market_cfg.get(section, []):
            if isinstance(item, dict):
                names[item["ticker"]] = item.get("name", item["ticker"])
            else:
                names[str(item)] = str(item)

    return jsonify(names)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5002, debug=True)
