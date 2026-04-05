from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.graph import compile_graph
from src.state import AgentState

app = FastAPI(
    title="IATA Correction Agent",
    description="LangGraph-powered agent for FFM/FWB message validation and correction.",
    version="0.1.0",
)

_graph = compile_graph()


class CorrectRequest(BaseModel):
    raw_message: str = Field(..., description="Raw IATA FFM or FWB message text")


class IssueOut(BaseModel):
    line_index: int
    field: str
    issue_code: str
    severity: str
    raw_value: str
    description: str


class FixOut(BaseModel):
    node: str
    field: str
    old_value: str
    new_value: str
    confidence: float
    rationale: str


class ValidationOut(BaseModel):
    passed: bool
    score: float
    remaining_issue_count: int


class CorrectResponse(BaseModel):
    status: str
    message_type: str
    parse_errors: list[str]
    issues_detected: list[IssueOut]
    fixes_applied: list[FixOut]
    escalation_tier: int
    validation_attempts: int
    validation: ValidationOut
    final_message: str


def _build_initial_state(raw: str) -> AgentState:
    return AgentState(
        raw_message=raw,
        parsed=None,
        parse_errors=[],
        message_type="",
        issues=[],
        escalation_tier=0,
        fixes_applied=[],
        corrected_message="",
        validation_result=None,
        validation_attempts=0,
        status="ESCALATED",
        final_message="",
    )


def _state_to_response(state: AgentState) -> CorrectResponse:
    vr = state.get("validation_result") or {}
    return CorrectResponse(
        status=state["status"],
        message_type=state.get("message_type", "UNKNOWN"),
        parse_errors=state.get("parse_errors", []),
        issues_detected=[IssueOut(**i) for i in state.get("issues", [])],
        fixes_applied=[FixOut(**f) for f in state.get("fixes_applied", [])],
        escalation_tier=state.get("escalation_tier", 0),
        validation_attempts=state.get("validation_attempts", 0),
        validation=ValidationOut(
            passed=vr.get("passed", False),
            score=vr.get("score", 0.0),
            remaining_issue_count=len(vr.get("remaining_issues", [])),
        ),
        final_message=state.get("final_message", state.get("raw_message", "")),
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


@app.post("/correct", response_model=CorrectResponse)
def correct(req: CorrectRequest):
    if not req.raw_message.strip():
        raise HTTPException(status_code=400, detail="raw_message is empty")
    try:
        state = _graph.invoke(_build_initial_state(req.raw_message))
        return _state_to_response(state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc