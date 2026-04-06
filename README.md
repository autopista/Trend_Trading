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

### Buy (매수) 조건

5가지 조건이 **모두 충족**되어야 매수 시그널이 발생합니다:

| 조건 | 설명 |
|------|------|
| Breakout | 저항선(피봇 고점) 돌파 감지 |
| Confirmed | 돌파가 확인됨 (일시적 돌파가 아님) |
| Volume Surge | 거래량이 평균 대비 급증 |
| Trend Aligned | Livermore 상태가 상승(up) 또는 중립(neutral) |
| RSI <= 70 | 과매수 구간이 아님 |

추가 강등(demote) 조건:

- 전체 시장 방향이 **하락(down)** 이면 buy → watch로 강등
- **Confidence < 60%** 이면 buy → watch로 강등

### Sell (매도) 조건

| 조건 | 설명 |
|------|------|
| Breakdown | 지지선(피봇 저점) 이탈 감지 |
| Confirmed | 이탈이 확인됨 |
| Volume Surge | 거래량이 평균 대비 급증 |
| Trend Aligned | Livermore 상태가 하락(down) 또는 중립(neutral) |

### Watch (관찰)

위 Buy/Sell 조건을 충족하지 못하거나 confidence 임계값(60%) 미달 시 watch로 분류됩니다.

### Confidence Score (신뢰도 점수)

각 시그널에는 6가지 팩터를 합산한 0-100% confidence 점수가 부여됩니다:

| 팩터 | 배점 | 계산 방법 |
|------|------|-----------|
| Pivot 명확도 | 0-25 | confirmed=25점, breakout/breakdown만 감지=10점 |
| 거래량 | 0-20 | volume_ratio x 8 (최대 20) |
| 시장 방향 일치 | 0-20 | 명확한 방향(up/down)=20점, neutral=10점 |
| Livermore 강도 | 0-15 | trend_strength x 0.15 |
| RSI | 0-10 | 30-70 구간=10점, 20-80 구간=5점 |
| 횡보(consolidation) 기간 | 0-10 | consolidation_days x 1.0 |

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
