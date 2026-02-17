from __future__ import annotations

from importlib.metadata import version as _distribution_version
from pathlib import Path
import tomllib

from refua_regulatory.bundle import build_evidence_bundle, load_bundle_summary, verify_evidence_bundle
from refua_regulatory.checklist import (
    available_checklist_templates,
    evaluate_regulatory_checklist,
    render_checklist_markdown,
)
from refua_regulatory.extractors import (
    extract_decisions_from_campaign,
    extract_model_provenance,
    infer_campaign_run_id,
    load_data_provenance_from_manifests,
)


def _read_version_from_pyproject() -> str | None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.exists():
        return None

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    version = project.get("version")
    if not version:
        return None
    return str(version)


def _resolve_version() -> str:
    local_version = _read_version_from_pyproject()
    if local_version is not None:
        return local_version
    return _distribution_version("refua-regulatory")


__version__ = _resolve_version()

__all__ = [
    "build_evidence_bundle",
    "verify_evidence_bundle",
    "load_bundle_summary",
    "available_checklist_templates",
    "evaluate_regulatory_checklist",
    "render_checklist_markdown",
    "infer_campaign_run_id",
    "extract_decisions_from_campaign",
    "extract_model_provenance",
    "load_data_provenance_from_manifests",
]
