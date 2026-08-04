"""CGV 상영시간표 API 호출 및 파싱."""

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import requests

import config

log = logging.getLogger(__name__)

API_URL = "https://cgv.co.kr/api/v1/booking/searchSchByMov"

# curl 같은 기본 UA는 CGV WAF(mets01081)에 차단된다. 브라우저 헤더 필수.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://cgv.co.kr/",
}

WEEKDAY_KR = ("월", "화", "수", "목", "금", "토", "일")


class CGVError(RuntimeError):
    """API 호출 실패(네트워크/차단/비정상 응답)."""


@dataclass(frozen=True)
class Screening:
    """상영 회차 한 건."""

    scn_ymd: str  # 상영일 20260818
    site_no: str  # 극장 번호 0013(용산아이파크몰) / P013(씨네드쉐프 용산)
    site_nm: str  # 극장 이름
    scns_no: str  # 상영관 번호 018
    scns_nm: str  # 상영관 이름 IMAX관
    scn_sseq: str  # 회차 1
    prod_nm: str  # 오디세이(IMAX LASER 2D)
    start_tm: str  # 0630
    end_tm: str  # 0932
    total_seats: int  # stcnt
    free_seats: int  # frSeatCnt

    @property
    def key(self) -> str:
        """상태 비교용 회차 고유 키.

        siteNo 필수: 같은 응답에 씨네드쉐프 용산(P013)이 섞여 들어오는데
        scnsNo/scnSseq가 본관과 겹친다.
        """
        return f"{self.scn_ymd}|{self.site_no}|{self.scns_no}|{self.scn_sseq}"

    @property
    def start_hhmm(self) -> str:
        return fmt_time(self.start_tm)

    @property
    def end_hhmm(self) -> str:
        return fmt_time(self.end_tm)

    @property
    def label(self) -> str:
        place = self.scns_nm
        if self.site_no != config.SITE_NO:  # 씨네드쉐프 등 별관은 극장명까지 표기
            place = f"{self.site_nm} {self.scns_nm}"
        return f"{place} {self.start_hhmm}~{self.end_hhmm} · {self.prod_nm}"


def fmt_time(hhmm: str) -> str:
    """0630 -> 06:30. 자정 넘긴 2400/2702 표기도 그대로 살린다."""
    if not hhmm or len(hhmm) != 4 or not hhmm.isdigit():
        return hhmm or "-"
    return f"{hhmm[:2]}:{hhmm[2:]}"


def fmt_date(scn_ymd: str) -> str:
    """20260818 -> 2026-08-18(화)."""
    try:
        d = date(int(scn_ymd[:4]), int(scn_ymd[4:6]), int(scn_ymd[6:8]))
    except (ValueError, IndexError):
        return scn_ymd
    return f"{d.isoformat()}({WEEKDAY_KR[d.weekday()]})"


def today_kst() -> date:
    from datetime import datetime

    return datetime.now(ZoneInfo(config.KST)).date()


def target_dates(base: date | None = None) -> list[str]:
    """오늘부터 LOOKAHEAD_DAYS 이내의 금/토/일 날짜를 YYYYMMDD로."""
    base = base or today_kst()
    return [
        (base + timedelta(days=i)).strftime("%Y%m%d")
        for i in range(config.LOOKAHEAD_DAYS + 1)
        if (base + timedelta(days=i)).weekday() in config.TARGET_WEEKDAYS
    ]


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse(payload: dict) -> list[Screening]:
    """API 응답 JSON -> Screening 목록. 예매 오픈 전이면 빈 리스트."""
    rows = payload.get("data") or []
    screenings = [
        Screening(
            scn_ymd=row.get("scnYmd", ""),
            site_no=row.get("siteNo", ""),
            site_nm=row.get("siteNm", ""),
            scns_no=row.get("scnsNo", ""),
            scns_nm=row.get("expoScnsNm") or row.get("scnsNm") or "",
            scn_sseq=row.get("scnSseq", ""),
            prod_nm=row.get("expoProdNm") or row.get("prodNm") or "",
            start_tm=row.get("scnsrtTm", ""),
            end_tm=row.get("scnendTm", ""),
            total_seats=_to_int(row.get("stcnt")),
            free_seats=_to_int(row.get("frSeatCnt")),
        )
        for row in rows
    ]
    return sorted(screenings, key=lambda s: (s.site_no, s.scns_no, s.start_tm))


def fetch(session: requests.Session, scn_ymd: str) -> list[Screening]:
    """해당 날짜의 상영 회차 조회. 실패 시 CGVError."""
    params = {
        "coCd": config.CO_CD,
        "siteNo": config.SITE_NO,
        "scnYmd": scn_ymd,
        "movNo": config.MOV_NO,
        "rtctlScopCd": config.RTCTL_SCOP_CD,
    }

    last_error: Exception | None = None
    for attempt in range(1, config.REQUEST_RETRIES + 1):
        try:
            res = session.get(API_URL, params=params, timeout=config.REQUEST_TIMEOUT)
            if res.status_code != 200:
                raise CGVError(f"HTTP {res.status_code} (WAF 차단 가능성)")
            payload = res.json()
            if payload.get("statusCode") != 0:
                raise CGVError(f"statusCode={payload.get('statusCode')} {payload.get('statusMessage')}")
            return parse(payload)
        except (requests.RequestException, ValueError, CGVError) as exc:
            last_error = exc
            if attempt < config.REQUEST_RETRIES:
                time.sleep(attempt * 1.5)

    raise CGVError(f"{scn_ymd} 조회 실패: {last_error}")


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_all(dates: list[str]) -> dict[str, list[Screening]]:
    """날짜별 조회. 개별 날짜 실패는 건너뛴다(그 날짜는 상태 비교에서 제외)."""
    session = make_session()
    result: dict[str, list[Screening]] = {}
    for i, scn_ymd in enumerate(dates):
        if i:
            time.sleep(config.REQUEST_DELAY)
        try:
            result[scn_ymd] = fetch(session, scn_ymd)
        except CGVError as exc:
            log.warning("%s 조회 실패, 건너뜀: %s", scn_ymd, exc)
    return result
