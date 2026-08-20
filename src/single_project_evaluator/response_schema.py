from __future__ import annotations

from typing import Any


EVALUATION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "assessment",
        "findings",
        "governance_conformance",
        "uncertainties",
        "narrative",
    ],
    "properties": {
        "assessment": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "functional_completeness",
                "implementation_quality",
                "intent_fidelity",
                "verification_confidence",
                "posture_fitness",
                "lifecycle_fitness",
                "release_eligibility",
                "blockers",
            ],
            "properties": {
                "functional_completeness": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
                "implementation_quality": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
                "intent_fidelity": {
                    "type": "string",
                    "enum": ["Strong", "Moderate", "Weak", "Contradictory", "Ambiguous"],
                },
                "verification_confidence": {
                    "type": "string",
                    "enum": ["Strong", "Substantial", "Partial", "Weak", "Unverified"],
                },
                "posture_fitness": {
                    "type": "string",
                    "pattern": "^(Personal|Shared|Adoptable) - (Strong|Adequate|Marginal|Weak|Not assessed)$",
                },
                "lifecycle_fitness": {
                    "type": "string",
                    "enum": ["Appropriate", "Ahead of Evidence", "Behind Actual State", "Ambiguous"],
                },
                "release_eligibility": {
                    "type": "string",
                    "enum": ["PASS", "BLOCKED", "NOT APPLICABLE"],
                },
                "blockers": {"type": "integer", "minimum": 0},
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "finding_class",
                    "area",
                    "authority",
                    "applicability",
                    "evidence",
                    "impact",
                    "consequence",
                    "recommendation",
                ],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "finding_class": {
                        "type": "string",
                        "enum": ["required", "should", "could", "observation"],
                    },
                    "area": {"type": "string", "minLength": 1},
                    "authority": {
                        "type": "string",
                        "enum": [
                            "governance_requirement",
                            "project_requirement",
                            "engineering_recommendation",
                            "adoption_recommendation",
                        ],
                    },
                    "applicability": {
                        "type": ["string", "null"],
                        "enum": ["satisfied", "unsatisfied", "deferred", "not_applicable", None],
                    },
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "impact": {"type": "string", "minLength": 1},
                    "consequence": {"type": "string", "minLength": 1},
                    "recommendation": {"type": ["string", "null"]},
                },
            },
        },
        "governance_conformance": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "uncertainties": {
            "type": "array",
            "items": {"type": "string"},
        },
        "narrative": {"type": ["string", "null"]},
    },
}


def build_openai_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "single_project_evaluation_response",
        "description": "Structured Single-Project Evaluator assessment response.",
        "strict": False,
        "schema": EVALUATION_RESPONSE_SCHEMA,
    }
