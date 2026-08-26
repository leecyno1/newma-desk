import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"


def _extract_function(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing function {name}")
    brace_start = source.find("{", start)
    if brace_start < 0:
        raise AssertionError(f"missing body for function {name}")
    depth = 0
    for idx in range(brace_start, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    raise AssertionError(f"unterminated function {name}")


def _extract_window_function(source: str, name: str) -> str:
    marker = f"window.{name} = function"
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing window function {name}")
    brace_start = source.find("{", start)
    if brace_start < 0:
        raise AssertionError(f"missing body for window function {name}")
    depth = 0
    end = -1
    for idx in range(brace_start, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    if end < 0:
        raise AssertionError(f"unterminated window function {name}")
    tail = source[end:]
    semi = tail.find(";")
    if semi < 0:
        raise AssertionError(f"missing terminator for window function {name}")
    return source[start : end + semi + 1]


def test_meeting_prefill_uses_v2_task_creation_not_legacy_send_management():
    source = INDEX_HTML.read_text(encoding="utf-8")
    block = _extract_function(source, "prefillMeetingAppointment")

    assert "createTasksFromTargets(" in block or "window.addToSendQueue(" in block
    assert "addToSendManagement(" not in block
    assert "updateSendManagementDisplay(" not in block
    assert "updateSendStats(" not in block


def test_add_to_send_queue_dedupes_same_unsent_quote_task():
    source = INDEX_HTML.read_text(encoding="utf-8")
    js = "\n\n".join(
        [
            "const tasks = [];",
            "const window = {};",
            "const localStorage = { setItem() {} };",
            "function uid(){ return 'task-' + (tasks.length + 1); }",
            "function nowIso(){ return '2026-04-17T10:00:00Z'; }",
            "function getWxid(){ return 'wxid_sender'; }",
            "function resolvePromptKeyForOperation(value){ return String(value || '答'); }",
            "function saveTasks() {}",
            "function renderTasks() {}",
            _extract_window_function(source, "addToSendQueue"),
            """
window.addToSendQueue({
  id: 101,
  db_id: 101,
  chat_id: 'wxid_test',
  talker_name: '张三',
  sender_name: '张三',
  operation_type: '约',
  content: '原始引用'
});
window.addToSendQueue({
  id: 101,
  db_id: 101,
  chat_id: 'wxid_test',
  talker_name: '张三',
  sender_name: '张三',
  operation_type: '约',
  content: '原始引用'
});
console.log(JSON.stringify(tasks));
            """.strip(),
        ]
    )
    proc = subprocess.run(
        ["node", "-e", js],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    tasks = json.loads(proc.stdout)

    assert len(tasks) == 1
    assert tasks[0]["operation"] == "约"
    assert tasks[0]["quote_message_id"] == 101
