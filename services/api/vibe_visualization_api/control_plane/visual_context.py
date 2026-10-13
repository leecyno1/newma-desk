import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from vibe_visualization_api.config import Settings


MAX_VISUAL_CAPTURE_BYTES = 5 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class VisualContextCaptureService:
    """Stores Mod visual evidence without owning any Agent execution."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._project_root = Path(__file__).resolve().parents[4]
        self._script = self._project_root / "scripts" / "capture-mod-visual-context.mjs"
        self._capture_dir = (
            settings.runtime_dir.expanduser().resolve() / "mod-page-captures"
        )
        allowed_origins = settings.origin_list()
        self._allowed_origins = set(allowed_origins)
        configured = (
            os.environ.get("NEWMA_DESK_SHELL_ORIGIN", "").strip()
            or os.environ.get("NEWMA_DOCK_SHELL_ORIGIN", "").strip()
            or os.environ.get("VIBEDESK_SHELL_ORIGIN", "").strip()
        )
        self._default_origin = configured or (
            allowed_origins[0] if allowed_origins else ""
        )

    async def capture(
        self,
        module_id: str,
        shell_origin: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, object]:
        origin = self._safe_origin(shell_origin) or self._safe_origin(
            self._default_origin
        )
        if origin is None:
            return {"status": "failed", "reason": "Desk origin is not allowed"}
        self._capture_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_expired()
        artifact_id = uuid4().hex
        output = self._capture_dir / f"{artifact_id}.png"
        process = await asyncio.create_subprocess_exec(
            self._settings.node_binary,
            str(self._script),
            "--mod",
            module_id,
            "--shell-origin",
            origin,
            *(
                ("--workspace", workspace_id)
                if workspace_id
                else ()
            ),
            "--output",
            str(output),
            "--timeout",
            "30000",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._project_root,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=35,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            output.unlink(missing_ok=True)
            return {"status": "failed", "reason": "Visual capture timed out"}
        if process.returncode != 0:
            output.unlink(missing_ok=True)
            detail = stderr.decode("utf-8", errors="replace").strip().splitlines()
            return {
                "status": "failed",
                "reason": detail[-1][:240] if detail else "Visual capture failed",
            }
        try:
            result = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            output.unlink(missing_ok=True)
            return {
                "status": "failed",
                "reason": "Visual capture returned invalid data",
            }
        image = result.get("image") if isinstance(result, dict) else None
        captured_path = image.get("path") if isinstance(image, dict) else None
        if (
            not isinstance(result, dict)
            or result.get("status") != "ready"
            or captured_path != str(output)
            or not output.is_file()
        ):
            output.unlink(missing_ok=True)
            return {"status": "failed", "reason": "Visual capture was incomplete"}
        image = result.get("image")
        dom = result.get("dom")
        adapter_readable = self.resolve_image(artifact_id) is not None
        return {
            "status": "ready",
            "source": "server-playwright",
            "captureMode": "reopened-module",
            "capturedAt": str(result.get("capturedAt") or datetime.now(timezone.utc).isoformat()),
            "moduleId": module_id,
            "dom": dom if isinstance(dom, dict) else {},
            "image": {
                "artifactId": artifact_id,
                "mimeType": "image/png",
                "width": int(image.get("width") or 0) if isinstance(image, dict) else 0,
                "height": int(image.get("height") or 0) if isinstance(image, dict) else 0,
                "bytes": output.stat().st_size,
            },
            "delivery": {
                "mode": "artifact-reference",
                "adapterReadable": adapter_readable,
            },
        }

    def save_browser_capture(
        self,
        module_id: str,
        data: bytes,
        *,
        width: int,
        height: int,
    ) -> dict[str, object]:
        if not data or len(data) > MAX_VISUAL_CAPTURE_BYTES:
            raise ValueError("Visual capture exceeds the size limit")
        if not data.startswith(PNG_SIGNATURE):
            raise ValueError("Visual capture must be a PNG image")
        self._capture_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_expired()
        artifact_id = uuid4().hex
        output = self._capture_dir / f"{artifact_id}.png"
        temporary = self._capture_dir / f".{artifact_id}.tmp"
        try:
            temporary.write_bytes(data)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        adapter_readable = self.resolve_image(artifact_id) is not None
        return {
            "status": "ready",
            "source": "browser-mod-bridge",
            "captureMode": "current-frame",
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "moduleId": module_id,
            "image": {
                "artifactId": artifact_id,
                "mimeType": "image/png",
                "width": width,
                "height": height,
                "bytes": len(data),
            },
            "delivery": {
                "mode": "artifact-reference",
                "adapterReadable": adapter_readable,
            },
        }

    def resolve_image(self, artifact_id: str) -> Path | None:
        if re.fullmatch(r"[0-9a-f]{32}", artifact_id) is None:
            return None
        path = self._capture_dir / f"{artifact_id}.png"
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return None
        return resolved if resolved.parent == self._capture_dir.resolve() else None

    def _safe_origin(self, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlsplit(value)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or origin not in self._allowed_origins
        ):
            return None
        return origin

    def _cleanup_expired(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        for path in self._capture_dir.glob("*.png"):
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                if modified < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
