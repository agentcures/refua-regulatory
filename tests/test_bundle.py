from __future__ import annotations

import json
from pathlib import Path

from refua_regulatory.bundle import build_evidence_bundle, verify_evidence_bundle


def test_build_and_verify_bundle(
    sample_campaign_run_file: Path,
    sample_data_manifest_file: Path,
    tmp_path: Path,
) -> None:
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps({"artifact": "ok"}) + "\n", encoding="utf-8")

    output_dir = tmp_path / "bundle"

    manifest = build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
        data_manifest_paths=[sample_data_manifest_file],
        extra_artifacts=[extra],
    )

    assert manifest["schema_version"] == "1.0.0"
    assert manifest["decision_count"] >= 3
    assert manifest["artifact_count"] >= 2
    assert manifest["checklist_reports"]
    assert manifest["checklist_summary"]

    assert output_dir.joinpath("manifest.json").exists()
    assert output_dir.joinpath("decisions.jsonl").exists()
    assert output_dir.joinpath("lineage.json").exists()
    assert output_dir.joinpath("checksums.sha256").exists()
    assert output_dir.joinpath("checklists", "drug_discovery_comprehensive.json").exists()
    assert output_dir.joinpath("checklists", "drug_discovery_comprehensive.md").exists()

    verification = verify_evidence_bundle(output_dir)
    assert verification.ok
    assert verification.checked_files > 0


def test_verify_detects_tampering(sample_campaign_run_file: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
    )

    tampered = output_dir / "artifacts" / "campaign_run.json"
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n#tampered\n", encoding="utf-8")

    verification = verify_evidence_bundle(output_dir)
    assert not verification.ok
    assert verification.errors


def test_build_strict_checklist_fails_without_required_data_provenance(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"

    try:
        build_evidence_bundle(
            campaign_run_path=sample_campaign_run_file,
            output_dir=output_dir,
            checklist_strict=True,
            checklist_templates=["core"],
        )
    except ValueError as exc:
        assert "Checklist strict mode failed" in str(exc)
    else:
        raise AssertionError("Expected checklist strict mode to fail")


def test_build_can_disable_auto_checklist(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    manifest = build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
        include_checklists=False,
    )

    assert manifest["checklist_reports"] == []
    assert not output_dir.joinpath("checklists").exists()
