from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from refua_regulatory.bundle import (
    build_evidence_bundle,
    load_bundle_summary,
    verify_evidence_bundle,
)
from refua_regulatory.checklist import (
    available_checklist_templates,
    evaluate_regulatory_checklist,
    render_checklist_markdown,
)
from refua_regulatory.utils import to_plain_data, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refua-regulatory",
        description="Build and verify regulatory evidence bundles for Refua campaigns.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build", help="Build an evidence bundle.")
    build_parser.add_argument(
        "--campaign-run",
        type=Path,
        required=True,
        help="Path to refua-campaign JSON output.",
    )
    build_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the evidence bundle is written.",
    )
    build_parser.add_argument(
        "--source-kind",
        default="refua-campaign",
        help="Source system label (e.g. refua-campaign, refua-studio).",
    )
    build_parser.add_argument(
        "--bundle-id",
        default=None,
        help="Optional explicit bundle ID.",
    )
    build_parser.add_argument(
        "--data-manifest",
        type=Path,
        action="append",
        default=[],
        help="Path to a refua-data manifest JSON (repeatable).",
    )
    build_parser.add_argument(
        "--extra-artifact",
        type=Path,
        action="append",
        default=[],
        help="Additional artifact to copy into the bundle (repeatable).",
    )
    build_parser.add_argument(
        "--model-name",
        default=None,
        help="Optional model name override for provenance.",
    )
    build_parser.add_argument(
        "--model-version",
        default=None,
        help="Optional model version override for provenance.",
    )
    build_parser.add_argument(
        "--no-checklist",
        action="store_true",
        help="Disable automatic checklist generation during bundle build.",
    )
    build_parser.add_argument(
        "--checklist-template",
        action="append",
        default=[],
        choices=available_checklist_templates(),
        help=(
            "Checklist template to generate during build (repeatable). "
            "Defaults to drug_discovery_comprehensive."
        ),
    )
    build_parser.add_argument(
        "--checklist-strict",
        action="store_true",
        help="Fail build when generated checklist has failed checks.",
    )
    build_parser.add_argument(
        "--checklist-require-no-manual-review",
        action="store_true",
        help="Fail build when generated checklist contains manual-review items.",
    )
    build_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output directory if it exists and is non-empty.",
    )
    build_parser.set_defaults(handler=_cmd_build)

    verify_parser = sub.add_parser("verify", help="Verify evidence bundle integrity.")
    verify_parser.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="Path to an evidence bundle directory.",
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    verify_parser.set_defaults(handler=_cmd_verify)

    summary_parser = sub.add_parser("summary", help="Print summary for an evidence bundle.")
    summary_parser.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="Path to an evidence bundle directory.",
    )
    summary_parser.set_defaults(handler=_cmd_summary)

    checklist_parser = sub.add_parser(
        "checklist",
        help="Evaluate a regulatory checklist for an evidence bundle.",
    )
    checklist_parser.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="Path to an evidence bundle directory.",
    )
    checklist_parser.add_argument(
        "--template",
        default="drug_discovery_comprehensive",
        choices=available_checklist_templates(),
        help="Checklist template name.",
    )
    checklist_parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write checklist report JSON.",
    )
    checklist_parser.add_argument(
        "--output-markdown",
        type=Path,
        default=None,
        help="Optional path to write checklist report markdown.",
    )
    checklist_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when one or more checks fail.",
    )
    checklist_parser.add_argument(
        "--require-no-manual-review",
        action="store_true",
        help="Exit non-zero when checklist includes manual-review items.",
    )
    checklist_parser.set_defaults(handler=_cmd_checklist)

    return parser


def _cmd_build(args: argparse.Namespace) -> int:
    manifest = build_evidence_bundle(
        campaign_run_path=args.campaign_run,
        output_dir=args.output_dir,
        source_kind=str(args.source_kind),
        bundle_id=args.bundle_id,
        data_manifest_paths=list(args.data_manifest),
        extra_artifacts=list(args.extra_artifact),
        model_name=args.model_name,
        model_version=args.model_version,
        include_checklists=not bool(args.no_checklist),
        checklist_templates=list(args.checklist_template),
        checklist_strict=bool(args.checklist_strict),
        checklist_require_no_manual_review=bool(
            args.checklist_require_no_manual_review
        ),
        overwrite=bool(args.overwrite),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify_evidence_bundle(args.bundle_dir)
    payload = to_plain_data(result)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "ok" if result.ok else "failed"
        print(f"verify: {status}")
        print(f"checked_files: {result.checked_files}")
        if result.warnings:
            print("warnings:")
            for item in result.warnings:
                print(f"- {item}")
        if result.errors:
            print("errors:")
            for item in result.errors:
                print(f"- {item}")

    return 0 if result.ok else 1


def _cmd_summary(args: argparse.Namespace) -> int:
    payload = load_bundle_summary(args.bundle_dir)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_checklist(args: argparse.Namespace) -> int:
    report = evaluate_regulatory_checklist(
        args.bundle_dir,
        template=str(args.template),
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.output_json is not None:
        write_json(args.output_json, report)

    if args.output_markdown is not None:
        markdown = render_checklist_markdown(report)
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown, encoding="utf-8")

    summary = report.get("summary", {})
    failed = int(summary.get("failed", 0)) if isinstance(summary, dict) else 0
    manual_review = int(summary.get("manual_review", 0)) if isinstance(summary, dict) else 0

    if args.strict and failed > 0:
        return 1
    if args.require_no_manual_review and manual_review > 0:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
