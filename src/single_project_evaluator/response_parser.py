from __future__ import annotations

import re
from typing import Any

from .models import (
    ApplicabilityState,
    AssessmentProfile,
    Finding,
    FindingAuthority,
    FindingClass,
)


class ResponseValidationError(ValueError):
    pass


INTENT_FIDELITY_VALUES = {"Strong", "Moderate", "Weak", "Contradictory", "Ambiguous"}
VERIFICATION_CONFIDENCE_VALUES = {"Strong", "Substantial", "Partial", "Weak", "Unverified"}
LIFECYCLE_FITNESS_VALUES = {"Appropriate", "Ahead of Evidence", "Behind Actual State", "Ambiguous"}
RELEASE_ELIGIBILITY_VALUES = {"PASS", "BLOCKED", "NOT APPLICABLE"}
POSTURE_FITNESS_PREFIXES = ("Personal - ", "Shared - ", "Adoptable - ")
POSTURE_FITNESS_VALUES = {"Strong", "Adequate", "Marginal", "Weak", "Not assessed"}
GOVERNANCE_CONFORMANCE_PATTERN = re.compile(
    r"^(?P<percent>100|[1-9]?\d)% \((?P<satisfied>0|[1-9]\d*)/(?P<applicable>0|[1-9]\d*) applicable controls satisfied\)$"
)
GOVERNANCE_CONFORMANCE_NOT_APPLICABLE = "N/A (0/0 applicable controls satisfied)"
UNCERTAINTY_EVIDENCE_PREFIX = "uncertainty:"


def parse_backend_response(
    data: dict[str, Any],
    expected_posture: str | None = None,
) -> tuple[AssessmentProfile, list[Finding], dict[str, str], list[str], str | None]:
    if not isinstance(data, dict):
        raise ResponseValidationError("Backend response must be a JSON object.")

    assessment = _parse_assessment(_required_dict(data, "assessment"))
    _validate_expected_posture(assessment.posture_fitness, expected_posture)
    findings = [_parse_finding(item) for item in _required_list(data, "findings")]
    _validate_finding_blocker_consistency(assessment, findings)
    governance = _parse_governance_conformance(data.get("governance_conformance", {}))
    uncertainties = data.get("uncertainties", [])
    if not isinstance(uncertainties, list) or not all(isinstance(item, str) for item in uncertainties):
        raise ResponseValidationError("uncertainties must be a list of strings when present.")
    narrative = _optional_string(data.get("narrative"), "narrative")

    return assessment, findings, governance, uncertainties, narrative


def _parse_assessment(data: dict[str, Any]) -> AssessmentProfile:
    release_eligibility = _enum_string(data, "release_eligibility", RELEASE_ELIGIBILITY_VALUES)
    blockers = _nonnegative_int(data.get("blockers"), "blockers")
    _validate_release_blocker_consistency(release_eligibility, blockers)
    return AssessmentProfile(
        functional_completeness=_optional_percent(data.get("functional_completeness"), "functional_completeness"),
        implementation_quality=_optional_percent(data.get("implementation_quality"), "implementation_quality"),
        intent_fidelity=_enum_string(data, "intent_fidelity", INTENT_FIDELITY_VALUES),
        verification_confidence=_enum_string(data, "verification_confidence", VERIFICATION_CONFIDENCE_VALUES),
        posture_fitness=_posture_fitness(data),
        lifecycle_fitness=_enum_string(data, "lifecycle_fitness", LIFECYCLE_FITNESS_VALUES),
        release_eligibility=release_eligibility,
        blockers=blockers,
    )


def _parse_finding(data: Any) -> Finding:
    if not isinstance(data, dict):
        raise ResponseValidationError("Each finding must be an object.")
    applicability = data.get("applicability")
    finding = Finding(
        title=_required_string(data, "title"),
        finding_class=FindingClass(_required_string(data, "finding_class")),
        area=_required_string(data, "area"),
        authority=FindingAuthority(_required_string(data, "authority")),
        applicability=ApplicabilityState(applicability) if applicability else None,
        evidence=_nonempty_string_list(data.get("evidence"), "evidence"),
        impact=_required_string(data, "impact"),
        consequence=_required_string(data, "consequence"),
        recommendation=_optional_string(data.get("recommendation"), "recommendation"),
    )
    _validate_finding_evidence_strength(finding)
    return finding


