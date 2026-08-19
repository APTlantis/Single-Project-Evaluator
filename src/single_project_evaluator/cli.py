from __future__ import annotations

import argparse
import json
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
from .response_parser import parse_backend_response


EXIT_OK = 0
EXIT_COMMAND_ERROR = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        try:
            return evaluate_command(args)
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            _print_error(exc, json_output=args.json)
            return EXIT_COMMAND_ERROR
    if args.command == "validate-response":
        try:
            return validate_response_command(args)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _print_error(exc, json_output=args.json)
            return EXIT_COMMAND_ERROR
    if args.command == "list-runs":
        try:
            return list_runs_command(args)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _print_error(exc, json_output=args.json)
            return EXIT_COMMAND_ERROR

    parser.print_help()
    return EXIT_USAGE


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
    evaluate.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable success or error output instead of text.",
    )

    validate_response = subparsers.add_parser(
        "validate-response",
        help="Validate a structured backend response JSON file.",
    )
    validate_response.add_argument(
        "--response-file",
        required=True,
        help="Path to the backend response JSON file to validate.",
    )
    validate_response.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable success or error output instead of text.",
    )

    list_runs = subparsers.add_parser(
        "list-runs",
        help="List preserved evaluation runs from an existing run index.",
    )
    list_runs.add_argument("--out", default="reports", help="Directory containing generated reports.")
    list_runs.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable success or error output instead of text.",
    )
    return parser


def evaluate_command(args: argparse.Namespace) -> int:
    project_root = Path(args.project)
    output_dir = Path(args.out)
    posture = AdoptionPosture(args.posture)

    evidence = collect_project_evidence(project_root, max_files=args.max_files)
    _ensure_output_outside_project(Path(evidence.root), output_dir)
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
    if args.json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "run_dir": str(artifacts["run_dir"]),
                    "artifacts": {key: str(value) for key, value in artifacts.items()},
                },
                indent=2,
            )
        )
        return EXIT_OK
    print(f"Wrote run directory: {artifacts['run_dir']}")
    print(f"Wrote evaluation: {artifacts['latest_evaluation']}")
    print(f"Wrote report: {artifacts['latest_report']}")
    print(f"Wrote run record: {artifacts['latest_run_record']}")
    print(f"Wrote context bundle: {artifacts['latest_context_bundle']}")
    print(f"Wrote reasoning request: {artifacts['latest_reasoning_request']}")
    print(f"Wrote run index: {artifacts['run_index']}")
    return EXIT_OK


def validate_response_command(args: argparse.Namespace) -> int:
    response_file = Path(args.response_file)
    data = json.loads(response_file.read_text(encoding="utf-8"))
    assessment, findings, governance_conformance, uncertainties = parse_backend_response(data)
    if args.json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "response_file": str(response_file),
                    "findings": len(findings),
                    "blockers": assessment.blockers,
                    "release_eligibility": assessment.release_eligibility,
                    "governance_conformance_entries": len(governance_conformance),
                    "uncertainties": len(uncertainties),
                },
                indent=2,
            )
        )
        return EXIT_OK
    print(f"Valid response: {response_file}")
    print(f"Findings: {len(findings)}")
    print(f"Blockers: {assessment.blockers}")
    print(f"Release eligibility: {assessment.release_eligibility}")
    print(f"Governance conformance entries: {len(governance_conformance)}")
    print(f"Uncertainties: {len(uncertainties)}")
    return EXIT_OK


def list_runs_command(args: argparse.Namespace) -> int:
    index_path = Path(args.out) / "runs" / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"run index not found: {index_path}")

    data = json.loads(index_path.read_text(encoding="utf-8"))
    runs = data.get("runs")
    if not isinstance(runs, list):
        raise ValueError(f"run index has no runs list: {index_path}")
    if args.json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "index_path": str(index_path),
                    "runs": runs,
                },
                indent=2,
            )
        )
        return EXIT_OK
    if not runs:
        print("No evaluation runs found.")
        return EXIT_OK

    print("Timestamp | Project | Posture | Backend | Release | Blockers | Findings | Run")
    print("--- | --- | --- | --- | --- | ---: | ---: | ---")
    for entry in runs:
        if not isinstance(entry, dict):
            raise ValueError(f"run index contains a non-object entry: {index_path}")
        print(
            " | ".join(
                [
                    _display_value(entry.get("timestamp_utc")),
                    _display_value(entry.get("project_root")),
                    _display_value(entry.get("declared_posture")),
                    _display_value(entry.get("reasoning_provider")),
                    _display_value(entry.get("release_eligibility")),
                    _display_value(entry.get("blockers")),
                    _display_value(entry.get("finding_count")),
                    _display_value(entry.get("run_dir")),
                ]
            )
        )
    return EXIT_OK


def _display_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ")


def _print_error(exc: Exception, *, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return
    print(f"error: {exc}", file=sys.stderr)


def _ensure_output_outside_project(project_root: Path, output_dir: Path) -> None:
    resolved_project = project_root.resolve()
    resolved_output = output_dir.resolve()
    if _is_relative_to(resolved_output, resolved_project):
        raise ValueError(
            "output directory must be outside the evaluated project to preserve the read-only boundary: "
            f"{resolved_output}"
        )


def _is_relative_to(path: Path, possible_parent: Path) -> bool:
    try:
        path.relative_to(possible_parent)
    except ValueError:
        return False
    return True
