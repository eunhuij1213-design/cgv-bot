"""디스코드 웹훅 알림."""

import logging
import time

import requests

import config
from cgv import booking_url, fmt_date
from state import OpenEvent, SeatEvent

log = logging.getLogger(__name__)

COLOR_OPEN = 0x2ECC71  # 초록
COLOR_SEAT = 0xE67E22  # 주황
MAX_FIELDS = 25  # 디스코드 embed 필드 상한


class NotifyError(RuntimeError):
    pass


def open_embed(event: OpenEvent) -> dict:
    fields = [
        {
            "name": s.label,
            "value": f"잔여 **{s.free_seats}** / {s.total_seats}석",
            "inline": False,
        }
        for s in event.screenings[:MAX_FIELDS]
    ]
    extra = len(event.screenings) - len(fields)
    description = f"**{fmt_date(event.scn_ymd)}** · {config.SITE_NAME}\n총 {len(event.screenings)}개 회차"
    if extra > 0:
        description += f" (아래 {len(fields)}개만 표시)"

    link = booking_url(event.scn_ymd)
    return {
        "title": f"🎟️ 예매 오픈! {config.MOV_NAME}",
        "url": link,
        "description": f"{description}\n\n[▶ 예매하러 가기]({link})",
        "color": COLOR_OPEN,
        "fields": fields,
    }


def seat_embed(event: SeatEvent) -> dict:
    s = event.screening
    link = booking_url(s.scn_ymd)
    return {
        "title": f"💺 자리 났다! {config.MOV_NAME}",
        "url": link,
        "description": (
            f"**{fmt_date(s.scn_ymd)}** · {config.SITE_NAME}\n"
            f"{s.label}\n"
            f"매진 → 잔여 **{s.free_seats}** / {s.total_seats}석\n\n"
            f"[▶ 예매하러 가기]({link})"
        ),
        "color": COLOR_SEAT,
    }


def _post(payload: dict) -> None:
    """웹훅 전송. 429면 retry_after만큼 기다렸다 재시도."""
    for attempt in range(1, 4):
        res = requests.post(config.WEBHOOK_URL, json=payload, timeout=config.REQUEST_TIMEOUT)
        if res.status_code in (200, 204):
            return
        if res.status_code == 429:
            wait = float(res.json().get("retry_after", 1))
            log.warning("웹훅 rate limit, %.1fs 대기", wait)
            time.sleep(wait + 0.2)
            continue
        if attempt == 3:
            raise NotifyError(f"웹훅 전송 실패 HTTP {res.status_code}: {res.text[:200]}")
        time.sleep(attempt)
    raise NotifyError("웹훅 전송 실패: rate limit 재시도 초과")


def send(embeds: list[dict], *, dry_run: bool = False) -> None:
    """embed를 10개씩 묶어 전송."""
    if not embeds:
        return
    if dry_run:
        for e in embeds:
            log.info("[dry-run] %s | %s", e["title"], e["description"].replace("\n", " / "))
        return
    if not config.WEBHOOK_URL:
        raise NotifyError("DISCORD_WEBHOOK_URL이 설정되지 않았습니다 (.env 확인)")

    for i in range(0, len(embeds), 10):
        chunk = embeds[i : i + 10]
        _post({"embeds": chunk})
        if i + 10 < len(embeds):
            time.sleep(0.5)
    log.info("디스코드 알림 %d건 전송", len(embeds))


def send_events(
    open_events: list[OpenEvent],
    seat_events: list[SeatEvent],
    *,
    dry_run: bool = False,
) -> None:
    embeds = [open_embed(e) for e in open_events] + [seat_embed(e) for e in seat_events]
    send(embeds, dry_run=dry_run)


def send_text(content: str, *, dry_run: bool = False) -> None:
    """단순 텍스트 알림(에러 보고 등)."""
    if dry_run:
        log.info("[dry-run] %s", content)
        return
    if config.WEBHOOK_URL:
        _post({"content": content})
