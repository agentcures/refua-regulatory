from __future__ import annotations

from pathlib import Path

from refua_regulatory.bundle import build_evidence_bundle
from refua_regulatory.checklist import (
    available_checklist_templates,
    evaluate_regulatory_checklist,
    render_checklist_markdown,
)


def test_available_templates_contains_core_and_fda() -> None:
    templates = available_checklist_templates()
    assert "core" in templates
    assert "drug_discovery_comprehensive" in templates
    assert "fda_cder_ai_ml" in templates


def test_core_checklist_passes_automated_checks_with_data(
    sample_campaign_run_file: Path,
    sample_data_manifest_file: Path,
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=bundle_dir,
        data_manifest_paths=[sample_data_manifest_file],
    )

    report = evaluate_regulatory_checklist(bundle_dir, template="core")
    summary = report["summary"]
    assert summary["failed"] == 0
    assert summary["auto_checks_passed"] is True


def test_fda_template_includes_manual_review_items(
    sample_campaign_run_file: Path,
    sample_data_manifest_file: Path,
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=bundle_dir,
        data_manifest_paths=[sample_data_manifest_file],
    )

    report = evaluate_regulatory_checklist(bundle_dir, template="fda_cder_ai_ml")
    summary = report["summary"]
    assert summary["manual_review"] >= 2
    assert summary["submission_ready"] is False

    markdown = render_checklist_markdown(report)
    assert "Regulatory Checklist" in markdown
    assert "submission_mapping" in markdown


def test_comprehensive_template_has_manual_review_sections(
    sample_campaign_run_file: Path,
    sample_data_manifest_file: Path,
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=sample_campaign_run_file,
        output_dir=bundle_dir,
        data_manifest_paths=[sample_data_manifest_file],
    )

    report = evaluate_regulatory_checklist(
        bundle_dir,
        template="drug_discovery_comprehensive",
    )
    summary = report["summary"]
    assert summary["failed"] == 0
    assert summary["manual_review"] >= 1


def test_validation_first_policy_uses_executed_tool_order(tmp_path: Path) -> None:
    payload = {
        "objective": "Execution order check",
        "plan": {
            "calls": [
                {"tool": "refua_validate_spec", "args": {}},
                {"tool": "refua_fold", "args": {}},
            ]
        },
        "results": [
            {
                "tool": "refua_fold",
                "args": {},
                "output": {"backend": "refua", "warnings": []},
            }
        ],
    }
    campaign_run = tmp_path / "campaign.json"
    campaign_run.write_text(__import__("json").dumps(payload) + "\n", encoding="utf-8")

    bundle_dir = tmp_path / "bundle"
    build_evidence_bundle(
        campaign_run_path=campaign_run,
        output_dir=bundle_dir,
        include_checklists=False,
    )

    report = evaluate_regulatory_checklist(bundle_dir, template="core")
    item = next(entry for entry in report["items"] if entry["id"] == "validation_first_policy")

    assert item["status"] == "fail"
    assert "first_executed_tool=refua_fold" in item["evidence"]
