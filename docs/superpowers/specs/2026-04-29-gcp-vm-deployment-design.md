# GCP VM 배포 설계 — Trend Trading

- **작성일**: 2026-04-29 (KST)
- **작성자**: Youngho (cyh1024@gmail.com)
- **대상 시스템**: Trend Trading (KR/US 일배치 + Flask 웹 대시보드)
- **목표**: 맥 로컬에서 운영 중인 시스템을 GCP Compute Engine VM으로 이전

---

## 1. 배경 / 결정 요약

현재 Trend Trading은 맥 launchd로 매일 KR 08:30 / US 09:30 KST에 배치를 실행하고, Flask 웹 대시보드는 필요 시 수동으로 띄우는 구조다. 맥 의존도를 없애고 GCP VM으로 이전한다.

| 항목 | 결정 |
|------|------|
| 배포 범위 | 데일리 배치 + 웹 대시보드 모두 VM으로 이전 |
| 웹 접근 제어 | Cloud IAP (Google 로그인, `cyh1024@gmail.com`만 허용) |
| GCP 환경 | 기존 VM `openclaw-instance` (Ubuntu 22.04, e2-small, us-central1-a)에 공존 — 프로젝트 `black-diorama-487911-n5` |
| 격리 방식 | 별도 시스템 사용자 `trendtrading`, 별도 디렉토리, systemd unit |
| 도메인 | 없음 — `<static-IP>.sslip.io` 형식 사용 (비용 0) |
| 배포 방식 | GitHub git pull + systemd restart |
| GitHub 저장소 | public 전환 (`autopista/Trend_Trading`) — git history 시크릿 검증 후 |
| 시크릿 | 수동 SCP로 `config/.env` 1회 복사 |
| DB | SQLite 그대로, VM에서 새로 시작 (맥 DB 이관 안 함) |
| WSGI | gunicorn (Flask 개발 서버 대신) |
| 백업 | SQLite → GCS 일일 백업, 30일 보관 |
| 스케줄러 | systemd timer (`OnCalendar=... Asia/Seoul`) |

---

## 2. 전체 아키텍처

```
┌─ Mac (개발 머신) ────────────┐         ┌─ GCP (us-central1-a) ────────────────────────┐
│                              │         │                                              │
│  코드 수정 → git commit/push │  HTTPS  │   ┌─ HTTPS Load Balancer ───────────────┐    │
│                              ├────────►│   │  Frontend: <static-IP>.sslip.io     │    │
│  웹 접속 시:                 │         │   │  Backend: openclaw-instance:5002    │    │
│  https://<ip>.sslip.io       │         │   │  Cloud IAP (Google 로그인 필수)      │    │
│  (Google 로그인)             │◄────────┤   └─────────────────────────────────────┘    │
└──────────────────────────────┘         │              │                               │
                                         │   ┌──────────▼──────────────────────────┐    │
              Telegram                   │   │  openclaw-instance (e2-small)        │    │
                  ▲                      │   │  ─ OpenClaw (기존)                   │    │
                  │                      │   │  ─ trendtrading 사용자 (신규)        │    │
                  │                      │   │     ├─ ~/Trend_Trading (git clone)   │    │
                  │                      │   │     ├─ venv (Python 3.12)            │    │
                  │                      │   │     ├─ config/.env (SCP 1회)         │    │
                  │                      │   │     └─ db/trend_trading.db (SQLite)  │    │
                  │                      │   │                                      │    │
                  │                      │   │  systemd units (Asia/Seoul TZ):      │    │
                  └──────────────────────┼───┤  ─ trend-web.service (gunicorn)      │    │
                                         │   │  ─ trend-kr.timer (매일 08:30 KST)   │    │
                                         │   │  ─ trend-us.timer (매일 09:30 KST)   │    │
                                         │   │  ─ trend-backup.timer (매일 03:00)   │    │
                                         │   └──────────────┬───────────────────────┘    │
                                         │                  │                            │
                                         │   ┌──────────────▼──────────────────────┐    │
                                         │   │  GCS 버킷 (DB 일일 백업, 30일 보관)   │    │
                                         │   └─────────────────────────────────────┘    │
                                         └──────────────────────────────────────────────┘
```

핵심:
- **OpenClaw와 같은 VM에서 공존**, 충돌 없도록 별도 사용자/디렉토리/포트
- 외부 IP는 정적(static) 예약 → `<IP>.sslip.io`로 IAP HTTPS 접근
- Flask는 gunicorn으로 systemd 상시 동작, 배치/백업은 systemd timer
- 시간대는 KST 기준으로 systemd `OnCalendar`에 명시 (VM 시스템 시간대는 UTC 유지 — OpenClaw 영향 방지)
- 맥의 launchd plist는 검증 후 비활성화 (이중 실행 방지)

