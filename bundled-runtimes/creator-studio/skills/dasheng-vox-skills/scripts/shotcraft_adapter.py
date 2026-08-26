#!/usr/bin/env python3
"""Search and bind video-shotcraft cards to approved Newma scenes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SHOTCRAFT_ROOT = PROJECT_ROOT / "vendor" / "reserved" / "video" / "video-shotcraft"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_library(root: Path) -> dict[str, Any]:
    path = root / "gallery" / "api" / "library.json"
    if not path.is_file():
        raise FileNotFoundError(f"Shotcraft catalog not found: {path}")
    payload = read_json(path)
    if not isinstance(payload.get("cards"), list):
        raise ValueError("Shotcraft library.json has no cards array")
    return payload


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def card_search_text(card: dict[str, Any]) -> str:
    styles = card.get("styles") or []
    values = [
        card.get("name"),
        card.get("summary"),
        card.get("use"),
        card.get("duration"),
        card.get("energy"),
        card.get("intention"),
        card.get("category"),
        " ".join(str(tag) for tag in card.get("tags") or []),
    ]
    for style in styles:
        values.extend([style.get("key"), style.get("label"), style.get("description"), style.get("use")])
    return " ".join(str(value or "") for value in values).lower()


def search_cards(
    library: dict[str, Any],
    *,
    query: str = "",
    category: str = "",
    limit: int = 12,
) -> list[dict[str, Any]]:
    query = query.strip().lower()
    terms = [term for term in query.split() if term]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for card in library["cards"]:
        if category and card.get("category") != category:
            continue
        text = card_search_text(card)
        score = 1
        if query:
            score = 8 if query in text else 0
            score += sum(4 if term in str(card.get("name") or "").lower() else 1 for term in terms if term in text)
            if score == 0:
                continue
        ranked.append((score, card))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("name"))))
    return [
        {
            "name": card.get("name"),
            "category": card.get("category"),
            "summary": card.get("summary"),
            "use": card.get("use"),
            "duration": card.get("duration"),
            "energy": card.get("energy"),
            "styles": [style.get("key") for style in card.get("styles") or []],
            "source": card.get("source"),
        }
        for _, card in ranked[: max(1, limit)]
    ]


def demo_directory(root: Path, card: dict[str, Any]) -> Path:
    source = root / str(card["source"])
    text = source.read_text(encoding="utf-8")
    section = text.split("## 参考实现", 1)[-1]
    match = re.search(r"(?m)^demos/[^\s（(]+/?", section)
    if not match:
        raise ValueError(f"{card['name']}: no demo directory in {card['source']}")
    directory = root / match.group(0).rstrip("/")
    if not directory.is_dir():
        raise FileNotFoundError(f"{card['name']}: demo directory missing: {directory}")
    return directory


def resolve_demo(root: Path, card: dict[str, Any], style_key: str, explicit: str = "") -> str:
    directory = demo_directory(root, card)
    if explicit:
        candidate = (root / explicit).resolve()
        try:
            candidate.relative_to(directory.resolve())
        except ValueError as exc:
            raise ValueError(f"{card['name']}: demo_source must stay inside {directory.relative_to(root)}") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"{card['name']}: demo source missing: {explicit}")
        return candidate.relative_to(root).as_posix()

    candidates = sorted(directory.glob("*.tsx"))
    style_name = normalized(style_key)
    matches = [path for path in candidates if style_name in normalized(path.stem)]
    if len(matches) == 1:
        return matches[0].relative_to(root).as_posix()
    if len(candidates) == 1:
        return candidates[0].relative_to(root).as_posix()
    options = ", ".join(path.name for path in candidates)
    raise ValueError(f"{card['name']}/{style_key}: set motion.demo_source explicitly; candidates: {options}")


def scene_duration(scene: dict[str, Any]) -> float:
    if scene.get("duration_sec") is not None:
        return float(scene["duration_sec"])
    return float(scene.get("end_sec", 0)) - float(scene.get("start_sec", 0))


def bind_payload(payload: dict[str, Any], library: dict[str, Any], root: Path, *, fps: int = 30) -> dict[str, Any]:
    items = payload.get("scenes") if isinstance(payload.get("scenes"), list) else payload.get("shots")
    if not isinstance(items, list):
        raise ValueError("input must contain scenes[] or shots[]")

    cards = {str(card.get("name")): card for card in library["cards"]}
    visual_bible = payload.get("visual_bible") or {}
    brand_tokens = (
        {
            key: visual_bible[key]
            for key in ["world", "materials", "palette", "type_system"]
            if visual_bible.get(key)
        }
        if isinstance(visual_bible, dict)
        else {}
    )
    bound = 0
    for scene in items:
        motion = scene.get("motion")
        if not isinstance(motion, dict):
            motion = {}
            scene["motion"] = motion
        card_name = str(motion.get("shotcraft_card") or scene.get("shotcraft_card") or "").strip()
        if not card_name:
            continue
        card = cards.get(card_name)
        if not card:
            raise ValueError(f"{scene.get('id')}: unknown Shotcraft card: {card_name}")

        styles = {str(style.get("key")): style for style in card.get("styles") or []}
        style_key = str(motion.get("style_key") or "").strip()
        if not style_key:
            if len(styles) != 1:
                raise ValueError(f"{scene.get('id')}: {card_name} requires style_key; options: {', '.join(styles)}")
            style_key = next(iter(styles))
        if style_key not in styles:
            raise ValueError(f"{scene.get('id')}: invalid style_key {style_key}; options: {', '.join(styles)}")

        duration_frames = max(1, round(scene_duration(scene) * fps))
        qa_frames = sorted({max(0, round(duration_frames * 0.35)), max(0, min(duration_frames - 1, round(duration_frames * 0.8)))})
        motion.update(
            {
                "engine": "video-shotcraft",
                "shotcraft_card": card_name,
                "style_key": style_key,
                "card_source": str(card["source"]),
                "demo_source": resolve_demo(root, card, style_key, str(motion.get("demo_source") or "")),
                "duration_frames": duration_frames,
                "qa_frames": qa_frames,
            }
        )
        if brand_tokens:
            motion.setdefault("brand_tokens", brand_tokens)
        scene["production_route"] = "shotcraft_remotion"
        scene["provider_order"] = ["remotion_local_motion"]
        scene["reference_image_required"] = False
        bound += 1

    if not bound:
        raise ValueError("no scene contains motion.shotcraft_card")
    payload["shotcraft_binding"] = {
        "catalog_revision": library.get("revision"),
        "bound_scene_count": bound,
        "fps": fps,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Search and bind video-shotcraft cards for Newma VOX scenes.")
    parser.add_argument("--shotcraft-root", type=Path, default=DEFAULT_SHOTCRAFT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search")
    search.add_argument("--query", default="")
    search.add_argument("--category", default="")
    search.add_argument("--limit", type=int, default=12)

    bind = sub.add_parser("bind")
    bind.add_argument("--input", type=Path, required=True)
    bind.add_argument("--output", type=Path, required=True)
    bind.add_argument("--fps", type=int, default=30)

    args = parser.parse_args()
    root = args.shotcraft_root.expanduser().resolve()
    library = load_library(root)
    if args.command == "search":
        print(json.dumps(search_cards(library, query=args.query, category=args.category, limit=args.limit), ensure_ascii=False, indent=2))
        return 0

    source = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    write_json(output, bind_payload(read_json(source), library, root, fps=args.fps))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
