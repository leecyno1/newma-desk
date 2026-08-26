import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.tushare_service import TushareDataService


class EmptyFrame:
    empty = True


class Pro:
    def __init__(self):
        self.calls = []

    def fund_portfolio(self, **kwargs):
        self.calls.append(kwargs)
        return EmptyFrame()


def main():
    service = object.__new__(TushareDataService)
    service.mock_mode = False
    service.strict_no_mock = True
    service._pro = Pro()
    result = service.get_fund_holdings("007379.OF", "2026Q1")
    if result:
        raise AssertionError(result)
    if not service.pro.calls or any(call.get("ts_code") != "007379.OF" for call in service.pro.calls):
        raise AssertionError(f"Every holdings query must remain scoped to the requested fund: {service.pro.calls}")
    print("OK Tushare holding fallbacks never query another fund's portfolio")


if __name__ == "__main__":
    main()
