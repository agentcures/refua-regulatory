from __future__ import annotations

import importlib.metadata
import os
import platform
import socket
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from refua_regulatory.models import ExecutionProvenance
from refua_regulatory.utils import utcnow_iso

_DEFAULT_DEPENDENCIES = (
    "refua-regulatory",
    "ClawCures",
    "refua-mcp",
    "refua-data",
    "refua-bench",
)


def collect_execution_provenance(
    *,
    cwd: str | Path | None = None,
    dependency_names: list[str] | tuple[str, ...] | None = None,
    extra: Mapping[str, Any] | None = None,
    include_sensitive_details: bool = False,
) -> ExecutionProvenance:
    base_dir = Path(cwd) if cwd is not None else Path.cwd()
    dependency_list = list(dependency_names or _DEFAULT_DEPENDENCIES)

    return ExecutionProvenance(
        captured_at=utcnow_iso(),
        runtime=_runtime_info(include_sensitive_details=include_sensitive_details),
        git=_git_info(
            base_dir,
            include_sensitive_details=include_sensitive_details,
        ),
        dependencies=_dependency_versions(dependency_list),
        extra={} if extra is None else dict(extra),
    )


def _runtime_info(*, include_sensitive_details: bool) -> dict[str, Any]:
    runtime = {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }
    if include_sensitive_details:
        runtime["hostname"] = socket.gethostname()
    return runtime


def _git_info(cwd: Path, *, include_sensitive_details: bool) -> dict[str, Any]:
    head = _run_git(["rev-parse", "HEAD"], cwd)
    if head is None:
        return {
            "available": False,
        }

    root = _run_git(["rev-parse", "--show-toplevel"], cwd)
    status = _run_git(["status", "--porcelain"], cwd)

    info: dict[str, Any] = {
        "available": True,
        "commit": head,
        "dirty": bool(status),
    }
    if root:
        info["repository"] = Path(root).name
        if include_sensitive_details:
            info["root"] = root
    return info


def _run_git(args: list[str], cwd: Path) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        check=False,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _dependency_versions(names: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for package_name in names:
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = "not-installed"
    return versions
