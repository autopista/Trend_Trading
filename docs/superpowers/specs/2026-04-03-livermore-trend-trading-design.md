# Livermore Trend Trading System — Design Spec

## 1. 개요

제시 리버모어의 추세매매 전략을 기반으로 한국/미국 주식시장을 분석하고, 매수/매도 시그널을 생성하며, 투자성과를 추적하는 시스템.

### 핵심 목적
- **시그널 생성**: 리버모어 전략에 따른 매수/매도 시점 알림
- **분석 대시보드**: 추세 시각화, 종목 스크리닝, 기술적 지표 차트
- **투자성과 추적**: 포트폴리오 수익률, 매매 이력, 시그널 정확도 통계
- **자동매매 (옵션)**: 시그널 기반 자동 주문 실행 (향후 확장)

### 대상 시장
- 한국: KOSPI, KOSDAQ (KRX/pykrx 데이터)
- 미국: S&P 500, NASDAQ, DOW (yfinance 데이터)

### 데이터 주기
- 일봉 기반, 장 마감 후 1~2회 데이터 갱신 및 분석

---

## 2. 아키텍처

### 접근방식: 모듈식 엔진 분리

리버모어 분석 엔진을 시장에 무관한 독립 모듈로 분리. 데이터 수집, 분석, 시그널, 프레젠테이션이 각각 독립적으로 동작.

### 디렉토리 구조

```
Trend_Trading/
├── config/
│   ├── settings.yaml          # 전략 파라미터, 종목 리스트
│   └── .env                   # API 키, 텔레그램 토큰
│
├── collectors/                # 데이터 수집 (시장별 독립)
│   ├── base.py                # 수집기 인터페이스 (BaseCollector ABC)
│   ├── us_collector.py        # yfinance 기반 미국 데이터
│   ├── kr_collector.py        # KRX/pykrx 기반 한국 데이터
│   └── market_collector.py    # 시장 전체 지수 수집 (KOSPI, S&P500 등)
│
├── db/                        # SQLite 데이터베이스
│   ├── database.py            # DB 연결, 세션 관리
│   ├── models.py              # 테이블 정의 (SQLAlchemy)
│   └── repository.py          # CRUD 쿼리 함수
│
├── livermore_engine/           # 핵심 분석 엔진 (시장 무관)
│   ├── market_key.py          # 리버모어 6단계 기록법
│   ├── pivot_points.py        # 피봇 포인트 감지
│   ├── volume_analysis.py     # 거래량 확인
│   ├── trend_analyzer.py      # 추세 판단 (top-down)
│   └── money_management.py    # 분할매수/매도, 손절 규칙
│
├── signals/                   # 시그널 생성 + 알림
│   ├── signal_generator.py    # 엔진 결과 → 매수/매도 시그널
│   ├── telegram_notifier.py   # 텔레그램 알림
│   └── signal_history.py      # 시그널 이력 관리 (DB)
│
├── web/                       # Flask 대시보드
│   ├── app.py                 # Flask 앱 + 라우팅
│   ├── api/                   # REST API 엔드포인트
│   ├── templates/
│   │   ├── index.html         # 메인 대시보드
│   │   └── performance.html   # 투자성과 추적
│   └── static/                # CSS, JS
│
├── update_all.py              # 메인 파이프라인 실행
├── requirements.txt
└── README.md
```

### 데이터 흐름

```
collectors/ → SQLite DB → livermore_engine/ → signals/ → Telegram + 대시보드
                ↑                                 │
                └─────── 분석 결과 저장 ───────────┘
```

1. `collectors/`가 시장별 OHLCV 데이터를 수집하여 SQLite DB에 저장
2. `livermore_engine/`이 DB에서 데이터를 읽어 분석, 결과를 DB에 저장
3. `signals/`가 분석 결과로부터 시그널 생성, DB에 기록 + 텔레그램 알림
4. `web/`이 DB에서 데이터를 읽어 대시보드에 표시

