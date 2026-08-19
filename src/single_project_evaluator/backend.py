from __future__ import annotations

from dataclasses import dataclass

from .models import (
    AssessmentProfile,
    EvaluationRun,
    Finding,
    FindingAuthority,
    FindingClass,
    PreparedContext,
    ProjectContext,
    ProjectEvidence,
)


@dataclass(frozen=True)
class BackendResult:
    assessment: AssessmentProfile
    findings: list[Finding]


@dataclass(frozen=True)
class BackendIdentity:
    provider: str
    model_identifier: str


class NoopReasoningBackend:
    identity = BackendIdentity(provider="none", model_identifier="phase-1-spine")

    def evaluate(
        self,
        run: EvaluationRun,
        evidence: ProjectEvidence,
        context: ProjectContext,
        prepared_context: PreparedContext,
    ) -> BackendResult:
        return BackendResult(
            assessment=AssessmentProfile(
                posture_fitness=f"{run.declared_posture.value.title()} - Not assessed",
                release_eligibility="NOT APPLICABLE",
            ),
            findings=[
                Finding(
                    title="Deep reasoning evaluation is not yet implemented",
                    finding_class=FindingClass.OBSERVATION,
                    area="Evaluation Spine",
                    authority=FindingAuthority.ENGINEERING_RECOMMENDATION,
                    evidence=[
                        "Deterministic collection and preparation completed without invoking a reasoning backend."
                    ],
                    impact=(
                        "The generated artifacts prove the evaluation object shape and prepared context, "
                        "but do not yet judge the target project."
                    ),
                    consequence="No project-quality conclusions should be drawn from this Phase 1 run.",
                    recommendation="Use the context bundle to validate preparation before implementing model-backed evaluation.",
                )
            ],
        )


def create_backend(name: str) -> NoopReasoningBackend:
    if name == "none":
        return NoopReasoningBackend()
    raise ValueError(f"Unsupported reasoning backend: {name}")
