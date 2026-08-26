from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import runpy
from types import ModuleType
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REDACTION_MARKER = "[REDACTED]"
SYNTHETIC_SECRET = "dummy-secret-value"
_CREDENTIAL_NAMES = {"TUSHARE_TOKEN", "TOKEN_FALLBACK"}
_SOURCE_ROOTS = (
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "cycle_forecast_system" / "cycle_forecast_system",
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "config",
)


def _production_python_files() -> list[Path]:
    return sorted(
        path
        for root in _SOURCE_ROOTS
        if root.exists()
        for path in root.rglob("*.py")
    )


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    return [node.target]


def _attribute_path(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        parent = _attribute_path(node.value)
        if parent is not None:
            return (*parent, node.attr)
    return None


def _call_arguments(
    call: ast.Call,
    *,
    position: int,
    keyword_name: str,
) -> list[ast.AST]:
    arguments = []
    if len(call.args) > position:
        arguments.append(call.args[position])
    arguments.extend(
        keyword.value
        for keyword in call.keywords
        if keyword.arg == keyword_name
    )
    return arguments


def _call_argument(
    call: ast.Call,
    *,
    position: int,
    keyword_name: str,
) -> ast.AST | None:
    arguments = _call_arguments(
        call,
        position=position,
        keyword_name=keyword_name,
    )
    return arguments[0] if arguments else None


def _credential_violations(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = _literal_string(node.value)
            if value:
                for target in _assignment_targets(node):
                    if (
                        isinstance(target, ast.Name)
                        and target.id in _CREDENTIAL_NAMES
                    ):
                        violations.append(
                            (node.lineno, f"non-empty {target.id} assignment")
                        )
        if not isinstance(node, ast.Call):
            continue
        call_path = _attribute_path(node.func)
        if call_path in {
            ("os", "getenv"),
            ("os", "environ", "get"),
            ("os", "environ", "setdefault"),
        }:
            name = _call_argument(
                node,
                position=0,
                keyword_name="key",
            )
            default = _call_argument(
                node,
                position=1,
                keyword_name="default",
            )
            if (
                _literal_string(name) == "TUSHARE_TOKEN"
                and _literal_string(default)
            ):
                violations.append(
                    (node.lineno, f"non-empty {'.'.join(call_path)} default")
                )
        if call_path in {
            ("ts", "set_token"),
            ("tushare", "set_token"),
            ("ts", "pro_api"),
            ("tushare", "pro_api"),
        }:
            token_arguments = _call_arguments(
                node,
                position=0,
                keyword_name="token",
            )
            if any(_literal_string(argument) for argument in token_arguments):
                violations.append(
                    (node.lineno, f"non-empty {'.'.join(call_path)} credential")
                )
    return violations


def _load_update_script() -> ModuleType:
    script_path = PROJECT_ROOT / "scripts" / "update_citic_l1_valuations.py"
    spec = importlib.util.spec_from_file_location(
        "_test_update_citic_l1_valuations",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load valuation update script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _redact(text: str) -> str:
    from seven_cycle_platform.security import redact_secrets

    return redact_secrets(text)


def test_production_code_has_no_non_empty_tushare_credentials() -> None:
    violations = [
        (path.relative_to(PROJECT_ROOT), line, kind)
        for path in _production_python_files()
        for line, kind in _credential_violations(path)
    ]
    rendered = ", ".join(
        f"{path}:{line} ({kind})" for path, line, kind in violations
    )

    assert not violations, f"prohibited credential constructs: {rendered}"


@pytest.mark.parametrize(
    "source",
    [
        f'TUSHARE_TOKEN = "{SYNTHETIC_SECRET}"',
        f'TOKEN_FALLBACK = "{SYNTHETIC_SECRET}"',
        f'os.getenv("TUSHARE_TOKEN", "{SYNTHETIC_SECRET}")',
        f'os.environ.get("TUSHARE_TOKEN", "{SYNTHETIC_SECRET}")',
        f'os.environ.setdefault("TUSHARE_TOKEN", "{SYNTHETIC_SECRET}")',
        f'ts.set_token("{SYNTHETIC_SECRET}")',
        f'tushare.set_token(token="{SYNTHETIC_SECRET}")',
        f'ts.pro_api("{SYNTHETIC_SECRET}")',
        f'tushare.pro_api(token="{SYNTHETIC_SECRET}")',
    ],
)
def test_credential_scanner_detects_literal_tushare_credentials(
    source: str,
    tmp_path: Path,
) -> None:
    snippet = tmp_path / "snippet.py"
    snippet.write_text(source, encoding="utf-8")

    violations = _credential_violations(snippet)

    assert len(violations) == 1
    assert violations[0][0] == 1


@pytest.mark.parametrize(
    "source",
    [
        'TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")',
        'TOKEN_FALLBACK = ""',
        'os.getenv("TUSHARE_TOKEN")',
        'os.getenv("TUSHARE_TOKEN", "")',
        'os.environ.get("TUSHARE_TOKEN")',
        'os.environ.get("TUSHARE_TOKEN", "")',
        'os.environ.setdefault("TUSHARE_TOKEN", "")',
        'ts.set_token(os.getenv("TUSHARE_TOKEN"))',
        'tushare.set_token(token=os.environ["TUSHARE_TOKEN"])',
        'ts.pro_api()',
        'ts.pro_api(os.getenv("TUSHARE_TOKEN"))',
        'tushare.pro_api(token=os.environ.get("TUSHARE_TOKEN"))',
    ],
)
def test_credential_scanner_allows_environment_only_forms(
    source: str,
    tmp_path: Path,
) -> None:
    snippet = tmp_path / "snippet.py"
    snippet.write_text(source, encoding="utf-8")

    assert _credential_violations(snippet) == []


def test_django_settings_reads_tushare_token_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = (
        PROJECT_ROOT
        / "cycle_forecast_system"
        / "cycle_forecast_system"
        / "settings.py"
    )
    monkeypatch.setenv("TUSHARE_TOKEN", SYNTHETIC_SECRET)

    settings = runpy.run_path(str(settings_path))

    assert settings["TUSHARE_TOKEN"] == SYNTHETIC_SECRET


@pytest.mark.parametrize("configured_value", [None, "   \t"])
def test_valuation_update_requires_token_before_external_work(
    configured_value: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_update_script()
    if configured_value is None:
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("TUSHARE_TOKEN", configured_value)

    def unexpected_external_work(*args: object, **kwargs: object) -> None:
        raise AssertionError("external work was reached")

    monkeypatch.setattr(module.ts, "set_token", unexpected_external_work)
    monkeypatch.setattr(module.ts, "pro_api", unexpected_external_work)
    monkeypatch.setattr(module.pd, "read_parquet", unexpected_external_work)

    with pytest.raises(RuntimeError, match=r"TUSHARE_TOKEN.*environment"):
        module.main()


def test_valuation_update_strips_token_before_tushare_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_update_script()
    captured: list[str] = []

    class StopAfterTokenSetup(Exception):
        pass

    monkeypatch.setenv("TUSHARE_TOKEN", f"  {SYNTHETIC_SECRET}\n")
    monkeypatch.setattr(module.ts, "set_token", captured.append)

    def stop_before_network() -> None:
        raise StopAfterTokenSetup

    monkeypatch.setattr(module.ts, "pro_api", stop_before_network)

    with pytest.raises(StopAfterTokenSetup):
        module.main()

    assert captured == [SYNTHETIC_SECRET]


@pytest.mark.parametrize(
    "key",
    [
        "token",
        "ACCESS_TOKEN",
        "auth_token",
        "api_key",
        "apikey",
        "x-api-key",
        "tushare_token",
        "secret",
        "client_secret",
        "password",
        "passwd",
    ],
)
def test_redacts_common_assignment_keys_case_insensitively(key: str) -> None:
    text = f"request failed: {key}={SYNTHETIC_SECRET}; retry=false"

    assert _redact(text) == (
        f"request failed: {key}={REDACTION_MARKER}; retry=false"
    )


def test_redacts_colon_and_dict_like_secret_values() -> None:
    colon_text = f"client_secret: {SYNTHETIC_SECRET}"
    mapping_text = (
        f'{{"api_key": "{SYNTHETIC_SECRET}", "status": "failed"}}'
    )

    assert _redact(colon_text) == f"client_secret: {REDACTION_MARKER}"
    assert _redact(mapping_text) == (
        f'{{"api_key": "{REDACTION_MARKER}", "status": "failed"}}'
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            f"Authorization: Bearer {SYNTHETIC_SECRET}",
            f"Authorization: Bearer {REDACTION_MARKER}",
        ),
        (
            f"authorization: Basic {SYNTHETIC_SECRET}",
            f"authorization: Basic {REDACTION_MARKER}",
        ),
        (
            f'{{"Authorization": "Bearer {SYNTHETIC_SECRET}", '
            '"status": 401}',
            f'{{"Authorization": "Bearer {REDACTION_MARKER}", '
            '"status": 401}',
        ),
        (
            f"{{'authorization': 'Basic {SYNTHETIC_SECRET}'}}",
            f"{{'authorization': 'Basic {REDACTION_MARKER}'}}",
        ),
    ],
)
def test_redacts_authorization_header_values(text: str, expected: str) -> None:
    assert _redact(text) == expected


def test_redacts_encoded_url_query_values_without_corrupting_url() -> None:
    text = (
        "https://example.test/data?ACCESS_TOKEN="
        "dummy%2Dsecret%2Dvalue&count=2&date=2026-07-12#summary"
    )

    assert _redact(text) == (
        "https://example.test/data?ACCESS_TOKEN=[REDACTED]"
        "&count=2&date=2026-07-12#summary"
    )


@pytest.mark.parametrize("punctuation", ["!", "?"])
def test_bare_secret_redaction_preserves_sentence_punctuation(
    punctuation: str,
) -> None:
    text = f"request failed: token={SYNTHETIC_SECRET}{punctuation}"

    assert _redact(text) == (
        f"request failed: token={REDACTION_MARKER}{punctuation}"
    )


def test_redacts_sensitive_environment_values_in_arbitrary_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TUSHARE_TOKEN",
        "SERVICE_TOKEN",
        "SERVICE_API_KEY",
        "SERVICE_SECRET",
        "SERVICE_PASSWORD",
    ):
        monkeypatch.setenv(name, SYNTHETIC_SECRET)
    text = f"HTTPError('upstream echoed ::{SYNTHETIC_SECRET}::')"

    assert _redact(text) == (
        f"HTTPError('upstream echoed ::{REDACTION_MARKER}::')"
    )


def test_redacts_environment_value_that_is_marker_substring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_substring = "REDACTED"
    monkeypatch.setenv("SERVICE_TOKEN", marker_substring)
    text = f"upstream echoed {marker_substring}"

    redacted = _redact(text)

    assert marker_substring in REDACTION_MARKER
    assert marker_substring != REDACTION_MARKER
    assert redacted == f"upstream echoed {REDACTION_MARKER}"
    assert _redact(redacted) == redacted


def test_context_free_environment_redaction_uses_token_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    short_secret = "abc12345"
    run_id = f"2026-06-30-dead{short_secret}-fedcba987654"
    checksum = f"{'a' * 28}{short_secret}{'b' * 28}"
    text = (
        f"ordinary=prefix{short_secret}suffix; "
        f"run_id={run_id}; sha256={checksum}"
    )
    monkeypatch.setenv("SERVICE_TOKEN", short_secret)

    assert _redact(text) == text


def test_context_free_environment_redaction_redacts_delimited_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    short_secret = "abc12345"
    monkeypatch.setenv("SERVICE_TOKEN", short_secret)
    text = f"RuntimeError('upstream echoed ::{short_secret}::')"

    assert _redact(text) == (
        f"RuntimeError('upstream echoed ::{REDACTION_MARKER}::')"
    )


def test_context_free_environment_redaction_skips_ultra_short_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "x")
    text = "RuntimeError('code x was rejected')"

    assert _redact(text) == text
    assert _redact("token=x") == f"token={REDACTION_MARKER}"


