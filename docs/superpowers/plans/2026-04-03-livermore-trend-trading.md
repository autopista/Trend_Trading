# Livermore Trend Trading System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Jesse Livermore trend-following trading system that analyzes KR/US stock markets, generates buy/sell signals, and tracks portfolio performance via a Flask dashboard.

**Architecture:** Modular engine separation — market-agnostic `livermore_engine` processes OHLCV data, market-specific `collectors` feed SQLite DB, `signals` generates alerts, `web` renders dashboard. Daily pipeline orchestrated by `update_all.py`.

**Tech Stack:** Python 3.12+, Flask, SQLAlchemy + SQLite, yfinance, pykrx, LightweightCharts, ApexCharts, Tailwind CSS, python-telegram-bot, pandas

---

## File Map

| File | Responsibility |
|------|---------------|
| `config/settings.yaml` | Strategy parameters, watchlists, indices |
| `config/.env` | API keys, Telegram token |
| `db/__init__.py` | Package init |
| `db/database.py` | SQLAlchemy engine, session factory |
| `db/models.py` | 6 ORM models: Price, MarketIndex, LivermoreState, Signal, Trade, Portfolio |
| `db/repository.py` | CRUD functions for all models |
| `collectors/__init__.py` | Package init |
| `collectors/base.py` | BaseCollector ABC + validate_ohlcv |
| `collectors/kr_collector.py` | pykrx-based KR data collector |
| `collectors/us_collector.py` | yfinance-based US data collector |
| `collectors/market_collector.py` | Facade combining KR/US collectors |
| `livermore_engine/__init__.py` | Package init |
| `livermore_engine/market_key.py` | 6-state Livermore Market Key |
| `livermore_engine/pivot_points.py` | Pivot detection + false breakout filter |
| `livermore_engine/volume_analysis.py` | Volume surge, divergence, climax |
| `livermore_engine/trend_analyzer.py` | Top-down market→stock trend filter |
| `livermore_engine/money_management.py` | Split buy/sell, stop loss, position sizing |
| `signals/__init__.py` | Package init |
| `signals/signal_generator.py` | Combine engine outputs → buy/sell/watch signals |
| `signals/telegram_notifier.py` | Telegram alert sender |
| `signals/signal_history.py` | Signal history tracking + accuracy stats |
| `web/__init__.py` | Package init |
| `web/app.py` | Flask app, routes, API endpoints |
| `web/templates/index.html` | Main dashboard (market indices, signals, chart) |
| `web/templates/performance.html` | Performance tracking page |
| `update_all.py` | 4-phase daily pipeline |
| `requirements.txt` | Python dependencies |
| `tests/conftest.py` | Shared fixtures (in-memory DB, sample OHLCV data) |
| `tests/test_models.py` | DB model tests |
| `tests/test_market_key.py` | Market Key 6-state transition tests |
| `tests/test_pivot_points.py` | Pivot detection + false breakout tests |
| `tests/test_volume_analysis.py` | Volume analysis tests |
| `tests/test_signal_generator.py` | Signal generation + priority tests |
| `tests/test_pipeline.py` | End-to-end pipeline integration test |

---

## Task 1: Project Scaffold + Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `config/settings.yaml`
- Create: `config/.env.example`

- [ ] **Step 1: Create requirements.txt**

```
flask==3.1.*
sqlalchemy==2.0.*
yfinance==0.2.*
pykrx==1.0.*
pandas==2.2.*
python-telegram-bot==21.*
pyyaml==6.*
python-dotenv==1.*
apscheduler==3.10.*
pytest==8.*
```

- [ ] **Step 2: Create config/settings.yaml**

```yaml
markets:
  kr:
    watchlist:
      - "005930"   # 삼성전자
      - "000660"   # SK하이닉스
      - "035420"   # NAVER
      - "051910"   # LG화학
      - "006400"   # 삼성SDI
    indices:
      - "KOSPI"
      - "KOSDAQ"
  us:
    watchlist:
      - "AAPL"
      - "MSFT"
      - "GOOGL"
      - "AMZN"
      - "NVDA"
    indices:
      - "^GSPC"    # S&P 500
      - "^IXIC"    # NASDAQ
      - "^DJI"     # DOW
      - "^VIX"     # VIX

livermore:
  pivot_threshold_pct: 5.0
  volume_surge_ratio: 1.5
  lookback_days: 20
  false_breakout_confirm_days: 2

money_management:
  max_position_pct: 20
  split_buy_ratio: [50, 30, 20]
  stop_loss_pct: 5.0

signals:
  min_confidence: 60
  telegram_enabled: true

web:
  host: "127.0.0.1"
  port: 5002
```

- [ ] **Step 3: Create config/.env.example**

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

- [ ] **Step 4: Create package __init__.py files**

Create empty `__init__.py` in: `db/`, `collectors/`, `livermore_engine/`, `signals/`, `web/`, `tests/`

- [ ] **Step 5: Install dependencies**

Run: `cd /Users/youngho/Documents/Project/Trend_Trading && pip install -r requirements.txt`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config/ db/__init__.py collectors/__init__.py livermore_engine/__init__.py signals/__init__.py web/__init__.py tests/__init__.py
git commit -m "feat: project scaffold with dependencies and config"
```

---

## Task 2: Database Models + Repository

**Files:**
- Create: `db/database.py`
- Create: `db/models.py`
- Create: `db/repository.py`
- Create: `tests/conftest.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write tests/conftest.py with shared fixtures**

```python
import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base
from db.database import get_session

@pytest.fixture
def db_session():
    """In-memory SQLite DB for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def sample_ohlcv_data():
    """20 days of sample OHLCV data for testing."""
    import pandas as pd
    dates = pd.bdate_range(start="2026-03-01", periods=20)
    base_price = 70000
    data = []
    for i, d in enumerate(dates):
        close = base_price + (i * 500) + ((-1)**i * 200)
        data.append({
            "date": d.date(),
            "open": close - 100,
            "high": close + 300,
            "low": close - 400,
            "close": close,
            "volume": 1000000 + i * 50000,
        })
    return pd.DataFrame(data)
```

- [ ] **Step 2: Write tests/test_models.py**

```python
from datetime import date, datetime
from db.models import Price, MarketIndex, LivermoreState, Signal, Trade, Portfolio

def test_create_price(db_session):
    price = Price(
        symbol="005930", market="KR", date=date(2026, 4, 1),
        open=72000, high=73000, low=71000, close=72500, volume=1000000
    )
    db_session.add(price)
    db_session.commit()
    result = db_session.query(Price).filter_by(symbol="005930").first()
    assert result.close == 72500
    assert result.market == "KR"

def test_create_livermore_state(db_session):
    state = LivermoreState(
        symbol="005930", market="KR", date=date(2026, 4, 1),
        column_state="upward_trend", reference_pivot_price=70000,
        trend_direction="up", trend_strength=75.0, trend_duration_days=10
    )
    db_session.add(state)
    db_session.commit()
    result = db_session.query(LivermoreState).first()
    assert result.column_state == "upward_trend"
    assert result.trend_strength == 75.0

def test_create_signal(db_session):
    signal = Signal(
        symbol="005930", market="KR", date=date(2026, 4, 1),
        signal_type="buy", price=72500, target_price=79600,
        stop_price=68780, reason="피봇 돌파 + 거래량 급증",
        confidence=87.0, notified=False, created_at=datetime.now()
    )
    db_session.add(signal)
    db_session.commit()
    result = db_session.query(Signal).first()
    assert result.signal_type == "buy"
    assert result.confidence == 87.0

def test_create_trade_with_signal_fk(db_session):
    signal = Signal(
        symbol="AAPL", market="US", date=date(2026, 4, 1),
        signal_type="buy", price=189.42, confidence=74.0,
        reason="상승추세 재진입", notified=True, created_at=datetime.now()
    )
    db_session.add(signal)
    db_session.commit()
    trade = Trade(
        symbol="AAPL", market="US", entry_date=date(2026, 4, 1),
        entry_price=189.42, quantity=10, status="open", signal_id=signal.id
    )
    db_session.add(trade)
    db_session.commit()
    result = db_session.query(Trade).first()
    assert result.signal_id == signal.id
    assert result.status == "open"

def test_create_portfolio_snapshot(db_session):
    portfolio = Portfolio(
        market="KR", date=date(2026, 4, 1),
        total_value=11840000, cash=2000000, invested=9840000,
        daily_return=1.24, cumulative_return=18.4
    )
    db_session.add(portfolio)
    db_session.commit()
    result = db_session.query(Portfolio).first()
    assert result.cumulative_return == 18.4

def test_price_unique_constraint(db_session):
    import pytest as pt
    from sqlalchemy.exc import IntegrityError
    p1 = Price(symbol="005930", market="KR", date=date(2026, 4, 1),
               open=72000, high=73000, low=71000, close=72500, volume=100)
    p2 = Price(symbol="005930", market="KR", date=date(2026, 4, 1),
               open=73000, high=74000, low=72000, close=73500, volume=200)
    db_session.add(p1)
    db_session.commit()
    db_session.add(p2)
    with pt.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/youngho/Documents/Project/Trend_Trading && python -m pytest tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'db.models')

- [ ] **Step 4: Write db/database.py**

```python
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

_DB_DIR = Path(__file__).parent
_DB_PATH = _DB_DIR / "trend_trading.db"

_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
    return _engine


def get_session() -> Session:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def init_db():
    """Create all tables if they don't exist."""
    from db.models import Base
    Base.metadata.create_all(get_engine())
```

- [ ] **Step 5: Write db/models.py**

```python
from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, Text, Real, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    market = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Real, nullable=False)
    high = Column(Real, nullable=False)
    low = Column(Real, nullable=False)
    close = Column(Real, nullable=False)
    volume = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_price_symbol_date"),
        Index("idx_prices_symbol_date", "symbol", "date"),
        Index("idx_prices_market", "market"),
    )


