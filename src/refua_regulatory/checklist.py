from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from refua_regulatory.bundle import verify_evidence_bundle
from refua_regulatory.utils import read_json_object, to_plain_data, utcnow_iso

ChecklistStatus = Literal["pass", "fail", "manual_review", "not_applicable"]
ChecklistSeverity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    check_id: str
    title: str
    domain: str
    severity: ChecklistSeverity
    automated: bool
    regulatory_tags: tuple[str, ...]
    evaluate: Callable[[_ChecklistContext], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _ChecklistContext:
    bundle_dir: Path
    manifest: dict[str, Any] | None
    lineage: dict[str, Any] | None
    decisions: list[dict[str, Any]]
    campaign_run: dict[str, Any] | None
    verification_ok: bool
    verification_errors: tuple[str, ...]
    verification_warnings: tuple[str, ...]

    @property
    def decision_count(self) -> int:
        if self.manifest is None:
            return 0
        value = self.manifest.get("decision_count")
        return int(value) if isinstance(value, int) else 0

    @property
    def model_count(self) -> int:
        if self.manifest is None:
            return 0
        value = self.manifest.get("model_count")
        return int(value) if isinstance(value, int) else 0

    @property
    def data_count(self) -> int:
        if self.manifest is None:
            return 0
        value = self.manifest.get("data_count")
        return int(value) if isinstance(value, int) else 0

    @property
    def manifest_warnings(self) -> list[str]:
        if self.manifest is None:
            return []
        value = self.manifest.get("warnings")
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    @property
    def objective(self) -> str:
        if self.campaign_run is None:
            return ""
        value = self.campaign_run.get("objective")
        return str(value).strip() if isinstance(value, str) else ""

    @property
    def planner_response_text(self) -> str:
        if self.campaign_run is None:
            return ""
        value = self.campaign_run.get("planner_response_text")
        return str(value).strip() if isinstance(value, str) else ""

    @property
    def plan_calls(self) -> list[dict[str, Any]]:
        if self.campaign_run is None:
            return []

        final_plan = self.campaign_run.get("final_plan")
        if isinstance(final_plan, dict):
            calls = final_plan.get("calls")
            if isinstance(calls, list):
                return [item for item in calls if isinstance(item, dict)]

        plan = self.campaign_run.get("plan")
        if isinstance(plan, dict):
            calls = plan.get("calls")
            if isinstance(calls, list):
                return [item for item in calls if isinstance(item, dict)]

        return []

    @property
    def tool_results(self) -> list[dict[str, Any]]:
        if self.campaign_run is None:
            return []
        results = self.campaign_run.get("results")
        if not isinstance(results, list):
            return []
        return [item for item in results if isinstance(item, dict)]

    @property
    def first_tool(self) -> str | None:
        calls = self.plan_calls
        if not calls:
            return None
        tool = calls[0].get("tool")
        return tool if isinstance(tool, str) else None

    @property
    def tools_used(self) -> list[str]:
        names: list[str] = []
        for call in self.plan_calls:
            tool = call.get("tool")
            if isinstance(tool, str):
                names.append(tool)
        return names


def available_checklist_templates() -> list[str]:
    return sorted(_TEMPLATES)


def evaluate_regulatory_checklist(
    bundle_dir: Path,
    *,
    template: str = "core",
) -> dict[str, Any]:
    if template not in _TEMPLATES:
        available = ", ".join(available_checklist_templates())
        raise ValueError(f"Unknown checklist template '{template}'. Available: {available}")

    resolved_dir = bundle_dir.expanduser().resolve()
    manifest = _safe_read_json_object(resolved_dir / "manifest.json")
    lineage = _safe_read_json_object(resolved_dir / "lineage.json")
    decisions = _load_decisions(resolved_dir / "decisions.jsonl")
    campaign_run = _safe_read_json_object(resolved_dir / "artifacts" / "campaign_run.json")
    verification = verify_evidence_bundle(resolved_dir)

    context = _ChecklistContext(
        bundle_dir=resolved_dir,
        manifest=manifest,
        lineage=lineage,
        decisions=decisions,
        campaign_run=campaign_run,
        verification_ok=verification.ok,
        verification_errors=verification.errors,
        verification_warnings=verification.warnings,
    )

    items: list[dict[str, Any]] = []
    for check in _TEMPLATES[template]:
        payload = check.evaluate(context)
        item = {
            "id": check.check_id,
            "title": check.title,
            "domain": check.domain,
            "severity": check.severity,
            "automated": check.automated,
            "regulatory_tags": list(check.regulatory_tags),
            "status": payload["status"],
            "details": payload.get("details", ""),
            "recommendation": payload.get("recommendation", ""),
            "evidence": payload.get("evidence", []),
        }
        items.append(item)

    summary = _build_summary(items)
    report = {
        "schema_version": "1.1.0",
        "template": template,
        "generated_at": utcnow_iso(),
        "bundle_dir": str(resolved_dir),
        "bundle_id": manifest.get("bundle_id") if isinstance(manifest, dict) else None,
        "campaign_run_id": (
            manifest.get("campaign_run_id") if isinstance(manifest, dict) else None
        ),
        "summary": summary,
        "items": items,
    }
    return to_plain_data(report)


def render_checklist_markdown(report: dict[str, Any]) -> str:
    template = report.get("template", "<unknown>")
    bundle_id = report.get("bundle_id", "<none>")
    campaign_run_id = report.get("campaign_run_id", "<none>")
    generated_at = report.get("generated_at", "<none>")
    summary = report.get("summary", {})
    items = report.get("items", [])

    lines = [
        f"# Regulatory Checklist: {template}",
        "",
        f"- Bundle ID: `{bundle_id}`",
        f"- Campaign Run ID: `{campaign_run_id}`",
        f"- Generated At: `{generated_at}`",
        "",
        "## Summary",
        "",
        f"- Total Checks: `{summary.get('total_checks', 0)}`",
        f"- Passed: `{summary.get('passed', 0)}`",
        f"- Failed: `{summary.get('failed', 0)}`",
        f"- Manual Review: `{summary.get('manual_review', 0)}`",
        f"- Not Applicable: `{summary.get('not_applicable', 0)}`",
        f"- Auto Checks Passed: `{summary.get('auto_checks_passed', False)}`",
        f"- Submission Ready: `{summary.get('submission_ready', False)}`",
        f"- Blocking Failed: `{summary.get('blocking_failed', 0)}`",
        "",
        "## Check Items",
        "",
        "| ID | Domain | Severity | Automated | Status | Details |",
        "|---|---|---|---|---|---|",
    ]

    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            check_id = item.get("id", "<unknown>")
            domain = item.get("domain", "<unknown>")
            severity = item.get("severity", "<unknown>")
            automated = item.get("automated", False)
            status = item.get("status", "<unknown>")
            details = str(item.get("details", "")).replace("|", "\\|")
            lines.append(
                f"| {check_id} | {domain} | {severity} | {automated} | {status} | {details} |"
            )

    return "\n".join(lines) + "\n"


def _safe_read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return read_json_object(path)
    except Exception:  # noqa: BLE001
        return None


def _load_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []

    decisions: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            decisions.append(payload)
    return decisions


def _build_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in items if item.get("status") == "pass")
    failed = sum(1 for item in items if item.get("status") == "fail")
    manual_review = sum(1 for item in items if item.get("status") == "manual_review")
    not_applicable = sum(1 for item in items if item.get("status") == "not_applicable")

    auto_failed = sum(
        1 for item in items if item.get("automated") and item.get("status") == "fail"
    )
    auto_manual = sum(
        1 for item in items if item.get("automated") and item.get("status") == "manual_review"
    )

    blocking_failed = sum(
        1
        for item in items
        if item.get("status") == "fail" and item.get("severity") in {"critical", "high"}
    )

    by_severity = {
        "critical": {
            "pass": _count(items, severity="critical", status="pass"),
            "fail": _count(items, severity="critical", status="fail"),
            "manual_review": _count(
                items,
                severity="critical",
                status="manual_review",
            ),
        },
        "high": {
            "pass": _count(items, severity="high", status="pass"),
            "fail": _count(items, severity="high", status="fail"),
            "manual_review": _count(items, severity="high", status="manual_review"),
        },
        "medium": {
            "pass": _count(items, severity="medium", status="pass"),
            "fail": _count(items, severity="medium", status="fail"),
            "manual_review": _count(
                items,
                severity="medium",
                status="manual_review",
            ),
        },
        "low": {
            "pass": _count(items, severity="low", status="pass"),
            "fail": _count(items, severity="low", status="fail"),
            "manual_review": _count(items, severity="low", status="manual_review"),
        },
    }

    return {
        "total_checks": len(items),
        "passed": passed,
        "failed": failed,
        "manual_review": manual_review,
        "not_applicable": not_applicable,
        "auto_checks_passed": auto_failed == 0 and auto_manual == 0,
        "submission_ready": failed == 0 and manual_review == 0,
        "blocking_failed": blocking_failed,
        "by_severity": by_severity,
    }


