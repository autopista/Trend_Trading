# GCP VM Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trend Trading 프로젝트를 맥 launchd 운영에서 GCP `openclaw-instance` VM 공존 배포로 이전한다 (배치 + 웹 + IAP).

**Architecture:** 별도 시스템 사용자(`trendtrading`) + systemd timer (Asia/Seoul TZ) + gunicorn + Cloud IAP HTTPS Load Balancer (sslip.io 도메인) + GCS 일일 백업.

**Tech Stack:** Python 3.12, gunicorn, SQLite, systemd, gcloud CLI, GCS, Cloud IAP, HTTPS Load Balancer.

**Spec:** `docs/superpowers/specs/2026-04-29-gcp-vm-deployment-design.md`

---

## 변수 (각 Phase 진행 중 채워짐)

| 변수 | 값 | 결정 시점 |
|------|-----|----------|
| `$GCP_PROJECT_ID` | (Phase B-0에서 확인) | gcloud config get-value project |
| `$VM_NAME` | `openclaw-instance` | 고정 |
| `$VM_ZONE` | `us-central1-a` | 고정 |
| `$VM_EXTERNAL_IP` | (Phase B-1에서 결정) | 정적 IP 예약 후 |
| `$IP_DOMAIN` | `<dash-separated-IP>.sslip.io` | 정적 IP 예약 후 |
| `$OAUTH_CLIENT_ID` | (Phase E-4에서 발급) | OAuth Client 생성 후 |
| `$OAUTH_CLIENT_SECRET` | (Phase E-4에서 발급) | OAuth Client 생성 후 |
| `$BACKUP_BUCKET` | `gs://trend-trading-backup-$GCP_PROJECT_ID` | Phase B-2 |

---

## File Structure

배포 작업이라 신규 파일은 적다.

| 파일 | 위치 | 변경 유형 | 책임 |
|------|------|----------|------|
| `.gitignore` | 맥 (repo) | 수정 | macOS/launchd 전용 파일 제외 |
| `requirements.txt` | 맥 (repo) | 수정 | gunicorn 추가 |
| `scripts/backup_db.sh` | VM | 생성 | SQLite → GCS 일일 백업 |
| `/etc/systemd/system/trend-web.service` | VM | 생성 | gunicorn 상시 실행 |
| `/etc/systemd/system/trend-kr.service` | VM | 생성 | KR 일배치 |
| `/etc/systemd/system/trend-kr.timer` | VM | 생성 | KR 08:30 KST |
| `/etc/systemd/system/trend-us.service` | VM | 생성 | US 일배치 |
| `/etc/systemd/system/trend-us.timer` | VM | 생성 | US 09:30 KST |
| `/etc/systemd/system/trend-backup.service` | VM | 생성 | DB 백업 |
| `/etc/systemd/system/trend-backup.timer` | VM | 생성 | 백업 03:00 KST |
| `/etc/logrotate.d/trend-trading` | VM | 생성 | 로그 30일 회전 |
| `lifecycle.json` | VM (임시) | 생성 | GCS 30일 보관 정책 |

---

## Phase A. 사전 준비 (맥에서 실행)

### Task 1: git history 시크릿 흔적 검증

**Files:**
- 검사 대상: 전체 git history

- [ ] **Step 1: 시크릿 패턴 검사**

```bash
cd ~/Documents/Project/Trend_Trading
git log --all -p | grep -iE "API_KEY|TOKEN|SECRET|PASSWORD|sk-[a-zA-Z0-9]" | head -20
```

Expected: 출력이 비어있거나 `.gitignore`/`README.md`의 변수명 언급만 보임 (실제 키 값이 commit된 흔적 없음). 만약 실제 키 값이 발견되면 **STOP** — public 전환 보류하고 사용자에게 보고.

- [ ] **Step 2: .env 파일이 git에 추적된 적 있는지 검사**

```bash
git log --all --full-history -- config/.env
```

Expected: 출력 없음 (한 번도 commit된 적 없음).

- [ ] **Step 3: 검증 결과 보고 후 다음 task 진행**

검증 통과 시 사용자에게 "git history 시크릿 검증 완료" 보고. 의심스러우면 사용자 결정 대기.

---

### Task 2: .gitignore 보강

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 현재 .gitignore 확인**

```bash
cat .gitignore
```

- [ ] **Step 2: 항목 추가**

`.gitignore`에 아래 라인을 append (기존 내용 유지):

```gitignore
# macOS
.DS_Store

# Logs
logs/

# Backup files
*.bak
0
config/settings.yaml.bak

# macOS launchd 전용 (VM에서는 systemd 사용)
com.youngho.trendtrading-*.plist
register_test_us.sh
run_daily_kr.sh
run_daily_us.sh
```

- [ ] **Step 3: 추적되던 .DS_Store가 있으면 제거**

```bash
git ls-files | grep -i "\.DS_Store" || echo "no tracked .DS_Store"
```

만약 출력이 있으면:
```bash
git rm --cached <path>/.DS_Store
```

- [ ] **Step 4: git status로 의도하지 않은 변경 확인**

```bash
git status -s
```

Expected: `.gitignore` modified, 미추적 파일들이 줄어듦 (`logs/`, `*.bak` 등이 사라짐).

- [ ] **Step 5: 커밋**

```bash
git add .gitignore
git commit -m "chore: extend .gitignore for macOS/launchd files

- Exclude .DS_Store, logs/, *.bak from tracking
- macOS-only launchd plists and run_daily_*.sh excluded
  (VM uses systemd instead)"
```

---

### Task 3: 미커밋 5개 파일 검토 후 커밋

**Files:**
- 검토: `config/settings.yaml`, `db/repository.py`, `run.sh`, `signals/telegram_notifier.py`, `web/templates/performance.html`

- [ ] **Step 1: 각 파일 변경사항 확인**

```bash
git diff config/settings.yaml
git diff db/repository.py
git diff run.sh
git diff signals/telegram_notifier.py
git diff web/templates/performance.html
```

- [ ] **Step 2: 변경 내용을 한 줄씩 요약**

각 파일의 변경 의도를 사용자에게 보고하고 커밋 메시지 분류:
- 같은 주제(예: telegram 알림 개선) → 한 commit
- 다른 주제 → 별도 commit

