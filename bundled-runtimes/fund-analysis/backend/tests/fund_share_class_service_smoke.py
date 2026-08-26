import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_share_class_service import FundShareClassService


class FakeClassificationRepo:
    def list_entity_share_classes(self, _wind_code):
        return [
            {
                "entity_id": "entity-1",
                "canonical_code": "000001.OF",
                "canonical_name": "示例基金",
                "wind_code": "000001.OF",
                "name": "示例基金A",
                "share_class": "A",
                "is_primary": True,
                "raw_data": {"universe": {"management_fee": 0.8, "custodian_fee": 0.1}},
            },
            {
                "entity_id": "entity-1",
                "canonical_code": "000001.OF",
                "canonical_name": "示例基金",
                "wind_code": "000002.OF",
                "name": "示例基金C",
                "share_class": "C",
                "raw_data": {
                    "product_profile": {
                        "status": "available",
                        "fees": {
                            "management_fee_rate": "0.80%",
                            "custodian_fee_rate": "0.10%",
                            "sales_service_fee_rate": "0.40%",
                        },
                    }
                },
            },
        ]


class FakeFundRepo:
    def get_fund(self, _wind_code):
        return {"wind_code": "000001.OF"}


def main():
    result = FundShareClassService(FakeClassificationRepo(), FakeFundRepo()).get("000001.OF")
    assert result["status"] == "available"
    assert result["share_count"] == 2
    assert abs(result["shares"][0]["known_core_fee_rate"] - 0.009) < 1e-10
    assert result["shares"][0]["sales_service_fee_rate"] is None
    assert abs(result["shares"][1]["sales_service_fee_rate"] - 0.004) < 1e-10
    assert result["fee_evidence"]["status"] == "partial"
    print("fund share class service smoke passed")


if __name__ == "__main__":
    main()