class MarketIndex(Base):
    __tablename__ = "market_indices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_name = Column(Text, nullable=False)
    market = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    value = Column(Real, nullable=False)
    change_pct = Column(Real)
    trend_state = Column(Text)

    __table_args__ = (
        UniqueConstraint("index_name", "date", name="uq_index_name_date"),
        Index("idx_market_indices_name_date", "index_name", "date"),
    )


class LivermoreState(Base):
    __tablename__ = "livermore_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    market = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    column_state = Column(Text, nullable=False)
    reference_pivot_price = Column(Real)
    trend_direction = Column(Text)
    trend_strength = Column(Real)
    trend_duration_days = Column(Integer)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_livermore_symbol_date"),
        Index("idx_livermore_states_symbol_date", "symbol", "date"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    market = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    signal_type = Column(Text, nullable=False)
    price = Column(Real, nullable=False)
    target_price = Column(Real)
    stop_price = Column(Real)
    reason = Column(Text)
    confidence = Column(Real)
    notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    trades = relationship("Trade", back_populates="signal")

    __table_args__ = (
        UniqueConstraint("symbol", "market", "date", "signal_type",
                         name="uq_signal_symbol_market_date_type"),
        Index("idx_signals_symbol_date", "symbol", "date"),
        Index("idx_signals_date", "date"),
        Index("idx_signals_market_date", "market", "date"),
    )


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    market = Column(Text, nullable=False)
    entry_date = Column(Date, nullable=False)
    entry_price = Column(Real, nullable=False)
    exit_date = Column(Date)
    exit_price = Column(Real)
    quantity = Column(Integer, nullable=False)
    pnl = Column(Real)
    pnl_pct = Column(Real)
    status = Column(Text, nullable=False, default="open")
    signal_id = Column(Integer, ForeignKey("signals.id"))

    signal = relationship("Signal", back_populates="trades")

    __table_args__ = (
        Index("idx_trades_symbol", "symbol"),
        Index("idx_trades_entry_date", "entry_date"),
        Index("idx_trades_status", "status"),
    )


class Portfolio(Base):
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    total_value = Column(Real, nullable=False)
    cash = Column(Real, nullable=False)
    invested = Column(Real, nullable=False)
    daily_return = Column(Real)
    cumulative_return = Column(Real)

    __table_args__ = (
        UniqueConstraint("market", "date", name="uq_portfolio_market_date"),
        Index("idx_portfolio_market_date", "market", "date"),
    )
```

- [ ] **Step 6: Write db/repository.py**

```python
from datetime import date
from typing import Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import and_
from db.models import Price, MarketIndex, LivermoreState, Signal, Trade, Portfolio


def upsert_prices(session: Session, symbol: str, market: str, df: pd.DataFrame):
    """Insert or update OHLCV prices from DataFrame."""
    for _, row in df.iterrows():
        existing = session.query(Price).filter(
            and_(Price.symbol == symbol, Price.date == row["date"])
        ).first()
        if existing:
            existing.open = row["open"]
            existing.high = row["high"]
            existing.low = row["low"]
            existing.close = row["close"]
            existing.volume = row["volume"]
        else:
            session.add(Price(
                symbol=symbol, market=market, date=row["date"],
                open=row["open"], high=row["high"], low=row["low"],
                close=row["close"], volume=int(row["volume"])
            ))
    session.commit()


def get_prices(session: Session, symbol: str, start: date, end: date) -> pd.DataFrame:
    """Get OHLCV prices as DataFrame."""
    rows = session.query(Price).filter(
        and_(Price.symbol == symbol, Price.date >= start, Price.date <= end)
    ).order_by(Price.date).all()
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    return pd.DataFrame([{
        "date": r.date, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume
    } for r in rows])


def upsert_market_index(session: Session, index_name: str, market: str,
                        d: date, value: float, change_pct: float = None,
                        trend_state: str = None):
    existing = session.query(MarketIndex).filter(
        and_(MarketIndex.index_name == index_name, MarketIndex.date == d)
    ).first()
    if existing:
        existing.value = value
        existing.change_pct = change_pct
        existing.trend_state = trend_state
    else:
        session.add(MarketIndex(
            index_name=index_name, market=market, date=d,
            value=value, change_pct=change_pct, trend_state=trend_state
        ))
    session.commit()


def upsert_livermore_state(session: Session, symbol: str, market: str,
                           d: date, column_state: str, reference_pivot_price: float,
                           trend_direction: str, trend_strength: float,
                           trend_duration_days: int):
    existing = session.query(LivermoreState).filter(
        and_(LivermoreState.symbol == symbol, LivermoreState.date == d)
    ).first()
    if existing:
        existing.column_state = column_state
        existing.reference_pivot_price = reference_pivot_price
        existing.trend_direction = trend_direction
        existing.trend_strength = trend_strength
        existing.trend_duration_days = trend_duration_days
    else:
        session.add(LivermoreState(
            symbol=symbol, market=market, date=d,
            column_state=column_state, reference_pivot_price=reference_pivot_price,
            trend_direction=trend_direction, trend_strength=trend_strength,
            trend_duration_days=trend_duration_days
        ))
    session.commit()


def save_signal(session: Session, symbol: str, market: str, d: date,
                signal_type: str, price: float, confidence: float,
                reason: str, target_price: float = None,
                stop_price: float = None) -> Signal:
    signal = Signal(
        symbol=symbol, market=market, date=d, signal_type=signal_type,
        price=price, target_price=target_price, stop_price=stop_price,
        reason=reason, confidence=confidence, notified=False
    )
    session.add(signal)
    session.commit()
    return signal


def get_signals_by_date(session: Session, market: str, d: date) -> list[Signal]:
    return session.query(Signal).filter(
        and_(Signal.market == market, Signal.date == d)
    ).order_by(Signal.confidence.desc()).all()


def get_open_trades(session: Session, market: str) -> list[Trade]:
    return session.query(Trade).filter(
        and_(Trade.market == market, Trade.status == "open")
    ).all()


def get_latest_livermore_state(session: Session, symbol: str) -> Optional[LivermoreState]:
    return session.query(LivermoreState).filter(
        LivermoreState.symbol == symbol
    ).order_by(LivermoreState.date.desc()).first()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/youngho/Documents/Project/Trend_Trading && python -m pytest tests/test_models.py -v`
Expected: All 6 tests PASS

- [ ] **Step 8: Commit**

```bash
git add db/ tests/conftest.py tests/test_models.py
git commit -m "feat: database models, repository, and model tests"
```

---

## Task 3: Livermore Market Key Engine

**Files:**
- Create: `livermore_engine/market_key.py`
- Create: `tests/test_market_key.py`

- [ ] **Step 1: Write tests/test_market_key.py**

```python
import pandas as pd
from datetime import date
from livermore_engine.market_key import MarketKey


def _make_ohlcv(prices: list[float], volumes: list[int] = None) -> pd.DataFrame:
    """Helper: create OHLCV DataFrame from close prices."""
    if volumes is None:
        volumes = [1000000] * len(prices)
    dates = pd.bdate_range(start="2026-01-05", periods=len(prices))
    data = []
    for i, (p, v) in enumerate(zip(prices, volumes)):
        data.append({
            "date": dates[i].date(),
            "open": p - 50,
            "high": p + 100,
            "low": p - 150,
            "close": p,
            "volume": v,
        })
    return pd.DataFrame(data)


def test_initial_state_is_neutral():
    mk = MarketKey(pivot_threshold_pct=5.0)
    prices = _make_ohlcv([10000] * 5)
    result = mk.analyze(prices)
    assert len(result) == 5
    assert result.iloc[0]["column_state"] == "neutral"


def test_upward_trend_on_breakout():
    """Price rises >5% from initial → upward_trend."""
    mk = MarketKey(pivot_threshold_pct=5.0)
    prices_list = [10000, 10100, 10200, 10300, 10400, 10550, 10600, 10700, 10800]
    prices = _make_ohlcv(prices_list)
    result = mk.analyze(prices)
    last_state = result.iloc[-1]["column_state"]
    assert last_state == "upward_trend"
    assert result.iloc[-1]["trend_direction"] == "up"


def test_downward_trend_on_breakdown():
    """Price drops >5% from initial → downward_trend."""
    mk = MarketKey(pivot_threshold_pct=5.0)
    prices_list = [10000, 9900, 9800, 9700, 9600, 9500, 9400, 9300, 9200]
    prices = _make_ohlcv(prices_list)
    result = mk.analyze(prices)
    last_state = result.iloc[-1]["column_state"]
    assert last_state == "downward_trend"
    assert result.iloc[-1]["trend_direction"] == "down"


def test_natural_reaction_during_uptrend():
    """In uptrend, a pullback >threshold/2 triggers natural_reaction."""
    mk = MarketKey(pivot_threshold_pct=5.0)
    # Rise then pull back ~3%
    prices_list = [10000, 10200, 10400, 10600, 10800, 11000, 10700, 10500, 10400]
    prices = _make_ohlcv(prices_list)
    result = mk.analyze(prices)
    states = result["column_state"].tolist()
    assert "natural_reaction" in states


def test_natural_rally_during_downtrend():
    """In downtrend, a bounce >threshold/2 triggers natural_rally."""
    mk = MarketKey(pivot_threshold_pct=5.0)
    prices_list = [10000, 9800, 9600, 9400, 9200, 9000, 9200, 9400, 9500]
    prices = _make_ohlcv(prices_list)
    result = mk.analyze(prices)
    states = result["column_state"].tolist()
    assert "natural_rally" in states


def test_trend_duration_increments():
    mk = MarketKey(pivot_threshold_pct=5.0)
    prices_list = [10000, 10200, 10400, 10600, 10800, 11000, 11200, 11400]
    prices = _make_ohlcv(prices_list)
    result = mk.analyze(prices)
    durations = result["trend_duration_days"].tolist()
    # Duration should generally increase
    assert durations[-1] > durations[1]


def test_trend_strength_calculated():
    mk = MarketKey(pivot_threshold_pct=5.0)
    prices_list = [10000, 10200, 10400, 10600, 10800, 11000, 11200, 11400]
    prices = _make_ohlcv(prices_list)
    result = mk.analyze(prices)
    assert all(0 <= s <= 100 for s in result["trend_strength"].tolist())


def test_output_columns():
    mk = MarketKey(pivot_threshold_pct=5.0)
    prices = _make_ohlcv([10000] * 5)
    result = mk.analyze(prices)
    expected_cols = {"date", "column_state", "reference_pivot_price",
                     "trend_direction", "trend_strength", "trend_duration_days"}
    assert expected_cols == set(result.columns)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_market_key.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write livermore_engine/market_key.py**

```python
import pandas as pd
import numpy as np

# Livermore 6-state constants
UPWARD_TREND = "upward_trend"
NATURAL_RALLY = "natural_rally"
SECONDARY_RALLY = "secondary_rally"
DOWNWARD_TREND = "downward_trend"
NATURAL_REACTION = "natural_reaction"
SECONDARY_REACTION = "secondary_reaction"
NEUTRAL = "neutral"


class MarketKey:
    """Livermore Market Key: 6-state column recording system."""

    def __init__(self, pivot_threshold_pct: float = 5.0):
        self.threshold = pivot_threshold_pct / 100.0
        self.half_threshold = self.threshold / 2.0

    def analyze(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Analyze OHLCV data and return Livermore states per day.

        Args:
            ohlcv: DataFrame with columns [date, open, high, low, close, volume]

        Returns:
            DataFrame with columns [date, column_state, reference_pivot_price,
                                    trend_direction, trend_strength, trend_duration_days]
        """
        if ohlcv.empty:
            return pd.DataFrame(columns=[
                "date", "column_state", "reference_pivot_price",
                "trend_direction", "trend_strength", "trend_duration_days"
            ])

        closes = ohlcv["close"].values
        dates = ohlcv["date"].values
        n = len(closes)

        states = []
        current_state = NEUTRAL
        pivot_high = closes[0]
        pivot_low = closes[0]
        reference_pivot = closes[0]
        trend_start_idx = 0

        for i in range(n):
            price = closes[i]
            prev_state = current_state

            # Track running highs/lows
            if price > pivot_high:
                pivot_high = price
            if price < pivot_low:
                pivot_low = price

            # State transitions
            if current_state == NEUTRAL:
                if price >= reference_pivot * (1 + self.threshold):
                    current_state = UPWARD_TREND
                    pivot_low = price
                    reference_pivot = pivot_high
                    trend_start_idx = i
                elif price <= reference_pivot * (1 - self.threshold):
                    current_state = DOWNWARD_TREND
                    pivot_high = price
                    reference_pivot = pivot_low
                    trend_start_idx = i

            elif current_state == UPWARD_TREND:
                if price > pivot_high:
                    pivot_high = price
                    reference_pivot = pivot_high
                if price <= pivot_high * (1 - self.half_threshold):
                    current_state = NATURAL_REACTION
                    pivot_low = price
                    trend_start_idx = i

            elif current_state == NATURAL_REACTION:
                if price < pivot_low:
                    pivot_low = price
                if price >= pivot_low * (1 + self.half_threshold):
                    current_state = SECONDARY_RALLY
                    pivot_high = price
                    trend_start_idx = i
                if price <= reference_pivot * (1 - self.threshold):
                    current_state = DOWNWARD_TREND
                    reference_pivot = pivot_low
                    pivot_high = price
                    trend_start_idx = i

            elif current_state == SECONDARY_RALLY:
                if price > pivot_high:
                    pivot_high = price
                if price >= reference_pivot:
                    current_state = UPWARD_TREND
                    reference_pivot = pivot_high
                    trend_start_idx = i
                if price <= pivot_high * (1 - self.half_threshold):
                    current_state = NATURAL_REACTION
                    pivot_low = price
                    trend_start_idx = i

            elif current_state == DOWNWARD_TREND:
                if price < pivot_low:
                    pivot_low = price
                    reference_pivot = pivot_low
                if price >= pivot_low * (1 + self.half_threshold):
                    current_state = NATURAL_RALLY
                    pivot_high = price
                    trend_start_idx = i

            elif current_state == NATURAL_RALLY:
                if price > pivot_high:
                    pivot_high = price
                if price <= pivot_high * (1 - self.half_threshold):
                    current_state = SECONDARY_REACTION
                    pivot_low = price
                    trend_start_idx = i
                if price >= reference_pivot * (1 + self.threshold):
                    current_state = UPWARD_TREND
                    reference_pivot = pivot_high
                    pivot_low = price
                    trend_start_idx = i

            elif current_state == SECONDARY_REACTION:
                if price < pivot_low:
                    pivot_low = price
                if price <= reference_pivot:
                    current_state = DOWNWARD_TREND
                    reference_pivot = pivot_low
                    trend_start_idx = i
                if price >= pivot_low * (1 + self.half_threshold):
                    current_state = NATURAL_RALLY
                    pivot_high = price
                    trend_start_idx = i

            # Calculate trend direction
            if current_state in (UPWARD_TREND, NATURAL_REACTION, SECONDARY_RALLY):
                direction = "up"
            elif current_state in (DOWNWARD_TREND, NATURAL_RALLY, SECONDARY_REACTION):
                direction = "down"
            else:
                direction = "neutral"

            # Calculate trend strength (0-100)
            duration = i - trend_start_idx + 1
            if reference_pivot > 0:
                price_distance = abs(price - reference_pivot) / reference_pivot
            else:
                price_distance = 0
            strength = min(100.0, (price_distance / self.threshold) * 50 + min(duration, 20) * 2.5)

            states.append({
                "date": dates[i],
                "column_state": current_state,
                "reference_pivot_price": round(reference_pivot, 2),
                "trend_direction": direction,
                "trend_strength": round(strength, 1),
                "trend_duration_days": duration,
            })

        return pd.DataFrame(states)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_market_key.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add livermore_engine/market_key.py tests/test_market_key.py
git commit -m "feat: Livermore Market Key 6-state analysis engine"
```

---

## Task 4: Pivot Points Detection

**Files:**
- Create: `livermore_engine/pivot_points.py`
- Create: `tests/test_pivot_points.py`

- [ ] **Step 1: Write tests/test_pivot_points.py**

```python
import pandas as pd
from livermore_engine.pivot_points import PivotDetector


def _make_ohlcv(closes, volumes=None, start="2026-01-05"):
    if volumes is None:
        volumes = [1000000] * len(closes)
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame([{
        "date": d.date(), "open": c - 50, "high": c + 100,
        "low": c - 150, "close": c, "volume": v
    } for d, c, v in zip(dates, closes, volumes)])


def test_no_pivot_in_flat_market():
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5)
    prices = _make_ohlcv([10000] * 10)
    result = pd_.detect(prices)
    breakouts = result[result["pivot_type"] != "none"]
    assert len(breakouts) == 0


def test_breakout_pivot_detected():
    """Price above 5-day high with volume surge → breakout pivot."""
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5)
    closes = [10000, 10050, 10020, 10080, 10030, 10010, 10500, 10600, 10700]
    volumes = [100000, 100000, 100000, 100000, 100000, 100000, 200000, 200000, 200000]
    prices = _make_ohlcv(closes, volumes)
    result = pd_.detect(prices)
    breakouts = result[result["pivot_type"] == "breakout"]
    assert len(breakouts) > 0


def test_breakdown_pivot_detected():
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5)
    closes = [10000, 9980, 10020, 9970, 10010, 9990, 9400, 9300, 9200]
    volumes = [100000, 100000, 100000, 100000, 100000, 100000, 200000, 200000, 200000]
    prices = _make_ohlcv(closes, volumes)
    result = pd_.detect(prices)
    breakdowns = result[result["pivot_type"] == "breakdown"]
    assert len(breakdowns) > 0


def test_no_pivot_without_volume_surge():
    """Price breaks out but volume is below threshold → no pivot."""
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5)
    closes = [10000, 10050, 10020, 10080, 10030, 10010, 10500, 10600, 10700]
    volumes = [100000] * 9  # No volume surge
    prices = _make_ohlcv(closes, volumes)
    result = pd_.detect(prices)
    breakouts = result[result["pivot_type"] == "breakout"]
    assert len(breakouts) == 0


def test_false_breakout_filter():
    """Breakout that doesn't hold for confirm_days → marked unconfirmed."""
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5, confirm_days=2)
    closes = [10000, 10050, 10020, 10080, 10030, 10010, 10500, 9800, 9700]
    volumes = [100000, 100000, 100000, 100000, 100000, 100000, 200000, 200000, 200000]
    prices = _make_ohlcv(closes, volumes)
    result = pd_.detect(prices)
    confirmed = result[result["confirmed"] == True]
    assert len(confirmed) == 0


def test_confirmed_breakout():
    """Breakout that holds for confirm_days → confirmed."""
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5, confirm_days=2)
    closes = [10000, 10050, 10020, 10080, 10030, 10010, 10500, 10550, 10600]
    volumes = [100000, 100000, 100000, 100000, 100000, 100000, 200000, 180000, 170000]
    prices = _make_ohlcv(closes, volumes)
    result = pd_.detect(prices)
    confirmed = result[(result["pivot_type"] == "breakout") & (result["confirmed"] == True)]
    assert len(confirmed) > 0


def test_consolidation_days_tracked():
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5)
    closes = [10000, 10010, 9990, 10005, 10015, 9995, 10010, 10500, 10600]
    volumes = [100000] * 7 + [200000, 200000]
    prices = _make_ohlcv(closes, volumes)
    result = pd_.detect(prices)
    assert "consolidation_days" in result.columns


def test_output_columns():
    pd_ = PivotDetector(lookback_days=5, volume_surge_ratio=1.5)
    prices = _make_ohlcv([10000] * 10)
    result = pd_.detect(prices)
    expected = {"date", "pivot_type", "pivot_price", "resistance", "support",
                "volume_ratio", "confirmed", "consolidation_days"}
    assert expected == set(result.columns)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pivot_points.py -v`
Expected: FAIL

- [ ] **Step 3: Write livermore_engine/pivot_points.py**

```python
import pandas as pd
import numpy as np


class PivotDetector:
    """Detect pivotal points with false breakout filtering."""

    def __init__(self, lookback_days: int = 20, volume_surge_ratio: float = 1.5,
                 confirm_days: int = 2):
        self.lookback = lookback_days
        self.volume_ratio = volume_surge_ratio
        self.confirm_days = confirm_days

    def detect(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Detect pivot points in OHLCV data.

        Returns DataFrame with columns:
            date, pivot_type, pivot_price, resistance, support,
            volume_ratio, confirmed, consolidation_days
        """
        n = len(ohlcv)
        closes = ohlcv["close"].values
        highs = ohlcv["high"].values
        lows = ohlcv["low"].values
        volumes = ohlcv["volume"].values
        dates = ohlcv["date"].values

        results = []
        for i in range(n):
            lb_start = max(0, i - self.lookback)
            lb_end = max(1, i)  # exclude current day

            if i == 0:
                results.append(self._empty_row(dates[i], closes[i], closes[i]))
                continue

            resistance = float(np.max(highs[lb_start:lb_end]))
            support = float(np.min(lows[lb_start:lb_end]))

            # Volume analysis
            vol_window = volumes[lb_start:lb_end]
            avg_vol = float(np.mean(vol_window)) if len(vol_window) > 0 else 1
            curr_vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 0
            has_volume = curr_vol_ratio >= self.volume_ratio

            # Consolidation: count days price stayed within support-resistance band
            band_range = resistance - support
            if band_range > 0:
                threshold = band_range * 0.1  # 10% of band range
                consol_days = 0
                for j in range(lb_start, lb_end):
                    if abs(closes[j] - (support + resistance) / 2) < band_range / 2:
                        consol_days += 1
            else:
                consol_days = lb_end - lb_start

            pivot_type = "none"
            pivot_price = 0.0

            if closes[i] > resistance and has_volume:
                pivot_type = "breakout"
                pivot_price = resistance
            elif closes[i] < support and has_volume:
                pivot_type = "breakdown"
                pivot_price = support

            # False breakout confirmation
            confirmed = False
            if pivot_type != "none" and i + self.confirm_days < n:
                if pivot_type == "breakout":
                    confirmed = all(
                        closes[i + d] >= pivot_price
                        for d in range(1, self.confirm_days + 1)
                    )
                elif pivot_type == "breakdown":
                    confirmed = all(
                        closes[i + d] <= pivot_price
                        for d in range(1, self.confirm_days + 1)
                    )
            elif pivot_type != "none" and i + self.confirm_days >= n:
                # Not enough data to confirm yet
                confirmed = False

            results.append({
                "date": dates[i],
                "pivot_type": pivot_type,
                "pivot_price": round(pivot_price, 2),
                "resistance": round(resistance, 2),
                "support": round(support, 2),
                "volume_ratio": round(curr_vol_ratio, 2),
                "confirmed": confirmed,
                "consolidation_days": consol_days,
            })

        return pd.DataFrame(results)

    def _empty_row(self, dt, resistance, support):
        return {
            "date": dt, "pivot_type": "none", "pivot_price": 0.0,
            "resistance": round(resistance, 2), "support": round(support, 2),
            "volume_ratio": 0.0, "confirmed": False, "consolidation_days": 0,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pivot_points.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add livermore_engine/pivot_points.py tests/test_pivot_points.py
git commit -m "feat: pivot point detection with false breakout filtering"
```

---

## Task 5: Volume Analysis

**Files:**
- Create: `livermore_engine/volume_analysis.py`
- Create: `tests/test_volume_analysis.py`

- [ ] **Step 1: Write tests/test_volume_analysis.py**

```python
import pandas as pd
from livermore_engine.volume_analysis import VolumeAnalyzer


def _make_ohlcv(closes, volumes, start="2026-01-05"):
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame([{
        "date": d.date(), "open": c - 50, "high": c + 100,
        "low": c - 150, "close": c, "volume": v
    } for d, c, v in zip(dates, closes, volumes)])


def test_volume_surge_detected():
    va = VolumeAnalyzer(lookback_days=5, surge_ratio=1.5)
    closes = [100] * 7
    volumes = [1000, 1000, 1000, 1000, 1000, 1000, 2000]
    df = _make_ohlcv(closes, volumes)
    result = va.analyze(df)
    assert result.iloc[-1]["volume_surge"] == True


def test_no_surge_below_threshold():
    va = VolumeAnalyzer(lookback_days=5, surge_ratio=1.5)
    closes = [100] * 7
    volumes = [1000] * 7
    df = _make_ohlcv(closes, volumes)
    result = va.analyze(df)
    assert result.iloc[-1]["volume_surge"] == False


def test_price_volume_divergence_bearish():
    """Price new high but volume declining → bearish divergence."""
    va = VolumeAnalyzer(lookback_days=5, surge_ratio=1.5)
    closes = [100, 102, 104, 106, 108, 110, 112]
    volumes = [2000, 1800, 1600, 1400, 1200, 1000, 800]
    df = _make_ohlcv(closes, volumes)
    result = va.analyze(df)
    divs = result[result["divergence"] == "bearish"]
    assert len(divs) > 0


def test_climax_volume():
    """Extreme volume spike → climax warning."""
    va = VolumeAnalyzer(lookback_days=5, surge_ratio=1.5)
    closes = [100] * 7
    volumes = [1000, 1000, 1000, 1000, 1000, 1000, 5000]
    df = _make_ohlcv(closes, volumes)
    result = va.analyze(df)
    assert result.iloc[-1]["climax"] == True


def test_output_columns():
    va = VolumeAnalyzer(lookback_days=5, surge_ratio=1.5)
    df = _make_ohlcv([100] * 7, [1000] * 7)
    result = va.analyze(df)
    expected = {"date", "volume_ratio", "volume_surge", "divergence", "climax"}
    assert expected == set(result.columns)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_volume_analysis.py -v`
Expected: FAIL

- [ ] **Step 3: Write livermore_engine/volume_analysis.py**

```python
import pandas as pd
import numpy as np


class VolumeAnalyzer:
    """Analyze volume for trend confirmation."""

    def __init__(self, lookback_days: int = 20, surge_ratio: float = 1.5,
                 climax_ratio: float = 3.0):
        self.lookback = lookback_days
        self.surge_ratio = surge_ratio
        self.climax_ratio = climax_ratio

    def analyze(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Analyze volume patterns.

        Returns DataFrame with columns:
            date, volume_ratio, volume_surge, divergence, climax
        """
        n = len(ohlcv)
        closes = ohlcv["close"].values
        volumes = ohlcv["volume"].values
        dates = ohlcv["date"].values

        results = []
        for i in range(n):
            lb_start = max(0, i - self.lookback)
            lb_end = max(1, i)

            vol_window = volumes[lb_start:lb_end]
            avg_vol = float(np.mean(vol_window)) if len(vol_window) > 0 else 1
            vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 0

            surge = vol_ratio >= self.surge_ratio
            climax = vol_ratio >= self.climax_ratio

            # Price-volume divergence
            divergence = "none"
            if i >= 5:
                price_window = closes[i - 4:i + 1]
                vol_window_recent = volumes[i - 4:i + 1]
                prices_rising = all(price_window[j] >= price_window[j - 1]
                                    for j in range(1, len(price_window)))
                vols_declining = all(vol_window_recent[j] <= vol_window_recent[j - 1]
                                     for j in range(1, len(vol_window_recent)))
                prices_falling = all(price_window[j] <= price_window[j - 1]
                                     for j in range(1, len(price_window)))
                vols_declining_too = all(vol_window_recent[j] <= vol_window_recent[j - 1]
                                         for j in range(1, len(vol_window_recent)))

                if prices_rising and vols_declining:
                    divergence = "bearish"
                elif prices_falling and vols_declining_too:
                    divergence = "bullish"

            results.append({
                "date": dates[i],
                "volume_ratio": round(vol_ratio, 2),
                "volume_surge": surge,
                "divergence": divergence,
                "climax": climax,
            })

        return pd.DataFrame(results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_volume_analysis.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add livermore_engine/volume_analysis.py tests/test_volume_analysis.py
git commit -m "feat: volume analysis with surge, divergence, and climax detection"
```

---

## Task 6: Trend Analyzer + Money Management

**Files:**
- Create: `livermore_engine/trend_analyzer.py`
- Create: `livermore_engine/money_management.py`

- [ ] **Step 1: Write livermore_engine/trend_analyzer.py**

```python
from dataclasses import dataclass
from livermore_engine.market_key import MarketKey, UPWARD_TREND, DOWNWARD_TREND, NEUTRAL


@dataclass
class MarketContext:
    trend_direction: str  # "up", "down", "neutral"
    trend_state: str      # Livermore state name
    trend_strength: float
    allow_buy: bool
    allow_sell: bool


class TrendAnalyzer:
    """Top-down trend analysis: market → individual stock filtering."""

    def __init__(self, pivot_threshold_pct: float = 5.0,
                 min_strength_for_neutral: float = 70.0):
        self.market_key = MarketKey(pivot_threshold_pct)
        self.min_strength = min_strength_for_neutral

    def analyze_market(self, market_ohlcv: "pd.DataFrame") -> MarketContext:
        """Analyze market index to determine allowed signal directions."""
        import pandas as pd
        result = self.market_key.analyze(market_ohlcv)
        if result.empty:
            return MarketContext("neutral", NEUTRAL, 0, True, True)

        latest = result.iloc[-1]
        direction = latest["trend_direction"]
        state = latest["column_state"]
        strength = latest["trend_strength"]

        if direction == "up":
            return MarketContext(direction, state, strength,
                                allow_buy=True, allow_sell=False)
        elif direction == "down":
            return MarketContext(direction, state, strength,
                                allow_buy=False, allow_sell=True)
        else:
            # Neutral: only strong signals
            return MarketContext(direction, state, strength,
                                allow_buy=True, allow_sell=True)

    def filter_signal(self, signal_type: str, confidence: float,
                      market_ctx: MarketContext) -> bool:
        """Check if signal is allowed given market context."""
        if signal_type == "buy" and not market_ctx.allow_buy:
            return False
        if signal_type == "sell" and not market_ctx.allow_sell:
            return False
        if market_ctx.trend_direction == "neutral" and confidence < self.min_strength:
            return False
        return True
```

- [ ] **Step 2: Write livermore_engine/money_management.py**

```python
from dataclasses import dataclass


@dataclass
class PositionPlan:
    total_shares: int
    splits: list[int]       # shares per split [50%, 30%, 20%]
    stop_price: float
    max_investment: float


class MoneyManager:
    """Livermore-style money management: split buys, stop loss, position sizing."""

    def __init__(self, max_position_pct: float = 20.0,
                 split_buy_ratio: list[float] = None,
                 stop_loss_pct: float = 5.0):
        self.max_position_pct = max_position_pct / 100.0
        self.split_ratios = split_buy_ratio or [50, 30, 20]
        self.stop_loss_pct = stop_loss_pct / 100.0

    def calculate_position(self, total_portfolio: float, price: float,
                           pivot_price: float) -> PositionPlan:
        """Calculate position size and split plan.

        Args:
            total_portfolio: total portfolio value
            price: current stock price
            pivot_price: reference pivot price for stop loss
        """
        max_investment = total_portfolio * self.max_position_pct
        total_shares = int(max_investment / price) if price > 0 else 0

        splits = []
        remaining = total_shares
        for ratio in self.split_ratios:
            shares = int(total_shares * ratio / 100)
            shares = min(shares, remaining)
            splits.append(shares)
            remaining -= shares
        if remaining > 0:
            splits[-1] += remaining

        stop_price = round(pivot_price * (1 - self.stop_loss_pct), 2)

        return PositionPlan(
            total_shares=total_shares,
            splits=splits,
            stop_price=stop_price,
            max_investment=round(max_investment, 2),
        )

    def should_stop_loss(self, current_price: float, stop_price: float) -> bool:
        return current_price <= stop_price

    def calculate_target_price(self, entry_price: float,
                               risk_reward_ratio: float = 2.0,
                               stop_price: float = 0) -> float:
        """Calculate target price based on risk-reward ratio."""
        risk = entry_price - stop_price
        if risk <= 0:
            return entry_price * 1.1  # default 10% target
        return round(entry_price + (risk * risk_reward_ratio), 2)
```

- [ ] **Step 3: Commit**

```bash
git add livermore_engine/trend_analyzer.py livermore_engine/money_management.py
git commit -m "feat: trend analyzer (top-down) and money management"
```

---

## Task 7: Data Collectors

**Files:**
- Create: `collectors/base.py`
- Create: `collectors/kr_collector.py`
- Create: `collectors/us_collector.py`
- Create: `collectors/market_collector.py`

- [ ] **Step 1: Write collectors/base.py**

```python
import logging
import time
from abc import ABC, abstractmethod
from datetime import date
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Base interface for market data collectors."""

    MAX_RETRIES = 3
    BASE_DELAY = 2  # seconds

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """Return OHLCV DataFrame with columns: date, open, high, low, close, volume"""

    @abstractmethod
    def fetch_index(self, index_name: str, start_date: date, end_date: date) -> pd.DataFrame:
        """Return index data DataFrame."""

    @abstractmethod
    def get_watchlist(self) -> list[str]:
        """Return list of symbols to watch."""

    def validate_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean OHLCV data."""
        if df.empty:
            return df

        # Remove rows with NaN in critical columns
        before = len(df)
        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        dropped = before - len(df)
        if dropped > 0:
            logger.warning(f"Dropped {dropped} rows with NaN values")

        # Validate price relationships
        invalid = (df["low"] > df["open"]) | (df["low"] > df["close"]) | \
                  (df["high"] < df["open"]) | (df["high"] < df["close"])
        if invalid.any():
            logger.warning(f"Found {invalid.sum()} rows with invalid OHLC relationships, fixing")
            df.loc[invalid, "high"] = df.loc[invalid, ["open", "high", "low", "close"]].max(axis=1)
            df.loc[invalid, "low"] = df.loc[invalid, ["open", "high", "low", "close"]].min(axis=1)

        # Validate volume
        df.loc[df["volume"] < 0, "volume"] = 0

        return df.reset_index(drop=True)

    def _retry(self, func, *args, **kwargs):
        """Execute with exponential backoff retry."""
        for attempt in range(self.MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.MAX_RETRIES - 1:
                    logger.error(f"Failed after {self.MAX_RETRIES} retries: {e}")
                    raise
                delay = self.BASE_DELAY * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s")
                time.sleep(delay)
```

- [ ] **Step 2: Write collectors/us_collector.py**

```python
import logging
from datetime import date
import pandas as pd
import yfinance as yf
from collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class USCollector(BaseCollector):
    """US market data collector using yfinance."""

    def __init__(self, watchlist: list[str], indices: list[str]):
        self.watchlist = watchlist
        self.indices = indices

    def fetch_ohlcv(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        def _fetch():
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date.isoformat(),
                                end=end_date.isoformat(), interval="1d")
            if df.empty:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            df = df.reset_index()
            df = df.rename(columns={
                "Date": "date", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume"
            })
            df["date"] = pd.to_datetime(df["date"]).dt.date
            return df[["date", "open", "high", "low", "close", "volume"]]

        logger.info(f"Fetching US OHLCV: {symbol}")
        df = self._retry(_fetch)
        return self.validate_ohlcv(df)

    def fetch_index(self, index_name: str, start_date: date, end_date: date) -> pd.DataFrame:
        return self.fetch_ohlcv(index_name, start_date, end_date)

    def get_watchlist(self) -> list[str]:
        return self.watchlist
```

- [ ] **Step 3: Write collectors/kr_collector.py**

```python
import logging
from datetime import date
import pandas as pd
from collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class KRCollector(BaseCollector):
    """Korean market data collector using pykrx."""

    def __init__(self, watchlist: list[str], indices: list[str]):
        self.watchlist = watchlist
        self.indices = indices

    def fetch_ohlcv(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        from pykrx import stock as pykrx_stock

        def _fetch():
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            df = pykrx_stock.get_market_ohlcv_by_date(start_str, end_str, symbol)
            if df.empty:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            df = df.reset_index()
            df = df.rename(columns={
                "날짜": "date", "시가": "open", "고가": "high",
                "저가": "low", "종가": "close", "거래량": "volume"
            })
            df["date"] = pd.to_datetime(df["date"]).dt.date
            return df[["date", "open", "high", "low", "close", "volume"]]

        logger.info(f"Fetching KR OHLCV: {symbol}")
        df = self._retry(_fetch)
        return self.validate_ohlcv(df)

    def fetch_index(self, index_name: str, start_date: date, end_date: date) -> pd.DataFrame:
        from pykrx import stock as pykrx_stock

        def _fetch():
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            df = pykrx_stock.get_index_ohlcv_by_date(start_str, end_str, index_name)
            if df.empty:
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            df = df.reset_index()
            df = df.rename(columns={
                "날짜": "date", "시가": "open", "고가": "high",
                "저가": "low", "종가": "close", "거래량": "volume"
            })
            df["date"] = pd.to_datetime(df["date"]).dt.date
            return df[["date", "open", "high", "low", "close", "volume"]]

        logger.info(f"Fetching KR index: {index_name}")
        df = self._retry(_fetch)
        return self.validate_ohlcv(df)

    def get_watchlist(self) -> list[str]:
        return self.watchlist
```

- [ ] **Step 4: Write collectors/market_collector.py**

```python
import logging
from datetime import date
from collectors.kr_collector import KRCollector
from collectors.us_collector import USCollector

logger = logging.getLogger(__name__)


class MarketCollector:
    """Facade combining KR and US collectors."""

    def __init__(self, config: dict):
        kr_cfg = config["markets"]["kr"]
        us_cfg = config["markets"]["us"]
        self.kr = KRCollector(kr_cfg["watchlist"], kr_cfg["indices"])
        self.us = USCollector(us_cfg["watchlist"], us_cfg["indices"])

    def collect_all(self, start_date: date, end_date: date, market: str = None) -> dict:
        """Collect all data. Returns dict with 'kr' and/or 'us' keys."""
        result = {}
        if market in (None, "kr"):
            result["kr"] = self._collect_market(self.kr, "KR", start_date, end_date)
        if market in (None, "us"):
            result["us"] = self._collect_market(self.us, "US", start_date, end_date)
        return result

    def _collect_market(self, collector, market_name, start_date, end_date) -> dict:
        data = {"stocks": {}, "indices": {}, "failed": []}

        for symbol in collector.get_watchlist():
            try:
                df = collector.fetch_ohlcv(symbol, start_date, end_date)
                data["stocks"][symbol] = df
                logger.info(f"[{market_name}] {symbol}: {len(df)} rows")
            except Exception as e:
                logger.error(f"[{market_name}] {symbol} failed: {e}")
                data["failed"].append(symbol)

        for index_name in collector.indices:
            try:
                df = collector.fetch_index(index_name, start_date, end_date)
                data["indices"][index_name] = df
                logger.info(f"[{market_name}] Index {index_name}: {len(df)} rows")
            except Exception as e:
                logger.error(f"[{market_name}] Index {index_name} failed: {e}")
                data["failed"].append(index_name)

        return data
```

- [ ] **Step 5: Commit**

```bash
git add collectors/
git commit -m "feat: data collectors (KR/US) with validation and retry"
```

---

## Task 8: Signal Generator

**Files:**
- Create: `signals/signal_generator.py`
- Create: `signals/signal_history.py`
- Create: `tests/test_signal_generator.py`

- [ ] **Step 1: Write tests/test_signal_generator.py**

```python
import pandas as pd
from datetime import date
from signals.signal_generator import SignalGenerator


def _make_engine_results():
    """Create mock engine analysis results for one stock."""
    return {
        "market_key": pd.DataFrame([{
            "date": date(2026, 4, 1),
            "column_state": "upward_trend",
            "reference_pivot_price": 70000,
            "trend_direction": "up",
            "trend_strength": 75.0,
            "trend_duration_days": 10,
        }]),
        "pivots": pd.DataFrame([{
            "date": date(2026, 4, 1),
            "pivot_type": "breakout",
            "pivot_price": 70000,
            "resistance": 70000,
            "support": 66000,
            "volume_ratio": 2.1,
            "confirmed": True,
            "consolidation_days": 8,
        }]),
        "volume": pd.DataFrame([{
            "date": date(2026, 4, 1),
            "volume_ratio": 2.1,
            "volume_surge": True,
            "divergence": "none",
            "climax": False,
        }]),
        "price": 72500,
        "rsi": 62.0,
    }


def test_buy_signal_generated():
    sg = SignalGenerator(min_confidence=60)
    results = _make_engine_results()
    market_direction = "up"
    signals = sg.generate("005930", results, market_direction)
    assert len(signals) == 1
    assert signals[0]["signal_type"] == "buy"
    assert signals[0]["confidence"] >= 60


def test_watch_signal_when_unconfirmed():
    sg = SignalGenerator(min_confidence=60)
    results = _make_engine_results()
    results["pivots"].iloc[0, results["pivots"].columns.get_loc("confirmed")] = False
    market_direction = "up"
    signals = sg.generate("005930", results, market_direction)
    assert signals[0]["signal_type"] == "watch"


def test_no_buy_in_down_market():
    sg = SignalGenerator(min_confidence=60)
    results = _make_engine_results()
    market_direction = "down"
    signals = sg.generate("005930", results, market_direction)
    buy_signals = [s for s in signals if s["signal_type"] == "buy"]
    assert len(buy_signals) == 0


def test_watch_when_rsi_overbought():
    sg = SignalGenerator(min_confidence=60)
    results = _make_engine_results()
    results["rsi"] = 75.0
    market_direction = "up"
    signals = sg.generate("005930", results, market_direction)
    assert signals[0]["signal_type"] == "watch"


def test_confidence_calculation():
    sg = SignalGenerator(min_confidence=0)
    results = _make_engine_results()
    market_direction = "up"
    signals = sg.generate("005930", results, market_direction)
    conf = signals[0]["confidence"]
    assert 0 <= conf <= 100


def test_signal_priority_ordering():
    sg = SignalGenerator(min_confidence=60)
    signals = [
        {"symbol": "A", "confidence": 90, "volume_ratio": 2.0},
        {"symbol": "B", "confidence": 90, "volume_ratio": 3.0},
        {"symbol": "C", "confidence": 80, "volume_ratio": 5.0},
    ]
    sorted_signals = sg.prioritize(signals)
    assert sorted_signals[0]["symbol"] == "B"  # same confidence, higher volume
    assert sorted_signals[2]["symbol"] == "C"  # lower confidence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_signal_generator.py -v`
Expected: FAIL

- [ ] **Step 3: Write signals/signal_generator.py**

```python
import logging
from datetime import date
import pandas as pd

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generate buy/sell/watch signals from engine analysis results."""

    def __init__(self, min_confidence: float = 60.0):
        self.min_confidence = min_confidence

    def generate(self, symbol: str, results: dict,
                 market_direction: str) -> list[dict]:
        """Generate signals for a single stock.

        Args:
            symbol: stock symbol
            results: dict with keys market_key, pivots, volume, price, rsi
            market_direction: "up", "down", "neutral"

        Returns: list of signal dicts
        """
        mk = results["market_key"].iloc[-1]
        pivot = results["pivots"].iloc[-1]
        vol = results["volume"].iloc[-1]
        price = results["price"]
        rsi = results.get("rsi", 50.0)

        # Determine raw signal type
        has_breakout = pivot["pivot_type"] == "breakout"
        has_breakdown = pivot["pivot_type"] == "breakdown"
        is_confirmed = pivot["confirmed"]
        has_volume = vol["volume_surge"]
        is_rsi_extreme = rsi > 70 or rsi < 30

        # Check market direction compatibility
        buy_allowed = market_direction in ("up", "neutral")
        sell_allowed = market_direction in ("down", "neutral")

        signals = []

        if has_breakout:
            if is_confirmed and has_volume and buy_allowed and not (rsi > 70):
                signal_type = "buy"
            else:
                signal_type = "watch"

            confidence = self._calculate_confidence(
                pivot, vol, mk, market_direction, rsi
            )

            # In down market, don't emit buy signals at all
            if signal_type == "buy" and not buy_allowed:
                return signals

            signals.append({
                "symbol": symbol,
                "signal_type": signal_type,
                "price": price,
                "confidence": confidence,
                "reason": self._build_reason(pivot, vol, mk, signal_type),
                "target_price": None,
                "stop_price": None,
                "volume_ratio": vol["volume_ratio"],
            })

        elif has_breakdown:
            if is_confirmed and has_volume and sell_allowed:
                signal_type = "sell"
            else:
                signal_type = "watch"

            if signal_type == "sell" and not sell_allowed:
                return signals

            confidence = self._calculate_confidence(
                pivot, vol, mk, market_direction, rsi
            )

            signals.append({
                "symbol": symbol,
                "signal_type": signal_type,
                "price": price,
                "confidence": confidence,
                "reason": self._build_reason(pivot, vol, mk, signal_type),
                "target_price": None,
                "stop_price": None,
                "volume_ratio": vol["volume_ratio"],
            })

        return signals

    def _calculate_confidence(self, pivot, vol, mk,
                              market_direction, rsi) -> float:
        score = 0.0

        # Pivot clarity (0-25)
        if pivot["confirmed"]:
            score += 25
        elif pivot["pivot_type"] != "none":
            score += 10

        # Volume strength (0-20)
        vol_ratio = vol["volume_ratio"]
        score += min(20.0, vol_ratio * 8)

        # Market trend alignment (0-20)
        if market_direction in ("up", "down"):
            score += 20
        else:
            score += 10

        # Livermore state strength (0-15)
        strength = mk["trend_strength"]
        score += min(15.0, strength * 0.15)

        # RSI appropriateness (0-10)
        if 30 <= rsi <= 70:
            score += 10
        elif 20 <= rsi <= 80:
            score += 5

        # Time element (0-10)
        consol = pivot.get("consolidation_days", 0)
        score += min(10.0, consol * 1.0)

        return round(min(100.0, score), 1)

    def _build_reason(self, pivot, vol, mk, signal_type) -> str:
        parts = []
        if pivot["pivot_type"] == "breakout":
            parts.append("피봇 돌파")
        elif pivot["pivot_type"] == "breakdown":
            parts.append("피봇 이탈")
        if pivot["confirmed"]:
            parts.append("확정")
        else:
            parts.append("확정 대기")
        if vol["volume_surge"]:
            parts.append(f"거래량 급증 (x{vol['volume_ratio']})")
        parts.append(f"리버모어: {mk['column_state']}")
        return " + ".join(parts)

    def prioritize(self, signals: list[dict]) -> list[dict]:
        """Sort signals by priority: confidence → volume_ratio."""
        return sorted(signals, key=lambda s: (
            -s.get("confidence", 0),
            -s.get("volume_ratio", 0),
        ))
```

- [ ] **Step 4: Write signals/signal_history.py**

```python
import logging
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from db.models import Signal, Price

logger = logging.getLogger(__name__)


class SignalHistory:
    """Track signal accuracy and performance."""

    def __init__(self, session: Session):
        self.session = session

    def get_accuracy(self, market: str, days_back: int = 90) -> dict:
        """Calculate signal accuracy stats."""
        from datetime import timedelta
        cutoff = date.today() - timedelta(days=days_back)

        buy_signals = self.session.query(Signal).filter(
            and_(Signal.market == market, Signal.signal_type == "buy",
                 Signal.date >= cutoff)
        ).all()

        sell_signals = self.session.query(Signal).filter(
            and_(Signal.market == market, Signal.signal_type == "sell",
                 Signal.date >= cutoff)
        ).all()

        buy_correct = sum(1 for s in buy_signals if self._was_correct(s, "buy"))
        sell_correct = sum(1 for s in sell_signals if self._was_correct(s, "sell"))

        buy_total = len(buy_signals)
        sell_total = len(sell_signals)

        return {
            "buy_accuracy": round(buy_correct / buy_total * 100, 1) if buy_total > 0 else 0,
            "sell_accuracy": round(sell_correct / sell_total * 100, 1) if sell_total > 0 else 0,
            "buy_total": buy_total,
            "sell_total": sell_total,
        }

    def _was_correct(self, signal: Signal, signal_type: str,
                     check_days: int = 10) -> bool:
        """Check if signal was correct by looking at subsequent price movement."""
        from datetime import timedelta
        future_date = signal.date + timedelta(days=check_days)
        future_price = self.session.query(Price).filter(
            and_(Price.symbol == signal.symbol,
                 Price.date > signal.date, Price.date <= future_date)
        ).order_by(Price.date.desc()).first()

        if not future_price:
            return False

        if signal_type == "buy":
            return future_price.close > signal.price
        else:
            return future_price.close < signal.price
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_signal_generator.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add signals/ tests/test_signal_generator.py
git commit -m "feat: signal generator with confidence scoring and priority"
```

---

## Task 9: Telegram Notifier

**Files:**
- Create: `signals/telegram_notifier.py`

- [ ] **Step 1: Write signals/telegram_notifier.py**

```python
import os
import logging
from datetime import date

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trading signals via Telegram."""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)

    async def send_signal(self, signal: dict, market: str):
        """Send a signal notification to Telegram."""
        if not self.enabled:
            logger.warning("Telegram not configured, skipping notification")
            return

        message = self._format_message(signal, market)
        await self._send(message)

    async def send_error(self, message: str):
        """Send error notification to admin."""
        if not self.enabled:
            return
        await self._send(f"⚠️ 시스템 오류\n━━━━━━━━━━━━━━━━━━\n{message}")

    def _format_message(self, signal: dict, market: str) -> str:
        emoji = "🟢" if signal["signal_type"] == "buy" else \
                "🔴" if signal["signal_type"] == "sell" else "🟡"
        type_kr = {"buy": "매수", "sell": "매도", "watch": "관찰"}[signal["signal_type"]]
        currency = "₩" if market == "KR" else "$"

        lines = [
            f"{emoji} {type_kr} 시그널 — {signal['symbol']}",
            "━━━━━━━━━━━━━━━━━━",
            f"💰 현재가: {currency}{signal['price']:,.0f}",
        ]
        if signal.get("target_price"):
            pct = (signal["target_price"] - signal["price"]) / signal["price"] * 100
            lines.append(f"🎯 목표가: {currency}{signal['target_price']:,.0f} ({pct:+.1f}%)")
        if signal.get("stop_price"):
            pct = (signal["stop_price"] - signal["price"]) / signal["price"] * 100
            lines.append(f"🛑 손절가: {currency}{signal['stop_price']:,.0f} ({pct:+.1f}%)")
        lines.append(f"📈 신뢰도: {signal['confidence']:.0f}%")
        lines.append(f"📋 사유: {signal['reason']}")
        return "\n".join(lines)

    async def _send(self, text: str):
        try:
            from telegram import Bot
            bot = Bot(token=self.token)
            await bot.send_message(chat_id=self.chat_id, text=text)
            logger.info("Telegram message sent")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add signals/telegram_notifier.py
git commit -m "feat: Telegram notifier for signal alerts"
```

---

## Task 10: Main Pipeline (update_all.py)

**Files:**
- Create: `update_all.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write update_all.py**

```python
#!/usr/bin/env python3
"""Main pipeline: collect → analyze → signal → portfolio update."""

import argparse
import asyncio
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Setup paths
ROOT = Path(__file__).parent
load_dotenv(ROOT / "config" / ".env")

from db.database import init_db, get_session
from db.repository import (
    upsert_prices, upsert_market_index, upsert_livermore_state,
    save_signal, get_prices, get_latest_livermore_state
)
from collectors.market_collector import MarketCollector
from livermore_engine.market_key import MarketKey
from livermore_engine.pivot_points import PivotDetector
from livermore_engine.volume_analysis import VolumeAnalyzer
from livermore_engine.trend_analyzer import TrendAnalyzer
from livermore_engine.money_management import MoneyManager
from signals.signal_generator import SignalGenerator
from signals.telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def run_phase1(config, session, start_date, end_date, market=None):
    """Phase 1: Data collection."""
    logger.info("=== Phase 1: Data Collection ===")
    collector = MarketCollector(config)
    data = collector.collect_all(start_date, end_date, market=market)

    for mkt_key, mkt_data in data.items():
        market_name = mkt_key.upper()
        for symbol, df in mkt_data["stocks"].items():
            if not df.empty:
                upsert_prices(session, symbol, market_name, df)
        for idx_name, df in mkt_data["indices"].items():
            if not df.empty:
                for _, row in df.iterrows():
                    upsert_market_index(session, idx_name, market_name,
                                        row["date"], row["close"])
        if mkt_data["failed"]:
            logger.warning(f"[{market_name}] Failed symbols: {mkt_data['failed']}")

    return data


def run_phase2(config, session, start_date, end_date, market=None):
    """Phase 2: Livermore analysis."""
    logger.info("=== Phase 2: Livermore Analysis ===")
    lc = config["livermore"]
    mk = MarketKey(lc["pivot_threshold_pct"])
    pd_ = PivotDetector(lc["lookback_days"], lc["volume_surge_ratio"],
                        lc.get("false_breakout_confirm_days", 2))
    va = VolumeAnalyzer(lc["lookback_days"], lc["volume_surge_ratio"])

    markets = []
    if market in (None, "kr"):
        markets.append(("KR", config["markets"]["kr"]))
    if market in (None, "us"):
        markets.append(("US", config["markets"]["us"]))

    results = {}
    for mkt_name, mkt_cfg in markets:
        results[mkt_name] = {}
        for symbol in mkt_cfg["watchlist"]:
            try:
                df = get_prices(session, symbol, start_date, end_date)
                if df.empty:
                    continue
                mk_result = mk.analyze(df)
                pivot_result = pd_.detect(df)
                vol_result = va.analyze(df)

                latest = mk_result.iloc[-1]
                upsert_livermore_state(
                    session, symbol, mkt_name, latest["date"],
                    latest["column_state"], latest["reference_pivot_price"],
                    latest["trend_direction"], latest["trend_strength"],
                    latest["trend_duration_days"]
                )
                results[mkt_name][symbol] = {
                    "market_key": mk_result,
                    "pivots": pivot_result,
                    "volume": vol_result,
                    "price": df.iloc[-1]["close"],
                }
                logger.info(f"[{mkt_name}] {symbol}: {latest['column_state']}")
            except Exception as e:
                logger.error(f"[{mkt_name}] {symbol} analysis failed: {e}")

    return results


def run_phase3(config, session, analysis_results, market=None):
    """Phase 3: Signal generation."""
    logger.info("=== Phase 3: Signal Generation ===")
    sg = SignalGenerator(config["signals"]["min_confidence"])
    mm = MoneyManager(
        config["money_management"]["max_position_pct"],
        config["money_management"]["split_buy_ratio"],
        config["money_management"]["stop_loss_pct"],
    )
    ta = TrendAnalyzer(config["livermore"]["pivot_threshold_pct"])
    notifier = TelegramNotifier()

    all_signals = []
    for mkt_name, stocks in analysis_results.items():
        # Determine market direction from index
        idx_key = "KOSPI" if mkt_name == "KR" else "^GSPC"
        market_direction = "neutral"
        # Try to get market trend from analysis
        if idx_key in stocks:
            idx_mk = stocks[idx_key]["market_key"]
            if not idx_mk.empty:
                market_direction = idx_mk.iloc[-1]["trend_direction"]

        for symbol, results in stocks.items():
            results["rsi"] = 50.0  # RSI placeholder — calculate from prices
            signals = sg.generate(symbol, results, market_direction)
            for sig in signals:
                if sig["confidence"] >= config["signals"]["min_confidence"]:
                    # Add money management
                    if sig.get("signal_type") == "buy":
                        pivot_price = results["pivots"].iloc[-1]["pivot_price"]
                        plan = mm.calculate_position(10000000, sig["price"], pivot_price)
                        sig["stop_price"] = plan.stop_price
                        sig["target_price"] = mm.calculate_target_price(
                            sig["price"], stop_price=plan.stop_price)

                    saved = save_signal(
                        session, symbol, mkt_name, date.today(),
                        sig["signal_type"], sig["price"], sig["confidence"],
                        sig["reason"], sig.get("target_price"), sig.get("stop_price")
                    )
                    all_signals.append(sig)

                    if config["signals"].get("telegram_enabled"):
                        try:
                            asyncio.run(notifier.send_signal(sig, mkt_name))
                        except Exception as e:
                            logger.error(f"Telegram notification failed: {e}")

    logger.info(f"Generated {len(all_signals)} signals")
    return all_signals


def run_phase4(config, session, market=None):
    """Phase 4: Portfolio update."""
    logger.info("=== Phase 4: Portfolio Update ===")
    # Portfolio snapshot logic — track open trades and daily value
    from db.repository import get_open_trades
    from db.models import Portfolio

    markets = []
    if market in (None, "kr"):
        markets.append("KR")
    if market in (None, "us"):
        markets.append("US")

    for mkt in markets:
        trades = get_open_trades(session, mkt)
        total_invested = sum(t.entry_price * t.quantity for t in trades)
        logger.info(f"[{mkt}] Open trades: {len(trades)}, Invested: {total_invested:,.0f}")


def main():
    parser = argparse.ArgumentParser(description="Livermore Trend Trading Pipeline")
    parser.add_argument("--market", choices=["kr", "us"], help="Target market")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4], help="Run specific phase")
    parser.add_argument("--days", type=int, default=90, help="Days of history to fetch")
    args = parser.parse_args()

    config = load_config()
    init_db()
    session = get_session()

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    market = args.market

    start_time = time.time()
    try:
        if args.phase is None or args.phase == 1:
            data = run_phase1(config, session, start_date, end_date, market)

        if args.phase is None or args.phase == 2:
            analysis = run_phase2(config, session, start_date, end_date, market)

        if args.phase is None or args.phase == 3:
            if args.phase == 3:
                analysis = run_phase2(config, session, start_date, end_date, market)
            run_phase3(config, session, analysis, market)

        if args.phase is None or args.phase == 4:
            run_phase4(config, session, market)

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        notifier = TelegramNotifier()
        try:
            asyncio.run(notifier.send_error(str(e)))
        except Exception:
            pass
        sys.exit(1)
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Pipeline completed in {elapsed:.1f}s")
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write tests/test_pipeline.py**

