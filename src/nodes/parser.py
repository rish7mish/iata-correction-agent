from __future__ import annotations

import re
from src.state import AgentState, ParsedFlight, ParsedMessage, ParsedShipment

RE_HEADER   = re.compile(r"^(FFM|FWB)/(\d+)$")
RE_FLIGHT   = re.compile(r"^\d+/([A-Z0-9]{2}\d{3,4})/(\d{1,2}[A-Z]{3})/([A-Z]{3})/([A-Z]{3})$")
RE_SHIPMENT = re.compile(
    r"^/(\d+)/(\d{3})-(\d+)([A-Z]{6})/([TP])(\d+)K(\d+(?:\.\d+)?)MC(\d+(?:\.\d+)?)/(.+)$"
)
RE_ULD      = re.compile(r"^/ULD/([A-Z]{3}\d+[A-Z]{2})$")


def _parse_shipment_line(line: str, current_uld: str | None) -> ParsedShipment | None:
    m = RE_SHIPMENT.match(line)
    if not m:
        return None
    _priority, awb_prefix, awb_number, routing, _ptype, _pc2, weight, volume, description = m.groups()
    return ParsedShipment(
        piece_count=int(_pc2),
        awb_prefix=awb_prefix,
        awb_number=awb_number,
        routing=routing,
        weight_kg=float(weight),
        volume=float(volume),
        chargeable_weight=0.0,
        description=description.strip(),
        uld=current_uld,
    )


def parse_node(state: AgentState) -> dict:
    raw = state["raw_message"].strip()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    parse_errors: list[str] = []

    if not lines:
        return {"parse_errors": ["Empty message"], "parsed": None, "message_type": "UNKNOWN"}

    hm = RE_HEADER.match(lines[0])
    if not hm:
        return {
            "parse_errors": [f"Unrecognised header: '{lines[0]}'"],
            "parsed": None,
            "message_type": "UNKNOWN",
        }

    msg_type, version = hm.group(1), hm.group(2)

    flight: ParsedFlight | None = None
    shipments: list[ParsedShipment] = []
    current_uld: str | None = None

    for i, line in enumerate(lines[1:], start=1):
        if line == "LAST":
            break

        fm = RE_FLIGHT.match(line)
        if fm:
            flight = ParsedFlight(
                flight_number=fm.group(1),
                flight_date=fm.group(2),
                origin=fm.group(3),
                destination=fm.group(4),
            )
            continue

        um = RE_ULD.match(line)
        if um:
            current_uld = um.group(1)
            continue

        sm = _parse_shipment_line(line, current_uld)
        if sm:
            shipments.append(sm)
            continue

        parse_errors.append(f"Line {i} unrecognised: '{line}'")

    if flight is None:
        parse_errors.append("No flight line found")

    parsed = ParsedMessage(
        message_type=msg_type,
        version=version,
        flight=flight or ParsedFlight(
            flight_number="", flight_date="", origin="", destination=""
        ),
        shipments=shipments,
        raw_lines=lines,
    )

    return {
        "parsed": parsed,
        "parse_errors": parse_errors,
        "message_type": msg_type,
        "issues": [],
        "escalation_tier": 0,
        "fixes_applied": [],
        "corrected_message": raw,
        "validation_result": None,
        "validation_attempts": 0,
        "status": "ESCALATED",
        "final_message": "",
    }