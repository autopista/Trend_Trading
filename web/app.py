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
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from sqlalchemy import and_, select, func

# Load .env before anything else
load_dotenv(Path(__file__).parent.parent / "config" / ".env")

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
# API — Gemini AI Analysis
# ---------------------------------------------------------------------------

@app.route("/api/<market>/analyze/<symbol>")
def api_analyze(market: str, symbol: str):
    """Run Gemini AI analysis on a stock and return summary."""
    import os
    import json
    import requests as http_requests

    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return jsonify({"error": "GOOGLE_API_KEY not configured"}), 500

    session = get_session()
    try:
        # Gather stock data
        cutoff = date.today() - timedelta(days=90)
        prices = session.execute(
            select(Price)
            .where(Price.symbol == symbol, Price.date >= cutoff)
            .order_by(Price.date.desc())
            .limit(60)
        ).scalars().all()

        if not prices:
            return jsonify({"error": "No price data found"}), 404

        latest = prices[0]
        oldest = prices[-1]
        price_change = round((latest.close - oldest.close) / oldest.close * 100, 2)
        high_60d = max(p.high for p in prices)
        low_60d = min(p.low for p in prices)
        avg_volume = int(sum(p.volume for p in prices) / len(prices))

        # Recent 5 days
        recent_5 = prices[:5]
        recent_prices_str = "\n".join([
            f"  {p.date}: 시가={p.open:,.0f} 고가={p.high:,.0f} 저가={p.low:,.0f} 종가={p.close:,.0f} 거래량={p.volume:,}"
            for p in recent_5
        ])

        # Livermore state
        state = session.execute(
            select(LivermoreState)
            .where(LivermoreState.symbol == symbol)
            .order_by(LivermoreState.date.desc())
            .limit(1)
        ).scalar_one_or_none()

        livermore_info = "N/A"
        if state:
            state_kr = {
                "upward_trend": "상승추세", "downward_trend": "하락추세",
                "natural_rally": "자연반등", "natural_reaction": "자연반락",
                "secondary_rally": "2차반등", "secondary_reaction": "2차반락",
                "neutral": "중립",
            }
            livermore_info = f"{state_kr.get(state.column_state, state.column_state)} (강도: {state.trend_strength:.0f}/100, 지속: {state.trend_duration_days}일)"

        # Latest signal
        signal = session.execute(
            select(Signal)
            .where(Signal.symbol == symbol)
            .order_by(Signal.date.desc())
            .limit(1)
        ).scalar_one_or_none()

        signal_info = "없음"
        if signal:
            type_kr = {"buy": "매수", "sell": "매도", "watch": "관찰"}
            signal_info = f"{type_kr.get(signal.signal_type, signal.signal_type)} (신뢰도: {signal.confidence:.0f}%, 사유: {signal.reason})"

        # Get symbol name
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        symbol_name = symbol
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            for mkt in cfg.get("markets", {}).values():
                for item in mkt.get("watchlist", []):
                    if isinstance(item, dict) and item.get("ticker") == symbol:
                        symbol_name = f"{item['name']} ({symbol})"
                        break
        except Exception:
            pass

        currency = "₩" if market == "kr" else "$"

        prompt = f"""당신은 제시 리버모어의 추세매매 전략 전문가입니다.
아래 데이터를 바탕으로 {symbol_name} 종목을 분석해주세요.

## 종목 데이터
- 현재가: {currency}{latest.close:,.0f}
- 60일 변동률: {price_change:+.2f}%
- 60일 고가: {currency}{high_60d:,.0f} / 저가: {currency}{low_60d:,.0f}
- 평균 거래량: {avg_volume:,}

## 최근 5거래일
{recent_prices_str}

## 리버모어 분석 상태
{livermore_info}

## 시스템 시그널
{signal_info}

## 분석 요청
다음 항목을 한국어로 간결하게 분석해주세요:

1. **추세 판단**: 현재 추세 방향과 강도
2. **핵심 가격대**: 주요 지지선/저항선
3. **거래량 분석**: 최근 거래량 동향
4. **리버모어 관점**: 리버모어 전략에 따른 현재 상태 해석
5. **매매 전략**: 구체적인 진입/퇴출 전략 제안
6. **리스크**: 주의해야 할 리스크 요인

각 항목을 2-3문장으로 요약해주세요."""

        # Call Gemini API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048}
        }
        resp = http_requests.post(url, json=payload, timeout=30)
        resp_data = resp.json()

        if "candidates" in resp_data:
            text = resp_data["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({
                "symbol": symbol,
                "name": symbol_name,
                "analysis": text,
                "price": latest.close,
                "change_pct": price_change,
                "livermore_state": livermore_info,
                "signal": signal_info,
            })
        else:
            return jsonify({"error": "Gemini API returned no response"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5002, debug=True)
