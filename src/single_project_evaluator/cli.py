from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
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
from .serialization import evaluation_from_dict
from .sensitivity import describe_sensitive_matches, find_sensitive_text


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
    if args.command == "show-run":
        try:
            return show_run_command(args)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _print_error(exc, json_output=args.json)
            return EXIT_COMMAND_ERROR
    if args.command == "validate-run":
        try:
            return validate_run_command(args)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _print_error(exc, json_output=args.json)
            return EXIT_COMMAND_ERROR
    if args.command == "complete-run":
        try:
            return complete_run_command(args)
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
        choices=["none", "response-file", "openai"],
        help="Reasoning backend to use.",
    )
    evaluate.add_argument(
        "--response-file",
        help="Path to a structured backend response JSON file for --backend response-file.",
    )
    evaluate.add_argument(
        "--model",
        help="Reasoning model identifier for --backend openai.",
    )
    evaluate.add_argument(
        "--api-base",
        default="https://api.openai.com/v1/responses",
        help="Responses API endpoint for --backend openai.",
    )
    evaluate.add_argument(
        "--timeout-seconds",
        default=120,
        type=int,
        help="HTTP timeout in seconds for --backend openai.",
    )
    evaluate.add_argument(
        "--allow-sensitive-hosted",
        action="store_true",
        help="Allow --backend openai to send context even when likely secrets are detected.",
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
        "--posture",
        choices=[posture.value for posture in AdoptionPosture],
        help="Optionally require posture_fitness to match a declared adoption posture.",
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

    show_run = subparsers.add_parser(
        "show-run",
        help="Show a preserved evaluation run summary and artifact paths.",
    )
    show_run.add_argument("--out", default="reports", help="Directory containing generated reports.")
    show_run.add_argument(
        "--run",
        help="Run directory name or report ID/prefix. Defaults to the newest indexed run.",
    )
    show_run.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable success or error output instead of text.",
    )

    validate_run = subparsers.add_parser(
        "validate-run",
        help="Validate a preserved evaluation run's artifact integrity.",
    )
    validate_run.add_argument("--out", default="reports", help="Directory containing generated reports.")
    validate_run.add_argument(
        "--run",
        help="Run directory name or report ID/prefix. Defaults to the newest indexed run.",
    )
    validate_run.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable success or error output instead of text.",
    )

    complete_run = subparsers.add_parser(
        "complete-run",
        help="Apply a structured response file to a preserved run without recollecting the target project.",
    )
    complete_run.add_argument("--out", default="reports", help="Directory containing generated reports.")
    complete_run.add_argument(
        "--run",
        help="Source run directory name or report ID/prefix. Defaults to the newest indexed run.",
    )
    complete_run.add_argument(
        "--response-file",
        required=True,
        help="Structured backend response JSON file to apply to the preserved run.",
    )
    complete_run.add_argument(
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
    backend = create_backend(
        args.backend,
        Path(args.response_file) if args.response_file else None,
        model=args.model,
        api_base=args.api_base,
        timeout_seconds=args.timeout_seconds,
        allow_sensitive=args.allow_sensitive_hosted,
    )
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
            "model": args.model,
            "api_base": args.api_base if args.backend == "openai" else None,
            "timeout_seconds": args.timeout_seconds if args.backend == "openai" else None,
            "allow_sensitive_hosted": args.allow_sensitive_hosted if args.backend == "openai" else None,
        },
    )
    backend_result = backend.evaluate(run, evidence, context, prepared_context)
    run = _run_with_backend_metadata(run, backend_result.metadata)
    evaluation = Evaluation(
        run=run,
        evidence=evidence,
        context=context,
        prepared_context=prepared_context,
        assessment=backend_result.assessment,
        findings=backend_result.findings,
        governance_conformance=backend_result.governance_conformance or {},
        uncertainties=backend_result.uncertainties or [],
        narrative=backend_result.narrative,
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
    print(f"Wrote response template: {artifacts['latest_response_template']}")
    print(f"Wrote run index: {artifacts['run_index']}")
    return EXIT_OK


def _run_with_backend_metadata(run: EvaluationRun, metadata: dict | None) -> EvaluationRun:
    if not metadata:
        return run
    configuration = dict(run.configuration)
    configuration["backend_response"] = metadata
    return replace(run, configuration=configuration)


def validate_response_command(args: argparse.Namespace) -> int:
    response_file = Path(args.response_file)
    data = json.loads(response_file.read_text(encoding="utf-8"))
    assessment, findings, governance_conformance, uncertainties, narrative = parse_backend_response(
        data,
        expected_posture=args.posture,
    )
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
                    "has_narrative": narrative is not None,
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
    print(f"Narrative: {'present' if narrative is not None else 'absent'}")
    return EXIT_OK


def list_runs_command(args: argparse.Namespace) -> int:
    index_path, runs = _read_run_index(Path(args.out))
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


def show_run_command(args: argparse.Namespace) -> int:
    output_dir = Path(args.out)
    index_path, runs = _read_run_index(output_dir)
    entry = _select_run(runs, args.run, index_path)
    run_dir = output_dir / "runs" / str(entry["run_dir"])
    evaluation_path = run_dir / "evaluation.json"
    if not evaluation_path.exists():
        raise FileNotFoundError(f"evaluation artifact not found for run `{entry['run_dir']}`: {evaluation_path}")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    artifacts = _run_artifact_paths(run_dir)
    payload = {
        "status": "ok",
        "index_path": str(index_path),
        "run_dir": str(run_dir),
        "run": evaluation.get("run", {}),
        "assessment": evaluation.get("assessment", {}),
        "finding_count": len(evaluation.get("findings", [])),
        "governance_conformance_entries": len(evaluation.get("governance_conformance", {})),
        "uncertainties": len(evaluation.get("uncertainties", [])),
        "has_narrative": evaluation.get("narrative") is not None,
        "artifacts": {key: str(path) for key, path in artifacts.items()},
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    run = payload["run"]
    assessment = payload["assessment"]
    print(f"Run: {entry['run_dir']}")
    print(f"Report ID: {_display_value(run.get('report_id'))}")
    print(f"Timestamp UTC: {_display_value(run.get('timestamp_utc'))}")
    print(f"Project: {_display_value(run.get('project_root'))}")
    print(f"Posture: {_display_value(run.get('declared_posture'))}")
    print(f"Backend: {_display_value(run.get('reasoning_provider'))}")
    print(f"Model: {_display_value(run.get('model_identifier'))}")
    print(f"Release eligibility: {_display_value(assessment.get('release_eligibility'))}")
    print(f"Blockers: {_display_value(assessment.get('blockers'))}")
    print(f"Findings: {payload['finding_count']}")
    print(f"Governance conformance entries: {payload['governance_conformance_entries']}")
    print(f"Uncertainties: {payload['uncertainties']}")
    print(f"Narrative: {'present' if payload['has_narrative'] else 'absent'}")
    print("Artifacts:")
    for key, path in artifacts.items():
        print(f"- {key}: {path}")
    return EXIT_OK


def validate_run_command(args: argparse.Namespace) -> int:
    output_dir = Path(args.out)
    index_path, runs = _read_run_index(output_dir)
    entry = _select_run(runs, args.run, index_path)
    run_dir = output_dir / "runs" / str(entry["run_dir"])
    artifacts = _run_artifact_paths(run_dir)
    checks = _validate_run_artifacts(entry, artifacts)
    payload = {
        "status": "ok",
        "index_path": str(index_path),
        "run_dir": str(run_dir),
        "checks": checks,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    print(f"Valid run: {entry['run_dir']}")
    for check in checks:
        print(f"- {check['name']}: {check['status']}")
    return EXIT_OK


def complete_run_command(args: argparse.Namespace) -> int:
    output_dir = Path(args.out)
    index_path, runs = _read_run_index(output_dir)
    source_entry = _select_run(runs, args.run, index_path)
    source_run_dir = output_dir / "runs" / str(source_entry["run_dir"])
    source_evaluation_path = source_run_dir / "evaluation.json"
    if not source_evaluation_path.exists():
        raise FileNotFoundError(
            f"evaluation artifact not found for source run `{source_entry['run_dir']}`: {source_evaluation_path}"
        )

    source_evaluation = evaluation_from_dict(json.loads(source_evaluation_path.read_text(encoding="utf-8")))
    response_file = Path(args.response_file)
    response_data = json.loads(response_file.read_text(encoding="utf-8"))
    assessment, findings, governance_conformance, uncertainties, narrative = parse_backend_response(
        response_data,
        expected_posture=source_evaluation.run.declared_posture.value,
    )
    run = EvaluationRun(
        report_id=str(uuid4()),
        timestamp_utc=datetime.now(UTC).replace(microsecond=0).isoformat(),
        project_root=source_evaluation.run.project_root,
        declared_posture=source_evaluation.run.declared_posture,
        evaluator_version=__version__,
        reasoning_provider="response-file",
        model_identifier=response_file.name,
        configuration={
            "active_target_commands": False,
            "backend": "response-file",
            "response_file": str(response_file),
            "completed_from_run_dir": source_entry["run_dir"],
            "completed_from_report_id": source_evaluation.run.report_id,
            "reused_preserved_context": True,
        },
    )
    completed_evaluation = Evaluation(
        run=run,
        evidence=source_evaluation.evidence,
        context=source_evaluation.context,
        prepared_context=source_evaluation.prepared_context,
        assessment=assessment,
        findings=findings,
        governance_conformance=governance_conformance,
        uncertainties=uncertainties,
        narrative=narrative,
    )

    artifacts = write_evaluation_artifacts(completed_evaluation, output_dir)
    payload = {
        "status": "ok",
        "source_run_dir": str(source_run_dir),
        "source_report_id": source_evaluation.run.report_id,
        "run_dir": str(artifacts["run_dir"]),
        "artifacts": {key: str(value) for key, value in artifacts.items()},
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    print(f"Completed source run: {source_entry['run_dir']}")
    print(f"Wrote run directory: {artifacts['run_dir']}")
    print(f"Wrote evaluation: {artifacts['latest_evaluation']}")
    print(f"Wrote report: {artifacts['latest_report']}")
    print(f"Wrote run record: {artifacts['latest_run_record']}")
    print(f"Wrote context bundle: {artifacts['latest_context_bundle']}")
    print(f"Wrote reasoning request: {artifacts['latest_reasoning_request']}")
    print(f"Wrote response template: {artifacts['latest_response_template']}")
    print(f"Wrote run index: {artifacts['run_index']}")
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


def _read_run_index(output_dir: Path) -> tuple[Path, list[dict]]:
    index_path = output_dir / "runs" / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"run index not found: {index_path}")
    data = json.loads(index_path.read_text(encoding="utf-8"))
    runs = data.get("runs")
    if not isinstance(runs, list):
        raise ValueError(f"run index has no runs list: {index_path}")
    if not all(isinstance(entry, dict) for entry in runs):
        raise ValueError(f"run index contains a non-object entry: {index_path}")
    return index_path, runs


def _select_run(runs: list[dict], requested_run: str | None, index_path: Path) -> dict:
    if not runs:
        raise ValueError(f"run index has no runs: {index_path}")
    if requested_run is None:
        return runs[0]

    matches = [
        entry for entry in runs
        if str(entry.get("run_dir") or "").startswith(requested_run)
        or str(entry.get("report_id") or "").startswith(requested_run)
    ]
    if not matches:
        raise ValueError(f"run not found in index `{index_path}`: {requested_run}")
    if len(matches) > 1:
        raise ValueError(f"run selector is ambiguous in index `{index_path}`: {requested_run}")
    return matches[0]


def _run_artifact_paths(run_dir: Path) -> dict[str, Path]:
    names = {
        "evaluation": "evaluation.json",
        "report": "report.md",
        "run_record": "run-record.json",
        "context_bundle": "context-bundle.json",
        "reasoning_request": "reasoning-request.json",
        "reasoning_request_md": "reasoning-request.md",
        "response_template": "response-template.json",
    }
    return {key: run_dir / filename for key, filename in names.items()}


def _validate_run_artifacts(entry: dict, artifacts: dict[str, Path]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def pass_check(name: str) -> None:
        checks.append({"name": name, "status": "ok"})

    missing = [key for key, path in artifacts.items() if not path.exists()]
    if missing:
        raise ValueError("run is missing required artifacts: " + ", ".join(missing))
    pass_check("required_artifacts_exist")

    evaluation = json.loads(artifacts["evaluation"].read_text(encoding="utf-8"))
    run_record = json.loads(artifacts["run_record"].read_text(encoding="utf-8"))
    context_bundle = json.loads(artifacts["context_bundle"].read_text(encoding="utf-8"))
    reasoning_request = json.loads(artifacts["reasoning_request"].read_text(encoding="utf-8"))
    response_template = json.loads(artifacts["response_template"].read_text(encoding="utf-8"))
    pass_check("json_artifacts_parse")

    report_id = _required_mapping(evaluation, "evaluation").get("run", {}).get("report_id")
    if not report_id or run_record.get("report_id") != report_id:
        raise ValueError("evaluation.json and run-record.json report IDs do not match.")
    if entry.get("report_id") != report_id:
        raise ValueError("run index and evaluation.json report IDs do not match.")
    pass_check("report_id_consistency")

    if run_record != _required_mapping(evaluation, "evaluation").get("run", {}):
        raise ValueError("run-record.json does not match evaluation.json run record.")
    pass_check("run_record_consistency")

    bundle_run = _required_mapping(context_bundle, "context-bundle.json").get("run", {})
    if bundle_run.get("report_id") != report_id:
        raise ValueError("context-bundle.json run record does not match evaluation.json.")
    request_bundle = _required_mapping(reasoning_request, "reasoning-request.json").get("context_bundle", {})
    request_run = _required_mapping(request_bundle, "reasoning-request context_bundle").get("run", {})
    if request_run.get("report_id") != report_id:
        raise ValueError("reasoning-request.json context bundle does not match evaluation.json.")
    pass_check("context_bundle_consistency")

    declared_posture = _required_mapping(evaluation, "evaluation").get("run", {}).get("declared_posture")
    if not isinstance(declared_posture, str) or not declared_posture:
        raise ValueError("evaluation.json run.declared_posture is missing or invalid.")
    parse_backend_response(response_template, expected_posture=declared_posture)
    pass_check("response_template_contract")

    _validate_backend_response_metadata(_required_mapping(evaluation, "evaluation").get("run", {}))
    pass_check("backend_response_metadata_hygiene")

    if not artifacts["report"].read_text(encoding="utf-8").strip():
        raise ValueError("report.md is empty.")
    if not artifacts["reasoning_request_md"].read_text(encoding="utf-8").strip():
        raise ValueError("reasoning-request.md is empty.")
    pass_check("markdown_artifacts_nonempty")

    return checks


def _required_mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


BACKEND_RESPONSE_FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "output_text",
    "password",
    "raw_output",
    "raw_response",
    "secret",
}


def _validate_backend_response_metadata(run: dict) -> None:
    configuration = run.get("configuration", {})
    if not isinstance(configuration, dict):
        raise ValueError("evaluation.json run.configuration must be an object.")
    metadata = configuration.get("backend_response")
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        raise ValueError("run.configuration.backend_response must be an object when present.")
    _validate_metadata_value(metadata, "run.configuration.backend_response")


def _validate_metadata_value(value: object, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            normalized_key = key_text.lower().replace("-", "_")
            if normalized_key in BACKEND_RESPONSE_FORBIDDEN_KEYS:
                raise ValueError(f"run.configuration.backend_response contains forbidden metadata key: {path}.{key_text}")
            _validate_metadata_value(item, f"{path}.{key_text}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_metadata_value(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        matches = find_sensitive_text(source="backend_response", path=path, text=value)
        if matches:
            raise ValueError(
                "run.configuration.backend_response contains likely sensitive metadata: "
                + describe_sensitive_matches(matches)
            )