def test_environment_redaction_handles_overlapping_values_longest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shorter_secret = "overlap-secret"
    longer_secret = "overlap-secret-value"
    monkeypatch.setenv("SERVICE_TOKEN", shorter_secret)
    monkeypatch.setenv("SERVICE_API_KEY", longer_secret)
    text = f"failure {longer_secret}; retry with {shorter_secret}"

    assert _redact(text) == (
        f"failure {REDACTION_MARKER}; retry with {REDACTION_MARKER}"
    )


def test_ignores_blank_sensitive_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "   \t")
    text = "ordinary   \tspacing remains intact"

    assert _redact(text) == text


def test_redaction_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", SYNTHETIC_SECRET)
    text = f"token={SYNTHETIC_SECRET}"
    once = _redact(text)

    assert _redact(once) == once == f"token={REDACTION_MARKER}"


def test_redaction_preserves_non_secret_context() -> None:
    checksum = "a" * 64
    text = (
        "token count is 42; token_count=42; date=2026-07-12; "
        "run_id=2026-06-30-123456789abc-fedcba987654; "
        f"sha256={checksum}"
    )

    assert _redact(text) == text


@pytest.mark.parametrize("value", [None, 7, object()])
def test_redaction_accepts_strings_only(value: Any) -> None:
    from seven_cycle_platform.security import redact_secrets

    with pytest.raises(TypeError, match="text must be a string"):
        redact_secrets(value)
