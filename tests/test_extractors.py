from __future__ import annotations

from refua_regulatory.extractors import (
    extract_decisions_from_campaign,
    extract_model_provenance,
    infer_campaign_run_id,
)


def test_extract_decisions_from_autonomous_payload(
    sample_autonomous_payload: dict[str, object],
) -> None:
    run_id = infer_campaign_run_id(sample_autonomous_payload)
    decisions = extract_decisions_from_campaign(
        sample_autonomous_payload,
        campaign_run_id=run_id,
    )

    assert decisions
    assert [item.step_index for item in decisions] == list(range(1, len(decisions) + 1))

    decision_types = {item.decision_type for item in decisions}
    assert "objective" in decision_types
    assert "policy" in decision_types
    assert "critic" in decision_types
    assert "planning" in decision_types
    assert "tool_call" in decision_types
    assert "tool_result" in decision_types

    decision_ids = {item.decision_id for item in decisions}
    assert len(decision_ids) == len(decisions)


def test_extract_model_provenance_infers_tools(
    sample_campaign_run_payload: dict[str, object],
) -> None:
    models = extract_model_provenance(sample_campaign_run_payload)

    names = {item.model_name for item in models}
    tools = {item.tool for item in models}

    assert "refua-validator" in names
    assert "refua-boltz" in names
    assert "refua_validate_spec" in tools
    assert "refua_fold" in tools


def test_extract_model_provenance_override_when_results_absent() -> None:
    payload = {"objective": "x", "results": []}
    models = extract_model_provenance(
        payload,
        override_model_name="custom-model",
        override_model_version="2026.02.16",
    )

    assert len(models) == 1
    assert models[0].model_name == "custom-model"
    assert models[0].model_version == "2026.02.16"
