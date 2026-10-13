import atexit
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_engine, init_database
from repositories.fund_dividends_repo import FundDividendsRepo
from services.tushare_service import TushareDataService
from smoke_cleanup import cleanup_fund_codes

WIND_CODE = "DIV.TEST.001"


class FakeProWithDividends:
    def fund_div(self, **kwargs):
        rows = [
            {
                "ts_code": "000001.OF",
                "ann_date": "20260120",
                "imp_anndate": "20260120",
                "base_date": "20251231",
                "div_proc": "实施",
                "record_date": "20260310",
                "ex_date": "20260311",
                "pay_date": "20260313",
                "earpay_date": None,
                "net_ex_date": "20260311",
                "div_cash": 0.05,
                "base_unit": 1000000.0,
                "ear_distr": None,
                "ear_amount": 500000.0,
                "account_date": "20260313",
                "base_year": "20251231",
            },
            {
                "ts_code": "000001.OF",
                "ann_date": "20250115",
                "imp_anndate": "20250115",
                "base_date": "20241231",
                "div_proc": "实施",
                "record_date": "20250310",
                "ex_date": "20250311",
                "pay_date": "20250313",
                "earpay_date": None,
                "net_ex_date": "20250311",
                "div_cash": 0.04,
                "base_unit": 900000.0,
                "ear_distr": None,
                "ear_amount": 360000.0,
                "account_date": "20250313",
                "base_year": "20241231",
            },
        ]
        # 数据源会对同一分红事件返回完全重复的行（修订公告），服务层必须去重
        rows.append(dict(rows[0]))
        return pd.DataFrame(rows)


def _build_service(fake_pro) -> TushareDataService:
    service = TushareDataService(token="test", mock_mode=True)
    service.mock_mode = False
    service._pro = fake_pro
    return service


def _insert_fake_fund():
    from sqlalchemy import text

    with get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO funds (wind_code, name) VALUES (:code, :name) "
            "ON CONFLICT (wind_code) DO NOTHING"
        ), {"code": WIND_CODE, "name": "分红链路测试基金"})


def main() -> int:
    # 1. 服务层解析：fund_div DataFrame → 标准化行
    service = _build_service(FakeProWithDividends())
    rows = service.get_fund_dividends("000001.OF")
    if len(rows) != 2:
        raise AssertionError(f"expected 2 dividend rows, got {rows}")
    first = rows[0]
    for key in ("ann_date", "record_date", "ex_date", "pay_date", "div_cash", "ear_amount"):
        if key not in first:
            raise AssertionError(f"dividend row missing {key}: {first}")
    if first["ex_date"] != "2026-03-11" or abs(float(first["div_cash"]) - 0.05) > 1e-9:
        raise AssertionError(f"dividend row normalization wrong: {first}")

    # 2. Repo 持久化：replace 语义 + 日期/金额序列化
    init_database()
    cleanup_fund_codes([WIND_CODE])
    atexit.register(cleanup_fund_codes, [WIND_CODE])
    _insert_fake_fund()

    repo = FundDividendsRepo()
    if repo.replace_fund_dividends(WIND_CODE, rows) != 2:
        raise AssertionError("replace_fund_dividends should report 2 inserted rows")
    stored = repo.list_fund_dividends(WIND_CODE)
    if len(stored) != 2:
        raise AssertionError(f"expected 2 stored rows, got {stored}")
    if stored[0]["ex_date"] != "2026-03-11":
        raise AssertionError(f"expected ex_date desc ordering, got {stored[0]}")
    if abs(float(stored[0]["div_cash"]) - 0.05) > 1e-9:
        raise AssertionError(f"div_cash must round-trip: {stored[0]}")

    # 3. replace 幂等：替换为单行后旧行消失
    if repo.replace_fund_dividends(WIND_CODE, rows[:1]) != 1:
        raise AssertionError("second replace should report 1 inserted row")
    stored = repo.list_fund_dividends(WIND_CODE)
    if len(stored) != 1 or stored[0]["ex_date"] != "2026-03-11":
        raise AssertionError(f"replace semantics broken: {stored}")

    print("OK fund dividends service + repo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
