from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import Evaluation, FindingClass
from .request_package import build_reasoning_request, build_response_template, render_reasoning_request_markdown


ARTIFACT_FILENAMES = {
    "evaluation": "evaluation.json",
    "report": "report.md",
    "run_record": "run-record.json",
    "context_bundle": "context-bundle.json",
    "reasoning_request": "reasoning-request.json",
    "reasoning_request_md": "reasoning-request.md",
    "response_template": "response-template.json",
}


def write_evaluation_artifacts(evaluation: Evaluation, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / "runs" / _run_directory_name(evaluation)
    run_dir.mkdir(parents=True, exist_ok=False)
    paths = {key: run_dir / filename for key, filename in ARTIFACT_FILENAMES.items()}

    data = evaluation.to_dict()
    context_bundle = _context_bundle(data)
    reasoning_request = build_reasoning_request(context_bundle)
    paths["evaluation"].write_text(json.dumps(data, indent=2), encoding="utf-8")
    paths["run_record"].write_text(json.dumps(data["run"], indent=2), encoding="utf-8")
    paths["context_bundle"].write_text(json.dumps(context_bundle, indent=2), encoding="utf-8")
    paths["reasoning_request"].write_text(json.dumps(reasoning_request, indent=2), encoding="utf-8")
    paths["reasoning_request_md"].write_text(render_reasoning_request_markdown(reasoning_request), encoding="utf-8")
    paths["response_template"].write_text(
        json.dumps(build_response_template(evaluation.run.declared_posture.value), indent=2),
        encoding="utf-8",
    )
    paths["report"].write_text(render_markdown_report(evaluation), encoding="utf-8")

    latest_paths = _write_latest_aliases(paths, output_dir)
    index_paths = _write_run_index(output_dir)
    return {"run_dir": run_dir, **paths, **latest_paths, **index_paths}


def _run_directory_name(evaluation: Evaluation) -> str:
    timestamp = evaluation.run.timestamp_utc
    timestamp = timestamp.replace("+00:00", "Z").replace(":", "").replace("-", "")
    timestamp = timestamp.replace("T", "-")
    return f"{timestamp}-{evaluation.run.report_id[:8]}"


def _write_latest_aliases(paths: dict[str, Path], output_dir: Path) -> dict[str, Path]:
    latest_paths: dict[str, Path] = {}
    for key, filename in ARTIFACT_FILENAMES.items():
        latest = output_dir / filename
        shutil.copyfile(paths[key], latest)
        latest_paths[f"latest_{key}"] = latest
    return latest_paths


def _write_run_index(output_dir: Path) -> dict[str, Path]:
    runs_dir = output_dir / "runs"
    entries = []
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), reverse=True):
        run_record_path = run_dir / ARTIFACT_FILENAMES["run_record"]
        evaluation_path = run_dir / ARTIFACT_FILENAMES["evaluation"]
        if not run_record_path.exists() or not evaluation_path.exists():
            continue
        try:
            run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries.append(
            {
                "run_dir": run_dir.name,
                "report_id": run_record.get("report_id"),
                "timestamp_utc": run_record.get("timestamp_utc"),
                "project_root": run_record.get("project_root"),
                "declared_posture": run_record.get("declared_posture"),
                "reasoning_provider": run_record.get("reasoning_provider"),
                "model_identifier": run_record.get("model_identifier"),
                "release_eligibility": evaluation.get("assessment", {}).get("release_eligibility"),
                "blockers": evaluation.get("assessment", {}).get("blockers"),
                "finding_count": len(evaluation.get("findings", [])),
            }
        )

    index_json = runs_dir / "index.json"
    index_md = runs_dir / "index.md"
    index_json.write_text(json.dumps({"runs": entries}, indent=2), encoding="utf-8")
    index_md.write_text(_render_run_index(entries), encoding="utf-8")
    return {
        "run_index": index_json,
        "run_index_md": index_md,
    }


