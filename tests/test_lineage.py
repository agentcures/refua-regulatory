from __future__ import annotations

from refua_regulatory.extractors import (
    extract_decisions_from_campaign,
    extract_model_provenance,
    infer_campaign_run_id,
)
from refua_regulatory.lineage import build_lineage_graph
from refua_regulatory.models import ArtifactRef, DecisionRecord


def test_build_lineage_graph_contains_core_nodes(
    sample_campaign_run_payload: dict[str, object],
) -> None:
    campaign_run_id = infer_campaign_run_id(sample_campaign_run_payload)
    decisions = extract_decisions_from_campaign(
        sample_campaign_run_payload,
        campaign_run_id=campaign_run_id,
    )
    models = extract_model_provenance(sample_campaign_run_payload)

    artifacts = [
        ArtifactRef(
            artifact_id="campaign_run",
            role="campaign_run",
            rel_path="artifacts/campaign_run.json",
            sha256="a" * 64,
            size_bytes=1200,
            media_type="application/json",
            metadata={},
        )
    ]

    graph = build_lineage_graph(
        campaign_run_id=campaign_run_id,
        decisions=decisions,
        artifacts=artifacts,
        model_provenance=models,
        data_provenance=[],
    )

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    assert isinstance(nodes, list)
    assert isinstance(edges, list)

    node_kinds = {item.get("kind") for item in nodes if isinstance(item, dict)}
    assert "campaign_run" in node_kinds
    assert "decision" in node_kinds
    assert "model" in node_kinds
    assert "artifact" in node_kinds

    assert edges


def test_tool_result_recorded_in_uses_explicit_artifact_ref() -> None:
    decision = DecisionRecord(
        decision_id="decision_a",
        campaign_run_id="run_1",
        step_index=1,
        timestamp="2026-03-01T00:00:00+00:00",
        decision_type="tool_result",
        actor="executor",
        rationale="captured output",
        tool="refua_fold",
        args={},
        output_preview="{}",
        input_refs=(),
        output_refs=("artifact:extra_001",),
        metadata={},
    )
    artifacts = [
        ArtifactRef(
            artifact_id="campaign_run",
            role="campaign_run",
            rel_path="artifacts/campaign_run.json",
            sha256="a" * 64,
            size_bytes=100,
            media_type="application/json",
            metadata={},
        ),
        ArtifactRef(
            artifact_id="extra_001",
            role="extra",
            rel_path="artifacts/extras/extra_001.json",
            sha256="b" * 64,
            size_bytes=200,
            media_type="application/json",
            metadata={},
        ),
    ]

    graph = build_lineage_graph(
        campaign_run_id="run_1",
        decisions=[decision],
        artifacts=artifacts,
        model_provenance=[],
        data_provenance=[],
    )

    edges = graph["edges"]
    recorded_in = [edge for edge in edges if edge.get("type") == "recorded_in"]
    assert recorded_in == [
        {
            "from": "decision:decision_a",
            "to": "artifact:extra_001",
            "type": "recorded_in",
        }
    ]


def test_tool_result_without_artifact_ref_does_not_default_to_first_artifact() -> None:
    decision = DecisionRecord(
        decision_id="decision_b",
        campaign_run_id="run_1",
        step_index=1,
        timestamp="2026-03-01T00:00:00+00:00",
        decision_type="tool_result",
        actor="executor",
        rationale="captured output",
        tool="refua_fold",
        args={},
        output_preview="{}",
        input_refs=(),
        output_refs=(),
        metadata={},
    )
    artifacts = [
        ArtifactRef(
            artifact_id="campaign_run",
            role="campaign_run",
            rel_path="artifacts/campaign_run.json",
            sha256="a" * 64,
            size_bytes=100,
            media_type="application/json",
            metadata={},
        ),
        ArtifactRef(
            artifact_id="extra_001",
            role="extra",
            rel_path="artifacts/extras/extra_001.json",
            sha256="b" * 64,
            size_bytes=200,
            media_type="application/json",
            metadata={},
        ),
    ]

    graph = build_lineage_graph(
        campaign_run_id="run_1",
        decisions=[decision],
        artifacts=artifacts,
        model_provenance=[],
        data_provenance=[],
    )

    edges = graph["edges"]
    assert not any(edge.get("type") == "recorded_in" for edge in edges)