### 핵심 설계 원칙
- **livermore_engine은 시장에 무관**: OHLCV DataFrame만 받으면 한국/미국 어디든 동작
- **collectors는 시장별 독립**: 각 수집기가 BaseCollector를 구현, 동일 형식의 DataFrame 반환
- **SQLite 중심 데이터 관리**: 모든 모듈이 DB를 통해 데이터 교환
- **자동매매 확장 용이**: signals/에 executor 모듈만 추가하면 되는 구조

---

## 3. SQLite 데이터베이스 스키마

ORM: SQLAlchemy, DB 파일: `db/trend_trading.db`

### 테이블 정의

**prices** — 일봉 가격 데이터
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| symbol | TEXT | 종목 코드 (예: 005930, AAPL) |
| market | TEXT | 'KR' 또는 'US' |
| date | DATE | 거래일 |
| open | REAL | 시가 |
| high | REAL | 고가 |
| low | REAL | 저가 |
| close | REAL | 종가 |
| volume | INTEGER | 거래량 |
| UNIQUE(symbol, date) | | |

**market_indices** — 시장 지수
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| index_name | TEXT | 지수명 (KOSPI, S&P500 등) |
| market | TEXT | 'KR' 또는 'US' |
| date | DATE | 날짜 |
| value | REAL | 지수 값 |
| change_pct | REAL | 변동률 (%) |
| trend_state | TEXT | 리버모어 상태 |
| UNIQUE(index_name, date) | | |

**livermore_states** — 리버모어 분석 상태
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| symbol | TEXT | 종목 코드 |
| market | TEXT | 'KR' 또는 'US' |
| date | DATE | 분석일 |
| column_state | TEXT | 6단계 상태 (upward_trend, natural_rally, secondary_rally, downward_trend, natural_reaction, secondary_reaction) |
| pivot_price | REAL | 현재 피봇 가격 |
| trend_direction | TEXT | 추세 방향 (up, down, neutral) |
| UNIQUE(symbol, date) | | |

**signals** — 매매 시그널
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| symbol | TEXT | 종목 코드 |
| market | TEXT | 'KR' 또는 'US' |
| date | DATE | 시그널 발생일 |
| signal_type | TEXT | 'buy', 'sell', 'watch' |
| price | REAL | 시그널 발생 가격 |
| target_price | REAL | 목표가 (nullable) |
| stop_price | REAL | 손절가 (nullable) |
| reason | TEXT | 시그널 사유 |
| confidence | REAL | 신뢰도 (0~100) |
| notified | BOOLEAN | 텔레그램 알림 여부 |
| created_at | DATETIME | 생성 시각 |
| UNIQUE(symbol, market, date, signal_type) | | |

**trades** — 매매 기록
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| symbol | TEXT | 종목 코드 |
| market | TEXT | 'KR' 또는 'US' |
| entry_date | DATE | 매수일 |
| entry_price | REAL | 매수가 |
| exit_date | DATE | 매도일 (nullable, 보유 중이면 NULL) |
| exit_price | REAL | 매도가 (nullable) |
| quantity | INTEGER | 수량 |
| pnl | REAL | 실현 손익 (nullable) |
| pnl_pct | REAL | 수익률 % (nullable) |
| status | TEXT | 'open', 'closed_profit', 'closed_loss' |
| signal_id | INTEGER FK | 연결된 시그널 ID |

**portfolio** — 일별 포트폴리오 스냅샷
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| market | TEXT | 'KR' 또는 'US' |
| date | DATE | 날짜 |
| total_value | REAL | 총 자산 |
| cash | REAL | 현금 |
| invested | REAL | 투자 금액 |
| daily_return | REAL | 일일 수익률 (%) |
| cumulative_return | REAL | 누적 수익률 (%) |
| UNIQUE(market, date) | | |

---

## 4. 리버모어 분석 엔진 상세

### 4.1 Market Key (market_key.py)

리버모어의 6단계 컬럼 기록 시스템을 구현.

**6단계 상태:**
1. **상승추세 (Upward Trend)** — 가격이 직전 피봇 고점을 돌파
2. **자연반등 (Natural Rally)** — 하락추세 중 일시적 반등
3. **2차 반등 (Secondary Rally)** — 자연반등에서 추가 상승했으나 상승추세 미달
4. **하락추세 (Downward Trend)** — 가격이 직전 피봇 저점을 이탈
5. **자연반락 (Natural Reaction)** — 상승추세 중 일시적 하락
6. **2차 반락 (Secondary Reaction)** — 자연반락에서 추가 하락했으나 하락추세 미달