---

## 3. VM 초기 셋업

### 3.1 시스템 사용자
```bash
sudo useradd -m -s /bin/bash trendtrading
```
홈 디렉토리 `/home/trendtrading/`. OpenClaw와 권한 분리.

### 3.2 swap 추가 (2GB)
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
e2-small의 2GB RAM 부족 대비 (OpenClaw + Trend Trading + gunicorn 2 workers).

### 3.3 Python 3.12
Ubuntu 22.04 기본은 3.10. 프로젝트가 3.12+ 명시.
```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev build-essential
```

### 3.4 시간대
VM 자체는 UTC 유지 (OpenClaw 영향 회피). systemd `OnCalendar`에 `Asia/Seoul` 명시.

### 3.5 시스템 패키지
```bash
sudo apt-get install -y git tzdata curl sqlite3
```

### 3.6 VPC 방화벽
LB health check 대역(`130.211.0.0/22`, `35.191.0.0/16`)에서 5002 포트로 ingress 허용.

---

## 4. 코드 배치 + 시크릿

### 4.1 배포 전 git 정리 (맥)

`.gitignore` 추가:
```gitignore
.DS_Store
logs/
*.bak
0
config/settings.yaml.bak
com.youngho.trendtrading-*.plist
register_test_us.sh
run_daily_kr.sh
run_daily_us.sh
```

미커밋 5개 파일 검토 후 commit:
- `config/settings.yaml`
- `db/repository.py`
- `run.sh`
- `signals/telegram_notifier.py`
- `web/templates/performance.html`

`requirements.txt`에 추가:
```
gunicorn==21.*
```

### 4.2 GitHub public 전환
사전 점검:
```bash
git log --all -p | grep -iE "API_KEY|TOKEN|SECRET|PASSWORD" | head
```
시크릿 commit 흔적 없음 확인 후 GitHub 저장소 설정에서 public 전환.

### 4.3 VM 클론 + venv
```bash
sudo su - trendtrading
git clone https://github.com/autopista/Trend_Trading.git ~/Trend_Trading
cd ~/Trend_Trading
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p logs scripts
```

### 4.4 시크릿 SCP
맥에서:
```bash
gcloud compute scp config/.env openclaw-instance:~/Trend_Trading/config/.env \
  --zone=us-central1-a --tunnel-through-iap
ssh ... 'chmod 600 ~/Trend_Trading/config/.env'
```

### 4.5 DB
VM에서 새로 시작. 첫 배치 실행 시 SQLAlchemy `Base.metadata.create_all()`이 `db/trend_trading.db` 자동 생성.

---

## 5. systemd 서비스 + 타이머

### 5.1 `trend-web.service` (gunicorn 상시)
```ini
[Unit]
Description=Trend Trading Flask Web Dashboard
After=network.target

[Service]
Type=simple
User=trendtrading
Group=trendtrading
WorkingDirectory=/home/trendtrading/Trend_Trading
EnvironmentFile=/home/trendtrading/Trend_Trading/config/.env
Environment=PYTHONPATH=/home/trendtrading/Trend_Trading
ExecStart=/home/trendtrading/Trend_Trading/venv/bin/gunicorn \
  --chdir /home/trendtrading/Trend_Trading \
  --bind 0.0.0.0:5002 \
  --workers 2 \
  --timeout 60 \
  --access-logfile /home/trendtrading/Trend_Trading/logs/gunicorn-access.log \
  --error-logfile /home/trendtrading/Trend_Trading/logs/gunicorn-error.log \
  web.app:app
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5.2 `trend-kr.service` + `trend-kr.timer`
```ini
# trend-kr.service
[Unit]
Description=Trend Trading KR Pipeline
After=network-online.target

[Service]
Type=oneshot
User=trendtrading
WorkingDirectory=/home/trendtrading/Trend_Trading
EnvironmentFile=/home/trendtrading/Trend_Trading/config/.env
ExecStart=/home/trendtrading/Trend_Trading/venv/bin/python3 update_all.py --market kr
StandardOutput=append:/home/trendtrading/Trend_Trading/logs/daily_kr.log
StandardError=append:/home/trendtrading/Trend_Trading/logs/daily_kr.log
```
```ini
# trend-kr.timer
[Unit]
Description=Daily KR pipeline at 08:30 KST

[Timer]
OnCalendar=*-*-* 08:30:00 Asia/Seoul
Persistent=true

