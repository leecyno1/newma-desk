import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def packaging(title: str, tid: int | None = None):
    rows = {}
    for channel in ("xiaohongshu_video", "douyin_video", "bilibili_video", "wechat_channels_video"):
        platform_notes = {"tid": tid} if channel == "bilibili_video" and tid else {}
        rows[channel] = {
            "title": title,
            "description": "三组数字重新判断科技拥挤度。不构成投资建议。",
            "tags": ["科技", "TMT", "半导体", "A股"],
            "platform_notes": platform_notes,
        }
    return rows


def test_account_registry_has_two_cross_platform_logical_accounts():
    registry = json.loads((ROOT / "configs/publish/account_registry.json").read_text(encoding="utf-8"))
    assert registry["logical_accounts"]["publisher-a"]["routes"]["xiaohongshu_video"] == "slot-1"
    assert registry["logical_accounts"]["publisher-b"]["routes"]["wechat_channels_video"] == "slot-2"
    assert registry["channels"]["bilibili_video"]["slots"]["slot-2"]["browser_profile"] == "bilibili_video_2"


def test_build_matrix_routes_two_variants_to_eight_independent_tasks(tmp_path):
    module = load_module("build_publish_campaign_test", ROOT / "scripts/build_publish_campaign.py")
    video_a = tmp_path / "a.mp4"
    video_b = tmp_path / "b.mp4"
    video_a.write_bytes(b"video-a")
    video_b.write_bytes(b"video-b")
    cover = tmp_path / "cover.jpg"
    Image.new("RGB", (1080, 1080), "#062124").save(cover)
    spec_path = tmp_path / "campaign_spec.json"
    spec = {
        "run_id": "run-publish-campaign-test",
        "topic_id": "tech-crowding",
        "title": "科技可能已经不拥挤了",
        "variants": [
            {
                "variant_id": "new",
                "logical_account": "publisher-a",
                "video": str(video_a),
                "cover_source": str(cover),
                "packaging": packaging("科技可能不拥挤了", tid=188),
            },
            {
                "variant_id": "previous",
                "logical_account": "publisher-b",
                "video": str(video_b),
                "cover_source": str(cover),
                "packaging": packaging("TMT持仓已降到42%", tid=188),
            },
        ],
    }
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    registry = json.loads((ROOT / "configs/publish/account_registry.json").read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "configs/publish/platform_content_rules.json").read_text(encoding="utf-8"))

    matrix, index = module.build_matrix(
        spec,
        spec_path=spec_path,
        output_dir=tmp_path / "out",
        registry=registry,
        rules=rules,
    )

    assert len(matrix["items"]) == 2
    assert sum(len(item["targets"]) for item in matrix["items"]) == 8
    assert len(index) == 8
    assert {target["account_slots"][0] for target in matrix["items"][0]["targets"]} == {"slot-1"}
    assert {target["account_slots"][0] for target in matrix["items"][1]["targets"]} == {"slot-2"}
    assert all(Path(row["cover"]).exists() for row in index)


def test_douyin_declaration_is_explicit_and_activity_is_not_invented(tmp_path):
    module = load_module("build_publish_campaign_declaration_test", ROOT / "scripts/build_publish_campaign.py")
    video = tmp_path / "a.mp4"
    video.write_bytes(b"video")
    cover = tmp_path / "cover.jpg"
    Image.new("RGB", (1080, 1080), "black").save(cover)
    rows = packaging("科技可能不拥挤了", tid=188)
    rows["douyin_video"]["declaration"] = "内容由本人原创"
    spec = {
        "run_id": "run-explicit-declaration",
        "topic_id": "tech-crowding",
        "title": "科技可能已经不拥挤了",
        "variants": [
            {
                "variant_id": "new",
                "logical_account": "publisher-a",
                "video": str(video),
                "cover_source": str(cover),
                "packaging": rows,
            }
        ],
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    registry = json.loads((ROOT / "configs/publish/account_registry.json").read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "configs/publish/platform_content_rules.json").read_text(encoding="utf-8"))

    matrix, _ = module.build_matrix(spec, spec_path=spec_path, output_dir=tmp_path / "out", registry=registry, rules=rules)
    douyin = next(target for target in matrix["items"][0]["targets"] if target["channel"] == "douyin_video")
    notes = douyin["publish_metadata"]["platform_notes"]
    assert notes["declaration"] == "内容由本人原创"
    assert notes["activity_candidates"] == []
    assert notes["activity_status"] == "live_discovery_required"


