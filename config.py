"""감시 대상과 실행 옵션 설정."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

# --- 감시 대상 ---------------------------------------------------------------
CO_CD = "A420"
SITE_NO = "0013"  # CGV 용산아이파크몰
SITE_NAME = "CGV 용산아이파크몰"
MOV_NO = "30001323"  # 오디세이
MOV_NAME = "오디세이"
RTCTL_SCOP_CD = "08"

# 감시할 요일 (0=월 ... 4=금, 5=토, 6=일)
TARGET_WEEKDAYS = (4, 5, 6)

# 오늘로부터 며칠 뒤까지의 금/토/일을 감시할지
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "30"))

# --- 실행 옵션 ---------------------------------------------------------------
STATE_PATH = Path(os.getenv("STATE_PATH", BASE_DIR / "state.json"))
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
# 알림에 걸리는 바로가기 링크. {scn_ymd} {site_no} {mov_no} 를 치환해 쓸 수 있다.
BOOKING_URL = os.getenv("BOOKING_URL", "https://cgv.co.kr/")

REQUEST_TIMEOUT = 10
REQUEST_RETRIES = 3
# 같은 실행 안에서 날짜별 요청 사이 간격(초). WAF 차단 예방용.
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.7"))

# 상태 파일이 없는 첫 실행에서도 알림을 보낼지.
# 기본 False = 첫 실행은 현재 상태를 기준선으로만 저장(과거 상태를 새 변화로 오인하지 않음).
NOTIFY_ON_FIRST_RUN = os.getenv("NOTIFY_ON_FIRST_RUN", "false").lower() == "true"

KST = "Asia/Seoul"