**전환 규칙:**
- 상승추세 진입: 자연반등 또는 2차반등 고점이 직전 상승추세 피봇을 돌파
- 하락추세 진입: 자연반락 또는 2차반락 저점이 직전 하락추세 피봇을 이탈
- 전환 임계값: 설정 가능 (settings.yaml의 `pivot_threshold_pct`)

**입력**: symbol, OHLCV DataFrame
**출력**: 날짜별 column_state, pivot_price, trend_direction

### 4.2 Pivot Points (pivot_points.py)

주요 가격대(pivotal point) 감지.

- **돌파 피봇**: 저항선을 거래량과 함께 상향 돌파
- **이탈 피봇**: 지지선을 거래량과 함께 하향 이탈
- **계속 피봇**: 추세 진행 중 나타나는 중간 피봇 (pullback 후 재진입)

**감지 방법**:
- 최근 N일 (기본 20일) 고점/저점 기반 지지/저항 계산
- 돌파/이탈 시 거래량이 20일 평균 대비 1.5배 이상이면 유효한 피봇으로 판정

### 4.3 Volume Analysis (volume_analysis.py)

거래량 확인을 통한 추세 유효성 검증.

- **거래량 급증 감지**: 20일 이동평균 대비 비율 계산
- **가격-거래량 다이버전스**: 가격 신고가인데 거래량 감소 → 추세 약화 경고
- **클라이맥스 거래량**: 극단적 거래량 급증 → 추세 전환 가능성

### 4.4 Trend Analyzer (trend_analyzer.py)

Top-down 접근: 시장 전체 추세 확인 후 개별 종목 진입 판단.

1. **시장 추세 판단**: 주요 지수(KOSPI/S&P500)의 리버모어 상태 확인
2. **섹터 추세** (선택적): 업종별 강약 분석
3. **개별 종목 필터링**: 시장 추세와 동일 방향인 종목만 시그널 생성
   - 시장 상승추세 → 매수 시그널만 활성
   - 시장 하락추세 → 매도 시그널만 활성
   - 시장 중립 → 강한 시그널만 활성

### 4.5 Money Management (money_management.py)

리버모어식 자금 관리 규칙.

- **분할 매수**: 총 3회 분할 (1차 50%, 2차 30%, 3차 20%)
  - 1차: 최초 시그널 발생 시
  - 2차: 1차 매수 후 가격이 유리한 방향으로 이동 확인 시
  - 3차: 추세 확정 시
- **손절 규칙**: 피봇 포인트 기준 설정 가능한 % 이탈 시 (기본 -5%)
- **익절 규칙**: 추세 전환 시그널 발생 시 또는 목표가 도달 시
- **포지션 크기**: 총 자산 대비 종목당 최대 비중 제한 (기본 20%)

---

## 5. 데이터 수집기 상세

### BaseCollector (base.py)

```python
class BaseCollector(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """OHLCV DataFrame 반환 (컬럼: date, open, high, low, close, volume)"""

    @abstractmethod
    def fetch_index(self, index_name: str, start_date: date, end_date: date) -> pd.DataFrame:
        """지수 데이터 반환"""

    @abstractmethod
    def get_watchlist(self) -> list[str]:
        """감시 종목 리스트 반환"""
```

### KR Collector (kr_collector.py)
- **라이브러리**: pykrx
- **지수**: KOSPI, KOSDAQ
- **추가 데이터**: 원/달러 환율, 투자자별 매매동향 (외인/기관)
- **종목 리스트**: settings.yaml에서 관리

### US Collector (us_collector.py)
- **라이브러리**: yfinance
- **지수**: S&P 500, NASDAQ Composite, DOW, VIX
- **종목 리스트**: settings.yaml에서 관리

### Market Collector (market_collector.py)
- KR/US Collector를 조합하여 시장 전체 지수를 한번에 수집
- `update_all.py`에서 이 모듈을 호출

