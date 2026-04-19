from __future__ import annotations

from pathlib import Path

from refua_regulatory.studio import (
    build_evidence_bundle_from_payload,
    verify_bundle_with_summary,
)


def test_build_bundle_from_payload_and_verify(
    sample_campaign_run_payload: dict,
    sample_data_manifest_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    manifest = build_evidence_bundle_from_payload(
        campaign_run=sample_campaign_run_payload,
        output_dir=output_dir,
        data_manifest_paths=[sample_data_manifest_file],
        overwrite=True,
    )

    assert manifest["bundle_id"]
    assert manifest["decision_count"] >= 1

    verification = verify_bundle_with_summary(output_dir)
    assert verification["summary"]["bundle_id"] == manifest["bundle_id"]
    assert verification["verification"]["ok"] is True


def test_build_bundle_from_payload_uses_stable_campaign_run_id(
    sample_campaign_run_payload: dict,
    tmp_path: Path,
) -> None:
    first_bundle = tmp_path / "bundle_a"
    second_bundle = tmp_path / "bundle_b"

    first_manifest = build_evidence_bundle_from_payload(
        campaign_run=sample_campaign_run_payload,
        output_dir=first_bundle,
        include_checklists=False,
        overwrite=True,
    )
    second_manifest = build_evidence_bundle_from_payload(
        campaign_run=sample_campaign_run_payload,
        output_dir=second_bundle,
        include_checklists=False,
        overwrite=True,
    )

    assert first_manifest["campaign_run_id"] == second_manifest["campaign_run_id"]
