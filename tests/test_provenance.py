from __future__ import annotations

from pathlib import Path

from refua_regulatory.provenance import collect_execution_provenance


def test_collect_execution_provenance_has_runtime_and_dependencies(tmp_path: Path) -> None:
    provenance = collect_execution_provenance(cwd=tmp_path)

    assert provenance.captured_at
    assert "python_version" in provenance.runtime
    assert "platform" in provenance.runtime
    assert "refua-regulatory" in provenance.dependencies
    assert "available" in provenance.git
