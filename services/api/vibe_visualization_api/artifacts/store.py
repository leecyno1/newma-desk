import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import ValidationError

from vibe_visualization_api.artifacts.models import (
    ArtifactRecord,
    ArtifactSummary,
    GraphArtifactCreate,
    ReplayArtifactCreate,
    ReplayArtifactRecord,
)


MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
ARTIFACT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class ArtifactStoreError(Exception):
    """Base error for persisted artifact operations."""


class ArtifactNotFoundError(ArtifactStoreError):
    """Raised when an artifact does not exist or has an unsafe identity."""


class CorruptArtifactError(ArtifactStoreError):
    """Raised when persisted artifact metadata is invalid."""


class ArtifactStore:
    def __init__(self, runtime_dir: Path):
        self._root = runtime_dir / "artifacts"
        self._root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        spec: GraphArtifactCreate,
        archify_ir: dict[str, Any],
        rendered_html: str,
    ) -> ArtifactRecord:
        now = datetime.now(timezone.utc)
        artifact_id = uuid4().hex
        artifact_dir = self._artifact_dir(spec.module_id, artifact_id)
        artifact_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "id": artifact_id,
            "moduleId": spec.module_id,
            "kind": "graph",
            "renderer": "archify",
            "title": spec.title,
            "status": "draft",
            "createdAt": now.isoformat(),
            "updatedAt": now.isoformat(),
            "viewUrl": f"/api/artifacts/{artifact_id}/view",
            "spec": spec.model_dump(mode="json", by_alias=True),
            "archifyIr": archify_ir,
        }
        self._atomic_write_text(
            artifact_dir / "view.html",
            rendered_html,
        )
        self._atomic_write_json(artifact_dir / "artifact.json", payload)
        self._atomic_write_json(
            self._module_dir(spec.module_id) / "latest.json",
            {"artifactId": artifact_id},
        )
        return ArtifactRecord.model_validate(payload)

    def create_replay(
        self,
        spec: ReplayArtifactCreate,
        rendered_html: str,
    ) -> ReplayArtifactRecord:
        now = datetime.now(timezone.utc)
        artifact_id = uuid4().hex
        artifact_dir = self._replay_artifact_dir(spec.module_id, artifact_id)
        artifact_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "id": artifact_id,
            "moduleId": spec.module_id,
            "kind": "replay",
            "renderer": "replay-html",
            "title": spec.title,
            "status": "draft",
            "createdAt": now.isoformat(),
            "updatedAt": now.isoformat(),
            "viewUrl": f"/api/artifacts/replays/{artifact_id}/view",
            "spec": spec.model_dump(mode="json", by_alias=True),
        }
        self._atomic_write_text(artifact_dir / "view.html", rendered_html)
        self._atomic_write_json(artifact_dir / "artifact.json", payload)
        self._atomic_write_json(
            self._replay_module_dir(spec.module_id) / "latest.json",
            {"artifactId": artifact_id},
        )
        return ReplayArtifactRecord.model_validate(payload)

    def list_replays(
        self,
        module_id: str,
        status: Literal["draft", "published"] | None = None,
    ) -> list[ReplayArtifactRecord]:
        module_dir = self._replay_module_dir(module_id)
        if not module_dir.is_dir():
            return []
        records: list[ReplayArtifactRecord] = []
        for path in module_dir.glob("*/artifact.json"):
            record = self._read_replay_record(path)
            if status is None or record.status == status:
                records.append(record)
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def latest_replay(
        self,
        module_id: str,
        status: Literal["draft", "published"] | None = None,
    ) -> ReplayArtifactRecord:
        records = self.list_replays(module_id, status=status)
        if not records:
            raise ArtifactNotFoundError("replay artifact was not found")
        return records[0]

    def get_replay(self, artifact_id: str) -> ReplayArtifactRecord:
        record, _ = self._read_replay_by_id(artifact_id)
        return record

    def publish_replay(self, artifact_id: str) -> ReplayArtifactRecord:
        record, path = self._read_replay_by_id(artifact_id)
        payload = record.model_dump(mode="json", by_alias=True)
        payload["status"] = "published"
        payload["updatedAt"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write_json(path, payload)
        return ReplayArtifactRecord.model_validate(payload)

    def read_replay_html(self, artifact_id: str) -> str:
        record, path = self._read_replay_by_id(artifact_id)
        html_path = path.parent / "view.html"
        try:
            html = html_path.read_text(encoding="utf-8")
        except OSError as error:
            raise ArtifactNotFoundError("replay artifact view was not found") from error
        if record.renderer != "replay-html" or "<!doctype html" not in html.lower():
            raise CorruptArtifactError("replay artifact view is invalid")
        return html

    def publish(self, artifact_id: str) -> ArtifactRecord:
        record, path = self._read_by_id(artifact_id)
        now = datetime.now(timezone.utc)
        payload = record.model_dump(mode="json", by_alias=True)
        payload["status"] = "published"
        payload["updatedAt"] = now.isoformat()
        self._atomic_write_json(path, payload)
        return ArtifactRecord.model_validate(payload)

    def latest(
        self,
        module_id: str,
        status: Literal["draft", "published"] | None = None,
    ) -> ArtifactRecord:
        records = self.list(module_id, status=status)
        if not records:
            raise ArtifactNotFoundError("artifact was not found")
        return records[0]

    def list(
        self,
        module_id: str,
        status: Literal["draft", "published"] | None = None,
    ) -> list[ArtifactRecord]:
        module_dir = self._module_dir(module_id)
        if not module_dir.is_dir():
            return []
        records: list[ArtifactRecord] = []
        for path in module_dir.glob("*/artifact.json"):
            record = self._read_record(path)
            if status is None or record.status == status:
                records.append(record)
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def get(self, artifact_id: str) -> ArtifactRecord:
        record, _ = self._read_by_id(artifact_id)
        return record

    def read_html(self, artifact_id: str) -> str:
        record, path = self._read_by_id(artifact_id)
        html_path = path.parent / "view.html"
        try:
            html = html_path.read_text(encoding="utf-8")
        except OSError as error:
            raise ArtifactNotFoundError("artifact view was not found") from error
        if record.renderer != "archify" or "<!doctype html" not in html.lower():
            raise CorruptArtifactError("artifact view is invalid")
        return html

    def _read_by_id(self, artifact_id: str) -> tuple[ArtifactRecord, Path]:
        if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
            raise ArtifactNotFoundError("artifact was not found")
        matches = list(self._root.glob(f"*/{artifact_id}/artifact.json"))
        if len(matches) != 1:
            raise ArtifactNotFoundError("artifact was not found")
        record = self._read_record(matches[0])
        if record.id != artifact_id:
            raise CorruptArtifactError("artifact identity does not match its path")
        return record, matches[0]

    def _module_dir(self, module_id: str) -> Path:
        if MODULE_ID_PATTERN.fullmatch(module_id) is None:
            raise ArtifactNotFoundError("artifact module was not found")
        return self._root / module_id

    def _artifact_dir(self, module_id: str, artifact_id: str) -> Path:
        if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
            raise ArtifactNotFoundError("artifact was not found")
        return self._module_dir(module_id) / artifact_id

    def _replay_module_dir(self, module_id: str) -> Path:
        if MODULE_ID_PATTERN.fullmatch(module_id) is None:
            raise ArtifactNotFoundError("replay artifact module was not found")
        return self._root / "_replays" / module_id

    def _replay_artifact_dir(self, module_id: str, artifact_id: str) -> Path:
        if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
            raise ArtifactNotFoundError("replay artifact was not found")
        return self._replay_module_dir(module_id) / artifact_id

    def _read_replay_by_id(
        self,
        artifact_id: str,
    ) -> tuple[ReplayArtifactRecord, Path]:
        if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
            raise ArtifactNotFoundError("replay artifact was not found")
        matches = list(self._root.glob(f"_replays/*/{artifact_id}/artifact.json"))
        if len(matches) != 1:
            raise ArtifactNotFoundError("replay artifact was not found")
        record = self._read_replay_record(matches[0])
        if record.id != artifact_id:
            raise CorruptArtifactError("replay artifact identity does not match its path")
        return record, matches[0]

    @staticmethod
    def _read_record(path: Path) -> ArtifactRecord:
        try:
            return ArtifactRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise CorruptArtifactError("artifact metadata is invalid") from error

    @staticmethod
    def _read_replay_record(path: Path) -> ReplayArtifactRecord:
        try:
            return ReplayArtifactRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise CorruptArtifactError("replay artifact metadata is invalid") from error

    @staticmethod
    def _atomic_write_json(path: Path, payload: object) -> None:
        ArtifactStore._atomic_write_text(
            path,
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)
