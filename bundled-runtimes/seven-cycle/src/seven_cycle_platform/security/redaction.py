"""Redact credential values while retaining useful failure context."""

import os
import re


REDACTION_MARKER = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth_token",
        "client_secret",
        "passwd",
        "password",
        "secret",
        "token",
        "tushare_token",
        "x-api-key",
    }
)

_KEY_PATTERN = "|".join(
    re.escape(key) for key in sorted(SENSITIVE_KEYS, key=len, reverse=True)
)
_KEY_BOUNDARY = r"A-Za-z0-9_-"
_AUTHORIZATION_QUOTED = re.compile(
    rf"""
    (?P<prefix>
        (?<![{_KEY_BOUNDARY}])
        ["']?authorization["']?
        (?![{_KEY_BOUNDARY}])
        \s*[:=]\s*
        (?P<quote>["'])
    )
    (?P<scheme>(?:(?:Bearer|Basic)\s+)?)
    (?P<value>.*?)
    (?P=quote)
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)
_AUTHORIZATION_BARE = re.compile(
    rf"""
    (?P<prefix>
        (?<![{_KEY_BOUNDARY}])
        ["']?authorization["']?
        (?![{_KEY_BOUNDARY}])
        \s*[:=]\s*
    )
    (?!["'])
    (?P<scheme>(?:(?:Bearer|Basic)\s+)?)
    (?P<value>\[REDACTED\]|[^\s,;}}\])&#"']+)
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)
_SECRET_QUOTED = re.compile(
    rf"""
    (?P<prefix>
        (?<![{_KEY_BOUNDARY}])
        ["']?(?:{_KEY_PATTERN})["']?
        (?![{_KEY_BOUNDARY}])
        \s*[:=]\s*
        (?P<quote>["'])
    )
    (?P<value>.*?)
    (?P=quote)
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)
_SECRET_BARE = re.compile(
    rf"""
    (?P<prefix>
        (?<![{_KEY_BOUNDARY}])
        ["']?(?:{_KEY_PATTERN})["']?
        (?![{_KEY_BOUNDARY}])
        \s*[:=]\s*
    )
    (?!["'])
    (?P<value>\[REDACTED\]|[^\s,;}}\])&#"']+)
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)
_SENSITIVE_ENV_NAME = re.compile(
    r"(?:^TUSHARE_TOKEN$|(?:^|_)(?:TOKEN|API_KEY|SECRET|PASSWORD|PASSWD)$)",
    flags=re.IGNORECASE,
)
_CONTEXT_FREE_ENV_VALUE_MIN_LENGTH = 8
_TOKEN_CHARACTER_CLASS = r"A-Za-z0-9_"


def is_sensitive_key(name: str) -> bool:
    """Return whether a structured field name denotes a secret value."""

    return name.casefold() in SENSITIVE_KEYS or name.casefold() == "authorization"


def _redact_quoted(match: re.Match[str]) -> str:
    value = match.group("value")
    if not value.strip():
        return match.group(0)
    scheme = match.groupdict().get("scheme") or ""
    return (
        f"{match.group('prefix')}{scheme}{REDACTION_MARKER}"
        f"{match.group('quote')}"
    )


def _redact_bare(match: re.Match[str]) -> str:
    value = match.group("value")
    if value == REDACTION_MARKER:
        return match.group(0)
    scheme = match.groupdict().get("scheme") or ""
    trailing = ""
    while len(value) > 1 and value[-1] in ".:!?":
        trailing = value[-1] + trailing
        value = value[:-1]
    if not value:
        return match.group(0)
    return f"{match.group('prefix')}{scheme}{REDACTION_MARKER}{trailing}"


def _sensitive_environment_values() -> tuple[str, ...]:
    """Return context-free secret candidates of at least eight characters."""

    values: set[str] = set()
    for name, raw_value in os.environ.items():
        if not _SENSITIVE_ENV_NAME.search(name) or not raw_value:
            continue
        stripped_value = raw_value.strip()
        if len(stripped_value) < _CONTEXT_FREE_ENV_VALUE_MIN_LENGTH:
            continue
        for value in (raw_value, stripped_value):
            if value and value != REDACTION_MARKER:
                values.add(value)
    return tuple(sorted(values, key=len, reverse=True))


def _redact_environment_value(text: str, value: str) -> str:
    value_pattern = re.compile(
        rf"(?<![{_TOKEN_CHARACTER_CLASS}])"
        rf"{re.escape(value)}"
        rf"(?![{_TOKEN_CHARACTER_CLASS}])"
    )
    return REDACTION_MARKER.join(
        value_pattern.sub(REDACTION_MARKER, segment)
        for segment in text.split(REDACTION_MARKER)
    )


def redact_secrets(text: str) -> str:
    """Replace secret values in text with one stable marker."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    redacted = _AUTHORIZATION_QUOTED.sub(_redact_quoted, text)
    redacted = _AUTHORIZATION_BARE.sub(_redact_bare, redacted)
    redacted = _SECRET_QUOTED.sub(_redact_quoted, redacted)
    redacted = _SECRET_BARE.sub(_redact_bare, redacted)
    for value in _sensitive_environment_values():
        redacted = _redact_environment_value(redacted, value)
    return redacted
