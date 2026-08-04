# CGV 예매 감시 봇

CGV **용산아이파크몰**의 **오디세이** 상영 일정을 주기적으로 확인해서, 변화가 생긴 순간에만 디스코드로 알립니다.

## 감시 조건

| 조건 | 감지 방식 |
|---|---|
| 예매 오픈 | 해당 날짜의 `data` 배열이 비어 있다가 채워짐 |
| 매진 → 자리 남음 | 특정 회차의 `frSeatCnt`가 `0` → `1` 이상 |

감시 대상은 **IMAX관**(`SCREEN_KEYWORD`)이고, 날짜는 오늘부터 `LOOKAHEAD_DAYS`(기본 30일) 이내의 **금·토·일**입니다.
직전 상태를 `state.json`에 저장하고 비교하므로, 상태가 바뀐 순간에만 알림이 갑니다.

## 구성

| 파일 | 역할 |
|---|---|
| `config.py` | 감시 대상(극장/영화/요일)과 실행 옵션 |
| `cgv.py` | CGV API 호출·파싱 (`Screening` 데이터클래스) |
| `state.py` | `state.json` 입출력과 변화 감지(`diff`) |
| `notify.py` | 디스코드 웹훅 embed 전송 |
| `main.py` | 조회 → 비교 → 알림 → 상태 저장 |
| `test.py` | 웹훅 연결 확인용 |

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env      # DISCORD_WEBHOOK_URL 채우기

python main.py            # 1회 실행
python main.py --dry-run  # 웹훅 전송·상태 저장 없이 감지 결과만 출력
python main.py --watch 60 --duration 270   # 60초 간격으로 약 4.5분 반복
```

## GitHub Actions

`.github/workflows/watch.yml`이 5분마다 실행되고, 잡 안에서 60초 간격으로 폴링합니다.
GitHub Actions의 cron 최소 간격이 5분이라 이런 구조입니다(실제로는 부하에 따라 더 늦게 뜨거나 건너뛸 수 있습니다).

설정할 것:

1. 레포 Settings → Secrets and variables → Actions → `DISCORD_WEBHOOK_URL` 추가
2. Settings → Actions → General → Workflow permissions를 **Read and write**로 (state.json 커밋용)

`state.json`은 실행할 때마다 레포에 커밋됩니다. 이게 실행 간에 상태를 이어주는 유일한 수단이라 `.gitignore`에 넣으면 안 됩니다.

## 알아둘 점

- **UA 헤더 필수** — 기본 curl/파이썬 UA로 호출하면 CGV WAF가 403(`mets01081`)을 돌려줍니다. `cgv.py`의 브라우저 헤더를 지우지 마세요. GitHub Actions IP가 차단되면 같은 403이 뜨는데, 이때는 해당 날짜를 건너뛰고 로그에 경고만 남깁니다.
- **씨네드쉐프 용산 제외** — API 응답에 `siteNo=P013`(씨네드쉐프 용산) 회차가 같이 들어오는데, 감시 대상은 본관뿐이라 `cgv.parse()`에서 걸러냅니다. 포함하고 싶으면 그 필터를 지우면 됩니다(단, `scnsNo`/`scnSseq`가 본관과 겹쳐서 회차 키에 `siteNo`가 반드시 필요합니다).
- **첫 실행은 기준선** — `state.json`이 없으면 현재 상태를 저장만 하고 알림은 보내지 않습니다(이미 열려 있던 날짜로 도배되는 것 방지). 첫 실행에도 받고 싶으면 `NOTIFY_ON_FIRST_RUN=true`.
- **알림 후 저장** — 웹훅 전송이 실패하면 상태를 저장하지 않아 다음 실행에서 다시 시도합니다.
- **바로가기 링크** — `BOOKING_URL`에 `{scn_ymd}` `{site_no}` `{mov_no}`를 쓰면 알림마다 해당 날짜 예매 페이지로 링크가 걸립니다. 디스코드는 `http(s)`만 링크로 허용해서(커스텀 스킴은 embed에서 HTTP 400) 앱 스킴은 넣을 수 없습니다.
