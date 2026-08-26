import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError


STATUS_URL = os.environ.get(
    "RESEARCH_REPORTS_SEARCH_STATUS_URL",
    "http://127.0.0.1:8005/api/research-reports/search/status",
)
WARMUP_URL = os.environ.get(
    "RESEARCH_REPORTS_SEARCH_WARMUP_URL",
    "http://127.0.0.1:8005/api/research-reports/search/warmup",
)


def read_json(url: str, method: str = "GET"):
    data = b"{}" if method != "GET" else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        status_code, status_payload = read_json(STATUS_URL)
    except (HTTPError, URLError) as exc:
        print(f"Status request failed for {STATUS_URL}: {exc}")
        return 1

    if status_code != 200:
        print(f"Expected status endpoint to return 200, got {status_code}")
        return 1

    if "model_loaded" not in status_payload or "model_name" not in status_payload:
        print(f"Expected semantic search status payload, got: {status_payload}")
        return 1

    try:
        warmup_code, warmup_payload = read_json(WARMUP_URL, method="POST")
    except HTTPError as exc:
        print(f"Expected warmup endpoint to return 200, got {exc.code}")
        return 1
    except URLError as exc:
        print(f"Warmup request failed for {WARMUP_URL}: {exc}")
        return 1

    if warmup_code != 200:
        print(f"Expected warmup endpoint to return 200, got {warmup_code}")
        return 1

    if warmup_payload.get("status") != "ready" or warmup_payload.get("model_loaded") is not True:
        print(f"Expected ready warmup payload, got: {warmup_payload}")
        return 1

    if not warmup_payload.get("model_name") or not warmup_payload.get("vector_size"):
        print(f"Expected model metadata in warmup payload, got: {warmup_payload}")
        return 1

    print(f"OK semantic search warmup {WARMUP_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