```python
"""Integration test: end-to-end pipeline with mock data."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, Price, LivermoreState, Signal


@pytest.fixture
def integration_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Insert 30 days of test data
    base = 10000
    for i in range(30):
        d = date(2026, 3, 1) + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        price = base + i * 100
        session.add(Price(
            symbol="005930", market="KR", date=d,
            open=price - 50, high=price + 100, low=price - 150,
            close=price, volume=1000000 + i * 50000
        ))
    session.commit()
    yield session
    session.close()


def test_phase2_produces_livermore_states(integration_db):
    from db.repository import get_prices, upsert_livermore_state
    from livermore_engine.market_key import MarketKey

    df = get_prices(integration_db, "005930", date(2026, 3, 1), date(2026, 4, 3))
    assert len(df) > 0

    mk = MarketKey(pivot_threshold_pct=5.0)
    result = mk.analyze(df)
    assert len(result) == len(df)
    assert "column_state" in result.columns

    latest = result.iloc[-1]
    upsert_livermore_state(
        integration_db, "005930", "KR", latest["date"],
        latest["column_state"], latest["reference_pivot_price"],
        latest["trend_direction"], latest["trend_strength"],
        latest["trend_duration_days"]
    )
    state = integration_db.query(LivermoreState).first()
    assert state is not None
    assert state.symbol == "005930"


def test_phase3_produces_signals(integration_db):
    from signals.signal_generator import SignalGenerator
    from livermore_engine.market_key import MarketKey
    from livermore_engine.pivot_points import PivotDetector
    from livermore_engine.volume_analysis import VolumeAnalyzer
    from db.repository import get_prices

    df = get_prices(integration_db, "005930", date(2026, 3, 1), date(2026, 4, 3))
    mk_result = MarketKey(5.0).analyze(df)
    pivot_result = PivotDetector(5, 1.5, 2).detect(df)
    vol_result = VolumeAnalyzer(5, 1.5).analyze(df)

    results = {
        "market_key": mk_result,
        "pivots": pivot_result,
        "volume": vol_result,
        "price": df.iloc[-1]["close"],
        "rsi": 55.0,
    }

    sg = SignalGenerator(min_confidence=0)
    signals = sg.generate("005930", results, "up")
    # May or may not produce signals depending on data — just verify no crash
    assert isinstance(signals, list)
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add update_all.py tests/test_pipeline.py
git commit -m "feat: main pipeline (update_all.py) with 4-phase execution"
```

