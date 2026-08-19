from __future__ import annotations

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


def parse_backend_response(data: dict[str, Any]) -> tuple[AssessmentProfile, list[Finding], dict[str, str], list[str]]:
    if not isinstance(data, dict):
        raise ResponseValidationError("Backend response must be a JSON object.")

    assessment = _parse_assessment(_required_dict(data, "assessment"))
    findings = [_parse_finding(item) for item in _required_list(data, "findings")]
    governance = data.get("governance_conformance", {})
    if not isinstance(governance, dict):
        raise ResponseValidationError("governance_conformance must be an object when present.")
    uncertainties = data.get("uncertainties", [])
    if not isinstance(uncertainties, list) or not all(isinstance(item, str) for item in uncertainties):
        raise ResponseValidationError("uncertainties must be a list of strings when present.")

    return assessment, findings, {str(key): str(value) for key, value in governance.items()}, uncertainties


def _parse_assessment(data: dict[str, Any]) -> AssessmentProfile:
    return AssessmentProfile(
        functional_completeness=_optional_percent(data.get("functional_completeness"), "functional_completeness"),
        implementation_quality=_optional_percent(data.get("implementation_quality"), "implementation_quality"),
        intent_fidelity=_enum_string(data, "intent_fidelity", INTENT_FIDELITY_VALUES),
        verification_confidence=_enum_string(data, "verification_confidence", VERIFICATION_CONFIDENCE_VALUES),
        posture_fitness=_posture_fitness(data),
        lifecycle_fitness=_enum_string(data, "lifecycle_fitness", LIFECYCLE_FITNESS_VALUES),
        release_eligibility=_enum_string(data, "release_eligibility", RELEASE_ELIGIBILITY_VALUES),
        blockers=_nonnegative_int(data.get("blockers"), "blockers"),
    )


def _parse_finding(data: Any) -> Finding:
    if not isinstance(data, dict):
        raise ResponseValidationError("Each finding must be an object.")
    applicability = data.get("applicability")
    return Finding(
        title=_required_string(data, "title"),
        finding_class=FindingClass(_required_string(data, "finding_class")),
        area=_required_string(data, "area"),
        authority=FindingAuthority(_required_string(data, "authority")),
        applicability=ApplicabilityState(applicability) if applicability else None,
        evidence=_string_list(data.get("evidence"), "evidence"),
        impact=_required_string(data, "impact"),
        consequence=_required_string(data, "consequence"),
        recommendation=_optional_string(data.get("recommendation"), "recommendation"),
    )


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
