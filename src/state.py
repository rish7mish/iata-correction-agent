from __future__ import annotations
from typing import Literal, TypedDict


class ParsedShipment(TypedDict):
    piece_count: int
    awb_prefix: str
    awb_number: str
    routing: str
    weight_kg: float
    volume: float
    chargeable_weight: float
    description: str
    uld: str | None


class ParsedFlight(TypedDict):
    flight_number: str
    flight_date: str
    origin: str
    destination: str


class ParsedMessage(TypedDict):
    message_type: str
    version: str
    flight: ParsedFlight
    shipments: list[ParsedShipment]
    raw_lines: list[str]


class IssueDetail(TypedDict):
    line_index: int
    field: str
    issue_code: str
    severity: Literal["ERROR", "WARNING"]
    raw_value: str
    description: str


class AppliedFix(TypedDict):
    node: str
    field: str
    old_value: str
    new_value: str
    confidence: float
    rationale: str


class ValidationResult(TypedDict):
    passed: bool
    remaining_issues: list[IssueDetail]
    score: float


class RagChunk(TypedDict):
    issue_code: str      # which issue this chunk was retrieved for
    heading: str         # section heading from the spec doc
    source: str          # which spec file (e.g. 'error_correction')
    text: str            # full chunk text
    distance: float      # cosine distance — lower = more relevant


class AgentState(TypedDict):
    raw_message: str
    parsed: ParsedMessage | None
    parse_errors: list[str]
    message_type: str
    issues: list[IssueDetail]
    escalation_tier: int
    fixes_applied: list[AppliedFix]
    corrected_message: str
    validation_result: ValidationResult | None
    validation_attempts: int
    status: Literal["PASS", "FAIL", "ESCALATED", "PARSE_ERROR"]
    final_message: str
    rag_context: list[RagChunk]   # populated by rag_retriever_node