[Install]
WantedBy=timers.target
```

### 5.3 `trend-us.service` + `trend-us.timer`
KR과 동일 구조. `--market us`, `OnCalendar=*-*-* 09:30:00 Asia/Seoul`.

### 5.4 `trend-backup.service` + `trend-backup.timer`
백업 로직은 §6. `OnCalendar=*-*-* 03:00:00 Asia/Seoul`.

### 5.5 활성화
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trend-web.service
sudo systemctl enable --now trend-kr.timer trend-us.timer trend-backup.timer
```

### 5.6 운영 명령
```bash
sudo systemctl status trend-web
sudo systemctl list-timers --all | grep trend
sudo journalctl -u trend-web -f
sudo systemctl start trend-kr.service     # 수동 즉시 실행
```

---

## 6. Cloud IAP + HTTPS Load Balancer

### 6.1 정적 IP 예약
```bash
gcloud compute addresses create trend-trading-ip --global --ip-version=IPV4
```

### 6.2 Instance Group (단일 VM)
```bash
gcloud compute instance-groups unmanaged create trend-trading-ig --zone=us-central1-a
gcloud compute instance-groups unmanaged add-instances trend-trading-ig \
  --instances=openclaw-instance --zone=us-central1-a
gcloud compute instance-groups unmanaged set-named-ports trend-trading-ig \
  --named-ports=http:5002 --zone=us-central1-a
```

### 6.3 Health Check
```bash
gcloud compute health-checks create http trend-trading-hc \
  --port=5002 --request-path=/ \
  --check-interval=30s --healthy-threshold=2 --unhealthy-threshold=3
```
Flask `GET /`가 200을 반환하는지 검증 단계에서 확인. 필요 시 별도 `/healthz` 엔드포인트 추가.

### 6.4 VPC 방화벽
```bash
gcloud compute firewall-rules create allow-lb-health-check-trend \
  --direction=INGRESS --action=ALLOW --rules=tcp:5002 \
  --source-ranges=130.211.0.0/22,35.191.0.0/16 \
  --target-tags=trend-trading-backend
gcloud compute instances add-tags openclaw-instance \
  --tags=trend-trading-backend --zone=us-central1-a
```

### 6.5 OAuth Consent Screen
GCP Console → APIs & Services → OAuth consent screen
- User Type: External
- App name: `Trend Trading Dashboard`
- Support email: `cyh1024@gmail.com`
- Authorized domains: `sslip.io`
- Test users: `cyh1024@gmail.com`
- Publishing status: Testing 유지

### 6.6 OAuth Client ID
APIs & Services → Credentials → OAuth client ID
- Type: Web application
- Name: `Trend Trading IAP`
- Redirect URI: `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect`

### 6.7 Backend Service + URL Map + HTTPS Proxy
```bash
gcloud compute backend-services create trend-trading-backend --global \
  --protocol=HTTP --port-name=http \
  --health-checks=trend-trading-hc \
  --iap=enabled,oauth2-client-id=<CLIENT_ID>,oauth2-client-secret=<SECRET>

gcloud compute backend-services add-backend trend-trading-backend --global \
  --instance-group=trend-trading-ig \
  --instance-group-zone=us-central1-a

gcloud compute url-maps create trend-trading-urlmap \
  --default-service=trend-trading-backend

gcloud compute ssl-certificates create trend-trading-cert \
  --domains=<IP>.sslip.io --global

gcloud compute target-https-proxies create trend-trading-https-proxy \
  --url-map=trend-trading-urlmap \
  --ssl-certificates=trend-trading-cert

gcloud compute forwarding-rules create trend-trading-fr --global \
  --target-https-proxy=trend-trading-https-proxy \
  --address=trend-trading-ip --ports=443
```

### 6.8 IAP 권한
```bash
gcloud iap web add-iam-policy-binding \
  --resource-type=backend-services \
  --service=trend-trading-backend \
  --member=user:cyh1024@gmail.com \
  --role=roles/iap.httpsResourceAccessor
```

### 6.9 비용 (월 추정)
- Static IP (LB attach): $0
- HTTPS LB forwarding rule: ~$18
- GCS 백업: <$0.01
- 합계: ~$18/월 (VM 운영비 제외)

---

## 7. DB 백업 + 로그 관리

### 7.1 GCS 버킷
```bash
gsutil mb -l us-central1 -c standard gs://trend-trading-backup-<project-id>
gsutil lifecycle set lifecycle.json gs://trend-trading-backup-<project-id>
```
`lifecycle.json`:
```json
{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}
```

