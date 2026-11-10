
import json
import os
import urllib.request
import urllib.error
from urllib.parse import quote
from datetime import datetime, timezone, timedelta


API_KEY = os.environ.get("ECOS_API_KEY")

BASE_URL = "https://ecos.bok.or.kr/api"

KST = timezone(timedelta(hours=9))

OUTPUT_FILE = "data/economy_catalog.json"


class EcosNoData(Exception):
    pass


def ecos_request(service, start, end, stat_code=None):
    """ECOS API 요청"""

    if not API_KEY:
        raise RuntimeError("ECOS_API_KEY 환경변수를 찾을 수 없습니다.")

    url = (
        f"{BASE_URL}/{service}/{quote(API_KEY, safe='')}"
        f"/json/kr/{start}/{end}"
    )

    if stat_code:
        url += f"/{quote(str(stat_code), safe='')}"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DailyEconomicBoard/1.0"}
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"ECOS HTTP 오류: {error.code}"
        )

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"ECOS 연결 오류: {error.reason}"
        )

    # ECOS 오류 응답 확인
    result_info = result.get("RESULT", {})

    if result_info:
        code = result_info.get("CODE", "")
        message = result_info.get("MESSAGE", "")

        if code == "INFO-200":
            raise EcosNoData(message)

        if code and code != "INFO-000":
            raise RuntimeError(
                f"ECOS 오류 {code}: {message}"
            )

    # 서비스별 데이터 추출
    service_data = result.get(service, {})

    if not service_data:
        return []

    rows = service_data.get("row", [])

    if isinstance(rows, dict):
        rows = [rows]

    return rows or []


def main():

    print("ECOS 통계 목록을 확인합니다.")

    # 전체 통계표 목록
    tables = ecos_request(
        "StatisticTableList",
        1,
        1000
    )

    print("통계표 수:", len(tables))

    # 실제 검색 가능한 통계표만 선택
    searchable_tables = [
        table for table in tables
        if str(table.get("SRCH_YN", "")).upper() == "Y"
    ]

    print(
        "검색 가능한 통계표 수:",
        len(searchable_tables)
    )

    # 기준금리 및 환율 관련 통계표 검색
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

            if not any(
                keyword in table_name
                for keyword in keywords
            ):
                continue

            print()
            print("통계표 발견:", table_name)
            print("통계표 코드:", table_code)

            selected_tables[category].append({
                "stat_code": table_code,
                "stat_name": table_name,
                "cycle": table.get("CYCLE", "")
            })

            print("세부 항목을 확인합니다:", table_name)

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
                        "unit_name": item.get("UNIT_NAME", ""),
                        "start_time": item.get("START_TIME", ""),
                        "end_time": item.get("END_TIME", "")
                    })

            except EcosNoData:
                print(
                    "세부 항목 없음. 다음 통계표로 넘어갑니다."
                )
                continue

    # 결과 저장
    output = {
        "updated_at": datetime.now(KST).isoformat(),
        "source": "한국은행 ECOS",
        "tables": selected_tables,
        "items": selected_items
    }

    os.makedirs("data", exist_ok=True)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("수집 작업 완료")
    print(
        "기준금리 통계표:",
        len(selected_tables["기준금리"])
    )
    print(
        "환율 통계표:",
        len(selected_tables["환율"])
    )
    print(
        "기준금리 세부 항목:",
        len(selected_items["기준금리"])
    )
    print(
        "환율 세부 항목:",
        len(selected_items["환율"])
    )
    print("저장 위치:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