---

## 6. 시그널 시스템 상세

### Signal Generator (signal_generator.py)

리버모어 엔진의 분석 결과를 종합하여 최종 시그널 생성.

**시그널 타입:**
- **buy**: 매수 시그널 (피봇 돌파 + 거래량 확인 + 시장 추세 일치)
- **sell**: 매도 시그널 (추세 전환 + 손절선 이탈)
- **watch**: 관찰 (조건 일부 충족, 아직 확정 아님)

**신뢰도 계산 (0~100):**
- 피봇 돌파/이탈 명확성: 0~30점
- 거래량 확인 강도: 0~25점
- 시장 추세 일치도: 0~25점
- 리버모어 상태 강도: 0~20점

### Telegram Notifier (telegram_notifier.py)

시그널 발생 시 텔레그램으로 즉시 알림.

**메시지 형식 (예시):**
```
🟢 매수 시그널 — 삼성전자 (005930)
━━━━━━━━━━━━━━━━━━
📊 리버모어 상태: 상승추세 전환
💰 현재가: ₩72,400
🎯 목표가: ₩79,600 (+9.9%)
🛑 손절가: ₩68,780 (-5.0%)
📈 신뢰도: 87%
📋 사유: 피봇 돌파 + 거래량 급증 (평균 대비 2.3배)
```

### Signal History (signal_history.py)

- 모든 시그널을 DB에 기록
- 과거 시그널의 성과를 추적 (후속 가격 변동과 비교)
- 시그널 정확도 통계 산출

---

## 7. 웹 대시보드 상세

### 기술 스택
- **백엔드**: Flask (Python)
- **프론트엔드**: HTML + Tailwind CSS + JavaScript
- **차트**: LightweightCharts (캔들스틱), ApexCharts (통계 차트)

### URL 라우팅

| URL | 화면 | 설명 |
|-----|------|------|
| `/kr/dashboard` | 한국 대시보드 | 국장 시그널 + 차트 |
| `/kr/performance` | 한국 투자성과 | 국장 포트폴리오 추적 |
| `/us/dashboard` | 미국 대시보드 | 미장 시그널 + 차트 |
| `/us/performance` | 미국 투자성과 | 미장 포트폴리오 추적 |

기본 URL(`/`)은 `/kr/dashboard`로 리다이렉트.

### 7.1 메인 대시보드 (index.html)

**네비게이션 바:**
- 시장 전환 토글: 🇰🇷 국장 / 🇺🇸 미장
- 서브 메뉴: 대시보드 / 투자성과
- 마지막 업데이트 시각

**시장 지수 카드 (4개, 시장별):**
- 국장: KOSPI, KOSDAQ, 원/달러, 투자자동향(외인/기관)
- 미장: S&P 500, NASDAQ, DOW, VIX
- 각 카드: 지수 값, 변동률, 리버모어 추세 상태

**시그널 요약 카드 (3개):**
- 매수 시그널 건수 (녹색)
- 매도 시그널 건수 (빨간색)
- 관찰 중 건수 (노란색)

**시그널 상세 리스트 (좌측 패널):**
- 종목별: 이름, 시그널 타입(매수/매도/관찰), 사유, 신뢰도, 가격/목표가
- 클릭 시 우측 차트 영역이 해당 종목으로 전환

**차트 영역 (우측 패널):**
- 기간 선택: 1M / 3M / 6M / 1Y
- 캔들스틱 차트: 일봉 + 피봇 포인트 마커 + 이동평균선 (MA20, MA60)
- 거래량 바 차트: 평균 대비 급증 구간 하이라이트 (파란색)
- RSI (14): 현재값 + 과매수/과매도 경계선 (30/70)
- 리버모어 상태 바: 6단계 중 현재 상태 하이라이트

### 7.2 투자성과 추적 (performance.html)

**기간 선택**: 1M / 3M / 6M / 1Y / 전체

