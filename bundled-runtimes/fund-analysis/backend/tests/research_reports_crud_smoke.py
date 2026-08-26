import json
import os
import sys
import urllib.parse
import urllib.request
import uuid
from urllib.error import HTTPError, URLError


BASE_URL = os.environ.get("RESEARCH_REPORTS_BASE_URL", "http://127.0.0.1:8005/api/research-reports")


def request_json(url: str, method: str = "GET", payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    unique = uuid.uuid4().hex[:8]
    manager_id = f"smoke-manager-{unique}"
    title = f"Smoke Report {unique}"

    create_params = {
        "manager_id": manager_id,
        "title": title,
        "report_date": "2026-05-02",
        "source": "smoke",
        "content": f"smoke content {unique}",
        "summary": "initial summary",
    }

    try:
        create_status, created = request_json(f"{BASE_URL}/", method="POST", payload=create_params)
        report_id = created.get("id")
        if create_status != 200 or not report_id:
            print(f"Expected report create to succeed, got: status={create_status}, body={created}")
            return 1

        list_status, listing = request_json(
            f"{BASE_URL}/?{urllib.parse.urlencode({'manager_id': manager_id})}"
        )
        if list_status != 200:
            print(f"Expected filtered list to return 200, got: {list_status}")
            return 1
        if not any(item.get("id") == report_id for item in listing.get("data", [])):
            print(f"Expected created report {report_id} in list result, got: {listing}")
            return 1

        detail_status, detail = request_json(f"{BASE_URL}/{report_id}")
        if detail_status != 200 or detail.get("title") != title:
            print(f"Expected detail to return created title, got: status={detail_status}, body={detail}")
            return 1

        update_status, updated = request_json(
            f"{BASE_URL}/{report_id}?{urllib.parse.urlencode({'summary': 'updated summary'})}",
            method="PUT",
        )
        if update_status != 200 or updated.get("status") != "updated":
            print(f"Expected update to succeed, got: status={update_status}, body={updated}")
            return 1

        _, detail_after = request_json(f"{BASE_URL}/{report_id}")
        if detail_after.get("summary") != "updated summary":
            print(f"Expected updated summary, got: {detail_after}")
            return 1

        delete_status, deleted = request_json(f"{BASE_URL}/{report_id}", method="DELETE")
        if delete_status != 200 or deleted.get("status") != "deleted":
            print(f"Expected delete to succeed, got: status={delete_status}, body={deleted}")
            return 1

        try:
            request_json(f"{BASE_URL}/{report_id}")
        except HTTPError as exc:
            if exc.code != 404:
                print(f"Expected deleted report lookup to return 404, got: {exc.code}")
                return 1
        else:
            print("Expected deleted report lookup to return 404")
            return 1

    except HTTPError as exc:
        print(f"Unexpected HTTP error for {BASE_URL}: {exc.code}")
        return 1
    except URLError as exc:
        print(f"Request failed for {BASE_URL}: {exc}")
        return 1

    print(f"OK CRUD {BASE_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
