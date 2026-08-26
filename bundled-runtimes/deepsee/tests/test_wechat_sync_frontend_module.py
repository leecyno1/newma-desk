from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"
MODULE_JS = PROJECT_ROOT / "static" / "modules" / "wechat-sync.js"


def _read_index() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _wrapper_body(source: str, name: str) -> tuple[str, str, bool]:
    match = re.search(
        rf"(?P<async>async\s+)?function\s+{re.escape(name)}\s*"
        rf"\((?P<params>[^)]*)\)\s*\{{(?P<body>.*?)^\s{{8}}\}}",
        source,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"missing wrapper: {name}"
    body_without_comments = re.sub(r"//[^\n]*", "", match.group("body"))
    body = " ".join(body_without_comments.split())
    params = " ".join(match.group("params").split())
    return body, params, bool(match.group("async"))


def test_wechat_sync_module_file_exists() -> None:
    assert MODULE_JS.is_file(), "static/modules/wechat-sync.js must be extracted from index.html"


def test_wechat_sync_module_is_loaded_before_the_main_body_script() -> None:
    source = _read_index()
    include = '    <script src="/static/modules/wechat-sync.js"></script>'
    main_script = "    <script>\n        \n        // 全局状态变量"

    assert include in source
    assert source.index(include) < source.index(main_script)
    assert source[source.index(include) + len(include) : source.index(main_script)].strip() == ""


def test_index_keeps_only_compatibility_wrappers_for_wechat_sync() -> None:
    source = _read_index()
    assert "const WECHAT_TRACK_DEFS" not in source

    wrappers = {
        "normalizeWechatTrackPolicy": (
            "policy = {}",
            False,
            "return window.WechatSyncModule.normalizeTrackPolicy(policy);",
        ),
        "renderWechatTrackOrder": (
            "policy = {}",
            False,
            "return window.WechatSyncModule.renderTrackOrder(policy);",
        ),
        "collectWechatTrackPolicy": (
            "",
            False,
            "return window.WechatSyncModule.collectTrackPolicy();",
        ),
        "updateWechatTrackPolicySummary": (
            "",
            False,
            "return window.WechatSyncModule.updateTrackPolicySummary();",
        ),
        "moveWechatTrack": (
            "track, delta",
            False,
            "return window.WechatSyncModule.moveTrack(track, delta);",
        ),
        "moveWechatTrackBefore": (
            "fromTrack, toTrack",
            False,
            "return window.WechatSyncModule.moveTrackBefore(fromTrack, toTrack);",
        ),
        "renderWechatDualTrackState": (
            "data",
            False,
            "return window.WechatSyncModule.renderDualTrackState(data);",
        ),
        "loadWechatDualTrackState": (
            "silent = false",
            True,
            "return window.WechatSyncModule.loadDualTrackState(silent);",
        ),
        "saveWechatDualTrackPolicy": (
            "",
            True,
            "return window.WechatSyncModule.saveDualTrackPolicy();",
        ),
        "runWechatDualTrackSync": (
            "days",
            True,
            "return window.WechatSyncModule.runDualTrackSync(days);",
        ),
        "syncIncrementalAndReload": (
            "days = 7, pullOp = null",
            True,
            "return window.WechatSyncModule.syncIncrementalAndReload(days, pullOp);",
        ),
    }

    for name, (expected_params, expected_async, expected_body) in wrappers.items():
        body, params, is_async = _wrapper_body(source, name)
        assert params == expected_params, name
        assert is_async is expected_async, name
        assert body == expected_body, name

    pull_body, pull_params, pull_is_async = _wrapper_body(source, "pullFromChatlogDays")
    assert pull_params == "days, pullOp = null"
    assert pull_is_async is True
    assert pull_body == "return syncIncrementalAndReload(days, pullOp);"


def test_wechat_sync_module_has_valid_javascript_syntax() -> None:
    result = subprocess.run(
        ["node", "--check", str(MODULE_JS)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_wechat_sync_module_loads_without_dom_and_exports_frozen_api() -> None:
    smoke_test = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: process.argv[1] });
const api = sandbox.window.WechatSyncModule;
const methodNames = [
  'normalizeTrackPolicy',
  'renderTrackOrder',
  'collectTrackPolicy',
  'updateTrackPolicySummary',
  'moveTrack',
  'moveTrackBefore',
  'renderDualTrackState',
  'loadDualTrackState',
  'saveDualTrackPolicy',
  'runDualTrackSync',
  'syncIncrementalAndReload',
];
const normalized = api.normalizeTrackPolicy({ mode: 'chatlog_only' });
process.stdout.write(JSON.stringify({
  frozen: Object.isFrozen(api),
  methodNames,
  methodTypes: methodNames.map((name) => typeof api[name]),
  normalized,
}));
"""
    result = subprocess.run(
        ["node", "-e", smoke_test, str(MODULE_JS)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    output = json.loads(result.stdout)
    assert output["frozen"] is True
    assert output["methodTypes"] == ["function"] * len(output["methodNames"])
    assert output["normalized"] == {
        "order": ["chatlog", "wx_cli", "wechatapi"],
        "enabled": ["chatlog", "wx_cli"],
        "useMultiple": False,
    }