**성과 요약 카드 (5개):**
- 총 수익률 (금액 포함)
- 승률 (승/패 건수)
- 손익비 (평균 이익 / 평균 손실)
- 최대 낙폭 MDD (발생일)
- 벤치마크 대비 초과수익 (국장: vs KOSPI, 미장: vs S&P500)

**수익률 곡선 차트:**
- 내 포트폴리오 수익률 곡선 (실선)
- 벤치마크 지수 비교 (점선)
- MDD 구간 표시

**최근 매매 이력 테이블:**
- 컬럼: 종목, 구분(익절/손절/보유), 매수가, 매도가, 수익률, 보유일

**월별 수익률 히트맵:**
- 월별 수익률을 색상 블록으로 표시 (녹색: 이익, 빨간색: 손실)

**시그널 통계:**
- 매수 시그널 정확도 (프로그레스 바)
- 매도 시그널 정확도 (프로그레스 바)
- 평균 보유 기간
- 평균 수익 / 평균 손실

---

## 8. 메인 파이프라인 (update_all.py)

장 마감 후 실행하는 일일 파이프라인.

```
Phase 1: 데이터 수집
  └── collectors/ → 시장 지수 + 종목 OHLCV → DB 저장

Phase 2: 리버모어 분석
  └── livermore_engine/ → Market Key 업데이트 + 피봇 감지 + 거래량 분석 + 추세 판단 → DB 저장

Phase 3: 시그널 생성
  └── signals/ → 시그널 생성 + DB 저장 + 텔레그램 알림

Phase 4: 포트폴리오 업데이트
  └── 보유 종목 평가 + 일별 스냅샷 → DB 저장
```

**실행 방법:**
```bash
python update_all.py              # 전체 실행 (KR + US)
python update_all.py --market kr  # 한국만
python update_all.py --market us  # 미국만
python update_all.py --phase 1    # 데이터 수집만
```

---

## 9. 설정 (settings.yaml)

```yaml
markets:
  kr:
    watchlist:
      - "005930"   # 삼성전자
      - "000660"   # SK하이닉스
      # ...
    indices:
      - "KOSPI"
      - "KOSDAQ"
  us:
    watchlist:
      - "AAPL"
      - "MSFT"
      - "GOOGL"
      # ...
    indices:
      - "^GSPC"    # S&P 500
      - "^IXIC"    # NASDAQ
      - "^DJI"     # DOW
      - "^VIX"     # VIX

livermore:
  pivot_threshold_pct: 5.0        # 피봇 전환 임계값 (%)
  volume_surge_ratio: 1.5         # 거래량 급증 판정 배수
  lookback_days: 20               # 지지/저항 계산 기간

money_management:
  max_position_pct: 20            # 종목당 최대 비중 (%)
  split_buy_ratio: [50, 30, 20]   # 분할 매수 비율
  stop_loss_pct: 5.0              # 손절 기준 (%)

signals:
  min_confidence: 60              # 시그널 최소 신뢰도
  telegram_enabled: true

web:
  host: "127.0.0.1"
  port: 5002
```

---

## 10. 기술 스택 요약

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.12+ |
| 웹 프레임워크 | Flask |
| 프론트엔드 | HTML + Tailwind CSS + JavaScript |
| 차트 | LightweightCharts (캔들), ApexCharts (통계) |
| DB | SQLite + SQLAlchemy |
| 데이터 수집 | yfinance (US), pykrx (KR) |
| 알림 | python-telegram-bot |
| 설정 | PyYAML + python-dotenv |
| 데이터 처리 | pandas |

### requirements.txt (예상)
```
flask
sqlalchemy
yfinance
pykrx
pandas
python-telegram-bot
pyyaml
python-dotenv
apscheduler
```

---

## 11. 향후 확장 (옵션)

### 자동매매
- `signals/executor.py` 추가
- 키움증권 REST API (한국), Alpaca API (미국) 연동
- 시그널 발생 시 자동 주문 실행
- 분할 매수/매도 자동화

### 추가 기능 후보
- AI 분석 (Gemini/GPT 연동, 기존 trading_dashboard 참고)
- 백테스팅 모듈 (과거 데이터로 전략 성과 시뮬레이션)
- 알림 채널 추가 (슬랙, 이메일 등)