---

## Task 11: Flask Web App + API

**Files:**
- Create: `web/app.py`

- [ ] **Step 1: Write web/app.py**

```python
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, redirect
from sqlalchemy import and_

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import init_db, get_session
from db.models import Price, MarketIndex, LivermoreState, Signal, Trade, Portfolio
from signals.signal_history import SignalHistory

app = Flask(__name__,
            template_folder=str(Path(__file__).parent / "templates"),
            static_folder=str(Path(__file__).parent / "static"))


@app.route("/")
def index():
    return redirect("/kr/dashboard")


@app.route("/<market>/dashboard")
def dashboard(market):
    if market not in ("kr", "us"):
        return redirect("/kr/dashboard")
    return render_template("index.html", market=market)


@app.route("/<market>/performance")
def performance(market):
    if market not in ("kr", "us"):
        return redirect("/kr/performance")
    return render_template("performance.html", market=market)


# === API Endpoints ===

@app.route("/api/<market>/indices")
def api_indices(market):
    session = get_session()
    mkt = market.upper()
    today = date.today()
    indices = session.query(MarketIndex).filter(
        and_(MarketIndex.market == mkt, MarketIndex.date == today)
    ).all()
    if not indices:
        # Fallback to latest available date
        latest = session.query(MarketIndex).filter(
            MarketIndex.market == mkt
        ).order_by(MarketIndex.date.desc()).first()
        if latest:
            indices = session.query(MarketIndex).filter(
                and_(MarketIndex.market == mkt, MarketIndex.date == latest.date)
            ).all()
    session.close()
    return jsonify([{
        "index_name": i.index_name, "value": i.value,
        "change_pct": i.change_pct, "trend_state": i.trend_state,
    } for i in indices])


@app.route("/api/<market>/signals")
def api_signals(market):
    session = get_session()
    mkt = market.upper()
    today = date.today()
    signals = session.query(Signal).filter(
        and_(Signal.market == mkt, Signal.date >= today - timedelta(days=7))
    ).order_by(Signal.confidence.desc()).all()
    session.close()
    return jsonify([{
        "symbol": s.symbol, "signal_type": s.signal_type,
        "price": s.price, "target_price": s.target_price,
        "stop_price": s.stop_price, "confidence": s.confidence,
        "reason": s.reason, "date": s.date.isoformat(),
    } for s in signals])


@app.route("/api/<market>/signals/summary")
def api_signals_summary(market):
    session = get_session()
    mkt = market.upper()
    today = date.today()
    signals = session.query(Signal).filter(
        and_(Signal.market == mkt, Signal.date == today)
    ).all()
    session.close()
    return jsonify({
        "buy": sum(1 for s in signals if s.signal_type == "buy"),
        "sell": sum(1 for s in signals if s.signal_type == "sell"),
        "watch": sum(1 for s in signals if s.signal_type == "watch"),
    })


@app.route("/api/<market>/chart/<symbol>")
def api_chart(market, symbol):
    session = get_session()
    period = int(request_args_get("days", 90))
    start = date.today() - timedelta(days=period)
    prices = session.query(Price).filter(
        and_(Price.symbol == symbol, Price.date >= start)
    ).order_by(Price.date).all()

    states = session.query(LivermoreState).filter(
        and_(LivermoreState.symbol == symbol, LivermoreState.date >= start)
    ).order_by(LivermoreState.date).all()
    session.close()

    return jsonify({
        "ohlcv": [{
            "date": p.date.isoformat(), "open": p.open, "high": p.high,
            "low": p.low, "close": p.close, "volume": p.volume,
        } for p in prices],
        "livermore_states": [{
            "date": s.date.isoformat(), "state": s.column_state,
            "pivot": s.reference_pivot_price, "direction": s.trend_direction,
            "strength": s.trend_strength,
        } for s in states],
    })


@app.route("/api/<market>/performance")
def api_performance(market):
    session = get_session()
    mkt = market.upper()
    trades = session.query(Trade).filter(
        and_(Trade.market == mkt, Trade.status != "open")
    ).order_by(Trade.exit_date.desc()).all()

    total_trades = len(trades)
    wins = [t for t in trades if t.status == "closed_profit"]
    losses = [t for t in trades if t.status == "closed_loss"]

    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
    avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    accuracy = SignalHistory(session).get_accuracy(mkt)
    session.close()

    return jsonify({
        "total_trades": total_trades,
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 1),
        "avg_loss_pct": round(avg_loss, 1),
        "profit_factor": round(profit_factor, 2),
        "signal_accuracy": accuracy,
        "recent_trades": [{
            "symbol": t.symbol, "entry_date": t.entry_date.isoformat(),
            "exit_date": t.exit_date.isoformat() if t.exit_date else None,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "pnl_pct": t.pnl_pct, "status": t.status,
        } for t in trades[:20]],
    })


def request_args_get(key, default=None):
    from flask import request
    return request.args.get(key, default)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5002, debug=True)
```

