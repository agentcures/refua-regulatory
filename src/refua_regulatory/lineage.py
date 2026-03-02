from __future__ import annotations

from typing import Any

from refua_regulatory.models import (
    ArtifactRef,
    DataProvenance,
    DecisionRecord,
    ModelProvenance,
)


def build_lineage_graph(
    *,
    campaign_run_id: str,
    decisions: list[DecisionRecord],
    artifacts: list[ArtifactRef],
    model_provenance: list[ModelProvenance],
    data_provenance: list[DataProvenance],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    run_node_id = f"run:{campaign_run_id}"
    nodes.append(
        {
            "id": run_node_id,
            "kind": "campaign_run",
            "label": campaign_run_id,
            "metadata": {
                "decision_count": len(decisions),
                "artifact_count": len(artifacts),
                "model_count": len(model_provenance),
                "data_count": len(data_provenance),
            },
        }
    )

    model_nodes_by_tool: dict[str, list[str]] = {}
    for index, model in enumerate(model_provenance, start=1):
        model_node_id = f"model:{index}"
        nodes.append(
            {
                "id": model_node_id,
                "kind": "model",
                "label": model.model_name,
                "metadata": {
                    "version": model.model_version,
                    "tool": model.tool,
                    "backend": model.backend,
                    "parameters": model.parameters,
                },
            }
        )
        edges.append(
            {
                "from": run_node_id,
                "to": model_node_id,
                "type": "uses_model",
            }
        )
        if model.tool is not None:
            model_nodes_by_tool.setdefault(model.tool, []).append(model_node_id)

    for index, dataset in enumerate(data_provenance, start=1):
        data_node_id = f"data:{index}"
        nodes.append(
            {
                "id": data_node_id,
                "kind": "dataset",
                "label": dataset.dataset_id,
                "metadata": {
                    "version": dataset.version,
                    "source_url": dataset.source_url,
                    "sha256": dataset.sha256,
                    "license_name": dataset.license_name,
                    "manifest_rel_path": dataset.manifest_rel_path,
                    "metadata": dataset.metadata,
                },
            }
        )
        edges.append(
            {
                "from": run_node_id,
                "to": data_node_id,
                "type": "uses_dataset",
            }
        )

    artifact_nodes_by_id: dict[str, str] = {}
    artifact_nodes_by_rel_path: dict[str, str] = {}
    for artifact in artifacts:
        artifact_node_id = f"artifact:{artifact.artifact_id}"
        artifact_nodes_by_id[artifact.artifact_id] = artifact_node_id
        artifact_nodes_by_rel_path[artifact.rel_path] = artifact_node_id
        nodes.append(
            {
                "id": artifact_node_id,
                "kind": "artifact",
                "label": artifact.rel_path,
                "metadata": {
                    "role": artifact.role,
                    "sha256": artifact.sha256,
                    "size_bytes": artifact.size_bytes,
                    "media_type": artifact.media_type,
                    "metadata": artifact.metadata,
                },
            }
        )
        edges.append(
            {
                "from": run_node_id,
                "to": artifact_node_id,
                "type": "produced_artifact",
            }
        )

    previous_decision_node_id: str | None = None
    for decision in sorted(decisions, key=lambda item: item.step_index):
        decision_node_id = f"decision:{decision.decision_id}"
        nodes.append(
            {
                "id": decision_node_id,
                "kind": "decision",
                "label": decision.decision_type,
                "metadata": {
                    "step_index": decision.step_index,
                    "actor": decision.actor,
                    "tool": decision.tool,
                    "timestamp": decision.timestamp,
                    "rationale": decision.rationale,
                    "input_refs": list(decision.input_refs),
                    "output_refs": list(decision.output_refs),
                    "metadata": decision.metadata,
                },
            }
        )

        edges.append(
            {
                "from": run_node_id,
                "to": decision_node_id,
                "type": "has_decision",
            }
        )

        if previous_decision_node_id is not None:
            edges.append(
                {
                    "from": previous_decision_node_id,
                    "to": decision_node_id,
                    "type": "next",
                }
            )
        previous_decision_node_id = decision_node_id

        if decision.tool is not None:
            for model_node_id in model_nodes_by_tool.get(decision.tool, []):
                edges.append(
                    {
                        "from": decision_node_id,
                        "to": model_node_id,
                        "type": "used_model",
                    }
                )

        if decision.decision_type == "tool_result":
            recorded_artifact_nodes = _resolve_recorded_artifact_nodes(
                decision,
                artifact_nodes_by_id=artifact_nodes_by_id,
                artifact_nodes_by_rel_path=artifact_nodes_by_rel_path,
            )
            for artifact_node_id in recorded_artifact_nodes:
                edges.append(
                    {
                        "from": decision_node_id,
                        "to": artifact_node_id,
                        "type": "recorded_in",
                    }
                )

    return {
        "graph_version": "1.0.0",
        "campaign_run_id": campaign_run_id,
        "nodes": nodes,
        "edges": edges,
    }


def _resolve_recorded_artifact_nodes(
    decision: DecisionRecord,
    *,
    artifact_nodes_by_id: dict[str, str],
    artifact_nodes_by_rel_path: dict[str, str],
) -> list[str]:
    resolved: list[str] = []
    seen_node_ids: set[str] = set()
    refs = [*decision.output_refs, *decision.input_refs]

    for ref in refs:
        for candidate in _artifact_ref_candidates(ref):
            node_id = artifact_nodes_by_id.get(candidate)
            if node_id is None:
                node_id = artifact_nodes_by_rel_path.get(candidate)
            if node_id is None or node_id in seen_node_ids:
                continue
            seen_node_ids.add(node_id)
            resolved.append(node_id)
            break

    return resolved


def _artifact_ref_candidates(ref: str) -> tuple[str, ...]:
    candidates: list[str] = []
    value = ref.strip()
    if not value:
        return ()

    candidates.append(value)
    if value.startswith("artifact:"):
        artifact_ref = value.split(":", maxsplit=1)[1].strip()
        if artifact_ref:
            candidates.append(artifact_ref)
            candidates.append(artifact_ref.replace(":", "_"))

    seen: set[str] = set()
    deduped: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return tuple(deduped)
