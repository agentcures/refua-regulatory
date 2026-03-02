from __future__ import annotations

import json
from pathlib import Path

from refua_regulatory.bundle import build_evidence_bundle
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


def test_manifest_rel_path_tracks_parsed_manifest_after_invalid_entries(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    invalid_manifest = tmp_path / "invalid.json"
    invalid_manifest.write_text(json.dumps({"version": "v0"}) + "\n", encoding="utf-8")

    valid_manifest = tmp_path / "valid.json"
    valid_manifest.write_text(
        json.dumps({"dataset_id": "dataset_ok", "version": "v1"}) + "\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "bundle"
    manifest = build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
        include_checklists=False,
        data_manifest_paths=[invalid_manifest, valid_manifest],
    )

    data_provenance = manifest["data_provenance"]
    assert len(data_provenance) == 1
    assert data_provenance[0]["dataset_id"] == "dataset_ok"
    assert (
        data_provenance[0]["manifest_rel_path"]
        == "artifacts/data_manifests/manifest_002_valid.json"
    )
