from __future__ import annotations

import re
from src.state import AgentState, IssueDetail, ParsedMessage

VALID_AWB_PREFIXES = {
    "001": "American Airlines Cargo",
    "006": "Delta Air Lines",
    "014": "Air Canada",
    "020": "Lufthansa Cargo",
    "057": "Air France/KLM Cargo",
    "074": "Air France",
    "098": "China Airlines",
    "117": "British Airways",
    "125": "Lufthansa",
    "160": "Japan Airlines",
    "176": "Emirates SkyCargo",
    "180": "Singapore Airlines",
    "236": "Korean Air Cargo",
    "618": "Cathay Pacific",
}

VALID_IATA_AIRPORTS = {
    "FRA", "ORD", "JFK", "LAX", "LHR", "CDG", "DXB", "SIN", "HKG",
    "NRT", "ICN", "PVG", "BOM", "DEL", "SYD", "MEL", "AMS", "ZRH",
    "MUC", "MAN", "BCN", "MAD", "FCO", "ATL", "DFW", "MIA", "SFO",
}

RE_FLIGHT_NUM = re.compile(r"^[A-Z]{2}\d{3,4}$")
RE_DATE       = re.compile(r"^\d{2}(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$")
RE_AIRPORT    = re.compile(r"^[A-Z]{3}$")


def _issue(line_index, field, code, severity, raw_value, desc) -> IssueDetail:
    return IssueDetail(
        line_index=line_index,
        field=field,
        issue_code=code,
        severity=severity,
        raw_value=raw_value,
        description=desc,
    )


def classify_node(state: AgentState) -> dict:
    parsed: ParsedMessage = state["parsed"]
    issues: list[IssueDetail] = []
    flight = parsed["flight"]

    if not RE_FLIGHT_NUM.match(flight["flight_number"]):
        issues.append(_issue(1, "flight_number", "INVALID_FLIGHT_NUMBER", "ERROR",
                             flight["flight_number"],
                             f"Flight number '{flight['flight_number']}' does not match [A-Z]{{2}}[0-9]{{3,4}}"))

    if not RE_DATE.match(flight["flight_date"]):
        issues.append(_issue(1, "flight_date", "INVALID_DATE_FORMAT", "ERROR",
                             flight["flight_date"],
                             f"Date '{flight['flight_date']}' does not match DDMMM format"))

    for field, code in [("origin", flight["origin"]), ("destination", flight["destination"])]:
        if not RE_AIRPORT.match(code):
            issues.append(_issue(1, field, "INVALID_AIRPORT_FORMAT", "ERROR", code,
                                 f"'{code}' is not a 3-letter IATA code"))
        elif code not in VALID_IATA_AIRPORTS:
            issues.append(_issue(1, field, "UNKNOWN_AIRPORT", "WARNING", code,
                                 f"'{code}' not in known airport list"))

    for idx, s in enumerate(parsed["shipments"]):
        line_idx = idx + 2

        if s["awb_prefix"] not in VALID_AWB_PREFIXES:
            issues.append(_issue(line_idx, "awb_prefix", "UNKNOWN_AWB_PREFIX", "WARNING",
                                 s["awb_prefix"],
                                 f"AWB prefix '{s['awb_prefix']}' not in known airline prefix table"))

        expected_routing = flight["origin"] + flight["destination"]
        if s["routing"] != expected_routing:
            issues.append(_issue(line_idx, "routing", "ROUTING_MISMATCH", "ERROR",
                                 s["routing"],
                                 f"Routing '{s['routing']}' does not match flight {expected_routing}"))

        if s["weight_kg"] <= 0:
            issues.append(_issue(line_idx, "weight_kg", "INVALID_WEIGHT", "ERROR",
                                 str(s["weight_kg"]), "Weight must be > 0"))

        if s["weight_kg"] > 100_000:
            issues.append(_issue(line_idx, "weight_kg", "WEIGHT_EXCEEDS_MAX", "WARNING",
                                 str(s["weight_kg"]), "Weight > 100,000 kg is suspicious"))

        if not s["description"].strip():
            issues.append(_issue(line_idx, "description", "EMPTY_DESCRIPTION", "WARNING",
                                 "", "Shipment description is empty"))

    return {"issues": issues}