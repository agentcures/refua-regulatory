from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

_CHUNK_SIZE = 4 * 1024 * 1024


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload at {path} must be an object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, sort_keys=True))
            handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def stable_id(*parts: str) -> str:
    normalized = "::".join(part.strip() for part in parts)
    return uuid5(NAMESPACE_URL, normalized).hex


def to_plain_data(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return to_plain_data(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_plain_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    if isinstance(value, tuple):
        return [to_plain_data(item) for item in value]
    return value


def stable_json_dumps(value: Any) -> str:
    return json.dumps(
        to_plain_data(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def write_json_with_metadata(path: Path, payload: dict[str, Any]) -> tuple[str, int]:
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return sha256_bytes(content), len(content)


def write_jsonl_with_metadata(
    path: Path,
    items: list[dict[str, Any]],
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for item in items:
            line = (json.dumps(item, sort_keys=True) + "\n").encode("utf-8")
            handle.write(line)
            digest.update(line)
            size_bytes += len(line)
    return digest.hexdigest(), size_bytes


def write_text_with_metadata(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
) -> tuple[str, int]:
    payload = content.encode(encoding)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_bytes(payload), len(payload)


def copy_file_with_metadata(source: Path, target: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src_handle, target.open("wb") as dst_handle:
        while True:
            chunk = src_handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            dst_handle.write(chunk)
            digest.update(chunk)
            size_bytes += len(chunk)
    shutil.copystat(source, target)
    return digest.hexdigest(), size_bytes


def list_bundle_files(bundle_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(bundle_dir.rglob("*")):
        if path.is_file():
            files.append(path)
    return files


def truncate_preview(value: Any, *, max_chars: int = 1000) -> str:
    rendered = stable_json_dumps(value)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3] + "..."
