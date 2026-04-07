from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.state import AgentState, AppliedFix

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL      = "claude-haiku-4-5-20251001"   # fast + cheap for correction tasks
MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# Client — lazy init
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set in environment or .env file")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert IATA cargo message correction assistant.
You are given:
1. A list of unresolved issues found in an IATA message
2. Relevant spec context retrieved from the IATA specification
3. The parsed message fields for context

Your job is to suggest corrections for each issue.

Rules:
- Only correct what you are confident about
- Never fabricate airport codes, AWB prefixes, or carrier names
- If you cannot correct an issue with confidence >= 0.60, say so
- Return ONLY a JSON array, no explanation, no markdown fences

Each correction must be a JSON object with these exact keys:
{
  "field": "field name",
  "old_value": "original value",
  "new_value": "corrected value",
  "confidence": 0.00 to 1.00,
  "rationale": "one sentence explanation"
}

If you cannot correct an issue, omit it from the array.
Return an empty array [] if nothing can be corrected.
"""


def _build_user_prompt(
    issues: list[dict],
    rag_context: list[dict],
    parsed: dict | None,
) -> str:
    # Format unresolved issues
    issues_text = json.dumps(issues, indent=2)

    # Format RAG context — group by issue_code, take top 2 per code
    seen: dict[str, int] = {}
    context_lines: list[str] = []
    for chunk in rag_context:
        code = chunk["issue_code"]
        seen[code] = seen.get(code, 0) + 1
        if seen[code] <= 2:
            context_lines.append(
                f"[{code} | {chunk['source']} | {chunk['heading']} | dist={chunk['distance']:.3f}]\n{chunk['text'][:500]}"
            )
    context_text = "\n\n".join(context_lines) if context_lines else "No spec context retrieved."

    # Format parsed message summary
    if parsed:
        flight = parsed.get("flight", {})
        flight_summary = (
            f"Flight: {flight.get('flight_number')} on {flight.get('flight_date')} "
            f"from {flight.get('origin')} to {flight.get('destination')}"
        )
        shipment_count = len(parsed.get("shipments", []))
        parsed_summary = f"{flight_summary}\nShipments: {shipment_count}"
    else:
        parsed_summary = "Parsed message not available."

    return f"""## Unresolved Issues
{issues_text}

## Retrieved Spec Context
{context_text}

## Parsed Message Summary
{parsed_summary}

Return a JSON array of corrections only. No explanation outside the JSON.
"""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> list[dict]:
    """Extract JSON array from LLM response. Handles minor formatting issues."""
    text = text.strip()
    # Strip any accidental markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        )
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return []


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

def llm_corrector_node(state: AgentState) -> dict:
    """
    Uses Anthropic Claude to correct issues that rule_fixer and rag_retriever
    could not resolve. Uses rag_context as grounding to reduce hallucination.
    """
    # Get unresolved issues
    validation = state.get("validation_result")
    if validation and validation.get("remaining_issues"):
        issues = validation["remaining_issues"]
    else:
        issues = state.get("issues", [])

    if not issues:
        return {"escalation_tier": 2}

    rag_context = state.get("rag_context", [])
    parsed      = state.get("parsed")

    # Build prompt
    user_prompt = _build_user_prompt(issues, rag_context, parsed)

    # Call Anthropic API
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text     = response.content[0].text
    corrections  = _parse_response(raw_text)

    # Convert to AppliedFix list
    existing_fixes = list(state.get("fixes_applied", []))
    new_fixes: list[AppliedFix] = []

    for c in corrections:
        # Validate required keys present
        if not all(k in c for k in ("field", "old_value", "new_value", "confidence", "rationale")):
            continue
        # Only apply if confidence meets threshold
        if c["confidence"] < 0.60:
            continue
        new_fixes.append(AppliedFix(
            node="llm_corrector",
            field=c["field"],
            old_value=c["old_value"],
            new_value=c["new_value"],
            confidence=c["confidence"],
            rationale=f"LLM: {c['rationale']}",
        ))

    return {
        "fixes_applied":  existing_fixes + new_fixes,
        "escalation_tier": 2,
    }