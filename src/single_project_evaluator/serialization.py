from __future__ import annotations

from typing import Any

from .models import (
    AdoptionPosture,
    ApplicabilityState,
    AssessmentProfile,
    AuthorityRecord,
    ContextValue,
    DeterministicEvidence,
    Evaluation,
    EvaluationRun,
    FileEvidence,
    Finding,
    FindingAuthority,
    FindingClass,
    GovernanceApplicability,
    GovernanceMaterial,
    InventorySummary,
    PreparedContext,
    ProjectContext,
    ProjectEvidence,
    RepresentativeFile,
    SurfaceEvidence,
    SurfaceKind,
    TextSnippet,
)


def evaluation_from_dict(data: dict[str, Any]) -> Evaluation:
    return Evaluation(
        run=_run(data["run"]),
        evidence=_evidence(data["evidence"]),
        context=_context(data["context"]),
        prepared_context=_prepared_context(data["prepared_context"]),
        assessment=_assessment(data["assessment"]),
        findings=[_finding(item) for item in data.get("findings", [])],
        governance_conformance={str(key): str(value) for key, value in data.get("governance_conformance", {}).items()},
        uncertainties=[str(item) for item in data.get("uncertainties", [])],
        narrative=data.get("narrative"),
    )


def _run(data: dict[str, Any]) -> EvaluationRun:
    return EvaluationRun(
        report_id=str(data["report_id"]),
        timestamp_utc=str(data["timestamp_utc"]),
        project_root=str(data["project_root"]),
        declared_posture=AdoptionPosture(data["declared_posture"]),
        evaluator_version=str(data["evaluator_version"]),
        reasoning_provider=str(data["reasoning_provider"]),
        model_identifier=str(data["model_identifier"]),
        configuration=dict(data.get("configuration", {})),
    )


def _evidence(data: dict[str, Any]) -> ProjectEvidence:
    return ProjectEvidence(
        root=str(data["root"]),
        project_name=str(data["project_name"]),
        files_examined=int(data["files_examined"]),
        files=[FileEvidence(**item) for item in data.get("files", [])],
        detected_records={str(key): list(value) for key, value in data.get("detected_records", {}).items()},
        authority_records=[AuthorityRecord(**item) for item in data.get("authority_records", [])],
        git_commit=data.get("git_commit"),
        notes=[str(item) for item in data.get("notes", [])],
    )


def _context(data: dict[str, Any]) -> ProjectContext:
    return ProjectContext(
        project_name=_context_value(data.get("project_name", {})),
        project_classes=_context_value(data.get("project_classes", {})),
        lifecycle_state=_context_value(data.get("lifecycle_state", {})),
        manifest_adoption_posture=_context_value(data.get("manifest_adoption_posture", {})),
        primary_standard=_context_value(data.get("primary_standard", {})),
        expected_delivery_standard=_context_value(data.get("expected_delivery_standard", {})),
        applicable_governance=_context_value(data.get("applicable_governance", {})),
        governance_standard_paths=_context_value(data.get("governance_standard_paths", {})),
        pps_path=_context_value(data.get("pps_path", {})),
        readme_path=_context_value(data.get("readme_path", {})),
        notes=[str(item) for item in data.get("notes", [])],
    )


def _prepared_context(data: dict[str, Any]) -> PreparedContext:
    return PreparedContext(
        inventory_summary=InventorySummary(**data.get("inventory_summary", {})),
        surfaces=[
            SurfaceEvidence(
                kind=SurfaceKind(item["kind"]),
                confidence=str(item["confidence"]),
                evidence=[str(path) for path in item.get("evidence", [])],
            )
            for item in data.get("surfaces", [])
        ],
        governance_applicability=[
            GovernanceApplicability(
                standard=str(item["standard"]),
                state=ApplicabilityState(item["state"]),
                source=str(item["source"]),
                rationale=str(item["rationale"]),
            )
            for item in data.get("governance_applicability", [])
        ],
        governance_materials=[GovernanceMaterial(**item) for item in data.get("governance_materials", [])],
        deterministic_evidence=[DeterministicEvidence(**item) for item in data.get("deterministic_evidence", [])],
        representative_files=[RepresentativeFile(**item) for item in data.get("representative_files", [])],
        text_snippets=[TextSnippet(**item) for item in data.get("text_snippets", [])],
        notes=[str(item) for item in data.get("notes", [])],
    )


def _assessment(data: dict[str, Any]) -> AssessmentProfile:
    return AssessmentProfile(**data)


def _finding(data: dict[str, Any]) -> Finding:
    applicability = data.get("applicability")
    return Finding(
        title=str(data["title"]),
        finding_class=FindingClass(data["finding_class"]),
        area=str(data["area"]),
        authority=FindingAuthority(data["authority"]),
        evidence=[str(item) for item in data.get("evidence", [])],
        impact=str(data["impact"]),
        consequence=str(data["consequence"]),
        recommendation=data.get("recommendation"),
        applicability=ApplicabilityState(applicability) if applicability else None,
    )


def _context_value(data: dict[str, Any]) -> ContextValue:
    return ContextValue(value=data.get("value"), source=data.get("source"))
