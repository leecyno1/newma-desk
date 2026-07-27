import json
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from vibe_visualization_api.data_services.models import DataServiceDescriptor


class DataServiceDiscoveryError(ValueError):
    """Raised when an installed data-service descriptor is malformed."""


def discover_data_services(
    roots: list[Path],
    *,
    base_url_overrides: Mapping[str, str] | None = None,
) -> list[DataServiceDescriptor]:
    descriptors: list[DataServiceDescriptor] = []
    overrides = base_url_overrides or {}
    for root in roots:
        if not root.exists():
            continue
        if not root.is_dir():
            raise DataServiceDiscoveryError(
                f"data service discovery root is not a directory: {root}"
            )
        for descriptor_path in sorted(root.rglob("data-service.json")):
            try:
                raw = json.loads(descriptor_path.read_text(encoding="utf-8"))
                service_id = raw.get("id") if isinstance(raw, dict) else None
                override = (
                    overrides.get(service_id)
                    if isinstance(service_id, str)
                    else None
                )
                if override:
                    parsed = urlsplit(override)
                    if not parsed.hostname:
                        raise ValueError("data service override must contain a host")
                    raw["baseUrl"] = override
                    allowed_hosts = raw.setdefault("allowedHosts", [])
                    if not isinstance(allowed_hosts, list):
                        raise ValueError("allowedHosts must be a list")
                    if parsed.hostname not in allowed_hosts:
                        allowed_hosts.append(parsed.hostname)
                descriptors.append(DataServiceDescriptor.model_validate(raw))
            except (OSError, json.JSONDecodeError, ValueError) as error:
                raise DataServiceDiscoveryError(
                    f"invalid data service descriptor: {descriptor_path}"
                ) from error
    return descriptors