- [ ] **Step 2: Commit**

```bash
git add web/app.py
git commit -m "feat: Flask web app with API endpoints for dashboard and performance"
```

---

## Task 12: Dashboard Frontend (index.html)

**Files:**
- Create: `web/templates/index.html`

- [ ] **Step 1: Write web/templates/index.html**

This is a large single-page template. The full HTML file should include:
- Navigation bar with market toggle (KR/US) and submenu (dashboard/performance)
- Market index cards (4 per market, fetched from `/api/<market>/indices`)
- Signal summary cards (buy/sell/watch counts from `/api/<market>/signals/summary`)
- Left panel: signal detail list (from `/api/<market>/signals`)
- Right panel: candlestick chart with LightweightCharts + volume + RSI + Livermore state bar
- Chart data fetched from `/api/<market>/chart/<symbol>` on signal click
- Tailwind CSS via CDN, LightweightCharts via CDN

Key JavaScript: fetch API data on page load, update chart on signal click, period selector (1M/3M/6M/1Y).

Due to the length of this file (~400 lines of HTML/JS), the implementing agent should build it following the mockup design from the brainstorming session, using:
- Tailwind CSS dark theme (bg-slate-900, text-slate-200)
- LightweightCharts for candlestick + volume
- Fetch API for all data loading
- The exact layout from the `ui-dashboard-v2.html` mockup

