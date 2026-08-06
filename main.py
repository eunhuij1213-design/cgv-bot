"""CGV 예매 감시 봇.

사용법:
    python main.py                      # 1회 실행
    python main.py --dry-run            # 웹훅 전송 없이 감지 결과만 출력
    python main.py --watch 30 --duration 280   # 30초 간격으로 약 280초 동안 반복
"""

import argparse
import logging
import sys
import time

import cgv
import config
import notify
import state

log = logging.getLogger("cgv-bot")


def run_once(*, dry_run: bool = False) -> int:
    """한 번 조회 -> 비교 -> 알림 -> 상태 저장. 감지한 이벤트 수를 반환."""
    dates = cgv.target_dates()
    log.info("감시 대상 %d일: %s", len(dates), ", ".join(cgv.fmt_date(d) for d in dates))

    current = cgv.fetch_all(dates)
    if not current:
        log.error("모든 날짜 조회 실패. 상태를 갱신하지 않습니다.")
        return 0

    prev_state, first_run = state.load()
    if first_run:
        log.info("직전 상태 없음 - 이번 조회를 기준선으로 저장합니다.")

    open_events, seat_events, new_state = state.diff(prev_state, current, first_run=first_run)

    # 자리가 난 회차만 좌석 배치도를 추가 조회해 일반석/이동식을 구분한다.
    if seat_events:
        session = cgv.make_session()
        for e in seat_events:
            e.breakdown = cgv.fetch_seat_breakdown(session, e.screening)

    for e in open_events:
        log.info("[예매 오픈] %s - %d회차", cgv.fmt_date(e.scn_ymd), len(e.screenings))
    for e in seat_events:
        detail = f" ({e.breakdown})" if e.breakdown else ""
        log.info("[자리 남음] %s %s - 0 -> %d석%s", cgv.fmt_date(e.screening.scn_ymd), e.screening.label, e.screening.free_seats, detail)
    if not open_events and not seat_events:
        opened = sum(1 for v in new_state["dates"].values() if v["open"])
        log.info("변화 없음 (오픈된 날짜 %d/%d)", opened, len(new_state["dates"]))

    notify.send_events(open_events, seat_events, dry_run=dry_run)

    # 알림 전송 후 저장: 전송이 실패하면 상태를 유지해 다음 실행에서 다시 시도한다.
    if not dry_run:
        state.save(state.prune(new_state, dates))

    return len(open_events) + len(seat_events)


def main() -> int:
    parser = argparse.ArgumentParser(description="CGV 예매 오픈/좌석 감시 봇")
    parser.add_argument("--dry-run", action="store_true", help="웹훅 전송·상태 저장 없이 감지 결과만 출력")
    parser.add_argument("--watch", type=float, metavar="SEC", help="반복 실행 간격(초)")
    parser.add_argument("--duration", type=float, metavar="SEC", help="--watch 총 실행 시간(초)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.watch:
        run_once(dry_run=args.dry_run)
        return 0

    deadline = time.monotonic() + (args.duration or 300)
    while True:
        try:
            run_once(dry_run=args.dry_run)
        except Exception:  # 한 번 실패해도 루프는 계속
            log.exception("실행 중 오류")
        remaining = deadline - time.monotonic()
        if remaining <= args.watch:
            break
        time.sleep(args.watch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
