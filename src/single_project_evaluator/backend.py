from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from .response_parser import parse_backend_response


@dataclass(frozen=True)
class BackendResult:
    assessment: AssessmentProfile
    findings: list[Finding]
    governance_conformance: dict[str, str] | None = None
    uncertainties: list[str] | None = None
    narrative: str | None = None


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


class ResponseFileBackend:
    def __init__(self, response_file: Path) -> None:
        self.response_file = response_file
        self.identity = BackendIdentity(
            provider="response-file",
            model_identifier=response_file.name,
        )

    def evaluate(
        self,
        run: EvaluationRun,
        evidence: ProjectEvidence,
        context: ProjectContext,
        prepared_context: PreparedContext,
    ) -> BackendResult:
        try:
            data = json.loads(self.response_file.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"Could not read response file `{self.response_file}`: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Response file is not valid JSON `{self.response_file}`: {exc}") from exc

        return backend_result_from_response(data)


def create_backend(name: str, response_file: Path | None = None) -> NoopReasoningBackend | ResponseFileBackend:
    if name == "none":
        return NoopReasoningBackend()
    if name == "response-file":
        if response_file is None:
            raise ValueError("--response-file is required when --backend response-file is used.")
        return ResponseFileBackend(response_file)
    raise ValueError(f"Unsupported reasoning backend: {name}")


def backend_result_from_response(data: dict[str, Any]) -> BackendResult:
    assessment, findings, governance_conformance, uncertainties, narrative = parse_backend_response(data)
    return BackendResult(
        assessment=assessment,
        findings=findings,
        governance_conformance=governance_conformance,
        uncertainties=uncertainties,
        narrative=narrative,
    )
