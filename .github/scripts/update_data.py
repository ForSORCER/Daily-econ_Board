
import json
import os
import urllib.request
import urllib.error
from urllib.parse import quote
from datetime import datetime, timedelta, timezone


API_KEY = os.environ.get("ECOS_API_KEY")
BASE_URL = "https://ecos.bok.or.kr/api"
KST = timezone(timedelta(hours=9))
OUTPUT_FILE = "data/economy_catalog.json"


class EcosNoData(Exception):
    pass


def ecos_request(service, start, end, *parts):
    if not API_KEY:
        raise RuntimeError("ECOS_API_KEY를 찾을 수 없습니다.")

    url = (
        f"{BASE_URL}/{service}/{quote(API_KEY, safe='')}"
        f"/json/kr/{start}/{end}"
    )

    for part in parts:
        url += "/" + quote(str(part), safe="")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DailyEconomicBoard/1.0"}
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        raise RuntimeError(f"ECOS HTTP 오류: {error.code}")

    except urllib.error.URLError as error:
        raise RuntimeError(f"ECOS 연결 오류: {error.reason}")

    info = result.get("RESULT", {})

    if info:
        code = info.get("CODE", "")
        message = info.get("MESSAGE", "")

        if code == "INFO-200":
            raise EcosNoData(message)

        if code and code != "INFO-000":
            raise RuntimeError(f"ECOS 오류 {code}: {message}")

    service_data = result.get(service, {})

    if not service_data:
        return []

    rows = service_data.get("row", [])

    if isinstance(rows, dict):
        rows = [rows]

    return rows or []


def make_period(cycle, years_back):
    today = datetime.now(KST)

    if cycle == "D":
        start = today - timedelta(days=365 * years_back)
        return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")

    if cycle == "M":
        start_year = today.year - years_back
        return f"{start_year}{today.month:02d}", today.strftime("%Y%m")

    if cycle == "Q":
        start_year = today.year - years_back
        quarter = (today.month - 1) // 3 + 1
        return f"{start_year}Q{quarter}", f"{today.year}Q{quarter}"

    if cycle == "A":
        return str(today.year - years_back), str(today.year)

    raise ValueError(f"지원하지 않는 통계 주기: {cycle}")


def find_candidate(items, category):
    candidates = []

    for item in items:
        name = (
            str(item.get("item_name", "")) + " " +
            str(item.get("p_item_name", "")) + " " +
            str(item.get("grp_name", ""))
        )

        if category == "기준금리":
            if "한국은행 기준금리" in name:
                candidates.append(item)

        elif category == "환율":
            keywords = [
                "원/미국달러",
                "원/달러",
                "미국달러",
                "USD/KRW"
            ]

            if any(word in name for word in keywords):
                candidates.append(item)

    # 자료가 있는 항목을 우선 선택
    candidates.sort(
        key=lambda x: int(x.get("data_cnt") or 0),
        reverse=True
    )

    return candidates[0] if candidates else None


def fetch_observations(item, category):
    stat_code = item["stat_code"]
    item_code = item["item_code"]
    cycle = item["cycle"]

    years_back = 5 if category == "기준금리" else 1

    start_date, end_date = make_period(cycle, years_back)

    print()
    print("실제 데이터 조회:", category)
    print("통계표:", item["stat_name"])
    print("항목:", item["item_name"])
    print("주기:", cycle)
    print("기간:", start_date, "~", end_date)

    rows = ecos_request(
        "StatisticSearch",
        1,
        1000,
        stat_code,
        cycle,
        start_date,
        end_date,
        item_code
    )

    print("실제 데이터 수:", len(rows))

    return [
        {
            "time": row.get("TIME", ""),
            "value": row.get("DATA_VALUE", ""),
            "unit": row.get("UNIT_NAME", ""),
            "item_name": row.get("ITEM_NAME1", item["item_name"]),
            "stat_name": row.get("STAT_NAME", item["stat_name"])
        }
        for row in rows
    ]


def main():
    print("ECOS 통계 목록을 확인합니다.")

    tables = ecos_request("StatisticTableList", 1, 1000)

    print("통계표 수:", len(tables))

    searchable_tables = [
        table for table in tables
        if str(table.get("SRCH_YN", "")).upper() == "Y"
    ]

    print("검색 가능한 통계표 수:", len(searchable_tables))

    targets = {
        "기준금리": ["기준금리", "여수신금리"],
        "환율": ["환율", "외환"]
    }

    selected_tables = {
        "기준금리": [],
        "환율": []
    }

    selected_items = {
        "기준금리": [],
        "환율": []
    }

    for table in searchable_tables:
        table_name = table.get("STAT_NAME", "")
        table_code = table.get("STAT_CODE", "")

        if not table_code:
            continue

        for category, keywords in targets.items():
            if not any(word in table_name for word in keywords):
                continue

            print("통계표 발견:", table_name)

            selected_tables[category].append({
                "stat_code": table_code,
                "stat_name": table_name,
                "cycle": table.get("CYCLE", "")
            })

            try:
                items = ecos_request(
                    "StatisticItemList",
                    1,
                    1000,
                    table_code
                )

                print("세부 항목 수:", len(items))

                for item in items:
                    selected_items[category].append({
                        "stat_code": table_code,
                        "stat_name": table_name,
                        "cycle": item.get("CYCLE", ""),
                        "item_code": item.get("ITEM_CODE", ""),
                        "item_name": item.get("ITEM_NAME", ""),
                        "p_item_code": item.get("P_ITEM_CODE", ""),
                        "p_item_name": item.get("P_ITEM_NAME", ""),
                        "grp_name": item.get("GRP_NAME", ""),
                        "unit_name": item.get("UNIT_NAME", ""),
                        "start_time": item.get("START_TIME", ""),
                        "end_time": item.get("END_TIME", ""),
                        "data_cnt": item.get("DATA_CNT", 0)
                    })

            except EcosNoData:
                print("세부 항목 없음. 건너뜁니다.")
                continue

    # 실제 숫자 조회
    observations = {
        "기준금리": [],
        "환율": []
    }

    for category in ["기준금리", "환율"]:
        candidate = find_candidate(
            selected_items[category],
            category
        )

        if not candidate:
            print(category, "조회 후보를 찾지 못했습니다.")
            continue

        try:
            observations[category] = fetch_observations(
                candidate,
                category
            )

        except EcosNoData:
            print(category, "실제 데이터가 아직 없습니다.")

    output = {
        "updated_at": datetime.now(KST).isoformat(),
        "source": "한국은행 ECOS",
        "tables": selected_tables,
        "items": selected_items,
        "observations": observations
    }

    os.makedirs("data", exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print()
    print("수집 작업 완료")
    print("기준금리 실제 데이터:", len(observations["기준금리"]))
    print("환율 실제 데이터:", len(observations["환율"]))
    print("저장 위치:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