def _count(
    items: list[dict[str, Any]],
    *,
    severity: str,
    status: str,
) -> int:
    return sum(
        1
        for item in items
        if item.get("severity") == severity and item.get("status") == status
    )


def _flatten_keys(value: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.add(path.lower())
            keys.update(_flatten_keys(nested, path))
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            keys.update(_flatten_keys(nested, path))
    return keys


def _check_bundle_structure(context: _ChecklistContext) -> dict[str, Any]:
    required = (
        "manifest.json",
        "decisions.jsonl",
        "lineage.json",
        "checksums.sha256",
        "artifacts/campaign_run.json",
    )
    missing = [name for name in required if not context.bundle_dir.joinpath(name).exists()]
    if missing:
        return {
            "status": "fail",
            "details": "Missing required bundle files.",
            "recommendation": "Rebuild bundle and ensure required artifacts are present.",
            "evidence": missing,
        }
    return {
        "status": "pass",
        "details": "All required bundle files are present.",
        "recommendation": "",
        "evidence": list(required),
    }


def _check_integrity_verification(context: _ChecklistContext) -> dict[str, Any]:
    if context.verification_ok:
        return {
            "status": "pass",
            "details": "Bundle integrity verification passed.",
            "recommendation": "",
            "evidence": ["verify_evidence_bundle.ok=true"],
        }
    return {
        "status": "fail",
        "details": "Bundle integrity verification failed.",
        "recommendation": "Regenerate bundle and investigate checksum or missing-file errors.",
        "evidence": list(context.verification_errors),
    }


def _check_objective_defined(context: _ChecklistContext) -> dict[str, Any]:
    if context.objective:
        return {
            "status": "pass",
            "details": "Campaign objective is present.",
            "recommendation": "",
            "evidence": [context.objective],
        }
    return {
        "status": "fail",
        "details": "Campaign objective is missing.",
        "recommendation": "Set a clear, measurable campaign objective in run payload.",
        "evidence": [],
    }


def _check_executable_plan_present(context: _ChecklistContext) -> dict[str, Any]:
    calls = context.plan_calls
    if calls:
        return {
            "status": "pass",
            "details": "Executable tool plan is present.",
            "recommendation": "",
            "evidence": [f"call_count={len(calls)}"],
        }
    return {
        "status": "fail",
        "details": "No executable tool plan calls were found.",
        "recommendation": "Ensure plan/final_plan contains a `calls` list.",
        "evidence": [],
    }


def _check_validation_first_policy(context: _ChecklistContext) -> dict[str, Any]:
    first_tool = context.first_tool
    if first_tool is None:
        return {
            "status": "fail",
            "details": "No first tool is available for validation-first policy.",
            "recommendation": "Provide a non-empty plan.",
            "evidence": [],
        }
    if first_tool == "refua_validate_spec":
        return {
            "status": "pass",
            "details": "Validation-first policy satisfied.",
            "recommendation": "",
            "evidence": [f"first_tool={first_tool}"],
        }
    return {
        "status": "fail",
        "details": "Plan does not start with `refua_validate_spec`.",
        "recommendation": "Run validate_spec before expensive fold/affinity calls.",
        "evidence": [f"first_tool={first_tool}"],
    }


def _check_tool_results_present(context: _ChecklistContext) -> dict[str, Any]:
    results = context.tool_results
    if results:
        return {
            "status": "pass",
            "details": "Tool execution results are present.",
            "recommendation": "",
            "evidence": [f"result_count={len(results)}"],
        }
    return {
        "status": "manual_review",
        "details": "No tool execution results were found (dry-run or missing outputs).",
        "recommendation": "Attach execution outputs for reproducible evidence.",
        "evidence": [],
    }


def _check_traceability(context: _ChecklistContext) -> dict[str, Any]:
    if context.manifest is None:
        return {
            "status": "fail",
            "details": "Manifest is missing or invalid.",
            "recommendation": "Rebuild the evidence bundle.",
            "evidence": [],
        }

    if context.decision_count < 1:
        return {
            "status": "fail",
            "details": "No decision records were captured.",
            "recommendation": "Ensure campaign outputs include plan/results and rebuild bundle.",
            "evidence": [f"decision_count={context.decision_count}"],
        }

    lineage_nodes = context.lineage.get("nodes") if isinstance(context.lineage, dict) else None
    lineage_edges = context.lineage.get("edges") if isinstance(context.lineage, dict) else None
    node_count = len(lineage_nodes) if isinstance(lineage_nodes, list) else 0
    edge_count = len(lineage_edges) if isinstance(lineage_edges, list) else 0

    if node_count == 0 or edge_count == 0:
        return {
            "status": "fail",
            "details": "Lineage graph is empty or malformed.",
            "recommendation": "Inspect `lineage.json` generation and rebuild.",
            "evidence": [f"node_count={node_count}", f"edge_count={edge_count}"],
        }

    return {
        "status": "pass",
        "details": "Decision trail and lineage graph are present.",
        "recommendation": "",
        "evidence": [
            f"decision_count={context.decision_count}",
            f"node_count={node_count}",
            f"edge_count={edge_count}",
        ],
    }


def _check_model_provenance(context: _ChecklistContext) -> dict[str, Any]:
    if context.model_count < 1:
        return {
            "status": "fail",
            "details": "No model provenance records were captured.",
            "recommendation": "Include tool results and model metadata in campaign output.",
            "evidence": [f"model_count={context.model_count}"],
        }
    return {
        "status": "pass",
        "details": "Model provenance records are present.",
        "recommendation": "",
        "evidence": [f"model_count={context.model_count}"],
    }


def _check_data_provenance(context: _ChecklistContext) -> dict[str, Any]:
    if context.data_count < 1:
        return {
            "status": "fail",
            "details": "No data provenance records were captured.",
            "recommendation": (
                "Provide `--data-manifest` inputs during bundle build when external datasets "
                "inform campaign decisions."
            ),
            "evidence": [f"data_count={context.data_count}"],
        }
    return {
        "status": "pass",
        "details": "Data provenance records are present.",
        "recommendation": "",
        "evidence": [f"data_count={context.data_count}"],
    }


def _check_execution_provenance(context: _ChecklistContext) -> dict[str, Any]:
    if context.manifest is None:
        return {
            "status": "fail",
            "details": "Manifest is missing or invalid.",
            "recommendation": "Rebuild bundle.",
            "evidence": [],
        }

    execution = context.manifest.get("execution_provenance")
    if not isinstance(execution, dict):
        return {
            "status": "fail",
            "details": "Execution provenance block is missing.",
            "recommendation": "Capture execution provenance during bundle generation.",
            "evidence": [],
        }

    runtime = execution.get("runtime")
    git = execution.get("git")
    dependencies = execution.get("dependencies")
    if not isinstance(runtime, dict) or not isinstance(git, dict) or not isinstance(
        dependencies,
        dict,
    ):
        return {
            "status": "fail",
            "details": "Execution provenance block is malformed.",
            "recommendation": "Inspect provenance serialization and rebuild bundle.",
            "evidence": [],
        }

    return {
        "status": "pass",
        "details": "Execution provenance is present and structured.",
        "recommendation": "",
        "evidence": [
            f"runtime_keys={len(runtime)}",
            f"git_available={git.get('available')}",
            f"dependency_keys={len(dependencies)}",
        ],
    }


def _check_uncertainty_reporting(context: _ChecklistContext) -> dict[str, Any]:
    results = context.tool_results
    if not results:
        return {
            "status": "manual_review",
            "details": "No tool results available to evaluate uncertainty reporting.",
            "recommendation": "Attach execution outputs with confidence/uncertainty fields.",
            "evidence": [],
        }

    uncertainty_tokens = {
        "binding_probability",
        "confidence",
        "confidence_score",
        "uncertainty",
        "ci_low",
        "ci_high",
        "warnings",
    }

    matched: set[str] = set()
    for item in results:
        output = item.get("output")
        keys = _flatten_keys(output)
        for token in uncertainty_tokens:
            if any(token in key for key in keys):
                matched.add(token)

    if matched:
        return {
            "status": "pass",
            "details": "Uncertainty/confidence fields were detected in outputs.",
            "recommendation": "",
            "evidence": sorted(matched),
        }

    return {
        "status": "fail",
        "details": "No uncertainty/confidence fields detected in tool outputs.",
        "recommendation": "Include confidence metrics and uncertainty qualifiers in outputs.",
        "evidence": [],
    }


def _check_safety_signal_capture(context: _ChecklistContext) -> dict[str, Any]:
    results = context.tool_results
    if not results:
        return {
            "status": "manual_review",
            "details": "No tool results available to evaluate safety signal capture.",
            "recommendation": "Attach safety-related outputs (ADMET/toxicity/warnings).",
            "evidence": [],
        }

    safety_tokens = {
        "admet",
        "tox",
        "toxic",
        "hERG",
        "ames",
        "warning",
        "warnings",
        "assessment",
        "safety",
    }

    matched: set[str] = set()
    for item in results:
        output = item.get("output")
        keys = _flatten_keys(output)
        for token in safety_tokens:
            token_l = token.lower()
            if any(token_l in key for key in keys):
                matched.add(token_l)

    if matched:
        return {
            "status": "pass",
            "details": "Safety-related signal fields are present in outputs.",
            "recommendation": "",
            "evidence": sorted(matched),
        }

    return {
        "status": "fail",
        "details": "No safety-related fields detected in tool outputs.",
        "recommendation": "Include ADMET/toxicity/warning outputs in decision evidence.",
        "evidence": [],
    }


def _check_reproducibility_identifiers(context: _ChecklistContext) -> dict[str, Any]:
    if context.manifest is None:
        return {
            "status": "fail",
            "details": "Manifest is missing.",
            "recommendation": "Rebuild bundle.",
            "evidence": [],
        }

    required = (
        "bundle_id",
        "campaign_run_id",
        "created_at",
        "source_rel_path",
        "decision_count",
    )
    missing = [name for name in required if name not in context.manifest]
    if missing:
        return {
            "status": "fail",
            "details": "Manifest is missing reproducibility identifiers.",
            "recommendation": "Populate missing identifiers during bundle generation.",
            "evidence": missing,
        }

    return {
        "status": "pass",
        "details": "Bundle contains core reproducibility identifiers.",
        "recommendation": "",
        "evidence": list(required),
    }


def _check_no_prohibited_claims(context: _ChecklistContext) -> dict[str, Any]:
    text_blobs: list[str] = []
    if context.objective:
        text_blobs.append(context.objective)
    if context.planner_response_text:
        text_blobs.append(context.planner_response_text)

    prohibited = (
        "guaranteed cure",
        "guaranteed remission",
        "proven cure",
        "certain cure",
        "eradicate all disease",
    )

    lowered = "\n".join(text_blobs).lower()
    matches = [phrase for phrase in prohibited if phrase in lowered]

    if matches:
        return {
            "status": "fail",
            "details": "Prohibited overclaim language detected.",
            "recommendation": (
                "Replace absolute cure/guarantee language with evidence-qualified claims."
            ),
            "evidence": matches,
        }

    return {
        "status": "pass",
        "details": "No prohibited overclaim phrases detected.",
        "recommendation": "",
        "evidence": [],
    }


def _check_benchmark_evidence_linkage(context: _ChecklistContext) -> dict[str, Any]:
    if context.manifest is None:
        return {
            "status": "manual_review",
            "details": "Manifest unavailable to inspect benchmark artifacts.",
            "recommendation": "Attach benchmark and regression reports.",
            "evidence": [],
        }

    files = context.manifest.get("files")
    if not isinstance(files, list):
        files = []

    benchmark_tokens = (
        "benchmark",
        "baseline",
        "compare",
        "gate",
        "validation",
        "refua-bench",
    )

    matched = [
        str(path)
        for path in files
        if isinstance(path, str)
        and any(token in path.lower() for token in benchmark_tokens)
    ]

    if matched:
        return {
            "status": "pass",
            "details": "Benchmark/regression artifacts were detected in bundle files.",
            "recommendation": "",
            "evidence": matched,
        }

    return {
        "status": "manual_review",
        "details": "No explicit benchmark/regression artifact linkage found.",
        "recommendation": (
            "Attach `refua-bench` compare/gate outputs for model-change justification."
        ),
        "evidence": [],
    }


def _check_warning_review(context: _ChecklistContext) -> dict[str, Any]:
    warnings = context.manifest_warnings
    if warnings:
        return {
            "status": "manual_review",
            "details": "Bundle contains warnings that require reviewer sign-off.",
            "recommendation": "Review all warning entries and document disposition.",
            "evidence": warnings,
        }
    return {
        "status": "pass",
        "details": "No bundle warnings were reported.",
        "recommendation": "",
        "evidence": [],
    }


def _manual_assay_strategy(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "Assay strategy and endpoint definitions require SME review.",
        "recommendation": "Attach assay protocols, endpoint rationale, and acceptance criteria.",
        "evidence": [],
    }


def _manual_experimental_controls(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "Experimental controls and reproducibility protocol require manual review.",
        "recommendation": "Document positive/negative controls and replication strategy.",
        "evidence": [],
    }


def _manual_human_data_governance(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "Human-data governance, privacy, and consent controls require manual review.",
        "recommendation": "Attach IRB/privacy governance documentation when applicable.",
        "evidence": [],
    }


def _manual_translation_plan(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "PK/PD and translational validation strategy require manual review.",
        "recommendation": "Link in vitro, in vivo, and translational bridge plans.",
        "evidence": [],
    }


def _manual_change_control(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "Model/data change control approvals require manual review.",
        "recommendation": "Attach change tickets, approvals, and impact assessments.",
        "evidence": [],
    }


def _manual_benefit_risk(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "Benefit-risk rationale requires manual clinical/scientific review.",
        "recommendation": "Provide reviewer-signed benefit-risk narrative.",
        "evidence": [],
    }


def _manual_gxp_readiness(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "GxP readiness and quality-system alignment require manual review.",
        "recommendation": "Map bundle artifacts to relevant GxP/quality SOP controls.",
        "evidence": [],
    }


def _manual_submission_mapping(_context: _ChecklistContext) -> dict[str, Any]:
    return {
        "status": "manual_review",
        "details": "Regulatory submission mapping to dossier sections requires manual review.",
        "recommendation": "Map evidence artifacts to IND/CTA sections and reviewer notes.",
        "evidence": [],
    }


_CORE_TEMPLATE: list[ChecklistItem] = [
    ChecklistItem(
        check_id="bundle_structure",
        title="Evidence bundle contains required files",
        domain="audit_integrity",
        severity="critical",
        automated=True,
        regulatory_tags=("traceability", "audit"),
        evaluate=_check_bundle_structure,
    ),
    ChecklistItem(
        check_id="integrity_verification",
        title="Evidence bundle integrity verification passes",
        domain="audit_integrity",
        severity="critical",
        automated=True,
        regulatory_tags=("integrity", "audit"),
        evaluate=_check_integrity_verification,
    ),
    ChecklistItem(
        check_id="objective_defined",
        title="Campaign objective is explicitly defined",
        domain="campaign_design",
        severity="critical",
        automated=True,
        regulatory_tags=("intended_use",),
        evaluate=_check_objective_defined,
    ),
    ChecklistItem(
        check_id="executable_plan_present",
        title="Executable plan with tool calls is present",
        domain="campaign_design",
        severity="critical",
        automated=True,
        regulatory_tags=("traceability",),
        evaluate=_check_executable_plan_present,
    ),
    ChecklistItem(
        check_id="validation_first_policy",
        title="Validation-first tool policy is satisfied",
        domain="model_execution",
        severity="high",
        automated=True,
        regulatory_tags=("risk_control",),
        evaluate=_check_validation_first_policy,
    ),
    ChecklistItem(
        check_id="traceability_lineage",
        title="Decision traceability and lineage graph are complete",
        domain="traceability",
        severity="high",
        automated=True,
        regulatory_tags=("audit", "lineage"),
        evaluate=_check_traceability,
    ),
    ChecklistItem(
        check_id="model_provenance",
        title="Model provenance is captured",
        domain="model_governance",
        severity="high",
        automated=True,
        regulatory_tags=("reproducibility",),
        evaluate=_check_model_provenance,
    ),
    ChecklistItem(
        check_id="data_provenance",
        title="Data provenance is captured",
        domain="data_governance",
        severity="high",
        automated=True,
        regulatory_tags=("reproducibility", "data_lineage"),
        evaluate=_check_data_provenance,
    ),
    ChecklistItem(
        check_id="execution_provenance",
        title="Execution environment provenance is captured",
        domain="reproducibility",
        severity="high",
        automated=True,
        regulatory_tags=("reproducibility", "audit"),
        evaluate=_check_execution_provenance,
    ),
    ChecklistItem(
        check_id="tool_results_present",
        title="Tool execution results are present",
        domain="evidence_completeness",
        severity="high",
        automated=True,
        regulatory_tags=("evidence",),
        evaluate=_check_tool_results_present,
    ),
    ChecklistItem(
        check_id="uncertainty_reporting",
        title="Uncertainty/confidence reporting is present",
        domain="scientific_rigor",
        severity="medium",
        automated=True,
        regulatory_tags=("uncertainty",),
        evaluate=_check_uncertainty_reporting,
    ),
    ChecklistItem(
        check_id="safety_signal_capture",
        title="Safety signal capture fields are present",
        domain="safety",
        severity="high",
        automated=True,
        regulatory_tags=("safety",),
        evaluate=_check_safety_signal_capture,
    ),
    ChecklistItem(
        check_id="reproducibility_identifiers",
        title="Bundle reproducibility identifiers are complete",
        domain="reproducibility",
        severity="medium",
        automated=True,
        regulatory_tags=("traceability",),
        evaluate=_check_reproducibility_identifiers,
    ),
    ChecklistItem(
        check_id="no_prohibited_claims",
        title="No prohibited overclaim language is present",
        domain="communications",
        severity="critical",
        automated=True,
        regulatory_tags=("risk_control", "labeling"),
        evaluate=_check_no_prohibited_claims,
    ),
    ChecklistItem(
        check_id="warning_review",
        title="Warnings have been dispositioned",
        domain="quality_review",
        severity="medium",
        automated=True,
        regulatory_tags=("quality_system",),
        evaluate=_check_warning_review,
    ),
]

_DRUG_DISCOVERY_COMPREHENSIVE_TEMPLATE: list[ChecklistItem] = [
    *_CORE_TEMPLATE,
    ChecklistItem(
        check_id="benchmark_evidence_linkage",
        title="Benchmark/regression evidence linkage is present",
        domain="model_validation",
        severity="medium",
        automated=True,
        regulatory_tags=("validation", "change_control"),
        evaluate=_check_benchmark_evidence_linkage,
    ),
    ChecklistItem(
        check_id="assay_strategy_documented",
        title="Assay strategy and endpoints are documented",
        domain="experimental_design",
        severity="high",
        automated=False,
        regulatory_tags=("scientific_rigor",),
        evaluate=_manual_assay_strategy,
    ),
    ChecklistItem(
        check_id="experimental_controls_documented",
        title="Experimental controls and replication are documented",
        domain="experimental_design",
        severity="high",
        automated=False,
        regulatory_tags=("scientific_rigor", "quality_system"),
        evaluate=_manual_experimental_controls,
    ),
    ChecklistItem(
        check_id="human_data_governance",
        title="Human-data governance controls are documented",
        domain="governance",
        severity="high",
        automated=False,
        regulatory_tags=("privacy", "ethics"),
        evaluate=_manual_human_data_governance,
    ),
    ChecklistItem(
        check_id="translation_plan",
        title="Translational PK/PD validation plan is documented",
        domain="translation",
        severity="high",
        automated=False,
        regulatory_tags=("translation",),
        evaluate=_manual_translation_plan,
    ),
    ChecklistItem(
        check_id="change_control",
        title="Model/data change-control approvals are documented",
        domain="quality_system",
        severity="high",
        automated=False,
        regulatory_tags=("change_control", "quality_system"),
        evaluate=_manual_change_control,
    ),
    ChecklistItem(
        check_id="benefit_risk_narrative",
        title="Benefit-risk narrative is documented",
        domain="clinical_rationale",
        severity="high",
        automated=False,
        regulatory_tags=("benefit_risk",),
        evaluate=_manual_benefit_risk,
    ),
    ChecklistItem(
        check_id="gxp_readiness",
        title="GxP readiness mapping is documented",
        domain="quality_system",
        severity="medium",
        automated=False,
        regulatory_tags=("gxp", "quality_system"),
        evaluate=_manual_gxp_readiness,
    ),
]

_FDA_CDER_AI_ML_TEMPLATE: list[ChecklistItem] = [
    *_DRUG_DISCOVERY_COMPREHENSIVE_TEMPLATE,
    ChecklistItem(
        check_id="submission_mapping",
        title="Evidence artifacts are mapped to submission sections",
        domain="regulatory_submission",
        severity="high",
        automated=False,
        regulatory_tags=("submission",),
        evaluate=_manual_submission_mapping,
    ),
]

_TEMPLATES: dict[str, list[ChecklistItem]] = {
    "core": _CORE_TEMPLATE,
    "drug_discovery_comprehensive": _DRUG_DISCOVERY_COMPREHENSIVE_TEMPLATE,
    "fda_cder_ai_ml": _FDA_CDER_AI_ML_TEMPLATE,
}
