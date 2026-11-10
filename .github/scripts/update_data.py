import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_KEY = os.environ.get("ECOS_API_KEY")

if not API_KEY:
    print("오류: ECOS_API_KEY Secret을 찾을 수 없습니다.")
    sys.exit(1)

BASE_URL = "https://ecos.bok.or.kr/api/"


def ecos_request(service, *parts):
    path = "/".join(
        [service, API_KEY, "json", "kr"] + [str(p) for p in parts]
    )
    request = Request(
        BASE_URL + path,
        headers={"User-Agent": "Daily-Econ-Board/1.0"}
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise RuntimeError("ECOS API 접속 또는 응답 처리에 실패했습니다.")

    service_data = result.get(service, {})
    if "RESULT" in result:
        raise RuntimeError("ECOS에서 오류 응답을 받았습니다.")

    if not isinstance(service_data, dict):
        raise RuntimeError("ECOS 응답 형식이 예상과 다릅니다.")

    return service_data.get("row", [])


def main():
    print("ECOS 통계 목록을 확인하고 있습니다.")

    tables = ecos_request("StatisticTableList", 1, 1000)

    candidates = []

    for table in tables:
        table_name = table.get("STAT_NAME", "")
        table_code = table.get("STAT_CODE", "")

        if not table_code:
            continue

        if "환율" in table_name or "기준금리" in table_name:
            print("관련 통계표 발견:", table_name)

            items = ecos_request(
                "StatisticItemList", 1, 1000, table_code
            )

            for item in items:
                item_name = item.get("ITEM_NAME", "")
                item_code = item.get("ITEM_CODE", "")

                if not item_code:
                    continue

                is_exchange = (
                    "환율" in table_name
                    and ("미국달러" in item_name or "미국 달러" in item_name)
                )

                is_rate = (
                    "기준금리" in table_name
                    and "기준금리" in item_name
                )

                if is_exchange or is_rate:
                    candidates.append({
                        "table_name": table_name,
                        "table_code": table_code,
                        "item_name": item_name,
                        "item_code": item_code,
                        "cycle": item.get("CYCLE", ""),
                        "start_time": item.get("START_TIME", ""),
                        "end_time": item.get("END_TIME", ""),
                        "unit": item.get("UNIT_NAME", "")
                    })

    output = {
        "source": "한국은행 ECOS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "candidates": candidates
    }

    output_path = Path("data/economy_catalog.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("통계 항목 확인 완료.")
    print("후보 항목 수:", len(candidates))
    print("결과 파일: data/economy_catalog.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("수집 중 오류가 발생했습니다. 인증키와 ECOS 응답을 확인해 주세요.")
        sys.exit(1)
