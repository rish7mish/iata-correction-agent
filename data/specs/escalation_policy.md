# Escalation Policy
## When to Correct, When to Escalate, When to Involve a Human

---

## Overview

The IATA correction agent uses a 3-tier escalation model.
Each tier attempts correction with increasing capability and cost.
Escalation happens only when the current tier cannot resolve the issue.

```
Tier 0 — rule_fixer       → deterministic rules, fast, high confidence
Tier 1 — rag_retriever    → spec lookup, moderate confidence
Tier 2 — llm_corrector    → reasoning under uncertainty, lower confidence
Human  — escalate         → cannot be resolved by automation
```

---

## Tier 0 — Rule Fixer

**Use when:**
- The fix is deterministic and lossless
- Confidence can be 0.85 or above
- No external lookup is needed

**Handles:**
- `INVALID_DATE_FORMAT` — padding, separator removal
- `ROUTING_MISMATCH` — exact reversal correction

**Does not handle:**
- Any error requiring external knowledge (carrier lists, airport codes)
- Any error where the correct value cannot be derived from the message itself

**Escalate to Tier 1 if:** Rule fixer finds no matching rule for the issue code.

---

## Tier 1 — RAG Retriever

**Use when:**
- Correction requires lookup against spec or reference data
- The issue involves an unknown code that may be valid but absent from local tables
- Format is correct but value needs validation against a known set

**Handles well:**
- `INVALID_AIRPORT_FORMAT` — city name to IATA code lookup
- `UNKNOWN_AIRPORT` — confirm if valid IATA code outside local list
- `UNKNOWN_AWB_PREFIX` — confirm if valid carrier prefix outside local table
- `INVALID_FLIGHT_NUMBER` — carrier designator lookup

**Confidence threshold:** Only apply a RAG-derived correction if retrieved chunk similarity > 0.75 and correction rationale is unambiguous.

**Escalate to Tier 2 if:**
- RAG retrieves no relevant chunks (similarity < 0.50)
- Retrieved chunks are ambiguous or contradictory
- Issue requires reasoning, not just lookup

---

## Tier 2 — LLM Corrector

**Use when:**
- Tier 0 and Tier 1 have failed or are insufficient
- The correction requires reasoning about context, intent, or plausibility
- Multiple fields must be considered together

**Handles:**
- `WEIGHT_EXCEEDS_MAX` — unit conversion plausibility reasoning
- `EMPTY_DESCRIPTION` — candidate description generation (low confidence)
- `ROUTING_MISMATCH` — complex cases where RAG context is needed
- `INVALID_DATE_FORMAT` — ISO or ambiguous format conversion

**Confidence behaviour:**
- LLM corrections must include explicit confidence score
- Corrections below 0.60 confidence must be flagged `requires_human_confirmation: true`
- LLM must never fabricate reference data (airport codes, AWB prefixes, carrier names)

**Escalate to Human if:**
- LLM confidence < 0.50 after 1 attempt
- Error type is `INVALID_WEIGHT` (weight cannot be inferred)
- Multiple conflicting corrections would need to be applied simultaneously
- LLM produces inconsistent corrections across retry attempts

---

## Human Escalation

**Always escalate to human for:**

| Issue | Reason |
|-------|--------|
| `INVALID_WEIGHT` | Physical measurement required |
| `WEIGHT_EXCEEDS_MAX` with no plausible unit conversion | Source data needed |
| Any ERROR with confidence < 0.50 after Tier 2 | Risk of wrong correction |
| Conflicting fixes across fields | Systemic data problem |
| Message structurally unparseable | Parser failed before classification |

**Human escalation output:**
- Full original message
- List of unresolved issues with descriptions
- Any partial fixes applied by Tier 0/1/2 with confidence scores
- Recommended action for each unresolved issue

---

## Confidence Score Reference

| Range | Interpretation | Action |
|-------|---------------|--------|
| 0.90 – 1.00 | High confidence | Apply automatically |
| 0.75 – 0.89 | Moderate confidence | Apply, log for audit |
| 0.60 – 0.74 | Low confidence | Apply with flag |
| < 0.60 | Insufficient confidence | Escalate to next tier or human |

---

## Escalation Loop Limit

Maximum escalation attempts per issue: **2**
- Attempt 1: Tier 1 (RAG)
- Attempt 2: Tier 2 (LLM)
- After 2 failed attempts: human escalation, no further retries

This prevents infinite loops and bounds latency per message.