def _render_run_index(entries: list[dict]) -> str:
    lines = [
        "# Evaluation Run Index",
        "",
        "| Timestamp | Project | Posture | Backend | Release | Blockers | Findings | Run |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for entry in entries:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(entry.get("timestamp_utc") or ""),
                    str(entry.get("project_root") or ""),
                    str(entry.get("declared_posture") or ""),
                    str(entry.get("reasoning_provider") or ""),
                    str(entry.get("release_eligibility") or ""),
                    str(entry.get("blockers") if entry.get("blockers") is not None else ""),
                    str(entry.get("finding_count") if entry.get("finding_count") is not None else ""),
                    f"`{entry.get('run_dir')}`",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _context_bundle(evaluation_data: dict) -> dict:
    return {
        "run": evaluation_data["run"],
        "evidence": evaluation_data["evidence"],
        "context": evaluation_data["context"],
        "prepared_context": evaluation_data["prepared_context"],
    }


def render_markdown_report(evaluation: Evaluation) -> str:
    counts = {finding_class.value: 0 for finding_class in FindingClass}
    for finding in evaluation.findings:
        counts[finding.finding_class.value] += 1

    lines = [
        f"# Single-Project Evaluation: {evaluation.evidence.project_name}",
        "",
        "## Project Condition Summary",
        "",
        f"- Project root: `{evaluation.evidence.root}`",
        f"- Declared posture: `{evaluation.run.declared_posture}`",
        f"- Context project name: {_context_value(evaluation.context.project_name)}",
        f"- Context lifecycle: {_context_value(evaluation.context.lifecycle_state)}",
        f"- Context project class: {_context_value(evaluation.context.project_classes)}",
        f"- Files examined: {evaluation.evidence.files_examined}",
        f"- Git commit: `{evaluation.evidence.git_commit or 'unavailable'}`",
        f"- Functional Completeness: {_pct(evaluation.assessment.functional_completeness)}",
        f"- Implementation Quality: {_pct(evaluation.assessment.implementation_quality)}",
        f"- Intent Fidelity: {evaluation.assessment.intent_fidelity}",
        f"- Verification Confidence: {evaluation.assessment.verification_confidence}",
        f"- Posture Fitness: {evaluation.assessment.posture_fitness}",
        f"- Lifecycle Fitness: {evaluation.assessment.lifecycle_fitness}",
        f"- Release Eligibility: {evaluation.assessment.release_eligibility}",
        f"- Blockers: {evaluation.assessment.blockers}",
        f"- Findings: {counts['required']} Required, {counts['should']} Should, {counts['could']} Could, {counts['observation']} Observations",
        "",
        "## Detected Project Records",
        "",
    ]

    if evaluation.evidence.detected_records:
        for record_type, paths in sorted(evaluation.evidence.detected_records.items()):
            lines.append(f"- {record_type}: {', '.join(f'`{path}`' for path in paths[:10])}")
    else:
        lines.append("- No common project records were detected by the Phase 1 collector.")

    lines.extend(["", "## Extracted Project Context", ""])
    context_rows = [
        ("Project name", evaluation.context.project_name),
        ("Project classes", evaluation.context.project_classes),
        ("Lifecycle state", evaluation.context.lifecycle_state),
        ("Manifest adoption posture", evaluation.context.manifest_adoption_posture),
        ("Primary standard", evaluation.context.primary_standard),
        ("Expected delivery standard", evaluation.context.expected_delivery_standard),
        ("Applicable governance", evaluation.context.applicable_governance),
        ("Governance standard paths", evaluation.context.governance_standard_paths),
        ("PPS path", evaluation.context.pps_path),
        ("README path", evaluation.context.readme_path),
    ]
    for label, value in context_rows:
        lines.append(f"- {label}: {_context_value(value)}")
    if evaluation.context.notes:
        lines.append("- Context notes: " + "; ".join(evaluation.context.notes))
    else:
        lines.append("- Context notes: none")

    lines.extend(["", "## Governance Conformance", ""])
    if evaluation.governance_conformance:
        for standard, result in sorted(evaluation.governance_conformance.items()):
            lines.append(f"- {standard}: {result}")
    else:
        lines.append("- Governance conformance has not been evaluated.")

    lines.extend(["", "## Evaluation Uncertainties", ""])
    if evaluation.uncertainties:
        for uncertainty in evaluation.uncertainties:
            lines.append(f"- {uncertainty}")
    else:
        lines.append("- No backend-supplied uncertainties.")

    lines.extend(["", "## Backend Narrative", ""])
    if evaluation.narrative:
        lines.append(evaluation.narrative)
    else:
        lines.append("- No backend-supplied narrative.")

    lines.extend(["", "## Prepared Evaluation Context", ""])
    lines.extend(
        [
            f"- Total inventoried size: {evaluation.prepared_context.inventory_summary.total_size_bytes} bytes",
            "- Role counts: " + _mapping_summary(evaluation.prepared_context.inventory_summary.role_counts),
            "- Extension counts: "
            + _mapping_summary(evaluation.prepared_context.inventory_summary.extension_counts, limit=12),
            "",
            "### Detected Surfaces",
            "",
        ]
    )
    for surface in evaluation.prepared_context.surfaces:
        evidence = ", ".join(f"`{path}`" for path in surface.evidence[:8]) or "no file evidence"
        lines.append(f"- {surface.kind}: {surface.confidence} confidence; {evidence}")

    lines.extend(["", "### Governance Applicability", ""])
    if evaluation.prepared_context.governance_applicability:
        for applicability in evaluation.prepared_context.governance_applicability:
            lines.append(
                f"- {applicability.standard}: {applicability.state} "
                f"from `{applicability.source}`; {applicability.rationale}"
            )
    else:
        lines.append("- No governance applicability records were inferred.")

    lines.extend(["", "### Governance Material", ""])
    if evaluation.prepared_context.governance_materials:
        for material in evaluation.prepared_context.governance_materials:
            lines.extend(
                [
                    f"#### {material.standard}: `{material.path}`",
                    "",
                    f"- Source: {material.source}",
                ]
            )
            if material.read_error:
                lines.append(f"- Read error: {material.read_error}")
            else:
                lines.extend(
                    [
                        f"- Size: {material.size_bytes} bytes",
                        f"- SHA-256: `{material.sha256}`",
                        f"- Truncated: {'yes' if material.truncated else 'no'}",
                        "",
                        "```text",
                        material.excerpt or "[empty file]",
                        "```",
                    ]
                )
            lines.append("")
    else:
        lines.append("- No governance standard material was loaded.")

    if evaluation.prepared_context.notes:
        lines.append("")
        for note in evaluation.prepared_context.notes:
            lines.append(f"- Prepared context note: {note}")

    lines.extend(["", "### Deterministic Evidence Signals", ""])
    if evaluation.prepared_context.deterministic_evidence:
        for signal in evaluation.prepared_context.deterministic_evidence[:30]:
            lines.append(
                f"- {signal.category}: `{signal.path}` ({signal.size_bytes} bytes) - {signal.summary}"
            )
        if len(evaluation.prepared_context.deterministic_evidence) > 30:
            lines.append(
                f"- {len(evaluation.prepared_context.deterministic_evidence) - 30} additional evidence signals are present in `context-bundle.json`."
            )
    else:
        lines.append("- No deterministic evidence signals were inferred.")

    lines.extend(["", "### Representative Files", ""])
    if evaluation.prepared_context.representative_files:
        for file in evaluation.prepared_context.representative_files[:20]:
            lines.append(f"- `{file.path}` ({file.role}, {file.size_bytes} bytes): {file.reason}")
    else:
        lines.append("- No representative files selected.")

    lines.extend(["", "### Text Snippet Samples", ""])
    if evaluation.prepared_context.text_snippets:
        for snippet in evaluation.prepared_context.text_snippets[:6]:
            truncated = "yes" if snippet.truncated else "no"
            lines.extend(
                [
                    f"#### `{snippet.path}`",
                    "",
                    f"- Role: {snippet.role}",
                    f"- SHA-256: `{snippet.sha256}`",
                    f"- Truncated: {truncated}",
                    "",
                    "```text",
                    snippet.excerpt or "[empty file]",
                    "```",
                    "",
                ]
            )
        if len(evaluation.prepared_context.text_snippets) > 6:
            lines.append(f"- {len(evaluation.prepared_context.text_snippets) - 6} additional snippets are present in `context-bundle.json`.")
    else:
        lines.append("- No text snippets collected.")

    lines.extend(["", "## Authority Record Snapshots", ""])
    if evaluation.evidence.authority_records:
        for record in evaluation.evidence.authority_records[:10]:
            lines.extend(
                [
                    f"### {record.record_type}: `{record.path}`",
                    "",
                    f"- Size: {record.size_bytes} bytes",
                    f"- SHA-256: `{record.sha256}`",
                    "",
                    "```text",
                    record.excerpt or "[empty file]",
                    "```",
                    "",
                ]
            )
    else:
        lines.append("- No authority record snapshots were collected.")

    lines.extend(["", "## Evidence Notes", ""])
    if evaluation.evidence.notes:
        for note in evaluation.evidence.notes:
            lines.append(f"- {note}")
    else:
        lines.append("- No evidence collection notes.")

    lines.extend(["", "## Findings", ""])
    for finding in evaluation.findings:
        lines.extend(
            [
                f"### {finding.finding_class.value.title()}: {finding.title}",
                "",
                f"- Area: {finding.area}",
                f"- Authority: {finding.authority}",
                f"- Impact: {finding.impact}",
                f"- Consequence: {finding.consequence}",
            ]
        )
        if finding.recommendation:
            lines.append(f"- Recommendation: {finding.recommendation}")
        if finding.evidence:
            lines.append(f"- Evidence: {'; '.join(finding.evidence)}")
        lines.append("")

    lines.extend(
        [
            "## Run Record",
            "",
            f"- Report ID: `{evaluation.run.report_id}`",
            f"- Timestamp UTC: `{evaluation.run.timestamp_utc}`",
            f"- Evaluator version: `{evaluation.run.evaluator_version}`",
            f"- Reasoning provider: `{evaluation.run.reasoning_provider}`",
            f"- Model identifier: `{evaluation.run.model_identifier}`",
            "",
            "The prepared reasoning package is available in `reasoning-request.json` and `reasoning-request.md`.",
            "A fillable structured backend response skeleton is available in `response-template.json`.",
            "",
            _backend_note(evaluation.run.reasoning_provider),
            "",
        ]
    )
    return "\n".join(lines)


def _pct(value: int | None) -> str:
    return "Not assessed" if value is None else f"{value}%"


def _context_value(value) -> str:
    if value.value in (None, [], {}, ""):
        return "unknown"
    elif isinstance(value.value, list):
        rendered = ", ".join(str(item) for item in value.value)
    elif isinstance(value.value, dict):
        rendered = ", ".join(f"{key}={item}" for key, item in sorted(value.value.items()))
    else:
        rendered = str(value.value)

    if value.source:
        return f"{rendered} (`{value.source}`)"
    return rendered


def _mapping_summary(values: dict[str, int], limit: int | None = None) -> str:
    items = list(values.items())
    shown = items[:limit] if limit is not None else items
    rendered = ", ".join(f"{key}={value}" for key, value in shown)
    if limit is not None and len(items) > limit:
        rendered += f", +{len(items) - limit} more"
    return rendered or "none"


def _backend_note(provider: str) -> str:
    if provider == "none":
        return "This Phase 1 report is a structural evaluation artifact. Deep reasoning-model analysis is not enabled in this run."
    return "This report uses a parsed backend response. Deterministic preparation artifacts remain available for review."
