from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ChatlogContactRecord:
    wxid: str
    nick_name: str
    remark: str
    label_names: list[str]


def resolve_contact_db(chatlog_dir: str | None) -> Path | None:
    if not chatlog_dir:
        return None
    base = Path(chatlog_dir).expanduser()
    try:
        base = base.resolve()
    except Exception:
        base = Path(str(base))
    p = base / "db_storage" / "contact" / "contact.db"
    return p if p.exists() else None


def _decode_varint(data: bytes, idx: int) -> tuple[int | None, int]:
    """Decode protobuf varint from data[idx:]. Returns (value, next_idx)."""
    val = 0
    shift = 0
    i = idx
    while i < len(data) and shift <= 64:
        b = data[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, i
        shift += 7
    # malformed
    return None, min(len(data), idx + 1)


def _decode_packed_varints(chunk: bytes) -> list[int] | None:
    out: list[int] = []
    i = 0
    while i < len(chunk):
        v, ni = _decode_varint(chunk, i)
        if v is None:
            return None
        out.append(v)
        i = ni
    return out


def _extract_label_names(extra: bytes | None, label_map: dict[int, str]) -> list[str]:
    """Heuristically extract WeChat contact label names from extra_buffer blob.

    Notes:
    - WeChat stores contact labels in contact.extra_buffer (protobuf-like blob).
    - The exact schema varies; we use a conservative heuristic:
      1) Prefer packed varint candidates whose values are mostly label IDs.
      2) Additionally extract a small set of known repeated-varint fields observed in chatlog contact.db,
         to improve recall for some labels (still gated by label_id membership).
    """
    if not extra:
        return []
    label_ids = set(label_map)

    packed_best_ids: list[int] = []
    packed_best_score: tuple[float, int, int, int, int] | None = None

    def consider_packed_candidate(ids: list[int], *, frac: float, field_no: int, depth: int, packed_len: int) -> None:
        nonlocal packed_best_ids, packed_best_score
        if not ids:
            return
        uniq = sorted(set(ids))
        # Prefer higher fraction first (to avoid small-int collisions), then more unique labels.
        score = (float(frac), len(uniq), -int(depth), -int(packed_len), -int(field_no))
        if packed_best_score is None or score > packed_best_score:
            packed_best_score = score
            packed_best_ids = uniq

    # Some chatlog builds store label ids as repeated varints at specific (field_no, depth).
    # These were discovered empirically on the user's contact.db and are still guarded by label_id membership.
    VARINT_LABEL_FIELDS: set[tuple[int, int]] = {(8, 0), (37, 0), (7, 1)}
    varint_ids: set[int] = set()

    def walk(buf: bytes, *, depth: int) -> None:
        if not buf:
            return
        i = 0
        while i < len(buf):
            key, ni = _decode_varint(buf, i)
            i = ni
            if key is None:
                return
            wire_type = key & 0x7
            field_no = key >> 3
            if wire_type == 0:
                v, i = _decode_varint(buf, i)
                if v is not None and v in label_ids and (field_no, depth) in VARINT_LABEL_FIELDS:
                    varint_ids.add(int(v))
                continue
            if wire_type == 1:
                i += 8
                continue
            if wire_type == 5:
                i += 4
                continue
            if wire_type != 2:
                # Unknown wire type; stop scanning this branch.
                return
            ln, i = _decode_varint(buf, i)
            if ln is None or ln < 0:
                return
            chunk = buf[i : i + ln]
            i += ln
            if not chunk:
                continue

            # Candidate: packed varints (small chunks only to avoid false positives from long strings/urls).
            if len(chunk) <= 256:
                packed = _decode_packed_varints(chunk)
                if packed:
                    in_ids = [v for v in packed if v in label_ids]
                    if in_ids:
                        frac = len(in_ids) / len(packed)
                        # Require "mostly" label IDs. Lowering too far increases collisions because label ids are small.
                        if frac >= 0.7:
                            consider_packed_candidate(
                                in_ids, frac=frac, field_no=field_no, depth=depth, packed_len=len(packed)
                            )

            # Recurse into nested messages (extra_buffer often nests structures).
            if depth < 3 and len(chunk) <= 4096:
                walk(bytes(chunk), depth=depth + 1)

    walk(bytes(extra), depth=0)
    merged_ids = sorted(set(packed_best_ids) | varint_ids)
    return [label_map[i] for i in merged_ids if i in label_map]


def iter_chatlog_contacts(contact_db_path: Path, *, limit: int | None = None) -> Iterable[ChatlogContactRecord]:
    con = sqlite3.connect(str(contact_db_path))
    con.row_factory = sqlite3.Row
    try:
        label_map = {int(r["label_id_"]): str(r["label_name_"] or "").strip() for r in con.execute("SELECT label_id_, label_name_ FROM contact_label")}
        label_map = {k: v for k, v in label_map.items() if v}

        sql = "SELECT username, nick_name, remark, extra_buffer FROM contact WHERE username IS NOT NULL AND username<>''"
        if isinstance(limit, int) and limit > 0:
            sql += f" LIMIT {int(limit)}"
        for r in con.execute(sql):
            wxid = str(r["username"] or "").strip()
            if not wxid:
                continue
            nick = str(r["nick_name"] or "").strip()
            remark = str(r["remark"] or "").strip()
            extra = r["extra_buffer"]
            label_names = _extract_label_names(extra, label_map)
            yield ChatlogContactRecord(wxid=wxid, nick_name=nick, remark=remark, label_names=label_names)
    finally:
        con.close()