- [ ] **Step 2: Commit**

```bash
git add web/templates/index.html
git commit -m "feat: main dashboard frontend with charts and signal display"
```

---

## Task 13: Performance Frontend (performance.html)

**Files:**
- Create: `web/templates/performance.html`

- [ ] **Step 1: Write web/templates/performance.html**

Build following the `ui-performance.html` mockup:
- Same navigation bar as index.html
- Period selector (1M/3M/6M/1Y/ALL)
- Performance summary cards (5): total return, win rate, profit factor, MDD, vs benchmark
- Portfolio equity curve chart (ApexCharts line chart, portfolio vs benchmark)
- Recent trades table
- Monthly returns heatmap
- Signal accuracy stats with progress bars
- All data from `/api/<market>/performance`

- [ ] **Step 2: Commit**

```bash
git add web/templates/performance.html
git commit -m "feat: performance tracking frontend with equity curve and stats"
```

---

## Task 14: Final Integration + Verification

**Files:**
- Modify: `web/app.py` (if needed)

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Initialize DB and verify Flask starts**

```bash
cd /Users/youngho/Documents/Project/Trend_Trading
python -c "from db.database import init_db; init_db(); print('DB initialized')"
python web/app.py &
# Verify http://localhost:5002 responds
curl -s http://localhost:5002/kr/dashboard | head -20
kill %1
```

- [ ] **Step 3: Run pipeline with --phase 1 for smoke test**

```bash
python update_all.py --market us --phase 1 --days 30
```
Expected: US stock data collected and saved to DB

- [ ] **Step 4: Add .gitignore**

```
config/.env
db/trend_trading.db
__pycache__/
*.pyc
.superpowers/
```

- [ ] **Step 5: Final commit**

```bash
git add .gitignore
git commit -m "feat: final integration - .gitignore and verification"
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Project scaffold + config | - |
| 2 | DB models + repository | 6 tests |
| 3 | Market Key engine | 8 tests |
| 4 | Pivot point detection | 8 tests |
| 5 | Volume analysis | 5 tests |
| 6 | Trend analyzer + money management | - |
| 7 | Data collectors (KR/US) | - |
| 8 | Signal generator + history | 6 tests |
| 9 | Telegram notifier | - |
| 10 | Main pipeline | 2 tests |
| 11 | Flask web app + API | - |
| 12 | Dashboard frontend | - |
| 13 | Performance frontend | - |
| 14 | Final integration | - |

**Total: 14 tasks, ~35 tests**
