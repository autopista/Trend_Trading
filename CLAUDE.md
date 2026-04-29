# Trend Trading 프로젝트 — Claude 설정

## 시간대
- **항상 한국 표준시(KST, UTC+9)를 사용한다.**
- 시간 표시 시 KST 기준으로 명시한다. (예: 19:12 KST)
- bash에서 시간 조회 시: `TZ='Asia/Seoul' date`

## 프로젝트 개요
- KOSPI/KOSDAQ 및 미국 주식 시장 트렌드 트레이딩 자동화 시스템
- Livermore MarketKey / PivotDetector / VolumeAnalyzer 기반 분석
- 매매 시그널 생성 후 Telegram 알림 전송

## 주요 경로
- 맥 프로젝트 루트(개발): `/Users/youngho/Documents/Project/Trend_Trading`
- VM 프로젝트 루트(운영): `/home/trendtrading/Trend_Trading` (GCP `openclaw-instance`)
- 로그: VM `~/Trend_Trading/logs/`
- 설정: `config/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GOOGLE_API_KEY`)
- 백업: `gs://trend-trading-backup-black-diorama-487911-n5/daily/` (30일 보관)

## 운영 환경 — GCP VM

| 항목 | 값 |
|------|-----|
| VM | `openclaw-instance` (Ubuntu 22.04, e2-small, OpenClaw와 공존) |
| 프로젝트 | `black-diorama-487911-n5` |
| Zone | `us-central1-a` |
| 시스템 사용자 | `trendtrading` |
| 웹 대시보드 | `https://34-149-65-15.sslip.io` (Cloud IAP, Google 로그인 필요) |

## 스케줄 작업 (systemd timer, Asia/Seoul)

| 작업 | systemd unit | 스케줄 (KST) |
|------|-------------|-------------|
| 한국 시장 | `trend-kr.timer` | 매일 08:30 KST |
| 미국 시장 | `trend-us.timer` | 매일 09:30 KST |
| DB 백업 | `trend-backup.timer` | 매일 03:00 KST |
| 웹 서버 | `trend-web.service` | 상시 (gunicorn) |

## VM SSH 접속

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a
# 또는 alias 추가: alias vm='gcloud compute ssh openclaw-instance --zone=us-central1-a'
```

## 운영 명령 (VM 셸에서)

```bash
sudo systemctl status trend-web                       # 웹 상태
sudo systemctl list-timers --all | grep trend         # 타이머 다음 실행 시각
sudo journalctl -u trend-web -f                       # 웹 실시간 로그
sudo -u trendtrading tail -50 ~trendtrading/Trend_Trading/logs/daily_kr.log
sudo systemctl start trend-kr.service                 # 수동 즉시 실행 (테스트)
gsutil ls gs://trend-trading-backup-black-diorama-487911-n5/daily/  # 백업 목록
```

## 코드 배포 워크플로우

```bash
# 1. 맥에서 코드 수정 + 커밋 + 푸시
cd ~/Documents/Project/Trend_Trading
git add . && git commit -m "..." && git push origin main

# 2. VM에서 git pull + 재시작
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="
  sudo -u trendtrading bash -c 'cd ~/Trend_Trading && git pull origin main' &&
  sudo systemctl restart trend-web
"
```

systemd unit 변경 시(`deploy/systemd/*` 수정 후):

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="
  sudo -u trendtrading bash -c 'cd ~/Trend_Trading && git pull origin main' &&
  sudo bash -c 'cp /home/trendtrading/Trend_Trading/deploy/systemd/*.service /etc/systemd/system/' &&
  sudo bash -c 'cp /home/trendtrading/Trend_Trading/deploy/systemd/*.timer /etc/systemd/system/' &&
  sudo systemctl daemon-reload &&
  sudo systemctl restart trend-web
"
```

## 로컬 개발 (맥)

```bash
cd ~/Documents/Project/Trend_Trading

# 파이프라인 수동 실행 (개발/디버깅 용도)
python3 update_all.py --market kr
python3 update_all.py --market us

# 웹 서버 로컬 실행 (개발)
./run.sh web                      # http://127.0.0.1:5002
```

## DB 복구 (장애 시)

```bash
# VM에서
gsutil ls gs://trend-trading-backup-black-diorama-487911-n5/daily/ | tail -5
sudo systemctl stop trend-web trend-kr.timer trend-us.timer
gsutil cp gs://.../trend_trading_YYYYMMDD_HHMMSS.db.gz /tmp/
gunzip /tmp/trend_trading_*.db.gz
sudo -u trendtrading mv /tmp/trend_trading_*.db /home/trendtrading/Trend_Trading/db/trend_trading.db
sudo systemctl start trend-web trend-kr.timer trend-us.timer
```

## 롤백 (맥 launchd 복구)

VM 장애 시 즉시 맥 launchd로 복귀 가능 — 프로젝트 디렉토리에 plist 백업 보관:

```bash
cp ~/Documents/Project/Trend_Trading/com.youngho.trendtrading-kr.plist ~/Library/LaunchAgents/
cp ~/Documents/Project/Trend_Trading/com.youngho.trendtrading-us.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.youngho.trendtrading-kr.plist
launchctl load ~/Library/LaunchAgents/com.youngho.trendtrading-us.plist
```

## 배포 설계 문서
- Spec: `docs/superpowers/specs/2026-04-29-gcp-vm-deployment-design.md`
- Plan: `docs/superpowers/plans/2026-04-29-gcp-vm-deployment.md`
- Systemd unit: `deploy/systemd/`

## 개발자 정보
- 사용자: Youngho (컴퓨터 전공 개발자, 은퇴 예정)
- 관심사: AI 활용 주식투자, 은퇴 연금 자산관리, Claude 기반 1인 사업
