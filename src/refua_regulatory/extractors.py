from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from refua_regulatory.models import DataProvenance, DecisionRecord, ModelProvenance
from refua_regulatory.utils import (
    stable_id,
    to_plain_data,
    truncate_preview,
    utcnow_iso,
)

_TOOL_TO_MODEL = {
    "refua_validate_spec": "refua-validator",
    "refua_fold": "refua-boltz",
    "refua_affinity": "refua-boltz-affinity",
    "refua_antibody_design": "refua-boltzgen-antibody",
    "refua_admet_profile": "refua-admet",
    "refua_job": "refua-job-tracker",
}


def infer_campaign_run_id(payload: dict[str, Any], *, source_path: Path | None = None) -> str:
    explicit = payload.get("campaign_run_id") or payload.get("run_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    objective = str(payload.get("objective") or "")
    planner_text = str(payload.get("planner_response_text") or "")
    source_key = str(source_path or "")
    return stable_id("campaign_run", objective, planner_text, source_key)


def extract_decisions_from_campaign(
    payload: dict[str, Any],
    *,
    campaign_run_id: str,
) -> list[DecisionRecord]:
    decisions: list[DecisionRecord] = []
    step_index = 1

    objective = str(payload.get("objective") or "").strip()
    if objective:
        decisions.append(
            _decision(
                campaign_run_id=campaign_run_id,
                step_index=step_index,
                decision_type="objective",
                actor="campaign",
                rationale="Campaign objective accepted.",
                output_preview=objective,
            )
        )
        step_index += 1

    plan = payload.get("plan")
    if isinstance(plan, dict):
        decisions.append(
            _decision(
                campaign_run_id=campaign_run_id,
                step_index=step_index,
                decision_type="planning",
                actor="planner",
                rationale="Initial tool plan generated.",
                output_preview=truncate_preview(plan),
                output_refs=("plan:initial",),
            )
        )
        step_index += 1

    iterations = payload.get("iterations")
    if isinstance(iterations, list):
        for idx, item in enumerate(iterations, start=1):
            if not isinstance(item, dict):
                continue

            policy = item.get("policy")
            if isinstance(policy, dict):
                decisions.append(
                    _decision(
                        campaign_run_id=campaign_run_id,
                        step_index=step_index,
                        decision_type="policy",
                        actor="policy",
                        rationale=f"Policy evaluation completed for round {idx}.",
                        output_preview=truncate_preview(policy),
                        metadata={"round_index": idx},
                    )
                )
                step_index += 1

            critic = item.get("critic")
            if isinstance(critic, dict):
                decisions.append(
                    _decision(
                        campaign_run_id=campaign_run_id,
                        step_index=step_index,
                        decision_type="critic",
                        actor="critic",
                        rationale=f"Critic evaluation completed for round {idx}.",
                        output_preview=truncate_preview(critic),
                        metadata={"round_index": idx},
                    )
                )
                step_index += 1

    final_plan = payload.get("final_plan")
    if isinstance(final_plan, dict):
        if isinstance(plan, dict):
            rendered_plan = json.dumps(to_plain_data(plan), sort_keys=True)
        else:
            rendered_plan = ""
        rendered_final = json.dumps(to_plain_data(final_plan), sort_keys=True)
        if rendered_final != rendered_plan:
            decisions.append(
                _decision(
                    campaign_run_id=campaign_run_id,
                    step_index=step_index,
                    decision_type="planning",
                    actor="planner",
                    rationale="Final autonomous plan approved.",
                    output_preview=truncate_preview(final_plan),
                    output_refs=("plan:final",),
                    metadata={"stage": "final"},
                )
            )
            step_index += 1

    results = payload.get("results")
    if isinstance(results, list):
        for idx, item in enumerate(results, start=1):
            if not isinstance(item, dict):
                continue
            tool = item.get("tool")
            args = item.get("args")
            output = item.get("output")

            tool_name = str(tool) if isinstance(tool, str) else None
            tool_args = dict(args) if isinstance(args, dict) else {}

            decisions.append(
                _decision(
                    campaign_run_id=campaign_run_id,
                    step_index=step_index,
                    decision_type="tool_call",
                    actor="executor",
                    rationale=f"Dispatch tool call #{idx}.",
                    tool=tool_name,
                    args=tool_args,
                    output_preview=None,
                    input_refs=(f"tool:{tool_name or 'unknown'}",),
                    output_refs=(f"result:{idx}",),
                    metadata={"tool_index": idx},
                )
            )
            step_index += 1

            decisions.append(
                _decision(
                    campaign_run_id=campaign_run_id,
                    step_index=step_index,
                    decision_type="tool_result",
                    actor="executor",
                    rationale=f"Captured tool result #{idx}.",
                    tool=tool_name,
                    args=tool_args,
                    output_preview=truncate_preview(output),
                    input_refs=(f"result:{idx}",),
                    output_refs=(f"artifact:tool_result:{idx}",),
                    metadata={"tool_index": idx},
                )
            )
            step_index += 1

    warnings = payload.get("warnings")
    if isinstance(warnings, list) and warnings:
        decisions.append(
            _decision(
                campaign_run_id=campaign_run_id,
                step_index=step_index,
                decision_type="note",
                actor="system",
                rationale="Run emitted warnings.",
                output_preview=truncate_preview(warnings),
            )
        )

    if not decisions:
        decisions.append(
            _decision(
                campaign_run_id=campaign_run_id,
                step_index=1,
                decision_type="note",
                actor="system",
                rationale="No structured decisions were detected in payload.",
                output_preview=truncate_preview(payload),
            )
        )

    return decisions


def extract_model_provenance(
    payload: dict[str, Any],
    *,
    override_model_name: str | None = None,
    override_model_version: str | None = None,
) -> list[ModelProvenance]:
    models: list[ModelProvenance] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()

    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool")
            args = item.get("args")
            output = item.get("output")

            tool_name = str(tool) if isinstance(tool, str) else None
            if tool_name is None:
                continue

            output_map = output if isinstance(output, dict) else {}
            raw_backend = output_map.get("backend")
            backend = raw_backend if isinstance(raw_backend, str) else None

            model_name = override_model_name or _TOOL_TO_MODEL.get(tool_name, tool_name)
            model_version = override_model_version
            if model_version is None:
                version_candidate = output_map.get("model_version")
                if isinstance(version_candidate, str) and version_candidate.strip():
                    model_version = version_candidate.strip()

            params = dict(args) if isinstance(args, dict) else {}
            key = (model_name, model_version, tool_name, backend)
            if key in seen:
                continue
            seen.add(key)

            models.append(
                ModelProvenance(
                    model_name=model_name,
                    model_version=model_version,
                    tool=tool_name,
                    backend=backend,
                    parameters=params,
                )
            )

    if not models and override_model_name:
        models.append(
            ModelProvenance(
                model_name=override_model_name,
                model_version=override_model_version,
                tool=None,
                backend=None,
                parameters={},
            )
        )

    return models


def load_data_provenance_from_manifests(
    manifest_paths: list[Path],
) -> tuple[list[DataProvenance], list[str]]:
    records: list[DataProvenance] = []
    warnings: list[str] = []

    for path in manifest_paths:
        if not path.exists():
            warnings.append(f"Missing data manifest: {path}")
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Failed to parse data manifest {path}: {exc}")
            continue

        if not isinstance(payload, dict):
            warnings.append(f"Data manifest is not a JSON object: {path}")
            continue

        dataset_id = payload.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            warnings.append(f"Data manifest missing dataset_id: {path}")
            continue

        version = payload.get("version")
        version_value = str(version) if isinstance(version, str | int | float) else None

        source_url = None
        source_sha256 = None
        license_name = None

        source = payload.get("source")
        if isinstance(source, dict):
            raw_url = source.get("url")
            raw_sha = source.get("sha256")
            if isinstance(raw_url, str):
                source_url = raw_url
            if isinstance(raw_sha, str):
                source_sha256 = raw_sha

        if source_url is None:
            raw_source_url = payload.get("source_url")
            if isinstance(raw_source_url, str):
                source_url = raw_source_url

        if source_sha256 is None:
            raw_sha = payload.get("sha256")
            if isinstance(raw_sha, str):
                source_sha256 = raw_sha

        raw_license = payload.get("license_name")
        if isinstance(raw_license, str):
            license_name = raw_license

        records.append(
            DataProvenance(
                dataset_id=dataset_id.strip(),
                version=version_value,
                source_url=source_url,
                sha256=source_sha256,
                license_name=license_name,
                metadata={
                    "manifest_name": path.name,
                    "api_pages": payload.get("api_pages"),
                    "api_rows": payload.get("api_rows"),
                    "row_count": payload.get("row_count"),
                },
            )
        )

    return records, warnings


def _decision(
    *,
    campaign_run_id: str,
    step_index: int,
    decision_type: str,
    actor: str,
    rationale: str,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
    output_preview: str | None = None,
    input_refs: tuple[str, ...] = (),
    output_refs: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> DecisionRecord:
    decision_id = stable_id(campaign_run_id, str(step_index), decision_type, tool or "")
    return DecisionRecord(
        decision_id=decision_id,
        campaign_run_id=campaign_run_id,
        step_index=step_index,
        timestamp=utcnow_iso(),
        decision_type=decision_type,  # type: ignore[arg-type]
        actor=actor,
        rationale=rationale,
        tool=tool,
        args={} if args is None else dict(args),
        output_preview=output_preview,
        input_refs=input_refs,
        output_refs=output_refs,
        metadata={} if metadata is None else dict(metadata),
    )
