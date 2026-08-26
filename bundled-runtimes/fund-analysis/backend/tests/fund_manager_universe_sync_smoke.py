import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.sync_fund_manager_universe import build_manager_records


def main() -> int:
    records = build_manager_records(
        [{
            "manager_id": "测试经理|M|硕士",
            "name": "测试经理",
            "gender": "M",
            "edu": "硕士",
            "company": "",
            "funds": [
                {
                    "wind_code": "000001.OF",
                    "fund_name": "000001.OF",
                    "start_date": "20200102",
                    "end_date": "",
                    "company": "错误的托管人",
                },
                {
                    "wind_code": "000002.OF",
                    "fund_name": "测试基金B",
                    "start_date": "20180101",
                    "end_date": "20191231",
                },
                {
                    "wind_code": "999999.OF",
                    "fund_name": "本地不存在",
                    "start_date": "20200101",
                    "end_date": "",
                },
            ],
        }],
        {
            "000001.OF": {"name": "测试基金A", "company": "测试基金管理有限公司"},
            "000002.OF": {"name": "测试基金B", "company": "测试基金管理有限公司"},
        },
    )
    if len(records) != 1:
        raise AssertionError(records)
    manager = records[0]
    if manager["company"] != "测试基金管理有限公司":
        raise AssertionError(f"基金公司必须来自管理人字段或本地基金档案，不能使用托管人：{manager}")
    if manager["current_funds"] != ["000001.OF"]:
        raise AssertionError(f"现任基金关系错误：{manager}")
    if manager["tenures"][1]["fund_name"] != "测试基金A":
        raise AssertionError(f"基金名称必须优先使用本地基金档案：{manager}")
    if len(manager["tenures"]) != 2 or manager["tenures"][0]["start_date"] != "2018-01-01":
        raise AssertionError(f"完整任职关系未正确标准化：{manager}")
    if any(item["fund_code"] == "999999.OF" for item in manager["tenures"]):
        raise AssertionError(f"本地基金库不存在的代码不得写入外键表：{manager}")
    print("OK manager universe sync preserves authoritative companies and complete local tenures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
