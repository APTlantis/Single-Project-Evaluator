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


class SurfaceKind(StrEnum):
    COMMAND_TOOL = "command_tool"
    DESKTOP_APP = "desktop_app"
    WEBSITE = "website"
    LIBRARY = "library"
    SERVICE = "service"
    DATASET = "dataset"
    UNKNOWN = "unknown"


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
class ContextValue:
    value: Any
    source: str | None = None


@dataclass(frozen=True)
class ProjectContext:
    project_name: ContextValue = field(default_factory=lambda: ContextValue(None))
    project_classes: ContextValue = field(default_factory=lambda: ContextValue([]))
    lifecycle_state: ContextValue = field(default_factory=lambda: ContextValue(None))
    manifest_adoption_posture: ContextValue = field(default_factory=lambda: ContextValue(None))
    primary_standard: ContextValue = field(default_factory=lambda: ContextValue(None))
    expected_delivery_standard: ContextValue = field(default_factory=lambda: ContextValue(None))
    applicable_governance: ContextValue = field(default_factory=lambda: ContextValue([]))
    governance_standard_paths: ContextValue = field(default_factory=lambda: ContextValue({}))
    pps_path: ContextValue = field(default_factory=lambda: ContextValue(None))
    readme_path: ContextValue = field(default_factory=lambda: ContextValue(None))
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InventorySummary:
    role_counts: dict[str, int] = field(default_factory=dict)
    extension_counts: dict[str, int] = field(default_factory=dict)
    total_size_bytes: int = 0


@dataclass(frozen=True)
class SurfaceEvidence:
    kind: SurfaceKind
    confidence: str
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GovernanceApplicability:
    standard: str
    state: ApplicabilityState
    source: str
    rationale: str


@dataclass(frozen=True)
class RepresentativeFile:
    path: str
    role: str
    size_bytes: int
    reason: str


@dataclass(frozen=True)
class TextSnippet:
    path: str
    role: str
    sha256: str
    chars: int
    truncated: bool
    excerpt: str


@dataclass(frozen=True)
class GovernanceMaterial:
    standard: str
    path: str
    source: str
    size_bytes: int
    sha256: str
    chars: int
    truncated: bool
    excerpt: str
    standard_version: str | None = None
    read_error: str | None = None


@dataclass(frozen=True)
class DeterministicEvidence:
    category: str
    path: str
    size_bytes: int
    summary: str


@dataclass(frozen=True)
class PreparedContext:
    inventory_summary: InventorySummary = field(default_factory=InventorySummary)
    surfaces: list[SurfaceEvidence] = field(default_factory=list)
    governance_applicability: list[GovernanceApplicability] = field(default_factory=list)
    governance_materials: list[GovernanceMaterial] = field(default_factory=list)
    deterministic_evidence: list[DeterministicEvidence] = field(default_factory=list)
    representative_files: list[RepresentativeFile] = field(default_factory=list)
    text_snippets: list[TextSnippet] = field(default_factory=list)
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
    context: ProjectContext
    prepared_context: PreparedContext
    assessment: AssessmentProfile
    findings: list[Finding]
    governance_conformance: dict[str, str] = field(default_factory=dict)
    uncertainties: list[str] = field(default_factory=list)
    narrative: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