### 7.2 백업 스크립트 `scripts/backup_db.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="/home/trendtrading/Trend_Trading"
BUCKET="gs://trend-trading-backup-<project-id>"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
DB_PATH="$PROJECT_DIR/db/trend_trading.db"
TMP="/tmp/trend_trading_${TIMESTAMP}.db"

sqlite3 "$DB_PATH" ".backup '$TMP'"
gzip "$TMP"
gsutil cp "${TMP}.gz" "${BUCKET}/daily/trend_trading_${TIMESTAMP}.db.gz"
rm -f "${TMP}.gz"
```
`sqlite3 .backup` 사용해 트랜잭션 일관성 보장.

### 7.3 GCS 쓰기 권한
VM service account에 `Storage Object Admin` 또는 dedicated SA 발급. OpenClaw 권한과 충돌 없도록 검토.

### 7.4 복구 절차
```bash
gsutil ls gs://trend-trading-backup-.../daily/ | tail -5
sudo systemctl stop trend-web trend-kr.timer trend-us.timer
gsutil cp gs://trend-trading-backup-.../trend_trading_YYYYMMDD_HHMMSS.db.gz /tmp/
gunzip /tmp/trend_trading_*.db.gz
mv /tmp/trend_trading_*.db /home/trendtrading/Trend_Trading/db/trend_trading.db
sudo systemctl start trend-web trend-kr.timer trend-us.timer
```

### 7.5 logrotate `/etc/logrotate.d/trend-trading`
```
/home/trendtrading/Trend_Trading/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

---

## 8. 업데이트 워크플로우 + 맥 launchd 정리

### 8.1 일상 업데이트
맥:
```bash
git add . && git commit -m "..." && git push origin main
```
VM:
```bash
sudo su - trendtrading
cd ~/Trend_Trading && git pull origin main
# requirements.txt 변경 시
source venv/bin/activate && pip install -r requirements.txt
exit
sudo systemctl restart trend-web
```

### 8.2 (선택) 맥 deploy.sh
```bash
#!/usr/bin/env bash
set -e
git push origin main
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="
  sudo -u trendtrading bash -c '
    cd ~/Trend_Trading &&
    git pull origin main &&
    source venv/bin/activate &&
    pip install -q -r requirements.txt
  ' &&
  sudo systemctl restart trend-web
"
```
git에 올리지 않음 (개인 워크플로우).

### 8.3 맥 launchd 비활성화 (검증 후)
```bash
launchctl unload ~/Library/LaunchAgents/com.youngho.trendtrading-kr.plist
launchctl unload ~/Library/LaunchAgents/com.youngho.trendtrading-us.plist
rm ~/Library/LaunchAgents/com.youngho.trendtrading-*.plist
```

전환 순서:
1. VM 첫 배포 + 동작 확인
2. **VM과 맥 1주일 동시 운영** (Telegram 비교 검증)
3. 맥 launchd 비활성화

### 8.4 모니터링
기본:
```bash
sudo systemctl status trend-web
sudo systemctl list-timers --all | grep trend
sudo journalctl -u trend-kr.service --since today
```

Telegram 자체가 모니터링: 매일 08:30/09:30 KST 알림 도착 = 정상. 3일 연속 미수신 시 의심.

(선택) GCP Cloud Monitoring Uptime check로 `https://<IP>.sslip.io` 가용성 모니터링.

---

## 9. 단계별 실행 순서

```
Phase A. 사전 준비 (맥)
  A-1. git log 시크릿 흔적 검사
  A-2. .gitignore 보강
  A-3. 미커밋 5개 파일 검토 후 commit
  A-4. requirements.txt에 gunicorn 추가
  A-5. GitHub public 전환
  A-6. git push

Phase B. GCP 인프라 (gcloud CLI)
  B-1. 정적 IP 예약
  B-2. GCS 백업 버킷 + lifecycle
  B-3. VM service account에 GCS 쓰기 권한
  B-4. VPC 방화벽 (LB health check)
  B-5. VM에 backend tag 추가

Phase C. VM 셋업 (SSH)
  C-1. trendtrading 사용자 생성
  C-2. swap 2GB
  C-3. Python 3.12 설치
  C-4. 시스템 패키지 설치
  C-5. git clone + venv + pip install
  C-6. .env SCP + chmod 600
  C-7. logs/, scripts/ 디렉토리
  C-8. backup_db.sh 배치

Phase D. systemd
  D-1. 5개 unit 작성
  D-2. daemon-reload + enable --now
  D-3. trend-web 동작 확인 (curl localhost:5002)
  D-4. trend-kr.service 수동 실행 → Telegram 확인
  D-5. logrotate 설정

Phase E. IAP + LB
  E-1. Instance Group + named port
  E-2. Health check
  E-3. OAuth consent screen
  E-4. OAuth Client ID
  E-5. Backend service (IAP)
  E-6. URL Map + Managed SSL Cert
  E-7. HTTPS Proxy + Forwarding Rule
  E-8. IAP 권한 부여
  E-9. SSL 발급 대기 (~10-30분)
  E-10. https://<IP>.sslip.io 접속 검증

Phase F. 듀얼 운영 검증 (1주일)
  F-1. 맥 launchd + VM systemd 동시 운영
  F-2. Telegram 알림 일치 확인
  F-3. VM 메모리 사용량 모니터링

Phase G. 맥 launchd 비활성화
  G-1. launchctl unload + plist 제거
  G-2. README/CLAUDE.md 업데이트
```

