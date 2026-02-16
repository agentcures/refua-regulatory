from __future__ import annotations

from typing import Any

from refua_regulatory.models import ArtifactRef, DataProvenance, DecisionRecord, ModelProvenance


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

    artifact_node_ids: list[str] = []
    for artifact in artifacts:
        artifact_node_id = f"artifact:{artifact.artifact_id}"
        artifact_node_ids.append(artifact_node_id)
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

        if decision.decision_type == "tool_result" and artifact_node_ids:
            edges.append(
                {
                    "from": decision_node_id,
                    "to": artifact_node_ids[0],
                    "type": "recorded_in",
                }
            )

    return {
        "graph_version": "1.0.0",
        "campaign_run_id": campaign_run_id,
        "nodes": nodes,
        "edges": edges,
    }
