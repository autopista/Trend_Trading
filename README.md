# Livermore Trend Trading System

Jesse Livermore의 추세매매 전략을 기반으로 한국/미국 주식 시장을 분석하고 매매 시그널을 생성하는 시스템입니다.

## Overview

- **Livermore Market Key** 6-state 분석 엔진으로 추세 방향과 강도를 판별
- **Pivot Point 감지**, **거래량 분석**을 결합한 복합 시그널 생성
- KR(한국) / US(미국) 시장 동시 지원
- Flask 기반 대시보드에서 시그널 조회, 차트 분석, Gemini AI 종목 분석 제공
- Telegram 알림을 통한 실시간 매매 시그널 전송

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  update_all.py (4-Phase Pipeline)                        │
│                                                          │
│  Phase 1: Data Collection                                │
│  ├── kr_collector.py  →  pykrx (KRX)                    │
│  └── us_collector.py  →  yfinance (NASDAQ/NYSE)          │
│                                                          │
│  Phase 2: Livermore Analysis                             │
│  ├── market_key.py      →  6-state trend classification  │
│  ├── pivot_points.py    →  support/resistance detection  │
│  └── volume_analysis.py →  volume surge/divergence       │
│                                                          │
│  Phase 3: Signal Generation                              │
│  └── signal_generator.py →  buy/sell/watch + confidence  │
│                                                          │
│  Phase 4: Portfolio Update                               │
│  └── open trade tracking                                 │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  SQLite DB (prices, livermore_states, signals, trades)    │
└──────────────────────────────────────────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
 Flask      Telegram
Dashboard   Notifier
(port 5002)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Web Framework | Flask |
| ORM | SQLAlchemy 2.0 |
| KR Market Data | pykrx |
| US Market Data | yfinance |
| Charts | LightweightCharts |
| Frontend | Tailwind CSS |
| AI Analysis | Google Gemini API |
| Notification | Telegram Bot API |

## Quick Start

```bash
# 1. Clone & install
git clone <repo-url>
cd Trend_Trading
pip install -r requirements.txt

# 2. Configure
cp config/.env.example config/.env
# Edit config/.env with your API keys

# 3. Run data pipeline
python update_all.py                    # Full pipeline (KR + US)
python update_all.py --market kr        # Korean market only
python update_all.py --market us        # US market only
python update_all.py --phase 1 --days 180  # Data collection only, 180 days

# 4. Start dashboard
PYTHONPATH=. python web/app.py          # http://127.0.0.1:5002
```

## Dashboard Features

### Signal List with Date Navigation

날짜별로 시그널을 조회할 수 있는 캘린더 팝업 지원:

- 날짜 네비게이션 (◀ ▶)으로 시그널 있는 날짜 간 이동
- 캘린더에서 시그널 존재 날짜를 시각적으로 표시
- Buy/Sell/Watch 타입별 필터링
- KR/US 마켓별 선택 날짜 자동 저장

### Candlestick Chart

- OHLCV 캔들스틱 차트 (LightweightCharts)
- MACD (12, 26, 9) / RSI (14) 보조 지표
- Livermore 6-state 추세 상태 바

### AI Analysis

- Google Gemini 기반 종목 분석
- 추세 판단, 핵심 가격대, 거래량 분석, 매매 전략 제안

### Performance Tracking

- 매매 이력 및 승률 통계
- 시그널 정확도 추적

## Livermore Market Key States

| State | Description |
|-------|-------------|
| Upward Trend | 이전 피봇 고점 돌파 — 상승 추세 확인 |
| Natural Rally | 하락 추세 중 일시적 반등 |
| Secondary Rally | 자연 반락에서의 반등 (상승 추세 미도달) |
| Downward Trend | 이전 피봇 저점 붕괴 — 하락 추세 확인 |
| Natural Reaction | 상승 추세 중 일시적 조정 |
| Secondary Reaction | 자연 반등에서의 조정 (하락 추세 미도달) |

## Signal Generation Logic

시그널은 다음 조건의 조합으로 생성됩니다:

- **Buy**: 상승 추세 확인 + 거래량 급증 + RSI <= 70 + 시장 방향 상승/중립
- **Sell**: 하락 추세 확인 + 거래량 급증 + 시장 방향 하락/중립
- **Watch**: 위 조건 미충족 또는 confidence 임계값 미달

각 시그널에는 0-100% confidence 점수가 부여됩니다.

## Configuration

### Environment Variables (`config/.env`)

```
GOOGLE_API_KEY=         # Gemini AI analysis (required for AI feature)
TELEGRAM_BOT_TOKEN=     # Telegram notifications (optional)
TELEGRAM_CHAT_ID=       # Telegram chat ID (optional)
```

### Watchlist (`config/settings.yaml`)

KR/US 마켓별 감시 종목 및 지수를 설정합니다.

## Project Structure

```
Trend_Trading/
├── update_all.py           # 4-phase data pipeline orchestrator
├── requirements.txt
├── config/
│   ├── .env                # API keys (gitignored)
│   └── settings.yaml       # Watchlist & market config
├── collectors/             # Phase 1: Data collection
│   ├── market_collector.py
│   ├── kr_collector.py     # pykrx (KRX)
│   └── us_collector.py     # yfinance
├── livermore_engine/       # Phase 2: Livermore analysis
│   ├── market_key.py       # 6-state trend classification
│   ├── pivot_points.py     # Support/resistance detection
│   ├── volume_analysis.py  # Volume surge/divergence
│   ├── trend_analyzer.py   # Composite trend scoring
│   └── money_management.py # Position sizing
├── signals/                # Phase 3: Signal generation
│   ├── signal_generator.py # Buy/sell/watch logic
│   ├── signal_history.py   # Accuracy tracking
│   └── telegram_notifier.py
├── db/
│   ├── database.py         # SQLAlchemy engine/session
│   └── models.py           # ORM models
├── web/
│   ├── app.py              # Flask API server
│   └── templates/
│       ├── index.html      # Main dashboard
│       └── performance.html
├── tests/                  # pytest suite
└── docs/
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/<market>/indices` | 시장 지수 (KOSPI, S&P500 등) |
| `GET /api/<market>/signals?date=` | 날짜별 시그널 목록 |
| `GET /api/<market>/signals/dates` | 시그널 존재 날짜 목록 (90일) |
| `GET /api/<market>/signals/summary?date=` | Buy/Sell/Watch 카운트 |
| `GET /api/<market>/chart/<symbol>?days=` | OHLCV + Livermore 상태 |
| `GET /api/<market>/analyze/<symbol>` | Gemini AI 종목 분석 |
| `GET /api/<market>/performance` | 매매 통계 및 시그널 정확도 |

## Testing

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

## License

Private — All rights reserved.