만약 의도 불명확하면 사용자에게 질문.

- [ ] **Step 3: 분류에 따라 커밋 (예시: 모두 별개 변경인 경우)**

```bash
git add config/settings.yaml && git commit -m "chore: update settings.yaml"
git add db/repository.py && git commit -m "..."
# ... 각 파일별 또는 묶음별로 commit
```

각 commit 메시지는 변경 내용을 정확히 반영해야 함.

- [ ] **Step 4: working tree clean 확인**

```bash
git status -s
```

Expected: 5개 파일이 모두 사라짐. 미추적 파일 중 macOS 전용 plist/sh는 .gitignore로 안 보여야 함. `CLAUDE.md`는 untracked로 남아있을 수 있음 (별도 task에서 처리 결정).

---

### Task 4: requirements.txt에 gunicorn 추가

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 현재 requirements.txt 확인**

```bash
cat requirements.txt
```

- [ ] **Step 2: gunicorn 라인 추가**

`requirements.txt` 끝에 한 줄 추가:

```
gunicorn==21.*
```

- [ ] **Step 3: 맥에서 설치 가능한지 확인 (선택)**

```bash
pip install gunicorn==21.* --dry-run
```

Expected: 충돌 없음.

- [ ] **Step 4: 커밋**

```bash
git add requirements.txt
git commit -m "feat: add gunicorn for production WSGI server

GCP VM 배포 시 Flask 개발 서버 대신 gunicorn으로 실행"
```

---

### Task 5: GitHub 저장소 public 전환

**Files:** 없음 (GitHub 웹 UI 작업)

- [ ] **Step 1: Task 1의 검증 결과 재확인**

git history에 시크릿 흔적 없음을 다시 확인. 의심되면 STOP.

- [ ] **Step 2: GitHub 웹에서 public 전환**

1. https://github.com/autopista/Trend_Trading/settings 접속
2. 페이지 하단 "Danger Zone" → "Change repository visibility"
3. "Make public" 선택 → 저장소명 입력해 확인

- [ ] **Step 3: public 전환 확인**

```bash
curl -s https://api.github.com/repos/autopista/Trend_Trading | grep '"private"'
```

Expected: `"private": false`.

---

### Task 6: 모든 commit 푸시

**Files:** 없음

- [ ] **Step 1: 푸시할 commit 확인**

```bash
git log origin/main..HEAD --oneline
```

- [ ] **Step 2: 푸시**

```bash
git push origin main
```

Expected: 성공. `error: refusing to update` 등 오류 시 `git pull --rebase` 후 재시도.

- [ ] **Step 3: GitHub 웹에서 최신 commit 확인**

브라우저에서 저장소 페이지 → 최신 commit 메시지가 방금 push한 것과 일치하는지 확인.

---

## Phase B. GCP 인프라 (gcloud CLI)

### Task 7: gcloud 인증 + 프로젝트 ID 확인

**Files:** 없음

- [ ] **Step 1: gcloud 인증 상태 확인**

```bash
gcloud auth list
gcloud config get-value project
```

Expected: 활성 계정과 프로젝트 ID 출력. 인증 없으면 `gcloud auth login` 실행.

- [ ] **Step 2: 프로젝트 ID를 변수로 export (이후 task 명령에서 사용)**

```bash
export GCP_PROJECT_ID=$(gcloud config get-value project)
echo "Project: $GCP_PROJECT_ID"
```

- [ ] **Step 3: 필수 API 활성화 확인**

```bash
gcloud services list --enabled --filter="name:(compute.googleapis.com OR iap.googleapis.com OR storage.googleapis.com)" --format="value(name)"
```

Expected: 3개 모두 활성. 누락 시:
```bash
gcloud services enable compute.googleapis.com iap.googleapis.com storage.googleapis.com
```

- [ ] **Step 4: VM 정보 재확인**

```bash
gcloud compute instances describe openclaw-instance --zone=us-central1-a --format="value(status,machineType.basename(),networkInterfaces[0].accessConfigs[0].natIP)"
```

Expected: `RUNNING`, `e2-small`, 현재 임시 외부 IP. 임시 IP는 다음 task에서 정적으로 변환.

---

### Task 8: 정적 외부 IP 예약 + VM에 attach

**Files:** 없음

- [ ] **Step 1: 정적 IP 예약 (글로벌 — LB용)**

```bash
gcloud compute addresses create trend-trading-ip --global --ip-version=IPV4
```

Expected: `Created [...]`. 이미 존재하면 그대로 진행.

- [ ] **Step 2: 예약된 IP 값 확인**

```bash
export VM_EXTERNAL_IP=$(gcloud compute addresses describe trend-trading-ip --global --format="value(address)")
echo "Reserved IP: $VM_EXTERNAL_IP"
```

이 IP는 LB의 frontend가 됨. **VM 자체의 외부 IP와는 다름** — VM은 LB의 backend로만 동작. VM 외부 IP는 그대로 두거나(SSH 용도) 정적 변환은 별도 결정.

- [ ] **Step 3: sslip.io 도메인 형식 생성**

```bash
export IP_DOMAIN=$(echo $VM_EXTERNAL_IP | tr '.' '-').sslip.io
echo "Domain: $IP_DOMAIN"
```

이 도메인으로 IAP 접속하게 됨. Phase E의 SSL cert에 사용.

---

### Task 9: GCS 백업 버킷 + lifecycle 정책

**Files:**
- Create: `/tmp/lifecycle.json` (임시)

- [ ] **Step 1: 버킷 이름 변수 생성**

```bash
export BACKUP_BUCKET="gs://trend-trading-backup-${GCP_PROJECT_ID}"
echo "Bucket: $BACKUP_BUCKET"
```

- [ ] **Step 2: 버킷 생성 (us-central1, standard storage)**

```bash
gsutil mb -l us-central1 -c standard "$BACKUP_BUCKET"
```

Expected: `Creating ...`. 이미 존재하면 그대로 진행.

- [ ] **Step 3: lifecycle 정책 파일 작성**

