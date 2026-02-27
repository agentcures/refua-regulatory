from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from refua_regulatory.bundle import (
    build_evidence_bundle,
    load_bundle_summary,
    verify_evidence_bundle,
)
from refua_regulatory.utils import to_plain_data


def build_evidence_bundle_from_payload(
    *,
    campaign_run: Mapping[str, Any],
    output_dir: Path,
    source_kind: str = "refua-studio",
    data_manifest_paths: list[Path] | None = None,
    extra_artifacts: list[Path] | None = None,
    include_checklists: bool = True,
    checklist_templates: list[str] | None = None,
    checklist_strict: bool = False,
    checklist_require_no_manual_review: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build a regulatory evidence bundle from an in-memory campaign payload."""
    if not isinstance(campaign_run, Mapping):
        raise ValueError("campaign_run must be a mapping")

    resolved_output_dir = output_dir.expanduser().resolve()
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        delete=False,
    ) as tmp:
        source_file = Path(tmp.name)
        tmp.write(
            json.dumps(to_plain_data(dict(campaign_run)), ensure_ascii=True, indent=2)
        )
        tmp.write("\n")

    try:
        return build_evidence_bundle(
            campaign_run_path=source_file,
            output_dir=resolved_output_dir,
            source_kind=source_kind,
            data_manifest_paths=data_manifest_paths,
            extra_artifacts=extra_artifacts,
            include_checklists=include_checklists,
            checklist_templates=checklist_templates,
            checklist_strict=checklist_strict,
            checklist_require_no_manual_review=checklist_require_no_manual_review,
            overwrite=overwrite,
        )
    finally:
        try:
            source_file.unlink(missing_ok=True)
        except OSError:
            pass


def verify_bundle_with_summary(bundle_dir: Path) -> dict[str, Any]:
    """Return verification output plus summary payload for a bundle."""
    summary = load_bundle_summary(bundle_dir)
    verification = verify_evidence_bundle(bundle_dir)
    return {
        "bundle_dir": str(bundle_dir.expanduser().resolve()),
        "summary": summary,
        "verification": to_plain_data(verification),
    }
