from datetime import datetime


def test_extract_meeting_number_digits_only():
    from app.services.invitations_report import _extract_meeting_number

    assert _extract_meeting_number("#腾讯会议：481-243-881") == "481243881"
    assert _extract_meeting_number("会议号: 123 456 789") == "123456789"


def test_parse_event_time_common_formats():
    from app.services.invitations_report import _parse_event_time_from_text

    anchor = datetime(2025, 9, 1, 9, 0)

    dt = _parse_event_time_from_text("时间：9.18 周四 10:30", anchor)
    assert dt == datetime(2025, 9, 18, 10, 30)

    # Weird spacing + single-digit minute; also apply PM heuristic for 1-7 o'clock.
    dt = _parse_event_time_from_text("时间：9.22 周一 1 :3", anchor)
    assert dt == datetime(2025, 9, 22, 13, 30)


def test_split_invite_segments_keycap_digits():
    from app.services.invitations_report import _split_invite_segments

    key1 = "1\ufe0f\u20e3"
    key2 = "2\ufe0f\u20e3"

    msg = (
        f"{key1}【商业航天】\n时间：9.18 10:30\n#腾讯会议：481-243-881\n\n"
        f"{key2}【算力产业】\n时间：9.18 14:00\n腾讯会议：123-456-789"
    )

    segs = _split_invite_segments(msg)
    assert len(segs) == 2
    assert segs[0].startswith("【商业航天】")
    assert segs[1].startswith("【算力产业】")

