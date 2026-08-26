import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.hang_seng_index_service import HangSengIndexService


def main():
    snapshot = HangSengIndexService.build_factsheet_snapshot(
        """
        Hang Seng Index
        March 2026
        0700 KYG875721634 TENCENT Information Technology Other HK-listed Mainland Co. 8.10
        1109 KYG2108Y1052 CHINA RES LAND Properties & Construction Red Chip 1.25
        """,
        "https://www.hsi.com.hk/official-history/hsie-202603.pdf",
    )

    assert snapshot["status"] == "available", snapshot
    assert snapshot["as_of_date"] == "2026-03-31", snapshot
    assert snapshot["published_weight"] == 0.0935, snapshot
    assert snapshot["constituents"][0]["constituent_code"] == "00700.HK", snapshot
    assert snapshot["constituents"][0]["industry"] == "信息技术", snapshot
    assert snapshot["source_urls"] == [
        "https://www.hsi.com.hk/official-history/hsie-202603.pdf"
    ], snapshot
    print("OK historical official HSI factsheets produce point-in-time Brinson snapshots")


if __name__ == "__main__":
    main()
