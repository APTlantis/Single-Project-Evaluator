from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import __version__
from .analysis import prepare_evaluation_context
from .backend import create_backend
from .collector import collect_project_evidence
from .context import extract_project_context
from .models import (
    AdoptionPosture,
    Evaluation,
    EvaluationRun,
)
from .reports import write_evaluation_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        try:
            return evaluate_command(args)
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="single-project-evaluator",
        description="Read-only single-project evaluation spine.",
    )
    subparsers = parser.add_subparsers(dest="command")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate one project path.")
    evaluate.add_argument("--project", required=True, help="Path to the project to evaluate.")
    evaluate.add_argument(
        "--posture",
        required=True,
        choices=[posture.value for posture in AdoptionPosture],
        help="Declared current adoption posture for this evaluation run.",
    )
    evaluate.add_argument("--out", default="reports", help="Directory for generated artifacts.")
    evaluate.add_argument(
        "--max-files",
        default=500,
        type=int,
        help="Maximum project files to inventory during Phase 1 collection.",
    )
    evaluate.add_argument(
        "--backend",
        default="none",
        choices=["none", "response-file"],
        help="Reasoning backend to use.",
    )
    evaluate.add_argument(
        "--response-file",
        help="Path to a structured backend response JSON file for --backend response-file.",
    )
    return parser


def evaluate_command(args: argparse.Namespace) -> int:
    project_root = Path(args.project)
    output_dir = Path(args.out)
    posture = AdoptionPosture(args.posture)

    evidence = collect_project_evidence(project_root, max_files=args.max_files)
    context = extract_project_context(project_root, evidence)
    prepared_context = prepare_evaluation_context(evidence, context)
    backend = create_backend(args.backend, Path(args.response_file) if args.response_file else None)
    run = EvaluationRun(
        report_id=str(uuid4()),
        timestamp_utc=datetime.now(UTC).replace(microsecond=0).isoformat(),
        project_root=evidence.root,
        declared_posture=posture,
        evaluator_version=__version__,
        reasoning_provider=backend.identity.provider,
        model_identifier=backend.identity.model_identifier,
        configuration={
            "active_target_commands": False,
            "max_files": args.max_files,
            "backend": args.backend,
            "response_file": args.response_file,
        },
    )
    backend_result = backend.evaluate(run, evidence, context, prepared_context)
    evaluation = Evaluation(
        run=run,
        evidence=evidence,
        context=context,
        prepared_context=prepared_context,
        assessment=backend_result.assessment,
        findings=backend_result.findings,
        governance_conformance=backend_result.governance_conformance or {},
        uncertainties=backend_result.uncertainties or [],
    )

    artifacts = write_evaluation_artifacts(evaluation, output_dir)
    print(f"Wrote run directory: {artifacts['run_dir']}")
    print(f"Wrote evaluation: {artifacts['latest_evaluation']}")
    print(f"Wrote report: {artifacts['latest_report']}")
    print(f"Wrote run record: {artifacts['latest_run_record']}")
    print(f"Wrote context bundle: {artifacts['latest_context_bundle']}")
    print(f"Wrote reasoning request: {artifacts['latest_reasoning_request']}")
    return 0
