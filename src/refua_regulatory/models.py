from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DecisionType = Literal[
    "objective",
    "planning",
    "policy",
    "critic",
    "tool_call",
    "tool_result",
    "selection",
    "note",
]


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    role: str
    rel_path: str
    sha256: str
    size_bytes: int
    media_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelProvenance:
    model_name: str
    model_version: str | None
    tool: str | None = None
    backend: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DataProvenance:
    dataset_id: str
    version: str | None
    source_url: str | None = None
    sha256: str | None = None
    license_name: str | None = None
    manifest_rel_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str
    campaign_run_id: str
    step_index: int
    timestamp: str
    decision_type: DecisionType
    actor: str
    rationale: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    output_preview: str | None = None
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionProvenance:
    captured_at: str
    runtime: dict[str, Any]
    git: dict[str, Any]
    dependencies: dict[str, str]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceBundleManifest:
    schema_version: str
    bundle_id: str
    created_at: str
    campaign_run_id: str
    source_kind: str
    source_rel_path: str
    decision_count: int
    artifact_count: int
    model_count: int
    data_count: int
    files: tuple[str, ...]
    model_provenance: tuple[ModelProvenance, ...] = ()
    data_provenance: tuple[DataProvenance, ...] = ()
    execution_provenance: ExecutionProvenance | None = None
    checklist_reports: tuple[str, ...] = ()
    checklist_summary: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    checked_files: int
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