def test_portrait_cover_preserves_complete_square_source(tmp_path):
    module = load_module("build_publish_campaign_cover_test", ROOT / "scripts/build_publish_campaign.py")
    source = tmp_path / "source.jpg"
    image = Image.new("RGB", (1080, 1080), "#101010")
    for y, color in ((0, (255, 0, 0)), (1079, (0, 255, 0))):
        for x in range(1080):
            image.putpixel((x, y), color)
    image.save(source)
    output = tmp_path / "cover.jpg"

    module.render_cover(
        source=source,
        output=output,
        width=1080,
        height=1440,
        title=["完整图表", "禁止裁断"],
        kicker="发布封面",
        subtitle="完整保留原始方形构图",
        account_label="发布账号 A",
        accent="#ff6b6b",
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1080, 1440)


def test_account_auth_status_prefers_primary_social_uploader():
    module = load_module("build_publish_campaign_auth_test", ROOT / "scripts/build_publish_campaign.py")
    report = {
        "accounts": [
            {
                "channel": "douyin_video",
                "slot": "slot-1",
                "status": "state_present_unverified",
                "auth": [
                    {"mode": "browser_profile", "status": "state_present_unverified"},
                    {"mode": "social_auto_upload", "status": "invalid"},
                ],
            }
        ]
    }
    index = module.account_auth_index(report)
    assert module.primary_account_auth_status(index, channel="douyin_video", account_slot="slot-1") == "invalid"


def test_campaign_confirm_execute_blocks_until_account_auth_is_valid(tmp_path):
    module = load_module("execute_publish_campaign_auth_test", ROOT / "scripts/execute_publish_campaign.py")
    campaign_path = tmp_path / "publish_campaign.json"
    campaign_path.write_text(
        json.dumps(
            {
                "tasks": [{"task_id": "task-1"}],
                "summary": {"account_auth_status": "not_checked"},
            }
        ),
        encoding="utf-8",
    )

    report = module.execute_campaign(campaign_path, confirm_execute=True)

    assert report["status"] == "blocked_account_auth_not_valid"
    assert report["will_not_publish"] is True
    assert report["summary"]["processed_task_count"] == 0


def test_publish_console_plan_uses_external_secure_data_directory():
    module = load_module("start_publish_console_test", ROOT / "scripts/start_publish_console.py")

    plan = module.console_plan()

    assert "NewmaPublishSessions/qianfan-sync" in plan["data_dir"]
    assert plan["will_not_publish"] is True
    assert plan["cookie_contents_read"] is False
    assert plan["missing_dependencies"] == []
    assert plan["browser_window"]["never_maximize"] is True
    assert plan["browser_window"]["width"] <= 1180
    assert plan["browser_window"]["height"] <= 780


def test_campaign_dry_run_counts_ready_tasks(tmp_path, monkeypatch):
    module = load_module("execute_publish_campaign_ready_test", ROOT / "scripts/execute_publish_campaign.py")
    execution_request = tmp_path / "execution_request.json"
    execution_request.write_text("{}", encoding="utf-8")
    campaign_path = tmp_path / "publish_campaign.json"
    campaign_path.write_text(
        json.dumps(
            {
                "tasks": [{"task_id": "task-1", "execution_request": str(execution_request)}],
                "summary": {"account_auth_status": "not_checked"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "run_task",
        lambda _request, confirm_execute: {"status": "ready_for_user_confirmation", "will_not_publish": True},
    )

    report = module.execute_campaign(campaign_path, confirm_execute=False)

    assert report["summary"]["ready_count"] == 1
    assert report["summary"]["blocked_or_failed_count"] == 0
