from __future__ import annotations

import json
from pathlib import Path

from refua_regulatory import checklist as checklist_module
from refua_regulatory.bundle import build_evidence_bundle, verify_evidence_bundle
from refua_regulatory.utils import sha256_file


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
    assert output_dir.joinpath(
        "checklists", "drug_discovery_comprehensive.json"
    ).exists()
    assert output_dir.joinpath("checklists", "drug_discovery_comprehensive.md").exists()

    verification = verify_evidence_bundle(output_dir)
    assert verification.ok
    assert verification.checked_files > 0


def test_verify_detects_tampering(
    sample_campaign_run_file: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
    )

    tampered = output_dir / "artifacts" / "campaign_run.json"
    tampered.write_text(
        tampered.read_text(encoding="utf-8") + "\n#tampered\n", encoding="utf-8"
    )

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


def test_verify_fails_when_bundle_contains_unchecked_extra_file(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
        include_checklists=False,
    )

    unchecked = output_dir / "artifacts" / "injected.txt"
    unchecked.write_text("tampered\n", encoding="utf-8")

    verification = verify_evidence_bundle(output_dir)
    assert not verification.ok
    assert any("missing checksum entries" in item for item in verification.errors)


def test_verify_fails_for_empty_checksums_file(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
        include_checklists=False,
    )

    output_dir.joinpath("checksums.sha256").write_text("", encoding="utf-8")

    verification = verify_evidence_bundle(output_dir)
    assert not verification.ok
    assert any("contains no file entries" in item for item in verification.errors)


def test_build_strict_checklist_failure_still_writes_consistent_bundle(
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

    manifest = json.loads(output_dir.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert "checklists/core.json" in manifest["checklist_reports"]
    assert "checklists/core.md" in manifest["checklist_reports"]

    verification = verify_evidence_bundle(output_dir)
    assert verification.ok


def test_verify_detects_semantic_manifest_tampering_after_checksum_rewrite(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
        include_checklists=False,
    )

    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "999.0.0"
    manifest["artifact_count"] = 999
    manifest["model_count"] = 999
    manifest["data_count"] = 999
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    checksum_lines: list[str] = []
    for path in sorted(
        candidate
        for candidate in output_dir.rglob("*")
        if candidate.is_file() and candidate.name != "checksums.sha256"
    ):
        checksum_lines.append(f"{sha256_file(path)}  {path.relative_to(output_dir)}")
    output_dir.joinpath("checksums.sha256").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="utf-8",
    )

    verification = verify_evidence_bundle(output_dir)
    assert not verification.ok
    assert any("Unsupported manifest schema_version" in item for item in verification.errors)
    assert any("artifact_count mismatch" in item for item in verification.errors)
    assert any("model_count mismatch" in item for item in verification.errors)
    assert any("data_count mismatch" in item for item in verification.errors)


def test_build_multiple_checklists_reuses_single_verification_pass(
    sample_campaign_run_file: Path,
    sample_data_manifest_file: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "bundle"
    verification_calls = 0
    original_verify = checklist_module.verify_evidence_bundle

    def counting_verify(bundle_dir: Path):
        nonlocal verification_calls
        verification_calls += 1
        return original_verify(bundle_dir)

    monkeypatch.setattr(checklist_module, "verify_evidence_bundle", counting_verify)

    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=output_dir,
        data_manifest_paths=[sample_data_manifest_file],
        checklist_templates=["core", "fda_cder_ai_ml"],
    )

    assert verification_calls == 1
