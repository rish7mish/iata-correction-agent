from __future__ import annotations

import re
from src.state import AgentState, AppliedFix


def rule_fixer_node(state: AgentState) -> dict:
    issues = state.get("issues", [])
    existing_fixes = list(state.get("fixes_applied", []))
    parsed = state.get("parsed")

    new_fixes: list[AppliedFix] = []

    for issue in issues:
        code      = issue["issue_code"]
        field     = issue["field"]
        raw_value = issue["raw_value"]

        # R01 — routing mismatch
        if code == "ROUTING_MISMATCH" and parsed:
            flight   = parsed["flight"]
            expected = flight["origin"] + flight["destination"]
            if len(raw_value) == 6 and raw_value[3:] + raw_value[:3] == expected:
                corrected  = expected
                confidence = 0.90
                rationale  = f"R01: Routing '{raw_value}' is reversed; corrected to '{corrected}'."
            else:
                corrected  = expected
                confidence = 0.80
                rationale  = f"R01: Routing '{raw_value}' replaced with flight routing '{corrected}'. Verify AWB intent."
            new_fixes.append(AppliedFix(
                node="rule_fixer", field=field,
                old_value=raw_value, new_value=corrected,
                confidence=confidence, rationale=rationale,
            ))

        # R03 — date format
        elif code == "INVALID_DATE_FORMAT":
            cleaned = raw_value.replace("-", "").replace(" ", "")
            MON = r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
            if re.match(rf"^\d{MON}$", cleaned):
                corrected = "0" + cleaned
                new_fixes.append(AppliedFix(
                    node="rule_fixer", field=field,
                    old_value=raw_value, new_value=corrected,
                    confidence=0.95,
                    rationale=f"R03: Padded single-digit day: '{raw_value}' -> '{corrected}'.",
                ))
            elif re.match(rf"^\d\d{MON}$", cleaned) and cleaned != raw_value:
                new_fixes.append(AppliedFix(
                    node="rule_fixer", field=field,
                    old_value=raw_value, new_value=cleaned,
                    confidence=0.90,
                    rationale=f"R03: Removed separator: '{raw_value}' -> '{cleaned}'.",
                ))

    return {"fixes_applied": existing_fixes + new_fixes}