from __future__ import annotations

from pathlib import Path

from refua_regulatory.provenance import collect_execution_provenance


def test_collect_execution_provenance_has_runtime_and_dependencies(
    tmp_path: Path,
) -> None:
    provenance = collect_execution_provenance(cwd=tmp_path)

    assert provenance.captured_at
    assert "python_version" in provenance.runtime
    assert "platform" in provenance.runtime
    assert "refua-regulatory" in provenance.dependencies
    assert "available" in provenance.git
    assert "hostname" not in provenance.runtime
    assert "root" not in provenance.git


def test_collect_execution_provenance_can_include_sensitive_details(
    tmp_path: Path,
) -> None:
    provenance = collect_execution_provenance(
        cwd=tmp_path,
        include_sensitive_details=True,
    )

    assert "hostname" in provenance.runtime