```bash
cat > /tmp/lifecycle.json <<'EOF'
{
  "rule": [
    {"action": {"type": "Delete"}, "condition": {"age": 30}}
  ]
}
EOF
```

- [ ] **Step 4: lifecycle 적용**

```bash
gsutil lifecycle set /tmp/lifecycle.json "$BACKUP_BUCKET"
gsutil lifecycle get "$BACKUP_BUCKET"
```

Expected: 두 번째 명령이 방금 설정한 JSON을 출력.

- [ ] **Step 5: 임시 파일 삭제**

```bash
rm /tmp/lifecycle.json
```

---

### Task 10: VM service account에 GCS 쓰기 권한

**Files:** 없음

- [ ] **Step 1: VM의 service account 확인**

```bash
gcloud compute instances describe openclaw-instance --zone=us-central1-a \
  --format="value(serviceAccounts[0].email)"
```

Expected: `<숫자>-compute@developer.gserviceaccount.com` 또는 dedicated SA. 출력값을 변수로 저장:

```bash
export VM_SA=$(gcloud compute instances describe openclaw-instance --zone=us-central1-a --format="value(serviceAccounts[0].email)")
echo "VM SA: $VM_SA"
```

- [ ] **Step 2: VM의 access scope 확인**

```bash
gcloud compute instances describe openclaw-instance --zone=us-central1-a \
  --format="value(serviceAccounts[0].scopes)"
```

Expected: `https://www.googleapis.com/auth/cloud-platform` 또는 `https://www.googleapis.com/auth/devstorage.*`. 만약 `cloud-platform` scope가 없으면 IAM 권한이 있어도 GCS 쓰기 불가 → **STOP하고 사용자에게 보고**. scope 변경은 VM 중지 후 변경 필요 → OpenClaw 영향 → 사용자 결정.

- [ ] **Step 3: 버킷에 Object Admin 권한 부여**

```bash
gsutil iam ch "serviceAccount:${VM_SA}:objectAdmin" "$BACKUP_BUCKET"
```

- [ ] **Step 4: 권한 확인**

```bash
gsutil iam get "$BACKUP_BUCKET" | grep -A 2 "$VM_SA"
```

Expected: `roles/storage.objectAdmin` 표시.

---

### Task 11: VPC 방화벽 + VM에 backend tag 추가

**Files:** 없음

- [ ] **Step 1: 방화벽 규칙 생성 (LB health check 대역만 허용)**

```bash
gcloud compute firewall-rules create allow-lb-health-check-trend \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:5002 \
  --source-ranges=130.211.0.0/22,35.191.0.0/16 \
  --target-tags=trend-trading-backend \
  --description="Allow GCP LB health checks to Trend Trading on port 5002"
```

Expected: `Created [...]`.

- [ ] **Step 2: VM에 tag 추가**

```bash
gcloud compute instances add-tags openclaw-instance \
  --tags=trend-trading-backend \
  --zone=us-central1-a
```

기존 다른 tag가 있다면 합쳐서 추가됨 (덮어쓰지 않음).

- [ ] **Step 3: 적용 확인**

```bash
gcloud compute instances describe openclaw-instance --zone=us-central1-a \
  --format="value(tags.items)"
```

Expected: `trend-trading-backend`가 포함됨.

---

## Phase C. VM 셋업 (SSH)

### Task 12: VM에 SSH 접속 + trendtrading 사용자 생성

**Files:** 없음

- [ ] **Step 1: 맥에서 VM에 SSH 접속**

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a
```

이후 모든 단계는 VM 셸에서 실행.

- [ ] **Step 2: trendtrading 사용자 생성**

```bash
sudo useradd -m -s /bin/bash trendtrading
```

이미 존재하면 `useradd: user 'trendtrading' already exists` → 무시하고 다음 단계.

- [ ] **Step 3: 홈 디렉토리 확인**

```bash
ls -la /home/trendtrading
```

Expected: `/home/trendtrading/` 디렉토리 존재, owner `trendtrading`.

---

### Task 13: swap 2GB 추가

**Files:**
- Create: `/swapfile`
- Modify: `/etc/fstab`

- [ ] **Step 1: 현재 swap 상태 확인**

```bash
free -h
swapon --show
```

이미 충분한 swap(>=2GB)이 있으면 이 task 건너뜀.

- [ ] **Step 2: 2GB swap 파일 생성**

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
```

- [ ] **Step 3: swap 활성화**

```bash
sudo swapon /swapfile
```

- [ ] **Step 4: 부팅 시 자동 활성화**

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

- [ ] **Step 5: 확인**

```bash
free -h
```

Expected: `Swap` 라인에 `2.0Gi`.

---

### Task 14: Python 3.12 + 시스템 패키지 설치

**Files:** 없음

- [ ] **Step 1: 현재 Python 버전 확인**

```bash
python3 --version
which python3
```

Expected: Python 3.10.x (Ubuntu 22.04 기본). 3.12가 이미 있으면 PPA 추가 단계 건너뜀.

- [ ] **Step 2: deadsnakes PPA 추가**

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
```

- [ ] **Step 3: Python 3.12 + 시스템 패키지 설치**

```bash
sudo apt-get install -y \
  python3.12 python3.12-venv python3.12-dev \
  build-essential git tzdata curl sqlite3
