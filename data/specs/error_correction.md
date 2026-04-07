# Error Correction Reference
## All Issue Codes — Detection, Correction, and Escalation Guidance

---

## Flight-Level Errors

---

### INVALID_FLIGHT_NUMBER
**Severity:** ERROR
**Field:** `flight_number`
**Detection:** Does not match `^[A-Z]{2}\d{3,4}$`

**Correction guidance:**
1. Check if airline designator is lowercase → uppercase both characters
2. Check if space exists between designator and digits → remove space
3. Check if digits are fewer than 3 → pad with leading zero
4. If designator is unknown → RAG lookup against known IATA carrier list
5. If structure is unrecognisable → escalate to LLM with full message context

**Examples:**
| Raw | Corrected | Rule |
|-----|-----------|------|
| `lh401` | `LH401` | uppercase |
| `LH 401` | `LH401` | remove space |
| `LH41` | `LH041` | pad digits |

**Cannot auto-correct:** Completely unrecognisable string — escalate.

---

### INVALID_DATE_FORMAT
**Severity:** ERROR
**Field:** `flight_date`
**Detection:** Does not match `^\d{2}(JAN|FEB|...)$`

**Correction guidance (rule_fixer handles these):**
1. Single-digit day → prepend `0` (e.g. `1JAN` → `01JAN`)
2. Separator present → strip (e.g. `01-JAN` → `01JAN`)
3. Lowercase month → uppercase (e.g. `01jan` → `01JAN`)

**Correction guidance (RAG/LLM needed):**
4. ISO format date (`2024-01-14`) → reformat to `14JAN`
5. European format (`14/01/2024`) → extract day and month, reformat
6. Ambiguous date (month-first American format) → LLM with context to determine intent

**Cannot auto-correct:** Date value is logically invalid (e.g. `32JAN`) — escalate.

---

## Shipment-Level Errors

---

### INVALID_AIRPORT_FORMAT
**Severity:** ERROR
**Field:** `origin` or `destination`
**Detection:** Does not match `^[A-Z]{3}$`

**Correction guidance:**
1. Lowercase → uppercase all characters
2. Full city name present (e.g. `FRANKFURT`) → RAG lookup to find IATA code (`FRA`)
3. 4-letter ICAO code present (e.g. `EDDF`) → RAG lookup to convert to IATA (`FRA`)
4. Numeric characters present → escalate, cannot auto-correct

**Examples:**
| Raw | Corrected | Method |
|-----|-----------|--------|
| `fra` | `FRA` | uppercase |
| `FRANKFURT` | `FRA` | RAG city→code lookup |
| `EDDF` | `FRA` | RAG ICAO→IATA lookup |

---

### UNKNOWN_AIRPORT
**Severity:** WARNING
**Field:** `origin` or `destination`
**Detection:** Matches 3-letter format but not in known airport list

**Correction guidance:**
1. Format is valid — this is a data completeness warning, not a structural error
2. RAG lookup: is this airport code valid but missing from local list?
3. If RAG confirms valid IATA code → downgrade to INFO, no correction needed
4. If RAG cannot confirm → flag for human review

**Do not auto-correct** the airport code itself. The code may be correct and the local list incomplete.

---

### UNKNOWN_AWB_PREFIX
**Severity:** WARNING
**Field:** `awb_prefix`
**Detection:** 3-digit prefix not in known IATA prefix table

**Correction guidance:**
1. RAG lookup: is this prefix assigned to a carrier not in local table?
2. If RAG confirms valid carrier → downgrade to INFO, no correction needed
3. If RAG cannot confirm → flag for human review
4. Do not auto-correct the prefix

**Note:** IATA assigns hundreds of prefixes. The local table covers major carriers only.
An unknown prefix is more likely a table gap than a data error.

---

### ROUTING_MISMATCH
**Severity:** ERROR
**Field:** `routing`
**Detection:** Shipment routing does not equal `flight.origin + flight.destination`

**Correction guidance (rule_fixer handles these):**
1. Exact reversal (`JFKFRA` when flight is `FRA→JFK`) → swap halves, confidence 0.90
2. Flight routing substitution → replace with `origin+destination`, confidence 0.80

**Correction guidance (RAG/LLM needed):**
3. Routing contains valid airports but neither matches flight → AWB may belong to different flight
4. Partial match (one airport correct) → LLM to determine if transshipment routing is intended

**Cannot auto-correct:** Routing contains invalid airport codes — fix airport errors first.

---

### INVALID_WEIGHT
**Severity:** ERROR
**Field:** `weight_kg`
**Detection:** `weight_kg <= 0`

**Correction guidance:**
- Zero weight → cannot correct; weight is a mandatory measured value
- Negative weight → data entry error; cannot correct without source data
- Escalate to human in all cases

**RAG/LLM cannot help here.** Weight must come from physical measurement.
Always escalate INVALID_WEIGHT to human review.

---

### WEIGHT_EXCEEDS_MAX
**Severity:** WARNING
**Field:** `weight_kg`
**Detection:** `weight_kg > 100,000`

**Correction guidance:**
1. Check if weight is in grams instead of kg → divide by 1000 (if result is plausible)
2. Check if weight is in pounds → divide by 2.205 (if result is plausible)
3. LLM: use shipment description to assess plausibility of weight
4. If no unit conversion explains the value → flag for human review

**Examples:**
| Raw (kg) | Likely issue | Corrected |
|----------|-------------|-----------|
| 150000 | In grams? | 150 kg |
| 220000 | In pounds? | ~99,800 kg — still suspect |

**Do not auto-correct without high confidence.** Flag for human if uncertain.

---

### EMPTY_DESCRIPTION
**Severity:** WARNING
**Field:** `description`
**Detection:** Empty string or whitespace-only

**Correction guidance:**
1. Rule fixer cannot supply a description — no source data to derive from
2. LLM: if other shipment fields provide context (AWB prefix carrier, weight, routing), attempt to suggest a plausible generic description
3. Suggested descriptions must be clearly marked as AI-generated and require human confirmation
4. Do not insert a fabricated description as a confirmed correction

**LLM behaviour:** Generate a candidate description with low confidence (< 0.50), flagged as `requires_human_confirmation: true`.
