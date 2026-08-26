from instock.core.industry_taxonomy import (
    SW_2021_L1_INDUSTRIES,
    SW_2021_L2_DIRECTORY,
    SW_2021_L2_INDEX_CODES,
    UNCLASSIFIED_INDUSTRY,
    normalize_industry_name,
    resolve_sw_l1_industry,
    resolve_sw_l2_industry,
)


def test_normalizes_common_level_suffixes():
    assert normalize_industry_name(" 电子化学品Ⅱ ") == "电子化学品"
    assert normalize_industry_name("IT服务II") == "IT服务"


def test_resolves_desk_industries_to_sw_2021_level_one():
    assert len(SW_2021_L1_INDUSTRIES) == 31
    cases = {
        "半导体": "电子",
        "电子化学品Ⅱ": "电子",
        "电池": "电力设备",
        "通用设备": "机械设备",
        "证券": "非银金融",
        "银行": "银行",
        "医疗服务": "医药生物",
        "房地产开发": "房地产",
        "基础建设": "建筑装饰",
        "航空装备": "国防军工",
        "炼化及贸易": "石油石化",
    }
    assert {name: resolve_sw_l1_industry(name) for name in cases} == cases


def test_unknown_industry_is_not_guessed():
    assert resolve_sw_l1_industry("未来产业") == UNCLASSIFIED_INDUSTRY


def test_sw_2021_level_two_directory_matches_tushare_reference():
    assert len(SW_2021_L2_DIRECTORY) == 134
    assert SW_2021_L2_INDEX_CODES["半导体"] == "801081.SI"
    assert SW_2021_L2_INDEX_CODES["证券Ⅱ"] == "801193.SI"
    assert resolve_sw_l2_industry("半导体", "电子") == "半导体"
    assert resolve_sw_l2_industry("证券", "非银金融") == "证券Ⅱ"


def test_broad_bank_label_is_not_promoted_to_fake_level_two():
    assert resolve_sw_l1_industry("银行Ⅱ") == "银行"
    assert resolve_sw_l2_industry("银行Ⅱ", "银行") == ""
