"""직전 상태 저장 + 변화 감지.

state.json 구조:
{
  "version": 1,
  "updated_at": "2026-08-04T15:40:00+09:00",
  "dates": {
    "20260814": {"open": true, "sessions": {"20260814|0013|018|1": 7, ...}}
  }
}
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from cgv import Screening

log = logging.getLogger(__name__)

VERSION = 1


@dataclass
class OpenEvent:
    """조건 1: data가 비어 있다가 채워짐 = 예매 오픈."""

    scn_ymd: str
    screenings: list[Screening]


@dataclass
class SeatEvent:
    """조건 2: 특정 회차 frSeatCnt가 0 -> 1 이상."""

    screening: Screening
    prev_free: int


def empty_state() -> dict:
    return {"version": VERSION, "updated_at": None, "dates": {}}


def load(path: Path | None = None) -> tuple[dict, bool]:
    """(상태, 첫 실행 여부)를 반환. 파일이 깨졌으면 첫 실행으로 취급."""
    path = path or config.STATE_PATH
    if not path.exists():
        return empty_state(), True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("state.json 읽기 실패(%s). 새로 시작합니다.", exc)
        return empty_state(), True

    if data.get("version") != VERSION or not isinstance(data.get("dates"), dict):
        log.warning("state.json 형식이 달라 새로 시작합니다.")
        return empty_state(), True
    return data, False


def save(state: dict, path: Path | None = None) -> None:
    path = path or config.STATE_PATH
    state["updated_at"] = datetime.now(ZoneInfo(config.KST)).isoformat(timespec="seconds")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 중간에 죽어도 반쪽짜리 state가 남지 않도록


def snapshot(screenings: list[Screening]) -> dict:
    return {
        "open": bool(screenings),
        "sessions": {s.key: s.free_seats for s in screenings},
    }


def diff(
    prev_state: dict,
    current: dict[str, list[Screening]],
    *,
    first_run: bool = False,
) -> tuple[list[OpenEvent], list[SeatEvent], dict]:
    """직전 상태와 이번 조회 결과를 비교해 이벤트와 새 상태를 만든다.

    - 조회에 실패한 날짜는 current에 없으므로 직전 상태를 그대로 유지한다.
    - 처음 보는 날짜는 기준선으로만 저장한다(NOTIFY_ON_FIRST_RUN=true면 오픈 알림).
    """
    prev_dates: dict = prev_state.get("dates", {})
    new_dates = dict(prev_dates)

    open_events: list[OpenEvent] = []
    seat_events: list[SeatEvent] = []

    for scn_ymd, screenings in current.items():
        prev = prev_dates.get(scn_ymd)
        new_dates[scn_ymd] = snapshot(screenings)

        if prev is None:
            if screenings and first_run and config.NOTIFY_ON_FIRST_RUN:
                open_events.append(OpenEvent(scn_ymd, screenings))
            continue

        # 조건 1: 비어 있다가 채워짐
        if not prev.get("open") and screenings:
            open_events.append(OpenEvent(scn_ymd, screenings))
            continue  # 방금 열린 날은 좌석 변화 알림까지 낼 필요 없음

        # 조건 2: 매진 -> 자리 남음
        prev_sessions: dict = prev.get("sessions", {})
        for s in screenings:
            prev_free = prev_sessions.get(s.key)
            if prev_free == 0 and s.free_seats >= 1:
                seat_events.append(SeatEvent(s, prev_free))

    return open_events, seat_events, {"version": VERSION, "dates": new_dates}


def prune(state: dict, keep_dates: list[str]) -> dict:
    """지난 날짜 등 더 이상 감시하지 않는 날짜를 상태에서 제거."""
    keep = set(keep_dates)
    state["dates"] = {d: v for d, v in state.get("dates", {}).items() if d in keep}
    return state
