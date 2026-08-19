from __future__ import annotations

import json
from pathlib import Path

from .models import Evaluation, FindingClass


def write_evaluation_artifacts(evaluation: Evaluation, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    evaluation_json = output_dir / "evaluation.json"
    report_md = output_dir / "report.md"
    run_record_json = output_dir / "run-record.json"

    data = evaluation.to_dict()
    evaluation_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    run_record_json.write_text(json.dumps(data["run"], indent=2), encoding="utf-8")
    report_md.write_text(render_markdown_report(evaluation), encoding="utf-8")

    return {
        "evaluation": evaluation_json,
        "report": report_md,
        "run_record": run_record_json,
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
        ("PPS path", evaluation.context.pps_path),
        ("README path", evaluation.context.readme_path),
    ]
    for label, value in context_rows:
        lines.append(f"- {label}: {_context_value(value)}")
    if evaluation.context.notes:
        lines.append("- Context notes: " + "; ".join(evaluation.context.notes))
    else:
        lines.append("- Context notes: none")

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
            "This Phase 1 report is a structural evaluation artifact. Deep reasoning-model analysis is not enabled in this run.",
            "",
        ]
    )
    return "\n".join(lines)


def _pct(value: int | None) -> str:
    return "Not assessed" if value is None else f"{value}%"


def _context_value(value) -> str:
    if value.value in (None, [], ""):
        return "unknown"
    elif isinstance(value.value, list):
        rendered = ", ".join(str(item) for item in value.value)
    else:
        rendered = str(value.value)

    if value.source:
        return f"{rendered} (`{value.source}`)"
    return rendered
