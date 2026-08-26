import json
import sys
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


URL = "http://127.0.0.1:8005/api/research-reports/"


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
    if "data" not in payload or not isinstance(payload["data"], list):
        print(f"Expected response to include a list field 'data', got: {payload}")
        return 1

    print(f"OK {status} {URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