```

- [ ] **Step 4: 설치 확인**

```bash
python3.12 --version
sqlite3 --version
git --version
```

Expected: 모두 정상 출력.

---

### Task 15: Trend Trading 코드 클론 + venv + 의존성 설치

**Files:**
- Create: `/home/trendtrading/Trend_Trading/` (전체 디렉토리)

- [ ] **Step 1: trendtrading 사용자로 전환**

```bash
sudo su - trendtrading
```

- [ ] **Step 2: 저장소 클론**

```bash
git clone https://github.com/autopista/Trend_Trading.git ~/Trend_Trading
cd ~/Trend_Trading
```

Expected: 정상 clone (Phase A에서 public 전환했으므로 인증 불필요).

- [ ] **Step 3: venv 생성 + 활성화**

```bash
python3.12 -m venv venv
source venv/bin/activate
python --version
```

Expected: `Python 3.12.x`.

- [ ] **Step 4: 의존성 설치**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

`pykrx` 설치가 가장 오래 걸림 (~수 분). 완료 후:

```bash
pip list | grep -E "flask|gunicorn|pykrx|yfinance"
```

Expected: 4개 패키지 모두 표시.

- [ ] **Step 5: 디렉토리 준비**

```bash
mkdir -p logs scripts
```

- [ ] **Step 6: import 검증 (의존성 누락 사전 발견)**

```bash
python -c "import flask, gunicorn, pykrx, yfinance, sqlalchemy, telegram, dotenv, yaml; print('all imports OK')"
```

Expected: `all imports OK`. 실패 시 누락 패키지 추가 설치.

- [ ] **Step 7: 일반 사용자로 복귀**

```bash
exit
```

`trendtrading` 셸 종료, 일반 사용자로 돌아옴.

---

### Task 16: 시크릿 (config/.env) SCP 복사

**Files:**
- Create: `~/Trend_Trading/config/.env` (VM)

- [ ] **Step 1: 맥에서 SCP 실행 (별도 터미널)**

VM SSH 세션은 그대로 두고 **맥의 새 터미널**에서:

```bash
cd ~/Documents/Project/Trend_Trading
gcloud compute scp config/.env openclaw-instance:/tmp/.env \
  --zone=us-central1-a
```

`/tmp/`로 우선 올림 — `trendtrading` 홈은 SCP 사용자 권한이 없어서 직접 못 올림.

- [ ] **Step 2: VM SSH 세션에서 파일을 trendtrading 홈으로 이동**

```bash
sudo mv /tmp/.env /home/trendtrading/Trend_Trading/config/.env
sudo chown trendtrading:trendtrading /home/trendtrading/Trend_Trading/config/.env
sudo chmod 600 /home/trendtrading/Trend_Trading/config/.env
```

- [ ] **Step 3: 권한/내용 확인**

```bash
sudo -u trendtrading ls -la /home/trendtrading/Trend_Trading/config/.env
sudo -u trendtrading head -3 /home/trendtrading/Trend_Trading/config/.env | sed 's/=.*/=***/'
```

Expected: `-rw------- trendtrading trendtrading`, 키 변수명만 보이고 값은 `***`로 마스킹된 출력.

---

### Task 17: backup_db.sh 작성 + 실행 권한

**Files:**
- Create: `/home/trendtrading/Trend_Trading/scripts/backup_db.sh`

- [ ] **Step 1: trendtrading 사용자로 전환**

```bash
sudo su - trendtrading
```

- [ ] **Step 2: backup_db.sh 작성**

```bash
cat > ~/Trend_Trading/scripts/backup_db.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="/home/trendtrading/Trend_Trading"
BUCKET="gs://trend-trading-backup-${GCP_PROJECT_ID}"
TIMESTAMP=\$(date '+%Y%m%d_%H%M%S')
DB_PATH="\$PROJECT_DIR/db/trend_trading.db"
TMP="/tmp/trend_trading_\${TIMESTAMP}.db"

if [ ! -f "\$DB_PATH" ]; then
    echo "DB not found: \$DB_PATH (skipping backup)"
    exit 0
fi

sqlite3 "\$DB_PATH" ".backup '\$TMP'"
gzip "\$TMP"
gsutil cp "\${TMP}.gz" "\${BUCKET}/daily/trend_trading_\${TIMESTAMP}.db.gz"
rm -f "\${TMP}.gz"
echo "Backup complete: \${BUCKET}/daily/trend_trading_\${TIMESTAMP}.db.gz"
EOF
```

**중요**: `${GCP_PROJECT_ID}`는 heredoc에서 expansion되어야 하므로 따옴표 없이 EOF 사용. `\$` 이스케이프된 변수만 런타임 expansion.

- [ ] **Step 3: 실행 권한**

```bash
chmod +x ~/Trend_Trading/scripts/backup_db.sh
```

- [ ] **Step 4: 내용 확인**

```bash
cat ~/Trend_Trading/scripts/backup_db.sh
```

Expected: `BUCKET="gs://trend-trading-backup-<실제 project id>"`로 expand됨.

- [ ] **Step 5: 일반 사용자로 복귀**

```bash
exit
```

---

## Phase D. systemd 서비스 + 타이머

### Task 18: trend-web.service 작성 (gunicorn 상시)

**Files:**
- Create: `/etc/systemd/system/trend-web.service`

- [ ] **Step 1: unit 파일 작성**

```bash
sudo tee /etc/systemd/system/trend-web.service > /dev/null <<'EOF'
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
EOF
```

- [ ] **Step 2: 문법 검증**

```bash
sudo systemd-analyze verify /etc/systemd/system/trend-web.service
```

Expected: 출력 없음 (오류 없음).

---

### Task 19: trend-kr.service + trend-kr.timer 작성

**Files:**
- Create: `/etc/systemd/system/trend-kr.service`
- Create: `/etc/systemd/system/trend-kr.timer`

- [ ] **Step 1: service unit 작성**

```bash
sudo tee /etc/systemd/system/trend-kr.service > /dev/null <<'EOF'
[Unit]
Description=Trend Trading KR Pipeline
After=network-online.target

[Service]
Type=oneshot
User=trendtrading
Group=trendtrading
WorkingDirectory=/home/trendtrading/Trend_Trading
EnvironmentFile=/home/trendtrading/Trend_Trading/config/.env
Environment=PYTHONPATH=/home/trendtrading/Trend_Trading
ExecStart=/home/trendtrading/Trend_Trading/venv/bin/python3 update_all.py --market kr
StandardOutput=append:/home/trendtrading/Trend_Trading/logs/daily_kr.log
StandardError=append:/home/trendtrading/Trend_Trading/logs/daily_kr.log
EOF
```

- [ ] **Step 2: timer unit 작성**

```bash
sudo tee /etc/systemd/system/trend-kr.timer > /dev/null <<'EOF'
[Unit]
Description=Daily KR pipeline at 08:30 KST

[Timer]
OnCalendar=*-*-* 08:30:00 Asia/Seoul
Persistent=true
Unit=trend-kr.service

