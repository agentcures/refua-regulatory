from __future__ import annotations

import json
from pathlib import Path

from refua_regulatory.cli import main


def test_cli_build_verify_summary(sample_campaign_run_file: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle"

    rc_build = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert rc_build == 0
    assert output_dir.joinpath("manifest.json").exists()

    rc_verify = main(["verify", "--bundle-dir", str(output_dir)])
    assert rc_verify == 0

    rc_verify_json = main(["verify", "--bundle-dir", str(output_dir), "--json"])
    assert rc_verify_json == 0

    rc_summary = main(["summary", "--bundle-dir", str(output_dir)])
    assert rc_summary == 0

    rc_checklist = main(["checklist", "--bundle-dir", str(output_dir)])
    assert rc_checklist == 0


def test_cli_verify_fails_for_missing_bundle(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    rc_verify = main(["verify", "--bundle-dir", str(missing)])
    assert rc_verify == 1


def test_cli_build_overwrite_flag(sample_campaign_run_file: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle"

    rc_first = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert rc_first == 0

    # Non-empty directory without --overwrite should fail with CLI error path.
    rc_no_overwrite = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert rc_no_overwrite == 2

    rc_overwrite = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
            "--overwrite",
        ]
    )
    assert rc_overwrite == 0

    manifest = json.loads(output_dir.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)


def test_cli_checklist_strict_and_outputs(
    sample_campaign_run_file: Path,
    sample_data_manifest_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    rc_build = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
            "--data-manifest",
            str(sample_data_manifest_file),
        ]
    )
    assert rc_build == 0

    checklist_json = tmp_path / "checklist.json"
    checklist_md = tmp_path / "checklist.md"
    rc_strict = main(
        [
            "checklist",
            "--bundle-dir",
            str(output_dir),
            "--template",
            "core",
            "--strict",
            "--output-json",
            str(checklist_json),
            "--output-markdown",
            str(checklist_md),
        ]
    )
    assert rc_strict == 0
    assert checklist_json.exists()
    assert checklist_md.exists()


def test_cli_checklist_strict_fails_without_data_manifest(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    rc_build = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert rc_build == 0

    rc_strict = main(
        [
            "checklist",
            "--bundle-dir",
            str(output_dir),
            "--template",
            "core",
            "--strict",
        ]
    )
    assert rc_strict == 1


def test_cli_checklist_require_no_manual_review_fails_for_fda_template(
    sample_campaign_run_file: Path,
    sample_data_manifest_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    rc_build = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
            "--data-manifest",
            str(sample_data_manifest_file),
        ]
    )
    assert rc_build == 0

    rc_manual = main(
        [
            "checklist",
            "--bundle-dir",
            str(output_dir),
            "--template",
            "fda_cder_ai_ml",
            "--require-no-manual-review",
        ]
    )
    assert rc_manual == 1


def test_cli_build_checklist_strict_fails_when_core_requirements_missing(
    sample_campaign_run_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    rc_build = main(
        [
            "build",
            "--campaign-run",
            str(sample_campaign_run_file),
            "--output-dir",
            str(output_dir),
            "--checklist-template",
            "core",
            "--checklist-strict",
        ]
    )
    assert rc_build == 2
