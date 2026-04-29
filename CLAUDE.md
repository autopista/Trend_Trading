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
- 프로젝트 루트: `/Users/youngho/Documents/Project/Trend_Trading`
- bash 경로: `/sessions/zealous-trusting-keller/mnt/Trend_Trading/`
- 로그: `logs/`
- 설정: `config/.env` (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

## 스케줄 작업 (launchctl)
| 작업 | plist 파일 | 기본 스케줄 (KST) |
|------|-----------|-----------------|
| 한국 시장 | `com.youngho.trendtrading-kr.plist` | 매일 08:30 KST |
| 미국 시장 | `com.youngho.trendtrading-us.plist` | 매일 09:30 KST |

launchctl reload 명령:
```bash
launchctl unload ~/Library/LaunchAgents/com.youngho.trendtrading-kr.plist
cp ~/Documents/Project/Trend_Trading/com.youngho.trendtrading-kr.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.youngho.trendtrading-kr.plist
```

## 파이프라인 실행
```bash
cd ~/Documents/Project/Trend_Trading && python3 update_all.py --market kr
cd ~/Documents/Project/Trend_Trading && python3 update_all.py --market us
```

## 개발자 정보
- 사용자: Youngho (컴퓨터 전공 개발자, 은퇴 예정)
- 관심사: AI 활용 주식투자, 은퇴 연금 자산관리, Claude 기반 1인 사업
