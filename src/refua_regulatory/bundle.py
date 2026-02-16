from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from refua_regulatory.extractors import (
    extract_decisions_from_campaign,
    extract_model_provenance,
    infer_campaign_run_id,
    load_data_provenance_from_manifests,
)
from refua_regulatory.lineage import build_lineage_graph
from refua_regulatory.models import (
    ArtifactRef,
    DataProvenance,
    EvidenceBundleManifest,
    VerificationResult,
)
from refua_regulatory.provenance import collect_execution_provenance
from refua_regulatory.utils import (
    list_bundle_files,
    read_json_object,
    sha256_file,
    stable_id,
    to_plain_data,
    truncate_preview,
    utcnow_iso,
    write_json,
    write_jsonl,
)

BUNDLE_SCHEMA_VERSION = "1.0.0"
_DEFAULT_CHECKLIST_TEMPLATES = ("drug_discovery_comprehensive",)

_REQUIRED_BUNDLE_FILES = (
    "manifest.json",
    "decisions.jsonl",
    "lineage.json",
    "checksums.sha256",
)


def build_evidence_bundle(
    *,
    campaign_run_path: Path,
    output_dir: Path,
    source_kind: str = "refua-campaign",
    bundle_id: str | None = None,
    data_manifest_paths: list[Path] | None = None,
    extra_artifacts: list[Path] | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    dependency_names: list[str] | None = None,
    include_checklists: bool = True,
    checklist_templates: list[str] | None = None,
    checklist_strict: bool = False,
    checklist_require_no_manual_review: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    campaign_run_path = campaign_run_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    data_manifest_paths = list(data_manifest_paths or [])
    extra_artifacts = list(extra_artifacts or [])
    resolved_checklist_templates = list(checklist_templates or _DEFAULT_CHECKLIST_TEMPLATES)

    if not campaign_run_path.exists() or not campaign_run_path.is_file():
        raise ValueError(f"Campaign run file does not exist: {campaign_run_path}")

    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise ValueError(
            f"Output directory is not empty: {output_dir}. Use overwrite=True to replace."
        )

    if output_dir.exists() and overwrite:
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    payload = read_json_object(campaign_run_path)
    campaign_run_id = infer_campaign_run_id(payload, source_path=campaign_run_path)
    resolved_bundle_id = bundle_id or stable_id("bundle", campaign_run_id, utcnow_iso())

    decisions = extract_decisions_from_campaign(
        payload,
        campaign_run_id=campaign_run_id,
    )

    models = extract_model_provenance(
        payload,
        override_model_name=model_name,
        override_model_version=model_version,
    )

    datasets, data_warnings = _copy_and_load_data_manifests(
        output_dir=output_dir,
        artifacts_dir=artifacts_dir,
        data_manifest_paths=data_manifest_paths,
    )

    copied_artifacts, artifact_warnings = _copy_artifacts(
        campaign_run_path=campaign_run_path,
        artifacts_dir=artifacts_dir,
        extra_artifacts=extra_artifacts,
    )

    execution = collect_execution_provenance(
        cwd=campaign_run_path.parent,
        dependency_names=dependency_names,
    )

    lineage = build_lineage_graph(
        campaign_run_id=campaign_run_id,
        decisions=decisions,
        artifacts=copied_artifacts,
        model_provenance=models,
        data_provenance=datasets,
    )

    decisions_path = output_dir / "decisions.jsonl"
    write_jsonl(decisions_path, [to_plain_data(item) for item in decisions])

    lineage_path = output_dir / "lineage.json"
    write_json(lineage_path, to_plain_data(lineage))

    source_rel_path = str((artifacts_dir / "campaign_run.json").relative_to(output_dir))

    bootstrap_manifest = EvidenceBundleManifest(
        schema_version=BUNDLE_SCHEMA_VERSION,
        bundle_id=resolved_bundle_id,
        created_at=utcnow_iso(),
        campaign_run_id=campaign_run_id,
        source_kind=source_kind,
        source_rel_path=source_rel_path,
        decision_count=len(decisions),
        artifact_count=len(copied_artifacts),
        model_count=len(models),
        data_count=len(datasets),
        files=tuple(_bundle_file_list(output_dir, include_checksums=False)),
        model_provenance=tuple(models),
        data_provenance=tuple(datasets),
        execution_provenance=execution,
        checklist_reports=(),
        checklist_summary={},
        warnings=tuple([*data_warnings, *artifact_warnings]),
    )
    write_json(output_dir / "manifest.json", to_plain_data(bootstrap_manifest))
    _write_checksums(output_dir)

    checklist_reports: tuple[str, ...] = ()
    checklist_summary: dict[str, Any] = {}
    if include_checklists and resolved_checklist_templates:
        checklist_payloads, checklist_reports, checklist_summary = _generate_checklist_reports(
            output_dir=output_dir,
            templates=resolved_checklist_templates,
        )
        _enforce_checklist_policy(
            reports=checklist_payloads,
            strict=checklist_strict,
            require_no_manual_review=checklist_require_no_manual_review,
        )

    final_manifest = EvidenceBundleManifest(
        schema_version=BUNDLE_SCHEMA_VERSION,
        bundle_id=resolved_bundle_id,
        created_at=bootstrap_manifest.created_at,
        campaign_run_id=campaign_run_id,
        source_kind=source_kind,
        source_rel_path=source_rel_path,
        decision_count=len(decisions),
        artifact_count=len(copied_artifacts),
        model_count=len(models),
        data_count=len(datasets),
        files=tuple(_bundle_file_list(output_dir, include_checksums=False)),
        model_provenance=tuple(models),
        data_provenance=tuple(datasets),
        execution_provenance=execution,
        checklist_reports=checklist_reports,
        checklist_summary=checklist_summary,
        warnings=tuple([*data_warnings, *artifact_warnings]),
    )
    write_json(output_dir / "manifest.json", to_plain_data(final_manifest))
    _write_checksums(output_dir)

    return to_plain_data(final_manifest)


def verify_evidence_bundle(bundle_dir: Path) -> VerificationResult:
    bundle_dir = bundle_dir.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return VerificationResult(
            ok=False,
            checked_files=0,
            errors=(f"Bundle directory not found: {bundle_dir}",),
            warnings=(),
        )

    for rel_name in _REQUIRED_BUNDLE_FILES:
        if not bundle_dir.joinpath(rel_name).exists():
            errors.append(f"Missing required file: {rel_name}")

    manifest_path = bundle_dir / "manifest.json"
    manifest_payload: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            manifest_payload = read_json_object(manifest_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Invalid manifest.json: {exc}")

    checksum_path = bundle_dir / "checksums.sha256"
    checksum_entries: list[tuple[str, str]] = []
    if checksum_path.exists():
        try:
            checksum_entries = _parse_checksum_file(checksum_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Invalid checksums.sha256: {exc}")

    checked_files = 0
    for digest, rel_path in checksum_entries:
        if rel_path == "checksums.sha256":
            warnings.append("checksums.sha256 should not include itself")
            continue

        target = bundle_dir / rel_path
        if not target.exists() or not target.is_file():
            errors.append(f"Checksum file missing target: {rel_path}")
            continue

        actual = sha256_file(target)
        checked_files += 1
        if actual != digest:
            errors.append(
                f"Checksum mismatch for {rel_path}: expected {digest}, observed {actual}"
            )

    if manifest_payload is not None:
        files_field = manifest_payload.get("files")
        if isinstance(files_field, list):
            missing_from_manifest = []
            for rel_name in files_field:
                if not isinstance(rel_name, str):
                    errors.append("manifest.files must contain only strings")
                    break
                if not bundle_dir.joinpath(rel_name).exists():
                    missing_from_manifest.append(rel_name)
            if missing_from_manifest:
                errors.append(
                    "manifest.files contains missing files: "
                    + ", ".join(sorted(missing_from_manifest))
                )
        else:
            errors.append("manifest.files must be a list")

        decision_path = bundle_dir / "decisions.jsonl"
        if decision_path.exists():
            observed_decisions = _count_jsonl_lines(decision_path)
            declared_decisions = manifest_payload.get("decision_count")
            if isinstance(declared_decisions, int) and declared_decisions != observed_decisions:
                errors.append(
                    "Decision count mismatch: "
                    f"manifest={declared_decisions}, decisions.jsonl={observed_decisions}"
                )

    return VerificationResult(
        ok=(len(errors) == 0),
        checked_files=checked_files,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def load_bundle_summary(bundle_dir: Path) -> dict[str, Any]:
    bundle_dir = bundle_dir.expanduser().resolve()
    manifest = read_json_object(bundle_dir / "manifest.json")

    lineage = read_json_object(bundle_dir / "lineage.json")
    nodes = lineage.get("nodes")
    edges = lineage.get("edges")

    verification = verify_evidence_bundle(bundle_dir)

    return {
        "bundle_id": manifest.get("bundle_id"),
        "campaign_run_id": manifest.get("campaign_run_id"),
        "created_at": manifest.get("created_at"),
        "decision_count": manifest.get("decision_count"),
        "artifact_count": manifest.get("artifact_count"),
        "model_count": manifest.get("model_count"),
        "data_count": manifest.get("data_count"),
        "lineage": {
            "node_count": len(nodes) if isinstance(nodes, list) else 0,
            "edge_count": len(edges) if isinstance(edges, list) else 0,
        },
        "checklist_summary": (
            manifest.get("checklist_summary") if isinstance(manifest, dict) else {}
        ),
        "verification": to_plain_data(verification),
        "warnings_preview": truncate_preview(manifest.get("warnings", []), max_chars=400),
    }


def _copy_and_load_data_manifests(
    *,
    output_dir: Path,
    artifacts_dir: Path,
    data_manifest_paths: list[Path],
) -> tuple[list[DataProvenance], list[str]]:
    if not data_manifest_paths:
        return [], []

    data_dir = artifacts_dir / "data_manifests"
    data_dir.mkdir(parents=True, exist_ok=True)

    copied_paths: list[Path] = []
    warnings: list[str] = []

    for index, original in enumerate(data_manifest_paths, start=1):
        source = original.expanduser().resolve()
        if not source.exists() or not source.is_file():
            warnings.append(f"Missing data manifest: {source}")
            continue

        target_name = f"manifest_{index:03d}_{source.name}"
        target = data_dir / target_name
        shutil.copy2(source, target)
        copied_paths.append(target)

    records, parse_warnings = load_data_provenance_from_manifests(copied_paths)
    warnings.extend(parse_warnings)

    updated_records: list[DataProvenance] = []
    for idx, record in enumerate(records, start=1):
        if idx <= len(copied_paths):
            rel_path = str(copied_paths[idx - 1].relative_to(output_dir))
        else:
            rel_path = None
        updated_records.append(
            DataProvenance(
                dataset_id=record.dataset_id,
                version=record.version,
                source_url=record.source_url,
                sha256=record.sha256,
                license_name=record.license_name,
                manifest_rel_path=rel_path,
                metadata=dict(record.metadata),
            )
        )

    return updated_records, warnings


def _copy_artifacts(
    *,
    campaign_run_path: Path,
    artifacts_dir: Path,
    extra_artifacts: list[Path],
) -> tuple[list[ArtifactRef], list[str]]:
    warnings: list[str] = []
    artifact_refs: list[ArtifactRef] = []

    campaign_target = artifacts_dir / "campaign_run.json"
    shutil.copy2(campaign_run_path, campaign_target)

    artifact_refs.append(
        _artifact_ref(
            artifact_id="campaign_run",
            role="campaign_run",
            path=campaign_target,
            bundle_dir=artifacts_dir.parent,
            media_type="application/json",
        )
    )

    if extra_artifacts:
        extras_dir = artifacts_dir / "extras"
        extras_dir.mkdir(parents=True, exist_ok=True)

        for index, original in enumerate(extra_artifacts, start=1):
            source = original.expanduser().resolve()
            if not source.exists() or not source.is_file():
                warnings.append(f"Missing extra artifact: {source}")
                continue

            target_name = f"extra_{index:03d}_{source.name}"
            target = extras_dir / target_name
            shutil.copy2(source, target)

            artifact_refs.append(
                _artifact_ref(
                    artifact_id=f"extra_{index:03d}",
                    role="extra",
                    path=target,
                    bundle_dir=artifacts_dir.parent,
                    media_type=_guess_media_type(target),
                    metadata={"original_path": str(source)},
                )
            )

    return artifact_refs, warnings


def _artifact_ref(
    *,
    artifact_id: str,
    role: str,
    path: Path,
    bundle_dir: Path,
    media_type: str | None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactRef:
    rel_path = str(path.relative_to(bundle_dir))
    return ArtifactRef(
        artifact_id=artifact_id,
        role=role,
        rel_path=rel_path,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        media_type=media_type,
        metadata={} if metadata is None else dict(metadata),
    )


def _guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix in {".yaml", ".yml"}:
        return "application/yaml"
    if suffix == ".txt":
        return "text/plain"
    return "application/octet-stream"


def _bundle_file_list(bundle_dir: Path, *, include_checksums: bool) -> list[str]:
    names: list[str] = []
    for path in list_bundle_files(bundle_dir):
        rel_name = str(path.relative_to(bundle_dir))
        if not include_checksums and rel_name == "checksums.sha256":
            continue
        names.append(rel_name)
    return names


def _write_checksums(bundle_dir: Path) -> None:
    entries: list[tuple[str, str]] = []
    for path in list_bundle_files(bundle_dir):
        rel_name = str(path.relative_to(bundle_dir))
        if rel_name == "checksums.sha256":
            continue
        entries.append((sha256_file(path), rel_name))

    checksum_path = bundle_dir / "checksums.sha256"
    checksum_path.write_text(
        "".join(f"{digest}  {rel_name}\n" for digest, rel_name in entries),
        encoding="utf-8",
    )


def _parse_checksum_file(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            digest, rel_path = line.split("  ", maxsplit=1)
        except ValueError as exc:
            raise ValueError(f"Invalid checksum format on line {line_number}") from exc
        digest = digest.strip()
        rel_path = rel_path.strip()
        if len(digest) != 64:
            raise ValueError(f"Invalid checksum digest on line {line_number}")
        if not rel_path:
            raise ValueError(f"Invalid checksum path on line {line_number}")
        entries.append((digest, rel_path))
    return entries


def _count_jsonl_lines(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count


def _generate_checklist_reports(
    *,
    output_dir: Path,
    templates: list[str],
) -> tuple[list[dict[str, Any]], tuple[str, ...], dict[str, Any]]:
    from refua_regulatory.checklist import (
        evaluate_regulatory_checklist,
        render_checklist_markdown,
    )

    checklists_dir = output_dir / "checklists"
    checklists_dir.mkdir(parents=True, exist_ok=True)

    reports: list[dict[str, Any]] = []
    rel_paths: list[str] = []
    template_summaries: list[dict[str, Any]] = []

    for template in templates:
        report = evaluate_regulatory_checklist(output_dir, template=template)
        reports.append(report)

        json_path = checklists_dir / f"{template}.json"
        md_path = checklists_dir / f"{template}.md"

        write_json(json_path, report)
        md_path.write_text(render_checklist_markdown(report), encoding="utf-8")

        rel_paths.append(str(json_path.relative_to(output_dir)))
        rel_paths.append(str(md_path.relative_to(output_dir)))

        summary = report.get("summary", {})
        template_summaries.append(
            {
                "template": template,
                "total_checks": _safe_int(summary.get("total_checks")),
                "failed": _safe_int(summary.get("failed")),
                "manual_review": _safe_int(summary.get("manual_review")),
                "blocking_failed": _safe_int(summary.get("blocking_failed")),
                "auto_checks_passed": bool(summary.get("auto_checks_passed", False)),
                "submission_ready": bool(summary.get("submission_ready", False)),
            }
        )

    aggregate = {
        "template_count": len(template_summaries),
        "failed_templates": [
            item["template"] for item in template_summaries if int(item["failed"]) > 0
        ],
        "manual_review_templates": [
            item["template"] for item in template_summaries if int(item["manual_review"]) > 0
        ],
        "blocking_failed_templates": [
            item["template"] for item in template_summaries if int(item["blocking_failed"]) > 0
        ],
    }

    return reports, tuple(rel_paths), {"templates": template_summaries, "aggregate": aggregate}


def _enforce_checklist_policy(
    *,
    reports: list[dict[str, Any]],
    strict: bool,
    require_no_manual_review: bool,
) -> None:
    if not strict and not require_no_manual_review:
        return

    failed_templates: list[str] = []
    manual_templates: list[str] = []

    for report in reports:
        template = str(report.get("template", "<unknown>"))
        summary = report.get("summary", {})
        if not isinstance(summary, dict):
            continue

        if strict and _safe_int(summary.get("failed")) > 0:
            failed_templates.append(template)

        if require_no_manual_review and _safe_int(summary.get("manual_review")) > 0:
            manual_templates.append(template)

    errors: list[str] = []
    if failed_templates:
        errors.append(
            "Checklist strict mode failed for templates: " + ", ".join(sorted(failed_templates))
        )
    if manual_templates:
        errors.append(
            "Checklist no-manual-review mode failed for templates: "
            + ", ".join(sorted(manual_templates))
        )
    if errors:
        raise ValueError("; ".join(errors))


def _safe_int(value: Any) -> int:
    return int(value) if isinstance(value, int) else 0
