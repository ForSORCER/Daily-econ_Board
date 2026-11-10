import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_KEY = os.environ.get("ECOS_API_KEY")
BASE_URL = "https://ecos.bok.or.kr/api/"


class EcosError(Exception):
    pass


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

    except HTTPError as e:
        raise EcosError(f"HTTP 오류: {e.code}") from None
    except URLError:
        raise EcosError("ECOS 서버에 연결하지 못했습니다.") from None
    except Exception:
        raise EcosError("ECOS 응답을 읽지 못했습니다.") from None

    if "RESULT" in result:
        error = result["RESULT"]
        code = error.get("CODE", "알 수 없음")
        message = error.get("MESSAGE", "상세 메시지 없음")
        raise EcosError(f"ECOS 오류 {code}: {message}")

    service_data = result.get(service)

    if not isinstance(service_data, dict):
        raise EcosError(f"{service}: 예상하지 못한 응답 형식")

    return service_data.get("row", [])


def main():
    if not API_KEY:
        raise EcosError("ECOS_API_KEY Secret을 찾을 수 없습니다.")

    print("1. ECOS 통계 목록을 확인합니다.")

    tables = ecos_request("StatisticTableList", 1, 1000)
    print("통계표 수:", len(tables))

    candidates = []

    for table in tables:
        table_name = table.get("STAT_NAME", "")
        table_code = table.get("STAT_CODE", "")

        if not table_code:
            continue

        if "환율" in table_name or "기준금리" in table_name:
            print("통계표 발견:", table_name)

            print("세부 항목을 확인합니다:", table_name)

            items = ecos_request(
                "StatisticItemList", 1, 1000, table_code
            )

            print("세부 항목 수:", len(items))

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
    print("결과 파일:", str(output_path))


if __name__ == "__main__":
    try:
        main()
    except EcosError as e:
        print("ECOS 수집 오류:", str(e))
        sys.exit(1)
    except Exception as e:
        print("예상하지 못한 프로그램 오류:", type(e).__name__)
        sys.exit(1)
