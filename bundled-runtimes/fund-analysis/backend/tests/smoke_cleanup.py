"""Cleanup helpers for smoke fixtures that must never remain in the real fund database."""

from typing import Iterable


def cleanup_fund_codes(codes: Iterable[str]) -> None:
    from sqlalchemy import bindparam, text

    from database import get_engine

    normalized = [str(code).strip() for code in codes if str(code).strip()]
    if not normalized:
        return
    code_param = bindparam("codes", expanding=True)
    with get_engine().begin() as conn:
        entity_ids = [row[0] for row in conn.execute(
            text("SELECT DISTINCT entity_id FROM fund_share_classes WHERE wind_code IN :codes").bindparams(code_param),
            {"codes": normalized},
        )]
        if entity_ids:
            entity_param = bindparam("entity_ids", expanding=True)
            params = {"entity_ids": entity_ids}
            conn.execute(text("DELETE FROM peer_group_members WHERE entity_id IN :entity_ids").bindparams(entity_param), params)
            conn.execute(text("DELETE FROM benchmark_mappings WHERE entity_id IN :entity_ids").bindparams(entity_param), params)
            conn.execute(text("DELETE FROM fund_share_classes WHERE entity_id IN :entity_ids").bindparams(entity_param), params)
            conn.execute(text("DELETE FROM fund_entities WHERE id IN :entity_ids").bindparams(entity_param), params)
        conn.execute(text("DELETE FROM metric_snapshots WHERE target_type = 'fund' AND target_id IN :codes").bindparams(code_param), {"codes": normalized})
        conn.execute(text("DELETE FROM scores WHERE target_type = 'fund' AND target_id IN :codes").bindparams(code_param), {"codes": normalized})
        conn.execute(text("DELETE FROM fund_nav WHERE wind_code IN :codes").bindparams(code_param), {"codes": normalized})
        conn.execute(text("DELETE FROM fund_research_profiles WHERE wind_code IN :codes").bindparams(code_param), {"codes": normalized})
        conn.execute(text("DELETE FROM funds WHERE wind_code IN :codes").bindparams(code_param), {"codes": normalized})
