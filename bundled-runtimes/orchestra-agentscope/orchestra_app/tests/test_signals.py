from orchestra_app.signals import extract_vote_signal


def test_extracts_conditional_vote_before_positive_keyword() -> None:
    signal = extract_vote_signal("【置信度】中\n【投票】有条件赞成")

    assert signal == {
        "stance": "cautious",
        "vote": "有条件赞成",
        "confidence": "medium",
        "source": "report",
    }


def test_extracts_bearish_and_abstain_votes() -> None:
    assert extract_vote_signal("【投票】反对") == {
        "stance": "bearish",
        "vote": "反对",
        "source": "report",
    }
    assert extract_vote_signal("【投票】弃权") == {
        "stance": "abstain",
        "vote": "弃权",
        "source": "report",
    }


def test_ignores_reports_without_an_explicit_vote() -> None:
    assert extract_vote_signal("【核心观点】继续观察") is None