[Install]
WantedBy=timers.target
EOF
```

- [ ] **Step 3: 문법 검증**

```bash
sudo systemd-analyze verify /etc/systemd/system/trend-kr.service
sudo systemd-analyze verify /etc/systemd/system/trend-kr.timer
```

Expected: 출력 없음.

---

### Task 20: trend-us.service + trend-us.timer 작성

**Files:**
- Create: `/etc/systemd/system/trend-us.service`
- Create: `/etc/systemd/system/trend-us.timer`

- [ ] **Step 1: service unit 작성**

```bash
sudo tee /etc/systemd/system/trend-us.service > /dev/null <<'EOF'
[Unit]
Description=Trend Trading US Pipeline
After=network-online.target

[Service]
Type=oneshot
User=trendtrading
Group=trendtrading
WorkingDirectory=/home/trendtrading/Trend_Trading
EnvironmentFile=/home/trendtrading/Trend_Trading/config/.env
Environment=PYTHONPATH=/home/trendtrading/Trend_Trading
ExecStart=/home/trendtrading/Trend_Trading/venv/bin/python3 update_all.py --market us
StandardOutput=append:/home/trendtrading/Trend_Trading/logs/daily_us.log
StandardError=append:/home/trendtrading/Trend_Trading/logs/daily_us.log
EOF
```

- [ ] **Step 2: timer unit 작성**

```bash
sudo tee /etc/systemd/system/trend-us.timer > /dev/null <<'EOF'
[Unit]
Description=Daily US pipeline at 09:30 KST

[Timer]
OnCalendar=*-*-* 09:30:00 Asia/Seoul
Persistent=true
Unit=trend-us.service

[Install]
WantedBy=timers.target
EOF
```

- [ ] **Step 3: 문법 검증**

```bash
sudo systemd-analyze verify /etc/systemd/system/trend-us.service
sudo systemd-analyze verify /etc/systemd/system/trend-us.timer
```

---

### Task 21: trend-backup.service + trend-backup.timer 작성

**Files:**
- Create: `/etc/systemd/system/trend-backup.service`
- Create: `/etc/systemd/system/trend-backup.timer`

- [ ] **Step 1: service unit 작성**

```bash
sudo tee /etc/systemd/system/trend-backup.service > /dev/null <<'EOF'
[Unit]
Description=Trend Trading SQLite DB Backup to GCS

[Service]
Type=oneshot
User=trendtrading
Group=trendtrading
ExecStart=/home/trendtrading/Trend_Trading/scripts/backup_db.sh
StandardOutput=append:/home/trendtrading/Trend_Trading/logs/backup.log
StandardError=append:/home/trendtrading/Trend_Trading/logs/backup.log
EOF
```

- [ ] **Step 2: timer unit 작성**

```bash
sudo tee /etc/systemd/system/trend-backup.timer > /dev/null <<'EOF'
[Unit]
Description=Daily DB backup at 03:00 KST

[Timer]
OnCalendar=*-*-* 03:00:00 Asia/Seoul
Persistent=true
Unit=trend-backup.service

[Install]
WantedBy=timers.target
EOF
```

- [ ] **Step 3: 문법 검증**

```bash
sudo systemd-analyze verify /etc/systemd/system/trend-backup.service
sudo systemd-analyze verify /etc/systemd/system/trend-backup.timer
```

---

### Task 22: systemd 활성화 + 웹 서비스 동작 확인

**Files:** 없음

- [ ] **Step 1: daemon-reload**

```bash
sudo systemctl daemon-reload
```

- [ ] **Step 2: 웹 서비스 즉시 시작 + 부팅 시 자동 실행**

```bash
sudo systemctl enable --now trend-web.service
```

- [ ] **Step 3: 5초 대기 후 상태 확인**

```bash
sleep 5
sudo systemctl status trend-web --no-pager
```

Expected: `Active: active (running)`. 만약 `failed` 상태면:

```bash
sudo journalctl -u trend-web -n 50 --no-pager
```

로 로그 확인 후 디버깅. 흔한 원인: gunicorn 미설치, .env 권한 문제, web.app 모듈 import 실패.

- [ ] **Step 4: 로컬에서 HTTP 응답 확인**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5002/
```

Expected: `200`. `502/503`이면 gunicorn worker 시작 실패.

- [ ] **Step 5: 타이머들 활성화**

```bash
sudo systemctl enable --now trend-kr.timer trend-us.timer trend-backup.timer
```

- [ ] **Step 6: 타이머 다음 실행 시각 확인**

```bash
sudo systemctl list-timers --all | grep trend
```

Expected: 3개 타이머가 모두 표시되고, 다음 실행 시각이 KST 기준 08:30/09:30/03:00에 해당하는 UTC 시각으로 표기 (예: 08:30 KST = 23:30 UTC).

---

### Task 23: trend-kr.service 수동 실행 → Telegram 알림 검증

**Files:** 없음

이 단계로 전체 파이프라인이 VM에서 동작하는지 확인. **DB가 처음 생성되는 순간**.

- [ ] **Step 1: 수동 실행 (백그라운드)**

```bash
sudo systemctl start trend-kr.service
```

- [ ] **Step 2: 실시간 로그 모니터링**

```bash
sudo journalctl -u trend-kr.service -f
```

KR 시장 데이터 수집 + Livermore 분석 + 시그널 생성 + Telegram 알림이 순차 진행. 완료까지 1~3분.

종료 시 `Ctrl+C`로 journalctl 빠져나오기.

- [ ] **Step 3: 실행 결과 확인**

```bash
sudo systemctl status trend-kr.service --no-pager
```

Expected: `Active: inactive (dead)` + 마지막 ExecStart가 `code=exited, status=0/SUCCESS`.

- [ ] **Step 4: Telegram 알림 도착 확인**

본인 Telegram 채팅 확인 — 시그널 알림이 도착했는지. 시그널이 없는 날이면 "조건 불충족" 메시지가 와야 함 (현재 코드 동작 확인 필요).

- [ ] **Step 5: DB 생성 확인**

```bash
ls -la /home/trendtrading/Trend_Trading/db/trend_trading.db
sudo -u trendtrading sqlite3 /home/trendtrading/Trend_Trading/db/trend_trading.db ".tables"
```

