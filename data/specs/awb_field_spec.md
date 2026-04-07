# AWB Field Specification
## Air Waybill (FWB) — Shipment-Level Fields

Each shipment line in an FFM references a single Air Waybill (AWB).
FWB data describes the individual cargo consignment.

---

## 1. AWB Prefix

**Field:** `awb_prefix`
**Format:** 3-digit numeric string
**Examples (valid):** `020`, `176`, `618`
**Examples (invalid):** `99`, `9999`, `ABC`

**Rules:**
- Exactly 3 digits
- Must match a known IATA airline prefix
- Prefix identifies the issuing carrier, not necessarily the operating carrier

**Known valid prefixes:**

| Prefix | Carrier |
|--------|---------|
| 001 | American Airlines Cargo |
| 006 | Delta Air Lines |
| 014 | Air Canada |
| 020 | Lufthansa Cargo |
| 057 | Air France/KLM Cargo |
| 074 | Air France |
| 098 | China Airlines |
| 117 | British Airways |
| 125 | Lufthansa |
| 160 | Japan Airlines |
| 176 | Emirates SkyCargo |
| 180 | Singapore Airlines |
| 236 | Korean Air Cargo |
| 618 | Cathay Pacific |

**Common errors:**
- Unknown prefix → WARNING only; prefix may belong to a regional carrier not in local table
- Do not auto-correct; flag for human review or RAG lookup

---

## 2. Routing

**Field:** `routing`
**Format:** 6 uppercase letters — concatenation of origin and destination IATA codes
**Examples (valid):** `FRAJFK`, `DXBSIN`, `LHRDXB`
**Examples (invalid):** `FRA-JFK`, `jfkfra`, `JFKFRA` (if flight is FRA→JFK)

**Rules:**
- Must exactly match the flight-level routing string (`origin + destination`)
- If routing is reversed (destination+origin instead of origin+destination), it is a reversal error
- Separator characters are not permitted

**Common errors:**
- Reversed routing → swap first 3 and last 3 characters (confidence 0.90 if exact reverse)
- Routing does not match flight at all → flag ROUTING_MISMATCH, attempt correction with flight routing

---

## 3. Weight (kg)

**Field:** `weight_kg`
**Format:** Positive numeric value (float or integer)
**Valid range:** `0 < weight_kg ≤ 100,000`

**Rules:**
- Weight must be greater than zero
- Weight above 100,000 kg is flagged as suspicious but not auto-rejected
- Typical single-shipment weights: 10 kg (courier) to 10,000 kg (heavy freight)
- Weights above 45,000 kg are exceptional and should trigger a warning

**Common errors:**
- Zero or negative weight → INVALID_WEIGHT ERROR; cannot auto-correct, escalate
- Weight > 100,000 kg → WEIGHT_EXCEEDS_MAX WARNING; flag for human verification
- Weight in pounds transmitted as kg → value will appear ~2.2x expected; cannot auto-detect

---

## 4. Description

**Field:** `description`
**Format:** Free text string, non-empty
**Examples (valid):** `"Electronic Components"`, `"Pharmaceutical Supplies"`, `"Machine Parts"`
**Examples (invalid):** `""`, `"   "` (whitespace only)

**Rules:**
- Must not be empty or whitespace-only
- No specific format restriction beyond non-empty
- Description is used for customs and handling classification

**Common errors:**
- Empty string → EMPTY_DESCRIPTION WARNING; cannot auto-correct
- Whitespace-only → treated as empty
- Description is present but vague (e.g. "CARGO") → not flagged by current rules

---

## 5. AWB Number (full)

**Derived:** `awb_prefix` + `-` + serial number (if available)
**Format:** `NNN-NNNNNNNN` (3 digit prefix, hyphen, 8 digit serial)
**Example:** `020-12345678`

The serial number is not currently validated by classifier rules but may be added in future.
