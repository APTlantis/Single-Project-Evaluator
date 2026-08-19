from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class AdoptionPosture(StrEnum):
    PERSONAL = "personal"
    SHARED = "shared"
    ADOPTABLE = "adoptable"


class ApplicabilityState(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    DEFERRED = "deferred"
    NOT_APPLICABLE = "not_applicable"


class FindingClass(StrEnum):
    REQUIRED = "required"
    SHOULD = "should"
    COULD = "could"
    OBSERVATION = "observation"


class FindingAuthority(StrEnum):
    GOVERNANCE_REQUIREMENT = "governance_requirement"
    PROJECT_REQUIREMENT = "project_requirement"
    ENGINEERING_RECOMMENDATION = "engineering_recommendation"
    ADOPTION_RECOMMENDATION = "adoption_recommendation"


@dataclass(frozen=True)
class FileEvidence:
    path: str
    size_bytes: int
    role: str = "source"


@dataclass(frozen=True)
class AuthorityRecord:
    path: str
    record_type: str
    size_bytes: int
    sha256: str
    excerpt: str


@dataclass(frozen=True)
class ProjectEvidence:
    root: str
    project_name: str
    files_examined: int
    files: list[FileEvidence] = field(default_factory=list)
    detected_records: dict[str, list[str]] = field(default_factory=dict)
    authority_records: list[AuthorityRecord] = field(default_factory=list)
    git_commit: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssessmentProfile:
    functional_completeness: int | None = None
    implementation_quality: int | None = None
    intent_fidelity: str = "Ambiguous"
    verification_confidence: str = "Unverified"
    posture_fitness: str = "Ambiguous"
    lifecycle_fitness: str = "Ambiguous"
    release_eligibility: str = "NOT APPLICABLE"
    blockers: int = 0


@dataclass(frozen=True)
class Finding:
    title: str
    finding_class: FindingClass
    area: str
    authority: FindingAuthority
    evidence: list[str]
    impact: str
    consequence: str
    recommendation: str | None = None
    applicability: ApplicabilityState | None = None


@dataclass(frozen=True)
class EvaluationRun:
    report_id: str
    timestamp_utc: str
    project_root: str
    declared_posture: AdoptionPosture
    evaluator_version: str
    reasoning_provider: str
    model_identifier: str
    configuration: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evaluation:
    run: EvaluationRun
    evidence: ProjectEvidence
    assessment: AssessmentProfile
    findings: list[Finding]
    governance_conformance: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
