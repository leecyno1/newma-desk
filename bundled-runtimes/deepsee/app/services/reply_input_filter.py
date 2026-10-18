"""Conservative, local-only filtering of low-information auto-reply inputs."""
from __future__ import annotations

import re


def low_information_reason(text: str, rules: dict) -> str | None:
    if not rules.get('low_info_enabled'):
        return None
    text = str(text or '').strip()
    if not text or text in rules.get('low_info_allow_texts', []):
        return None
    if len(text) > rules['low_info_max_chars'] or any(ch in text for ch in '?？'):
        return None
    if rules.get('low_info_emoji_enabled'):
        remaining = text
        for name in rules.get('low_info_emoji_names', []):
            remaining = remaining.replace('[' + name + ']', '')
        remaining = re.sub(r'[#*0-9]\ufe0f?\u20e3', '', remaining)
        # Only recognized emoji ranges and their joiners, not arbitrary symbols,
        # punctuation, attachments, or arbitrary [bracketed] text.
        remaining = ''.join(ch for ch in remaining if not (
            '\U0001f000' <= ch <= '\U0001faff' or '\u2600' <= ch <= '\u27bf'
            or ch in '\u200d\ufe0f\ufe0e' or ch.isspace()))
        if not remaining:
            return 'low_info_emoji'
    if rules.get('low_info_repeat_enabled'):
        compact = re.sub(r'[\s!！。，,～~…]', '', text).casefold()
        for unit in rules.get('low_info_repeat_units', []):
            if re.fullmatch('(?:' + re.escape(unit.casefold()) + '){'
                            + str(rules['low_info_min_repeats']) + ',}', compact):
                return 'low_info_repetition'
    return None
