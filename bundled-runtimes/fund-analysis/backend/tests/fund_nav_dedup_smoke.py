import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


URL = "http://127.0.0.1:8005/api/funds/510050.SH/nav?start_date=2026-01-01&end_date=2026-05-04"


def main() -> int:
    try:
        with urlopen(URL) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        print(f"Expected {URL} to return 200, got {exc.code}")
        return 1
    except URLError as exc:
        print(f"Request failed for {URL}: {exc}")
        return 1

    if status != 200:
        print(f"Expected {URL} to return 200, got {status}")
        return 1

    payload = json.loads(body)
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        print(f"Expected a non-empty nav series, got: {payload}")
        return 1

    dates = [item.get("date") for item in data]
    if len(dates) != len(set(dates)):
        print(f"Expected unique nav dates, got duplicates in: {dates}")
        return 1

    if dates != sorted(dates, reverse=True):
        print(f"Expected nav dates to stay in descending order, got: {dates[:5]} ... {dates[-5:]}")
        return 1

    print(f"OK {status} {URL} points={len(dates)} unique_dates={len(set(dates))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
