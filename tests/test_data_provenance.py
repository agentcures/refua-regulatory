from __future__ import annotations

import json
from pathlib import Path

from refua_regulatory.extractors import load_data_provenance_from_manifests


def test_load_data_provenance_from_manifest(sample_data_manifest_file: Path) -> None:
    records, warnings = load_data_provenance_from_manifests([sample_data_manifest_file])

    assert not warnings
    assert len(records) == 1
    record = records[0]
    assert record.dataset_id == "chembl_activity_ki_human"
    assert record.version == "latest"
    assert record.source_url == "https://www.ebi.ac.uk/chembl/api/data/activity.json"
    assert record.sha256 == "f" * 64


def test_load_data_provenance_reports_invalid_manifest(tmp_path: Path) -> None:
    invalid_manifest = tmp_path / "invalid.json"
    invalid_manifest.write_text(json.dumps(["not", "object"]) + "\n", encoding="utf-8")

    records, warnings = load_data_provenance_from_manifests([invalid_manifest])

    assert not records
    assert warnings
