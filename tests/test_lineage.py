from __future__ import annotations

from refua_regulatory.extractors import (
    extract_decisions_from_campaign,
    extract_model_provenance,
    infer_campaign_run_id,
)
from refua_regulatory.lineage import build_lineage_graph
from refua_regulatory.models import ArtifactRef


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
