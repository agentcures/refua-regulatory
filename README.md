# refua-regulatory

`refua-regulatory` is the Refua regulatory workflow and audit package.
It helps teams follow drug regulation processes by turning campaign decisions and execution outputs into verifiable evidence bundles with end-to-end lineage across plans, tool calls, models, datasets, and generated artifacts.

## What it provides

- Campaign decision extraction from `refua-campaign` run outputs.
- Structured decision records (`decisions.jsonl`) with deterministic decision IDs.
- Model and data provenance capture per campaign decision.
- Lineage graph materialization (`lineage.json`) for traceability.
- Evidence bundle packaging with checksums (`checksums.sha256`).
- Integrity verification for audit handoff and compliance workflows.
- Regulatory checklist evaluation with strict and manual-review gates.
- Automatic comprehensive checklist generation during bundle build.
- Structured outputs that support internal regulatory readiness reviews before agency submission.

## Install

```bash
cd refua-regulatory
pip install -e .
```

## CLI

```bash
refua-regulatory --help
```

### Build a bundle

```bash
refua-regulatory build \
  --campaign-run artifacts/kras_campaign_run.json \
  --output-dir artifacts/evidence/kras_run_001 \
  --data-manifest ~/.cache/refua-data/_meta/parquet/chembl_activity_ki_human/latest/manifest.json \
  --extra-artifact artifacts/candidate_run.json
```

Output bundle layout:

```text
evidence/
  manifest.json
  decisions.jsonl
  lineage.json
  checksums.sha256
  artifacts/
    campaign_run.json
    data_manifests/
    extras/
  checklists/
    drug_discovery_comprehensive.json
    drug_discovery_comprehensive.md
```

By default, `build` auto-generates the `drug_discovery_comprehensive` checklist.

Build-time checklist controls:

```bash
refua-regulatory build \
  --campaign-run artifacts/kras_campaign_run.json \
  --output-dir artifacts/evidence/kras_run_001 \
  --checklist-template core \
  --checklist-template fda_cder_ai_ml \
  --checklist-strict
```

Disable checklist generation:

```bash
refua-regulatory build \
  --campaign-run artifacts/kras_campaign_run.json \
  --output-dir artifacts/evidence/kras_run_001 \
  --no-checklist
```

### Verify a bundle

```bash
refua-regulatory verify --bundle-dir artifacts/evidence/kras_run_001
```

JSON mode:

```bash
refua-regulatory verify --bundle-dir artifacts/evidence/kras_run_001 --json
```

### Show bundle summary

```bash
refua-regulatory summary --bundle-dir artifacts/evidence/kras_run_001
```

### Run a regulatory checklist

Core automated checklist:

```bash
refua-regulatory checklist \
  --bundle-dir artifacts/evidence/kras_run_001 \
  --template drug_discovery_comprehensive \
  --strict
```

FDA/CDER-oriented template (includes manual-review items):

```bash
refua-regulatory checklist \
  --bundle-dir artifacts/evidence/kras_run_001 \
  --template fda_cder_ai_ml \
  --output-json artifacts/evidence/kras_run_001/checklist.json \
  --output-markdown artifacts/evidence/kras_run_001/checklist.md
```

## Python API

```python
from pathlib import Path

from refua_regulatory import build_evidence_bundle, verify_evidence_bundle

manifest = build_evidence_bundle(
    campaign_run_path=Path("artifacts/kras_campaign_run.json"),
    output_dir=Path("artifacts/evidence/kras_run_001"),
)

verification = verify_evidence_bundle(Path("artifacts/evidence/kras_run_001"))
print(manifest["bundle_id"], verification.ok)
```

## Data and model provenance behavior

- Data provenance is loaded from explicit manifest paths (`--data-manifest`).
- `refua-data` parquet manifests are parsed directly for dataset IDs, versions, source URLs, and SHA256 checksums.
- Model provenance is inferred from executed tool outputs and optional CLI overrides (`--model-name`, `--model-version`).

## Test

```bash
cd refua-regulatory
python -m pytest -q
```

## Notes

- This package records reproducibility evidence; it does not claim biological efficacy.
- Regulatory submission requirements vary by jurisdiction and program type.