---

## 10. 검증 체크리스트

Phase D~E 완료 시점:
- [ ] `systemctl status trend-web` → active (running)
- [ ] `curl -I http://localhost:5002` (VM에서) → 200
- [ ] `gcloud compute backend-services get-health trend-trading-backend --global` → HEALTHY
- [ ] `https://<IP>.sslip.io` → Google 로그인 → 대시보드 정상
- [ ] 다른 Google 계정 접근 시 IAP 차단
- [ ] `systemctl start trend-kr.service` → Telegram 알림 도착
- [ ] `gsutil ls gs://trend-trading-backup-.../daily/` → 첫 백업 존재
- [ ] `journalctl -u trend-web` → gunicorn worker 정상

---

## 11. 롤백 계획

| 실패 단계 | 대응 |
|----------|------|
| Phase A~D | trendtrading 디렉토리 삭제, systemd unit 비활성화. OpenClaw 무영향. 맥 launchd 운영 지속 |
| Phase E (IAP) | LB 리소스만 `gcloud ... delete`. trend-web.service 유지. SSH 터널(`gcloud compute ssh ... -- -L 5002:localhost:5002`)로 본인 접근 |
| Phase G 후 VM 장애 | 보관 plist를 `~/Library/LaunchAgents/` 복구 후 `launchctl load`. DB는 GCS 백업에서 복원 |

---

## 12. 알려진 위험 / 제약

1. **us-central1 latency**: pykrx → KRX 서버 RTT ~150-200ms. 60-90종목 직렬 호출 시 한 번에 ~30-60초 추가. 비동기/병렬화는 이번 범위 밖.
2. **e2-small 메모리**: OpenClaw + Trend Trading + gunicorn 2 workers 시 swap 사용 가능. 모니터링 후 필요 시 e2-medium 업그레이드 (월 ~$15 → ~$25).
3. **Managed SSL provisioning**: 도메인 검증 최대 30분. SSL 발급 전 접속 시 인증서 오류 → Phase E-9 대기 필수.
4. **OAuth consent screen Testing 상태**: 정식 게시 안 하면 90일 단위 재인증이 필요할 가능성 (Google 정책 변경 가능). 본인만 쓰면 무시 가능.
5. **GitHub public 전환**: git history에 시크릿 commit 흔적이 있으면 history rewrite 또는 private 유지 필요. Phase A-1에서 사전 검사.

---

## 13. 결정 사항 요약 (의사결정 트레일)

| 질문 | 결정 | 대안 |
|------|------|------|
| 배포 범위 | 배치 + 웹 모두 | 배치만 / 웹만 / 비공개 |
| 웹 인증 | Cloud IAP | SSH 터널 / Basic Auth / 완전 공개 |
| GCP 환경 | 기존 VM 공존 | 신규 VM / 무료 e2-micro |
| 도메인 | sslip.io | 보유 도메인 / 신규 구매 / SSH 터널 |
| 배포 방식 | git pull | rsync / GitHub Actions / Docker |
| 시크릿 | 수동 SCP | GCP Secret Manager / 메타데이터 |
| 격리 | 별도 사용자 | Docker 컨테이너 / 신규 VM |
| GitHub | public 전환 | private + Deploy Key |
| DB | VM 새로 시작 | 맥 DB 이관 |
| WSGI | gunicorn | Flask 개발 서버 직접 (보안 위험) |

---

## 14. 다음 단계

이 spec 승인 후 `superpowers:writing-plans` 스킬로 단계별 구현 plan 작성. 그 plan에 Phase A~G 각각의 실제 명령, 검증 단계, 의존성 관계가 task 단위로 분해된다.
