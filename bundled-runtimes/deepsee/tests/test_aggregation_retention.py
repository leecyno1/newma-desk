from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    AnalysisSnapshot,
    Contact,
    ContactScoreSnapshot,
    ContactValueMetricSnapshot,
    Report,
    ReportArtifact,
)
from app.services.aggregation_retention import prune_aggregation_data


def test_prune_aggregation_data_keeps_only_recent_three_months(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    now = datetime(2026, 5, 3, 12, 0, 0)
    cutoff = now - timedelta(days=90)

    contact = Contact(id="wxid_a", name="A")
    db.add(contact)
    db.add_all(
        [
            AnalysisSnapshot(scope_key="old", created_at=cutoff - timedelta(seconds=1), updated_at=cutoff - timedelta(seconds=1)),
            AnalysisSnapshot(scope_key="new", created_at=cutoff, updated_at=cutoff),
            Report(title="old", created_at=cutoff - timedelta(days=1)),
            Report(title="new", created_at=cutoff + timedelta(days=1)),
            ContactScoreSnapshot(contact_id="wxid_a", as_of=cutoff - timedelta(seconds=1)),
            ContactScoreSnapshot(contact_id="wxid_a", as_of=cutoff),
            ContactValueMetricSnapshot(contact_id="wxid_a", as_of=cutoff - timedelta(seconds=1)),
            ContactValueMetricSnapshot(contact_id="wxid_a", as_of=cutoff),
        ]
    )
    db.commit()
    old_report = db.execute(select(Report).where(Report.title == "old")).scalar_one()
    new_report = db.execute(select(Report).where(Report.title == "new")).scalar_one()
    db.add_all(
        [
            ReportArtifact(report_id=old_report.id, module="market", data_text="old payload"),
            ReportArtifact(report_id=new_report.id, module="market", data_text="new payload"),
        ]
    )
    db.commit()

    result = prune_aggregation_data(db, now=now, retention_days=90)
    db.commit()

    assert result["cutoff"] == cutoff.isoformat()
    assert result["deleted"]["analysis_snapshots"] == 1
    assert result["deleted"]["reports"] == 1
    assert result["deleted"]["report_artifacts"] == 1
    assert result["deleted"]["contact_score_snapshots"] == 1
    assert result["deleted"]["contact_value_metric_snapshots"] == 1
    assert db.execute(select(AnalysisSnapshot.scope_key).order_by(AnalysisSnapshot.id)).scalars().all() == ["new"]
    assert db.execute(select(Report.title).order_by(Report.id)).scalars().all() == ["new"]
    assert db.execute(select(ReportArtifact.data_text)).scalar_one() == "new payload"
    assert db.execute(select(ContactScoreSnapshot)).scalar_one().as_of == cutoff
    assert db.execute(select(ContactValueMetricSnapshot)).scalar_one().as_of == cutoff


def test_prune_aggregation_data_removes_old_dataset_files(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    now = datetime(2026, 5, 3, 12, 0, 0)

    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    old_file = datasets_dir / "messages_3days_old.json"
    new_file = datasets_dir / "messages_3days_new.json"
    ignored_file = datasets_dir / "manual_notes.txt"
    old_file.write_text("{}")
    new_file.write_text("{}")
    ignored_file.write_text("keep")
    old_ts = (now - timedelta(days=91)).timestamp()
    new_ts = (now - timedelta(days=1)).timestamp()
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))
    os.utime(ignored_file, (old_ts, old_ts))

    result = prune_aggregation_data(db, now=now, retention_days=90, datasets_dir=datasets_dir)

    assert result["deleted"]["dataset_files"] == 1
    assert not old_file.exists()
    assert new_file.exists()
    assert ignored_file.exists()