Expected: 파일 존재 + 여러 테이블 출력.

- [ ] **Step 6: 로그 파일 확인**

```bash
sudo -u trendtrading cat /home/trendtrading/Trend_Trading/logs/daily_kr.log | tail -30
```

Expected: 정상 완료 로그.

---

### Task 24: 백업 스크립트 수동 실행 → GCS 업로드 검증

**Files:** 없음

- [ ] **Step 1: 수동 실행**

```bash
sudo systemctl start trend-backup.service
```

- [ ] **Step 2: 결과 확인**

```bash
sudo systemctl status trend-backup.service --no-pager
sudo -u trendtrading cat /home/trendtrading/Trend_Trading/logs/backup.log | tail -10
```

Expected: `code=exited, status=0/SUCCESS` + "Backup complete: gs://..." 메시지.

- [ ] **Step 3: GCS에 파일 도착 확인**

```bash
gsutil ls "gs://trend-trading-backup-${GCP_PROJECT_ID}/daily/"
```

Expected: `trend_trading_YYYYMMDD_HHMMSS.db.gz` 1개 이상.

---

### Task 25: logrotate 설정

**Files:**
- Create: `/etc/logrotate.d/trend-trading`

- [ ] **Step 1: logrotate 설정 작성**

```bash
sudo tee /etc/logrotate.d/trend-trading > /dev/null <<'EOF'
/home/trendtrading/Trend_Trading/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
```

- [ ] **Step 2: 문법 검증 (dry run)**

```bash
sudo logrotate -d /etc/logrotate.d/trend-trading
```

Expected: 오류 없이 "considering log /home/trendtrading/..." 등의 출력. 마지막에 "rotating pattern" 메시지.

---

## Phase E. Cloud IAP + HTTPS Load Balancer

이 Phase는 GCP Console UI 작업과 gcloud 명령이 섞임. 작업은 **맥에서** 실행 (VM SSH는 종료해도 됨).

### Task 26: Instance Group + named port

**Files:** 없음

- [ ] **Step 1: Instance Group 생성**

```bash
gcloud compute instance-groups unmanaged create trend-trading-ig \
  --zone=us-central1-a
```

- [ ] **Step 2: VM을 Instance Group에 추가**

```bash
gcloud compute instance-groups unmanaged add-instances trend-trading-ig \
  --instances=openclaw-instance --zone=us-central1-a
```

- [ ] **Step 3: named port 설정**

```bash
gcloud compute instance-groups unmanaged set-named-ports trend-trading-ig \
  --named-ports=http:5002 --zone=us-central1-a
```

- [ ] **Step 4: 확인**

```bash
gcloud compute instance-groups unmanaged describe trend-trading-ig \
  --zone=us-central1-a --format="value(namedPorts)"
```

Expected: `[{'name': 'http', 'port': 5002}]`.

---

### Task 27: Health Check 생성

**Files:** 없음

- [ ] **Step 1: 헬스체크 생성**

```bash
gcloud compute health-checks create http trend-trading-hc \
  --port=5002 \
  --request-path=/ \
  --check-interval=30s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3
```

- [ ] **Step 2: VM에서 `GET /`이 200 반환하는지 확인**

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5002/"
```

Expected: `200`. 만약 다른 코드면 Flask 라우트 확인 필요. 필요 시 `web/app.py`에 `/healthz` 엔드포인트 추가하고 헬스체크 path 변경.

---

### Task 28: OAuth Consent Screen 설정 (GCP Console UI)

**Files:** 없음

이 단계는 GCP Console 웹 UI에서 진행.

- [ ] **Step 1: OAuth consent screen 페이지 접속**

https://console.cloud.google.com/apis/credentials/consent

- [ ] **Step 2: External 선택 + 기본 정보 입력**

- User Type: **External**
- App name: `Trend Trading Dashboard`
- User support email: `cyh1024@gmail.com`
- Developer contact: `cyh1024@gmail.com`

- [ ] **Step 3: Scopes 화면**

기본값 그대로 (email, profile, openid). 추가 scope 없음.

- [ ] **Step 4: Test users 추가**

- `cyh1024@gmail.com` 추가

- [ ] **Step 5: Authorized domains에 sslip.io 추가**

App registration 화면에서 Authorized domains에 `sslip.io` 입력.

- [ ] **Step 6: 저장 + Publishing status 확인**

- "Back to Dashboard"
- Publishing status: **Testing** (Production 게시 안 함)

---

### Task 29: OAuth Client ID 생성 (GCP Console UI)

**Files:** 없음

- [ ] **Step 1: Credentials 페이지 접속**

https://console.cloud.google.com/apis/credentials

- [ ] **Step 2: Create Credentials → OAuth client ID**

- Application type: **Web application**
- Name: `Trend Trading IAP`
- Authorized redirect URIs는 일단 비워두고 **Create** 클릭

- [ ] **Step 3: Client ID + Client Secret 저장**

생성 후 다이얼로그에 표시되는 값 복사:
- Client ID: `<숫자>-<해시>.apps.googleusercontent.com`
- Client Secret: `GOCSPX-...`

**안전한 곳에 임시 저장** (다음 task에서 사용).

- [ ] **Step 4: Redirect URI 등록**

방금 만든 Client를 클릭 → "Authorized redirect URIs"에 추가:

```
https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect
```

`<CLIENT_ID>`를 실제 값으로 치환. 저장.

- [ ] **Step 5: 변수로 export (이후 task에서 사용)**

```bash
export OAUTH_CLIENT_ID="<숫자>-<해시>.apps.googleusercontent.com"
export OAUTH_CLIENT_SECRET="GOCSPX-..."
```

---

### Task 30: Backend Service 생성 + IAP enable + 백엔드 attach

**Files:** 없음

- [ ] **Step 1: Backend Service 생성 (IAP enabled)**

```bash
gcloud compute backend-services create trend-trading-backend \
  --global \
  --protocol=HTTP \
  --port-name=http \
  --health-checks=trend-trading-hc \
  --iap=enabled,oauth2-client-id="$OAUTH_CLIENT_ID",oauth2-client-secret="$OAUTH_CLIENT_SECRET"
