# FFM Field Specification
## Flight Manifest (FFM) — Flight-Level Fields

FFM messages describe a single flight and the shipments loaded on it.
The flight-level header appears on line 1 of every FFM message.

---

## 1. Flight Number

**Field:** `flight_number`
**Format:** Two uppercase letters followed by 3 or 4 digits.
**Regex:** `^[A-Z]{2}\d{3,4}$`
**Examples (valid):** `LH401`, `EK0203`, `BA117`
**Examples (invalid):** `LH 401`, `lh401`, `LH40`, `L401`

**Rules:**
- First two characters are the IATA airline designator (e.g. LH = Lufthansa, EK = Emirates)
- Digits are the flight number, zero-padded to 3 or 4 digits depending on carrier convention
- No spaces, hyphens, or lowercase permitted
- Designator must belong to a known IATA carrier

**Common errors:**
- Lowercase airline designator → uppercase both characters
- Missing leading zero on flight number → pad to carrier convention
- Space between designator and digits → remove space

---

## 2. Flight Date

**Field:** `flight_date`
**Format:** `DDMMM` — two-digit day followed by three-letter uppercase month abbreviation
**Regex:** `^\d{2}(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$`
**Examples (valid):** `01JAN`, `14APR`, `31DEC`
**Examples (invalid):** `1JAN`, `01-JAN`, `01jan`, `2024-01-14`

**Rules:**
- Day must be two digits, zero-padded (01 not 1)
- Month must be exactly 3 uppercase ASCII letters from the approved set
- No separators (hyphens, slashes, spaces) between day and month
- No year component in the field (year is contextually implied)

**Common errors:**
- Single-digit day → prepend zero (e.g. `1JAN` → `01JAN`)
- Separator present → strip separator (e.g. `01-JAN` → `01JAN`)
- Lowercase month → uppercase (e.g. `01jan` → `01JAN`)
- ISO date format → reformat to DDMMM

---

## 3. Origin Airport

**Field:** `origin`
**Format:** Three uppercase letters — IATA airport code
**Regex:** `^[A-Z]{3}$`
**Examples (valid):** `FRA`, `JFK`, `DXB`
**Examples (invalid):** `fr`, `FRANKFURT`, `fr1`

**Rules:**
- Exactly 3 uppercase ASCII letters
- Must be a valid IATA-assigned airport code
- Origin and destination together form the routing pair used to validate shipment routing

**Common errors:**
- Lowercase → uppercase all three characters
- More than 3 characters → likely a city name; look up IATA code
- Numeric character present → invalid, escalate to human

---

## 4. Destination Airport

**Field:** `destination`
**Format:** Three uppercase letters — IATA airport code
**Rules:** Identical to origin field above.

**Additional rule:**
- Destination must differ from origin
- Together `origin + destination` forms the expected routing string (e.g. `FRAJFK`)
  used to cross-validate shipment routing fields

---

## 5. Routing String (derived)

**Derived field:** `origin + destination` concatenated (6 characters)
**Example:** Origin `FRA`, Destination `JFK` → routing string `FRAJFK`

This derived value is used to validate the `routing` field in each shipment line.
It is not transmitted as a standalone field but is computed from origin and destination.
