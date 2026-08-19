from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import __version__
from .collector import collect_project_evidence
from .context import extract_project_context
from .models import (
    AdoptionPosture,
    AssessmentProfile,
    Evaluation,
    EvaluationRun,
    Finding,
    FindingAuthority,
    FindingClass,
)
from .reports import write_evaluation_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        return evaluate_command(args)

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
    return parser


def evaluate_command(args: argparse.Namespace) -> int:
    project_root = Path(args.project)
    output_dir = Path(args.out)
    posture = AdoptionPosture(args.posture)

    evidence = collect_project_evidence(project_root, max_files=args.max_files)
    context = extract_project_context(project_root, evidence)
    run = EvaluationRun(
        report_id=str(uuid4()),
        timestamp_utc=datetime.now(UTC).replace(microsecond=0).isoformat(),
        project_root=evidence.root,
        declared_posture=posture,
        evaluator_version=__version__,
        reasoning_provider="none",
        model_identifier="phase-1-spine",
        configuration={
            "active_target_commands": False,
            "max_files": args.max_files,
        },
    )
    evaluation = Evaluation(
        run=run,
        evidence=evidence,
        context=context,
        assessment=AssessmentProfile(
            posture_fitness=f"{posture.value.title()} - Not assessed",
            release_eligibility="NOT APPLICABLE",
        ),
        findings=[
            Finding(
                title="Deep reasoning evaluation is not yet implemented",
                finding_class=FindingClass.OBSERVATION,
                area="Evaluation Spine",
                authority=FindingAuthority.ENGINEERING_RECOMMENDATION,
                evidence=["Phase 1 collector and report writer completed without invoking a reasoning backend."],
                impact="The generated artifacts prove the evaluation object shape but do not yet judge the target project.",
                consequence="No project-quality conclusions should be drawn from this Phase 1 run.",
                recommendation="Use this output to validate artifact shape before implementing governance and reasoning stages.",
            )
        ],
    )

    artifacts = write_evaluation_artifacts(evaluation, output_dir)
    print(f"Wrote evaluation: {artifacts['evaluation']}")
    print(f"Wrote report: {artifacts['report']}")
    print(f"Wrote run record: {artifacts['run_record']}")
    return 0
