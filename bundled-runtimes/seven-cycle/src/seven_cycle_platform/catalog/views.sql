CREATE VIEW runs AS
SELECT
    run_id,
    as_of,
    data_vintage,
    model_version,
    config_hash,
    created_at,
    run_dir,
    manifest_checksum,
    product_count,
    catalog_schema_version,
    catalog_checksum
FROM _catalog_metadata;

CREATE VIEW cycle_history AS
SELECT history.*
FROM _src_cycle_phase_vintage AS history
JOIN _catalog_metadata AS metadata
  ON history.run_id = metadata.run_id;

CREATE VIEW cycle_current AS
WITH eligible AS (
    SELECT history.*
    FROM _src_cycle_phase_vintage AS history
    JOIN _catalog_metadata AS metadata
      ON history.run_id = metadata.run_id
     AND history.date <= metadata.as_of
     AND (history.as_of IS NULL OR history.as_of = metadata.as_of)
),
ranked AS (
    SELECT
        eligible.*,
        row_number() OVER (
            PARTITION BY cycle_id
            ORDER BY
                date DESC,
                CASE vintage
                    WHEN 'realtime' THEN 0
                    WHEN 'latest_historical' THEN 1
                    WHEN 'pseudo_vintage' THEN 2
                    ELSE 3
                END,
                vintage
        ) AS current_rank
    FROM eligible
)
SELECT * EXCLUDE (current_rank)
FROM ranked
WHERE current_rank = 1;

CREATE VIEW cycle_forecast AS
SELECT forecast.*
FROM _src_cycle_forecast AS forecast
JOIN _catalog_metadata AS metadata
  ON forecast.run_id = metadata.run_id;

CREATE VIEW attribution AS
SELECT attribution.*
FROM _src_asset_attribution AS attribution
JOIN _catalog_metadata AS metadata
  ON attribution.run_id = metadata.run_id;

CREATE VIEW asset_mapping_current AS
SELECT mapping.*
FROM _src_asset_mapping_current AS mapping
JOIN _catalog_metadata AS metadata
  ON mapping.run_id = metadata.run_id;

CREATE VIEW asset_mapping_future AS
SELECT mapping.*
FROM _src_asset_mapping_future AS mapping
JOIN _catalog_metadata AS metadata
  ON mapping.run_id = metadata.run_id;

CREATE VIEW cycle_asset_surface AS
SELECT surface.*
FROM _src_cycle_asset_surface AS surface
JOIN _catalog_metadata AS metadata
  ON surface.run_id = metadata.run_id;

CREATE VIEW assets AS
SELECT DISTINCT run_id, asset_id
FROM (
    SELECT run_id, asset_id FROM attribution
    UNION ALL
    SELECT run_id, asset_id FROM asset_mapping_current
    UNION ALL
    SELECT run_id, asset_id FROM asset_mapping_future
    UNION ALL
    SELECT run_id, asset_id FROM cycle_asset_surface
) AS asset_index
WHERE asset_id IS NOT NULL;

CREATE VIEW historical_analogs AS
SELECT analog.*
FROM _src_historical_analogs AS analog
JOIN _catalog_metadata AS metadata
  ON analog.run_id = metadata.run_id;

CREATE VIEW scenarios AS
SELECT DISTINCT
    mapping.run_id,
    mapping.as_of,
    mapping.data_vintage,
    mapping.scenario_id,
    mapping.scenario_version,
    mapping.catalog_version,
    mapping.scenario_config_hash,
    mapping.model_version,
    mapping.config_hash,
    mapping.created_at
FROM asset_mapping_future AS mapping
WHERE mapping.scenario_id IS NOT NULL;

CREATE VIEW quality_findings AS
SELECT
    summary.run_id,
    'manifest.quality_summary' AS source,
    summary.metadata_path AS finding_key,
    summary.value_type,
    summary.value_json
FROM _catalog_quality_summary AS summary
UNION ALL
SELECT
    records.run_id,
    records.source,
    records.finding_key,
    records.value_type,
    records.value_json
FROM _catalog_quality_records AS records;

CREATE VIEW cycle_evidence AS
SELECT evidence.*
FROM _src_cycle_evidence AS evidence
JOIN _catalog_metadata AS metadata ON evidence.run_id = metadata.run_id;

CREATE VIEW data_identity AS
SELECT identity.*
FROM _src_data_identity AS identity
JOIN _catalog_metadata AS metadata ON identity.run_id = metadata.run_id;

CREATE VIEW publication_gates AS
SELECT gate.*
FROM _src_publication_gate AS gate
JOIN _catalog_metadata AS metadata ON gate.run_id = metadata.run_id;

CREATE VIEW calibration_log AS
SELECT calibration.*
FROM _src_calibration_log AS calibration
JOIN _catalog_metadata AS metadata ON calibration.run_id = metadata.run_id;
