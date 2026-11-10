
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

API_KEY = os.environ.get("ECOS_API_KEY")

if not API_KEY:
    raise RuntimeError("ECOS_API_KEY secret을 찾을 수 없습니다.")

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
today = now.date()


def fetch_ecos(stat_code, cycle, start_date, end_date, item_code):
    """한국은행 ECOS에서 지정한 통계 항목을 조회합니다."""

    parts = [
        "StatisticSearch",
        API_KEY,
        "json",
        "kr",
        "1",
        "1000",
        stat_code,
        cycle,
        start_date,
        end_date,
        item_code,
    ]

    url = "https://ecos.bok.or.kr/api/" + "/".join(
        urllib.parse.quote(str(part), safe="") for part in parts
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Daily-Economic-Board/1.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    section = result.get("StatisticSearch", {})

    if "row" not in section:
        error = section.get("RESULT", {})
        raise RuntimeError(
            "ECOS 조회 실패: "
            + str(error.get("CODE", "UNKNOWN"))
            + " / "
            + str(error.get("MESSAGE", "데이터가 없습니다."))
        )

    observations = []

    for row in section["row"]:
        value = row.get("DATA_VALUE")

        if value is None or value == "":
            continue

        observations.append({
            "time": row.get("TIME"),
            "value": value,
            "unit": row.get("UNIT_NAME", ""),
            "item_name": row.get("ITEM_NAME1", ""),
            "stat_name": row.get("STAT_NAME", ""),
        })

    observations.sort(key=lambda item: str(item["time"]))

    if not observations:
        raise RuntimeError(
            f"{stat_code}에서 유효한 관측값을 찾지 못했습니다."
        )

    return observations


# 기준금리: 최근 3개월, 월별 자료
three_months_ago = (
    today.replace(day=1) - timedelta(days=60)
).replace(day=1)

base_start = three_months_ago.strftime("%Y%m")
base_end = today.strftime("%Y%m")

# 환율: 최근 45일, 일별 자료
fx_start = (today - timedelta(days=45)).strftime("%Y%m%d")
fx_end = today.strftime("%Y%m%d")

print("한국은행 기준금리 조회 중...")
base_rate = fetch_ecos(
    stat_code="722Y001",
    cycle="M",
    start_date=base_start,
    end_date=base_end,
    item_code="0101000",
)
print("기준금리 관측 건수:", len(base_rate))
print("기준금리 최근 자료:", base_rate[-1])

print("원/달러 환율 조회 중...")
usd_krw = fetch_ecos(
    stat_code="731Y003",
    cycle="D",
    start_date=fx_start,
    end_date=fx_end,
    item_code="0000003",
)
print("환율 관측 건수:", len(usd_krw))
print("환율 최근 자료:", usd_krw[-1])

# 대시보드에서 읽을 데이터 파일 생성
output = {
    "updated_at": now.isoformat(),
    "source": "한국은행 ECOS Open API",
    "tables": [
        {
            "name": "한국은행 기준금리",
            "stat_code": "722Y001",
            "item_code": "0101000",
            "cycle": "M",
        },
        {
            "name": "원/미국달러 환율 매매기준율",
            "stat_code": "731Y003",
            "item_code": "0000003",
            "cycle": "D",
        },
    ],
    "items": [],
    "observations": {
        "기준금리": base_rate,
        "환율": usd_krw,
    },
}

os.makedirs("data", exist_ok=True)

with open(
    "data/economy_catalog.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(output, file, ensure_ascii=False, indent=2)

print("데이터 파일 저장 완료")
print("수집 시각:", now.isoformat())