```

- [ ] **Step 2: Instance Group 연결**

```bash
gcloud compute backend-services add-backend trend-trading-backend \
  --global \
  --instance-group=trend-trading-ig \
  --instance-group-zone=us-central1-a
```

- [ ] **Step 3: 확인**

```bash
gcloud compute backend-services describe trend-trading-backend --global \
  --format="value(iap.enabled,backends[0].group)"
```

Expected: `True` + Instance Group URL.

---

### Task 31: URL Map + Managed SSL Cert

**Files:** 없음

- [ ] **Step 1: URL Map 생성**

```bash
gcloud compute url-maps create trend-trading-urlmap \
  --default-service=trend-trading-backend
```

- [ ] **Step 2: Managed SSL Cert 생성 (sslip.io 도메인)**

```bash
gcloud compute ssl-certificates create trend-trading-cert \
  --domains="${IP_DOMAIN}" \
  --global
```

`$IP_DOMAIN`은 Phase B Task 8의 `<dash-IP>.sslip.io`.

- [ ] **Step 3: Cert 발급 시작 확인**

```bash
gcloud compute ssl-certificates describe trend-trading-cert --global \
  --format="value(managed.status,managed.domainStatus)"
```

Expected: 처음에는 `PROVISIONING`. 도메인 검증이 끝나야 `ACTIVE`로 바뀜 — 이 단계에서는 PROVISIONING이면 정상.

---

### Task 32: HTTPS Proxy + Forwarding Rule

**Files:** 없음

- [ ] **Step 1: HTTPS Proxy 생성**

```bash
gcloud compute target-https-proxies create trend-trading-https-proxy \
  --url-map=trend-trading-urlmap \
  --ssl-certificates=trend-trading-cert
```

- [ ] **Step 2: Forwarding Rule 생성 (정적 IP attach)**

```bash
gcloud compute forwarding-rules create trend-trading-fr \
  --global \
  --target-https-proxy=trend-trading-https-proxy \
  --address=trend-trading-ip \
  --ports=443
```

- [ ] **Step 3: Forwarding Rule이 정적 IP에 attach 됐는지 확인**

```bash
gcloud compute forwarding-rules describe trend-trading-fr --global \
  --format="value(IPAddress,target.basename())"
```

Expected: 정적 IP + `trend-trading-https-proxy`.

---

### Task 33: IAP 사용자 권한 부여

**Files:** 없음

- [ ] **Step 1: 본인 이메일에 IAP accessor 권한 부여**

```bash
gcloud iap web add-iam-policy-binding \
  --resource-type=backend-services \
  --service=trend-trading-backend \
  --member=user:cyh1024@gmail.com \
  --role=roles/iap.httpsResourceAccessor
```

- [ ] **Step 2: 권한 확인**

```bash
gcloud iap web get-iam-policy \
  --resource-type=backend-services \
  --service=trend-trading-backend
```

Expected: `cyh1024@gmail.com`에 `roles/iap.httpsResourceAccessor` 표시.

---

### Task 34: SSL 발급 대기 + 접속 검증

**Files:** 없음

- [ ] **Step 1: SSL cert ACTIVE까지 대기 (최대 30분)**

```bash
while true; do
  STATUS=$(gcloud compute ssl-certificates describe trend-trading-cert --global --format="value(managed.status)")
  echo "$(date '+%H:%M:%S') status: $STATUS"
  [ "$STATUS" = "ACTIVE" ] && break
  sleep 60
done
```

`PROVISIONING` → `ACTIVE`로 바뀔 때까지. `FAILED_NOT_VISIBLE`이 나오면 도메인 검증 실패 — `IP_DOMAIN` 형식 재확인.

- [ ] **Step 2: 백엔드 헬스 확인**

```bash
gcloud compute backend-services get-health trend-trading-backend --global
```

Expected: `HEALTHY` 상태인 인스턴스 1개.

- [ ] **Step 3: HTTPS 접속 테스트 (브라우저)**

브라우저에서 `https://${IP_DOMAIN}` 접속 (실제 도메인 치환).

기대 동작:
1. Google 로그인 페이지로 리다이렉트
2. `cyh1024@gmail.com`로 로그인
3. (Testing 모드 경고 화면 → "Continue" 클릭)
4. Trend Trading 대시보드 로드

- [ ] **Step 4: 차단 검증 (선택)**

다른 Google 계정 또는 시크릿창에서 같은 URL 접속 → "You don't have access" IAP 차단 페이지 확인.

---

## Phase F. 듀얼 운영 검증 (1주일)

### Task 35: 듀얼 운영 시작

**Files:** 없음

VM systemd timer는 활성화된 상태 + 맥 launchd도 그대로 운영.

- [ ] **Step 1: 맥 launchd 상태 확인**

```bash
launchctl list | grep trendtrading
```

Expected: KR/US 두 개 모두 표시.

- [ ] **Step 2: VM systemd timer 다음 실행 시각 확인**

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="sudo systemctl list-timers --all | grep trend"
```

Expected: 다음 실행 시각이 정상 KST 시각에 해당함.

- [ ] **Step 3: 모니터링 시작 (1주일)**

매일 확인:
- Telegram 알림이 두 개씩 오는지 (맥 + VM, 동일한 내용?)
- VM에서 메모리 사용량이 OOM 임박 수준은 아닌지

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="free -h && uptime"
```

