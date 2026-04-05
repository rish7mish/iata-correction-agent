from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.state import AgentState
from src.nodes.parser import parse_node
from src.nodes.classifier import classify_node
from src.nodes.rule_fixer import rule_fixer_node
from src.nodes.rag_retriever import rag_retriever_node
from src.nodes.llm_corrector import llm_corrector_node
from src.nodes.validator import validator_node

MAX_VALIDATION_ATTEMPTS = 3


def route_after_parse(state: AgentState) -> str:
    if state.get("parsed") is None:
        return "end_parse_error"
    return "classify"


def route_to_fixer(state: AgentState) -> str:
    tier = state.get("escalation_tier", 0)
    if tier == 0:
        return "rule_fixer"
    elif tier == 1:
        return "rag_retriever"
    else:
        return "llm_corrector"


def route_after_validate(state: AgentState) -> str:
    vr       = state.get("validation_result")
    attempts = state.get("validation_attempts", 0)

    if vr and vr["passed"]:
        return "end_pass"

    if attempts >= MAX_VALIDATION_ATTEMPTS or state.get("escalation_tier", 0) >= 2:
        return "end_fail"

    return "escalate"


def escalate_tier(state: AgentState) -> dict:
    return {"escalation_tier": state.get("escalation_tier", 0) + 1}


def end_pass(state: AgentState) -> dict:
    return {
        "status": "PASS",
        "final_message": state.get("corrected_message", state["raw_message"]),
    }


def end_fail(state: AgentState) -> dict:
    return {
        "status": "FAIL",
        "final_message": state.get("corrected_message", state["raw_message"]),
    }


def end_parse_error(state: AgentState) -> dict:
    return {"status": "PARSE_ERROR", "final_message": state["raw_message"]}


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("parse",           parse_node)
    g.add_node("classify",        classify_node)
    g.add_node("rule_fixer",      rule_fixer_node)
    g.add_node("rag_retriever",   rag_retriever_node)
    g.add_node("llm_corrector",   llm_corrector_node)
    g.add_node("validate",        validator_node)
    g.add_node("escalate",        escalate_tier)
    g.add_node("end_pass",        end_pass)
    g.add_node("end_fail",        end_fail)
    g.add_node("end_parse_error", end_parse_error)

    g.set_entry_point("parse")

    g.add_conditional_edges("parse", route_after_parse, {
        "classify":        "classify",
        "end_parse_error": "end_parse_error",
    })

    g.add_conditional_edges("classify", route_to_fixer, {
        "rule_fixer":    "rule_fixer",
        "rag_retriever": "rag_retriever",
        "llm_corrector": "llm_corrector",
    })

    for fixer in ("rule_fixer", "rag_retriever", "llm_corrector"):
        g.add_edge(fixer, "validate")

    g.add_conditional_edges("validate", route_after_validate, {
        "end_pass": "end_pass",
        "end_fail": "end_fail",
        "escalate": "escalate",
    })

    g.add_conditional_edges("escalate", route_to_fixer, {
        "rule_fixer":    "rule_fixer",
        "rag_retriever": "rag_retriever",
        "llm_corrector": "llm_corrector",
    })

    for terminal in ("end_pass", "end_fail", "end_parse_error"):
        g.add_edge(terminal, END)

    return g


def compile_graph():
    return build_graph().compile()