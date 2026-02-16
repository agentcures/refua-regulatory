from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def sample_campaign_run_payload() -> dict[str, Any]:
    return {
        "objective": "Design an initial campaign against KRAS G12D",
        "system_prompt": "You are Refua Campaign.",
        "planner_response_text": "{\"calls\": [...]} ",
        "plan": {
            "calls": [
                {
                    "tool": "refua_validate_spec",
                    "args": {
                        "action": "fold",
                        "name": "kras_v1",
                        "entities": [
                            {
                                "type": "protein",
                                "id": "A",
                                "sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ",
                            },
                            {"type": "ligand", "id": "lig", "smiles": "CCO"},
                        ],
                    },
                },
                {
                    "tool": "refua_fold",
                    "args": {
                        "name": "kras_v1",
                        "entities": [
                            {
                                "type": "protein",
                                "id": "A",
                                "sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ",
                            },
                            {"type": "ligand", "id": "lig", "smiles": "CCO"},
                        ],
                        "affinity": True,
                    },
                },
            ]
        },
        "results": [
            {
                "tool": "refua_validate_spec",
                "args": {
                    "action": "fold",
                    "name": "kras_v1",
                },
                "output": {
                    "valid": True,
                    "warnings": [],
                },
            },
            {
                "tool": "refua_fold",
                "args": {
                    "name": "kras_v1",
                    "affinity": True,
                },
                "output": {
                    "name": "kras_v1",
                    "backend": "refua",
                    "affinity": {"binding_probability": 0.83, "ic50": 14.2},
                    "warnings": [],
                },
            },
        ],
        "dry_run": False,
    }


@pytest.fixture()
def sample_autonomous_payload() -> dict[str, Any]:
    return {
        "objective": "Autonomous campaign objective",
        "system_prompt": "system",
        "approved": True,
        "iterations": [
            {
                "round_index": 1,
                "policy": {
                    "approved": False,
                    "errors": ["missing validator first"],
                    "warnings": [],
                },
                "critic": {
                    "approved": False,
                    "issues": ["too vague"],
                    "suggested_fixes": ["add validation"],
                },
            },
            {
                "round_index": 2,
                "policy": {
                    "approved": True,
                    "errors": [],
                    "warnings": ["max_calls nearly reached"],
                },
                "critic": {
                    "approved": True,
                    "issues": [],
                    "suggested_fixes": [],
                },
            },
        ],
        "final_plan": {
            "calls": [
                {"tool": "refua_validate_spec", "args": {"action": "fold", "name": "auto1"}},
                {"tool": "refua_affinity", "args": {"name": "auto1", "binder": "lig"}},
            ]
        },
        "results": [
            {
                "tool": "refua_affinity",
                "args": {"name": "auto1", "binder": "lig"},
                "output": {
                    "name": "auto1",
                    "backend": "refua",
                    "affinity": {"binding_probability": 0.91, "ic50": 5.4},
                },
            }
        ],
        "dry_run": False,
    }


@pytest.fixture()
def sample_campaign_run_file(tmp_path: Path, sample_campaign_run_payload: dict[str, Any]) -> Path:
    path = tmp_path / "campaign_run.json"
    path.write_text(json.dumps(sample_campaign_run_payload, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def sample_data_manifest_file(tmp_path: Path) -> Path:
    payload = {
        "dataset_id": "chembl_activity_ki_human",
        "version": "latest",
        "generated_at": "2026-02-16T00:00:00+00:00",
        "source": {
            "url": "https://www.ebi.ac.uk/chembl/api/data/activity.json",
            "sha256": "f" * 64,
        },
        "row_count": 12500,
        "parts": ["part-00000.parquet", "part-00001.parquet"],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
