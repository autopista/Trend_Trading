# Deploy Artifacts

GCP VM 배포에 필요한 systemd unit 파일들 + 설치 스크립트.

## 디렉토리

- `systemd/` — systemd unit 파일 7개 (web 1개 service + KR/US/backup 각각 service+timer)

## 설치 (VM에서)

```bash
sudo cp /home/trendtrading/Trend_Trading/deploy/systemd/*.service /etc/systemd/system/
sudo cp /home/trendtrading/Trend_Trading/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

# 활성화
sudo systemctl enable --now trend-web.service
sudo systemctl enable --now trend-kr.timer trend-us.timer trend-backup.timer
```

## 업데이트

unit 파일 수정 후:

```bash
cd /home/trendtrading/Trend_Trading && git pull
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart trend-web.service
```

## 참고

- 시간대: 모든 timer는 `OnCalendar=... Asia/Seoul`로 KST 명시 (VM 시스템 시간대는 UTC 유지)
- gunicorn ExecStart는 멀티라인 백슬래시 continuation 사용 — git에 올라가는 한 paste wrap 위험 없음
- spec/plan: `docs/superpowers/specs/2026-04-29-gcp-vm-deployment-design.md`
