"""Read-only DuckDB catalog for immutable published products."""

from seven_cycle_platform.catalog.duckdb import (
    CATALOG_SCHEMA_VERSION,
    STABLE_VIEW_NAMES,
    CatalogBuildResult,
    CatalogDeviceIdentityDriftEvidence,
    CatalogBuildError,
    CatalogError,
    CatalogRepairRefusedError,
    CatalogVerificationError,
    VerifiedCatalogConnection,
    build_catalog,
    inspect_catalog_device_identity_drift,
    open_catalog,
    repair_catalog_device_identity_drift,
)


__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "STABLE_VIEW_NAMES",
    "CatalogBuildResult",
    "CatalogDeviceIdentityDriftEvidence",
    "CatalogBuildError",
    "CatalogError",
    "CatalogRepairRefusedError",
    "CatalogVerificationError",
    "VerifiedCatalogConnection",
    "build_catalog",
    "inspect_catalog_device_identity_drift",
    "open_catalog",
    "repair_catalog_device_identity_drift",
]