- VM 로그 이상 없는지

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="sudo journalctl -u trend-kr.service -u trend-us.service --since='1 day ago' | tail -50"
```

---

### Task 36: 듀얼 운영 결과 비교

**Files:** 없음

- [ ] **Step 1: 1주일치 Telegram 알림 비교**

매일 두 번씩 받은 알림이 내용 동일한지 확인. 차이가 있다면 원인 분석:
- 시간 차이: VM과 맥의 시계 동기화 (NTP) 확인
- 시그널 차이: 둘 중 하나의 데이터 수집이 실패한 가능성
- 종목 차이: settings.yaml 동기화 안 됨

- [ ] **Step 2: VM의 GCS 백업 확인 (1주일치)**

```bash
gsutil ls "gs://trend-trading-backup-${GCP_PROJECT_ID}/daily/" | wc -l
```

Expected: 7개 이상 (매일 03:00 KST에 누적).

- [ ] **Step 3: VM 메모리/스왑 추이**

```bash
gcloud compute ssh openclaw-instance --zone=us-central1-a --command="cat /proc/meminfo | grep -E 'MemAvailable|SwapFree'"
```

`SwapFree`가 거의 0이면 OOM 위험 → e2-medium 업그레이드 결정.

- [ ] **Step 4: 사용자에게 검증 결과 보고**

이상 없으면 다음 Phase G로 진행 신호 받기.

---

## Phase G. 맥 launchd 비활성화

### Task 37: 맥 launchd 비활성화 + plist 제거

**Files:**
- Delete: `~/Library/LaunchAgents/com.youngho.trendtrading-kr.plist`
- Delete: `~/Library/LaunchAgents/com.youngho.trendtrading-us.plist`

이 task는 **Phase F 검증 완료 후에만** 진행.

- [ ] **Step 1: launchd unload**

```bash
launchctl unload ~/Library/LaunchAgents/com.youngho.trendtrading-kr.plist
launchctl unload ~/Library/LaunchAgents/com.youngho.trendtrading-us.plist
```

- [ ] **Step 2: plist 파일 제거**

```bash
rm ~/Library/LaunchAgents/com.youngho.trendtrading-kr.plist
rm ~/Library/LaunchAgents/com.youngho.trendtrading-us.plist
```

프로젝트 디렉토리의 plist 원본(`com.youngho.trendtrading-*.plist`)은 .gitignore되어 있고 로컬 백업 용도로 그대로 둠 (롤백 시 복원 가능).

- [ ] **Step 3: 비활성화 확인**

```bash
launchctl list | grep trendtrading
```

Expected: 출력 없음.

---

### Task 38: README + CLAUDE.md 업데이트

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: CLAUDE.md 업데이트**

`CLAUDE.md`의 "스케줄 작업 (launchctl)" 섹션을 다음으로 교체:

```markdown
## 스케줄 작업 (GCP VM systemd)

운영 위치: GCP `openclaw-instance` (`us-central1-a`), 사용자 `trendtrading`

| 작업 | systemd unit | 스케줄 (KST) |
|------|-------------|-------------|
| 한국 시장 | `trend-kr.timer` | 매일 08:30 KST |
| 미국 시장 | `trend-us.timer` | 매일 09:30 KST |
| DB 백업 | `trend-backup.timer` | 매일 03:00 KST |

웹 대시보드: `https://<static-IP>.sslip.io` (Cloud IAP, Google 로그인 필요)

운영 명령:
\`\`\`bash
# VM SSH 접속
gcloud compute ssh openclaw-instance --zone=us-central1-a

# VM에서:
sudo systemctl status trend-web                       # 웹 상태
sudo systemctl list-timers --all | grep trend         # 타이머 다음 실행 시각
sudo journalctl -u trend-kr.service --since today     # KR 배치 로그
sudo systemctl start trend-kr.service                 # 수동 즉시 실행
\`\`\`

배포 (코드 업데이트):
\`\`\`bash
git push origin main  # 맥에서
# VM에서:
sudo su - trendtrading
cd ~/Trend_Trading && git pull origin main
exit
sudo systemctl restart trend-web
\`\`\`
```

기존 "파이프라인 실행" 섹션은 로컬 개발 용도로 유지.

- [ ] **Step 2: README.md 업데이트 (선택)**

배포 위치를 README에 추가하고 싶으면 "Deployment" 섹션 추가. 또는 CLAUDE.md만 업데이트해도 충분.

- [ ] **Step 3: 커밋 + 푸시**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update operations guide for GCP VM deployment

맥 launchd → GCP openclaw-instance systemd 이전 완료에 따라
스케줄/운영 명령/배포 흐름을 systemd + git pull 기반으로 갱신"
git push origin main
```

---

## 검증 체크리스트 (Phase G 완료 후)

전체 배포 완료 시점에 다음 항목 모두 OK여야 함:

- [ ] `gcloud compute ssh openclaw-instance ... sudo systemctl status trend-web` → active (running)
- [ ] `https://<IP>.sslip.io` 접속 → Google 로그인 → 대시보드 정상 표시
- [ ] 다른 Google 계정으로 같은 URL 접근 → IAP 차단 화면
- [ ] 매일 KR 08:30 KST + US 09:30 KST에 Telegram 알림 도착
- [ ] `gsutil ls gs://trend-trading-backup-.../daily/ | wc -l` → 매일 1씩 증가
- [ ] 맥 `launchctl list | grep trendtrading` → 출력 없음
- [ ] VM에서 OpenClaw 정상 동작 (영향 없음)

---

## 롤백 계획

| 실패 단계 | 대응 |
|----------|------|
| Task 1~6 (사전 준비) | 영향 없음. git revert로 .gitignore/requirements.txt 되돌리기. GitHub은 다시 private 전환 가능 |
| Task 7~11 (GCP 인프라) | `gcloud compute ... delete`로 생성한 리소스 제거. OpenClaw 영향 없음 |
| Task 12~17 (VM 셋업) | trendtrading 사용자 + 홈디렉토리 삭제 (`sudo userdel -r trendtrading`). swap 비활성화는 영향 적어 유지 가능 |
| Task 18~25 (systemd) | systemd unit 비활성화 + 파일 삭제 (`sudo systemctl disable --now trend-*; sudo rm /etc/systemd/system/trend-*`). 맥 launchd 그대로 운영 지속 |
| Task 26~34 (IAP/LB) | LB 리소스만 `gcloud compute ... delete`. trend-web.service 유지. 임시로 SSH 터널(`gcloud compute ssh openclaw-instance -- -L 5002:localhost:5002`)로 본인 접근 |
| Task 35~36 (듀얼 운영) | VM systemd timer 비활성화. 맥 launchd 그대로 |
| Task 37 후 VM 장애 | 프로젝트 디렉토리의 plist 원본을 `~/Library/LaunchAgents/`에 복사 후 `launchctl load`. DB는 GCS 백업에서 복원 |

---

## 다음 단계

이 plan을 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`로 실행. 사용자 결정.