def _parse_governance_conformance(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ResponseValidationError("governance_conformance must be an object when present.")
    parsed: dict[str, str] = {}
    for standard, result in value.items():
        if not isinstance(standard, str) or not standard.strip():
            raise ResponseValidationError("governance_conformance keys must be non-empty standard names.")
        if not isinstance(result, str) or not result.strip():
            raise ResponseValidationError("governance_conformance values must be non-empty strings.")
        if result == GOVERNANCE_CONFORMANCE_NOT_APPLICABLE:
            parsed[standard] = result
            continue
        match = GOVERNANCE_CONFORMANCE_PATTERN.match(result)
        if not match:
            raise ResponseValidationError(
                "governance_conformance values must use '<percent>% (<satisfied>/<applicable> applicable controls satisfied)' "
                f"or {GOVERNANCE_CONFORMANCE_NOT_APPLICABLE!r}."
            )
        percent = int(match.group("percent"))
        satisfied = int(match.group("satisfied"))
        applicable = int(match.group("applicable"))
        if applicable == 0:
            raise ResponseValidationError(
                "governance_conformance values with 0 applicable controls must use "
                f"{GOVERNANCE_CONFORMANCE_NOT_APPLICABLE!r}."
            )
        if satisfied > applicable:
            raise ResponseValidationError("governance_conformance satisfied controls cannot exceed applicable controls.")
        expected_percent = round((satisfied / applicable) * 100)
        if percent != expected_percent:
            raise ResponseValidationError(
                "governance_conformance percent must match the rounded satisfied/applicable control count."
            )
        parsed[standard] = result
    return parsed


def _required_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ResponseValidationError(f"{key} must be an object.")
    return value


def _required_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ResponseValidationError(f"{key} must be a list.")
    return value


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ResponseValidationError(f"{key} must be a non-empty string.")
    return value


def _enum_string(data: dict[str, Any], key: str, allowed_values: set[str]) -> str:
    value = _required_string(data, key)
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise ResponseValidationError(f"{key} must be one of: {allowed}.")
    return value


def _posture_fitness(data: dict[str, Any]) -> str:
    value = _required_string(data, "posture_fitness")
    for prefix in POSTURE_FITNESS_PREFIXES:
        if value.startswith(prefix):
            suffix = value[len(prefix):]
            if suffix in POSTURE_FITNESS_VALUES:
                return value
    raise ResponseValidationError(
        "posture_fitness must start with Personal, Shared, or Adoptable and end with a valid fitness value."
    )


def _validate_expected_posture(posture_fitness: str, expected_posture: str | None) -> None:
    if expected_posture is None:
        return
    expected_prefix = expected_posture.strip().title() + " - "
    if not posture_fitness.startswith(expected_prefix):
        raise ResponseValidationError(
            f"posture_fitness must start with {expected_prefix!r} for declared posture {expected_posture!r}."
        )


def _validate_release_blocker_consistency(release_eligibility: str, blockers: int) -> None:
    if release_eligibility == "BLOCKED" and blockers == 0:
        raise ResponseValidationError("release_eligibility BLOCKED requires blockers to be greater than 0.")
    if release_eligibility in {"PASS", "NOT APPLICABLE"} and blockers != 0:
        raise ResponseValidationError(
            "blockers must be 0 when release_eligibility is PASS or NOT APPLICABLE."
        )


def _validate_finding_blocker_consistency(assessment: AssessmentProfile, findings: list[Finding]) -> None:
    blocker_findings = [
        finding
        for finding in findings
        if finding.finding_class == FindingClass.REQUIRED
        and finding.applicability == ApplicabilityState.UNSATISFIED
        and _has_demonstrated_evidence(finding)
    ]
    if assessment.blockers > len(blocker_findings):
        raise ResponseValidationError(
            "blockers must be supported by at least that many required findings with unsatisfied applicability."
        )
    if assessment.release_eligibility in {"PASS", "NOT APPLICABLE"} and blocker_findings:
        raise ResponseValidationError(
            "required findings with unsatisfied applicability require BLOCKED release_eligibility."
        )


def _validate_finding_evidence_strength(finding: Finding) -> None:
    if (
        finding.finding_class == FindingClass.REQUIRED
        and finding.applicability == ApplicabilityState.UNSATISFIED
        and not _has_demonstrated_evidence(finding)
    ):
        raise ResponseValidationError(
            "required findings with unsatisfied applicability must include demonstrated evidence, "
            "not only uncertainty references."
        )


def _has_demonstrated_evidence(finding: Finding) -> bool:
    return any(not item.strip().lower().startswith(UNCERTAINTY_EVIDENCE_PREFIX) for item in finding.evidence)


def _optional_string(value: Any, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ResponseValidationError(f"{key} must be a string or null.")
    return value


def _string_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list):
        raise ResponseValidationError(f"{key} must be a list.")
    if not all(isinstance(item, str) for item in value):
        raise ResponseValidationError(f"{key} must contain only strings.")
    return value


def _nonempty_string_list(value: Any, key: str) -> list[str]:
    items = _string_list(value, key)
    if not items:
        raise ResponseValidationError(f"{key} must contain at least one evidence reference.")
    if not all(item.strip() for item in items):
        raise ResponseValidationError(f"{key} must contain only non-empty strings.")
    return items


def _optional_percent(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value < 0 or value > 100:
        raise ResponseValidationError(f"{key} must be an integer from 0 to 100 or null.")
    return value


def _nonnegative_int(value: Any, key: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ResponseValidationError(f"{key} must be a non-negative integer.")
    return value
