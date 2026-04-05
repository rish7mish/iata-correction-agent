from __future__ import annotations
from src.state import AgentState, ValidationResult

CONFIDENCE_THRESHOLD = 0.60


def validator_node(state: AgentState) -> dict:
    issues   = state.get("issues", [])
    fixes    = state.get("fixes_applied", [])
    attempts = state.get("validation_attempts", 0) + 1

    field_confidence: dict[str, float] = {}
    for fix in fixes:
        field_confidence[fix["field"]] = max(
            field_confidence.get(fix["field"], 0.0),
            fix["confidence"],
        )

    remaining = []
    for issue in issues:
        best_conf = field_confidence.get(issue["field"], 0.0)
        if best_conf < CONFIDENCE_THRESHOLD:
            remaining.append(issue)

    error_remaining = [i for i in remaining if i["severity"] == "ERROR"]
    total_issues    = len(issues) if issues else 1
    score           = 1.0 - len(remaining) / total_issues

    vr = ValidationResult(
        passed=len(error_remaining) == 0,
        remaining_issues=remaining,
        score=round(score, 3),
    )

    return {
        "validation_result":   vr,
        "validation_attempts": attempts,
    }