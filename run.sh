#!/usr/bin/env bash
# Trend Trading — 작업수행 스크립트
# Usage:
#   ./run.sh              전체 실행 (데이터 수집 → 분석 → 시그널 → 웹 서버)
#   ./run.sh update       데이터 파이프라인만 실행 (phase 1~4)
#   ./run.sh update --market us   미국 시장만
#   ./run.sh web          웹 서버만 실행
#   ./run.sh phase 1      특정 phase만 실행
#   ./run.sh phase 2 --market kr
#   ./run.sh install      의존성 설치

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠${NC}  $*"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC}  $*" >&2; }

# .env 확인
check_env() {
    if [ ! -f config/.env ]; then
        err "config/.env 파일이 없습니다."
        echo "  cp config/.env.example config/.env  # 예시 파일이 있다면"
        echo "  필수 키: GOOGLE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
        exit 1
    fi
}

# 의존성 설치
cmd_install() {
    log "의존성 설치 중..."
    pip install -r requirements.txt
    log "설치 완료"
}

# 데이터 파이프라인 실행
cmd_update() {
    check_env
    log "데이터 파이프라인 실행..."
    python3 update_all.py "$@"
    log "파이프라인 완료"
}

# 특정 phase 실행
cmd_phase() {
    check_env
    local phase_num="$1"
    shift
    log "Phase ${phase_num} 실행..."
    python3 update_all.py --phase "$phase_num" "$@"
    log "Phase ${phase_num} 완료"
}

# 웹 서버 실행
cmd_web() {
    check_env
    log "웹 서버 시작 (http://127.0.0.1:5002)..."
    PYTHONPATH="$PROJECT_DIR" python3 web/app.py
}

# 전체 실행 (파이프라인 + 웹 서버)
cmd_all() {
    check_env
    log "전체 실행: 데이터 파이프라인 → 웹 서버"
    echo ""

    log "Step 1/2: 데이터 파이프라인"
    python3 update_all.py "$@"
    echo ""

    log "Step 2/2: 웹 서버 시작"
    cmd_web
}

# 도움말
cmd_help() {
    cat <<'EOF'
Trend Trading 작업수행 스크립트

사용법:
  ./run.sh                       전체 실행 (파이프라인 + 웹 서버)
  ./run.sh update                데이터 파이프라인만 실행
  ./run.sh update --market kr    한국 시장만
  ./run.sh update --market us    미국 시장만
  ./run.sh update --days 180     180일치 데이터
  ./run.sh web                   웹 서버만 실행
  ./run.sh phase 1               Phase 1(데이터 수집)만
  ./run.sh phase 2               Phase 2(리버모어 분석)만
  ./run.sh phase 3               Phase 3(시그널 생성)만
  ./run.sh phase 4               Phase 4(포트폴리오 업데이트)만
  ./run.sh install               Python 의존성 설치
  ./run.sh help                  이 도움말 표시

Phase 설명:
  1. 데이터 수집    yfinance/pykrx로 가격·지수 데이터 수집 → DB 저장
  2. 리버모어 분석  MarketKey, PivotDetector, VolumeAnalyzer → 추세 상태 저장
  3. 시그널 생성    매수/매도/관찰 시그널 생성 → Telegram 알림
  4. 포트폴리오     오픈 포지션 업데이트
EOF
}

# 메인 분기
case "${1:-}" in
    install)
        cmd_install
        ;;
    update)
        shift
        cmd_update "$@"
        ;;
    phase)
        shift
        if [ -z "${1:-}" ]; then
            err "phase 번호를 지정하세요 (1~4)"
            exit 1
        fi
        cmd_phase "$@"
        ;;
    web)
        cmd_web
        ;;
    help|--help|-h)
        cmd_help
        ;;
    "")
        cmd_all
        ;;
    *)
        err "알 수 없는 명령: $1"
        cmd_help
        exit 1
        ;;
esac
