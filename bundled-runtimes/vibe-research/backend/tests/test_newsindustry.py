from newsindustry import classify_news_industry


def assigned(title, fallback, summary="", translated_title=""):
    return classify_news_industry(title, summary, translated_title, fallback)[0]


def test_classifies_news_by_headline_instead_of_feed_source():
    assert assigned("Chinese automakers expand production in Europe", "semi") == "auto"
    assert assigned("杭州男子突发耳聋，医生提醒及时就医", "tech") == "bio"
    assert assigned("Tesla cuts vehicle production at German factory", "energy") == "auto"


def test_keeps_source_sector_without_a_stronger_content_signal():
    assert assigned("Trump Is Spending Billions On The Minerals That Power EVs", "energy") == "energy"
    assert assigned("Company publishes its quarterly operating update", "macro") == "macro"


def test_does_not_classify_from_machine_translated_title():
    assert assigned(
        "Trump closes a tax loophole in new spending bill",
        "macro",
        translated_title="特朗普关闭税收漏洞",
    ) == "macro"


def test_recognizes_security_and_consumer_product_headlines():
    assert assigned("US government warns of escalating cyberattacks", "consumer") == "security"
    assert assigned("Spyware vendor exposed in major data breach", "tech") == "security"
    assert assigned("Google Pixel 11 phone gets a new camera system", "ai") == "consumer"


def test_recognizes_ai_models_and_drug_development_from_general_feeds():
    assert assigned("Google already launches Gemini 3.7 Flash", "consumer") == "ai"
    assert assigned("Kyntra Bio plans roxadustat Phase III start in Q4", "macro") == "bio"
