"""웹훅 연결 확인용 스크립트."""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

res = requests.post(WEBHOOK_URL, json={"content": "🎬 테스트 알림, 봇 살아있음"})

print("상태코드:", res.status_code)
