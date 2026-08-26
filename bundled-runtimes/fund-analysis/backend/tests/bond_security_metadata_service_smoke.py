from services.bond_security_metadata_service import BondSecurityMetadataService


chinamoney = BondSecurityMetadataService.parse_chinamoney(
    {
        "bondDefinedCode": "ficefgj9hn",
        "bondCode": "232580009",
        "bondType": "二级资本工具",
        "entyFullName": "中信银行股份有限公司",
        "debtRtng": "---",
    },
    {
        "entyFullName": "中信银行股份有限公司",
        "bondType": "二级资本工具",
        "mrtyDate": "2035-05-19",
        "parCouponRate": "1.9900",
        "creditRateEntyList": [{"creditSubjectRating": "AAA/AAA"}],
    },
)

assert chinamoney["issuer"] == "中信银行股份有限公司"
assert chinamoney["credit_rating"] == "AAA"
assert chinamoney["rating_type"] == "issuer_subject"
assert chinamoney["maturity_date"] == "2035-05-19"
assert chinamoney["coupon_rate"] == 0.0199

eastmoney = BondSecurityMetadataService.parse_eastmoney({
    "SECURITY_CODE": "113042",
    "CORRE_SECURITY_NAME": "上海银行",
    "RATING": "AAA",
    "RESIDUAL_YEAR": "2027-01-25 00:00:00",
})

assert eastmoney["issuer"] == "上海银行"
assert eastmoney["security_bond_type"] == "可转换公司债券"
assert eastmoney["rating_type"] == "bond"
assert eastmoney["maturity_date"] == "2027-01-25"

print("OK bond security metadata keeps bond rating and issuer rating semantics separate")
