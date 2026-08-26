import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError


URL = os.environ.get(
    "RESEARCH_REPORTS_SEARCH_URL",
    "http://127.0.0.1:8005/api/research-reports/search/similar",
)


def main() -> int:
    body = json.dumps({"content": "value investing manager", "top_k": 3}).encode("utf-8")
    request = urllib.request.Request(
        URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Expected {URL} to return 200, got {exc.code}")
        return 1
    except URLError as exc:
        print(f"Request failed for {URL}: {exc}")
        return 1

    if status != 200:
        print(f"Expected {URL} to return 200, got {status}")
        return 1

    if payload.get("query") != "value investing manager" or not isinstance(payload.get("results"), list):
        print(f"Expected semantic search payload with query/results, got: {payload}")
        return 1

    print(f"OK semantic search {URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
