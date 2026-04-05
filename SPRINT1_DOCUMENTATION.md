# IATA Correction Agent — Sprint 1 Documentation

## What We Built

An AI agent that reads airline cargo messages (IATA FFM format), finds errors in them, and fixes them automatically. The agent uses LangGraph to orchestrate a multi-step, decision-driven pipeline with 3-tier escalation.

---

## The Problem Being Solved

Airlines send each other cargo manifests in a strict format called IATA IMP. Example:

```
FFM/1
1/LH8234/15OCT/FRA/ORD
/1/125-99887766FRAORD/T10K550.5MC1.2/FLOWERS
LAST
```

If any field is wrong — bad date format, wrong routing code, invalid weight — the receiving system rejects the entire message. Someone has to manually find and fix it. This agent does that automatically.

---

## All Classes Explained

### 1. `ParsedFlight`

Represents the flight details extracted from the message header line.

```python
class ParsedFlight(TypedDict):
    flight_number: str    # e.g. "LH8234" — carrier code + number
    flight_date: str      # e.g. "15OCT" — must be DDMMM format
    origin: str           # e.g. "FRA" — 3-letter IATA airport code
    destination: str      # e.g. "ORD" — 3-letter IATA airport code
```

Where it comes from: the line `1/LH8234/15OCT/FRA/ORD` in the FFM message.

Why it matters: every shipment's routing must match origin+destination. If the flight is FRA→ORD, every AWB routing must be FRAORD. Any mismatch is an error.

---

### 2. `ParsedShipment`

Represents one cargo shipment (one AWB) within the message.

```python
class ParsedShipment(TypedDict):
    piece_count: int       # number of pieces, e.g. 10 from "T10"
    awb_prefix: str        # airline prefix, e.g. "125" (Lufthansa)
    awb_number: str        # e.g. "99887766"
    routing: str           # e.g. "FRAORD" — must match flight
    weight_kg: float       # e.g. 550.5
    volume: float          # e.g. 1.2 cubic meters
    chargeable_weight: float  # derived field, 0.0 for now
    description: str       # cargo description, e.g. "FLOWERS"
    uld: str | None        # ULD container tag if applicable, else None
```

Where it comes from: lines like `/1/125-99887766FRAORD/T10K550.5MC1.2/FLOWERS`.

The AWB number format is: `PREFIX-NUMBERROUTING`. So `125-99887766FRAORD` breaks into prefix=125, number=99887766, routing=FRAORD.

The weight token format is: `T{pieces}K{weight}MC{volume}`. So `T10K550.5MC1.2` means 10 pieces, 550.5 kg, 1.2 m³.

The `uld` field is set when a `/ULD/AKE12345LH` line appears above the shipment line. All shipments after that line belong to that ULD container until a new ULD line appears.

---

### 3. `ParsedMessage`

The complete parsed FFM/FWB message — the flight plus all shipments.

```python
class ParsedMessage(TypedDict):
    message_type: str              # "FFM" or "FWB"
    version: str                   # "1"
    flight: ParsedFlight           # the flight details
    shipments: list[ParsedShipment] # all AWBs in the message
    raw_lines: list[str]           # original lines, for reference
```

This is the output of `parser.py`. Everything downstream reads from this.

---

### 4. `IssueDetail`

Represents one specific error or warning found by the classifier.

```python
class IssueDetail(TypedDict):
    line_index: int     # which line in the message (approximate)
    field: str          # which field has the problem, e.g. "flight_date"
    issue_code: str     # machine-readable code, e.g. "INVALID_DATE_FORMAT"
    severity: str       # "ERROR" or "WARNING"
    raw_value: str      # the actual bad value found, e.g. "5OCT"
    description: str    # human-readable explanation
```

Severity matters a lot:
- `ERROR` — blocks PASS. Must be fixed for the message to be accepted.
- `WARNING` — flagged but doesn't block PASS. E.g. unknown AWB prefix (our table might just be incomplete).

Issue codes used so far:
- `INVALID_DATE_FORMAT` — date doesn't match DDMMM pattern
- `ROUTING_MISMATCH` — AWB routing doesn't match flight origin+destination
- `INVALID_WEIGHT` — weight is zero or negative
- `UNKNOWN_AWB_PREFIX` — prefix not in our known airline table (WARNING)
- `UNKNOWN_AIRPORT` — airport not in our known list (WARNING)
- `INVALID_FLIGHT_NUMBER` — doesn't match carrier+digits format

---

### 5. `AppliedFix`

Represents one correction that a fixer node applied.

```python
class AppliedFix(TypedDict):
    node: str           # which node fixed it: "rule_fixer", "rag_retriever", "llm_corrector"
    field: str          # which field was fixed, e.g. "routing"
    old_value: str      # what it was before, e.g. "ORDFRA"
    new_value: str      # what it became, e.g. "FRAORD"
    confidence: float   # 0.0 to 1.0 — how confident the fix is correct
    rationale: str      # explanation of why this fix was applied
```

Confidence is critical — the validator uses it to decide if a fix "counts." Threshold is 0.60. Below that, the fix is ignored and the issue remains open.

Rule-fixer fixes have high confidence (0.80–0.95) because they're deterministic. LLM fixes will have lower confidence because they're probabilistic.

---

### 6. `ValidationResult`

The result of one validation pass after a fixer node runs.

```python
class ValidationResult(TypedDict):
    passed: bool                      # True if no ERROR issues remain uncovered
    remaining_issues: list[IssueDetail]  # issues not yet fixed
    score: float                      # fraction of issues resolved, 0.0 to 1.0
```

Passed = True only when every ERROR-severity issue has a fix with confidence ≥ 0.60. WARNING issues don't affect passed.

Score is informational — 1.0 means everything fixed, 0.0 means nothing fixed.

---

### 7. `AgentState`

The most important class. This is the shared memory that flows through every node in the graph.

```python
class AgentState(TypedDict):
    # Input
    raw_message: str              # the original FFM text you fed in

    # After parse node
    parsed: ParsedMessage | None  # structured data, None if parse failed
    parse_errors: list[str]       # fatal parse failures

    # After classify node
    message_type: str             # "FFM", "FWB", or "UNKNOWN"
    issues: list[IssueDetail]     # all errors/warnings found

    # Escalation control
    escalation_tier: int          # 0=rule_fixer, 1=rag, 2=llm
    fixes_applied: list[AppliedFix]  # all fixes from all tiers
    corrected_message: str        # the rebuilt message after fixes

    # After validate node
    validation_result: ValidationResult | None
    validation_attempts: int      # how many times we've validated

    # Terminal
    status: str                   # "PASS", "FAIL", "ESCALATED", "PARSE_ERROR"
    final_message: str            # the output message
```

Think of this as a form that gets passed from person to person in an office. Each person (node) reads it, does their job, fills in their section, and passes it on. Nobody rewrites what someone else already filled in — they only add to it.

---

## How We Used LangGraph

### The Core Concept

LangGraph lets you define a workflow as a directed graph — nodes connected by edges. Unlike a simple function chain, edges can be conditional: "go here if X, go there if Y." This is what makes it suitable for agents.

In our case the graph looks like this:

```
[START]
   ↓
[parse] ──(parsed is None)──→ [end_parse_error] → [END]
   ↓ (parsed ok)
[classify]
   ↓
[route_to_fixer] ──tier=0──→ [rule_fixer]
                ──tier=1──→ [rag_retriever]
                ──tier=2──→ [llm_corrector]
                                  ↓ (all three lead here)
                             [validate]
                           ↙    ↓      ↘
                    (pass)   (escalate)  (fail/max)
                      ↓          ↓           ↓
                 [end_pass]  [escalate]  [end_fail]
                      ↓          ↓           ↓
                    [END]  (tier+1, back   [END]
                            to route_to_fixer)
```

### Three LangGraph Concepts Used

**1. StateGraph**

You create the graph by telling LangGraph what your state looks like:

```python
from langgraph.graph import StateGraph
g = StateGraph(AgentState)
```

LangGraph then handles merging state updates automatically. When a node returns `{"issues": [...]}`, LangGraph merges that into the full state — you don't manage the state object yourself.

**2. Nodes**

Every node is a plain Python function:

```python
def parse_node(state: AgentState) -> dict:
    # read from state
    raw = state["raw_message"]
    # do work
    result = do_parsing(raw)
    # return ONLY what changed
    return {"parsed": result, "message_type": "FFM"}
```

Key rule: nodes return partial dicts, not the full state. LangGraph merges the partial dict back in. This means nodes are independent — they don't know about each other.

**3. Conditional Edges**

This is where the intelligence lives. After `validate` runs, we need to decide where to go next:

```python
def route_after_validate(state: AgentState) -> str:
    vr = state["validation_result"]
    attempts = state["validation_attempts"]

    if vr["passed"]:
        return "end_pass"        # all errors fixed → done
    if attempts >= 3 or state["escalation_tier"] >= 2:
        return "end_fail"        # exhausted all options → give up
    return "escalate"            # try next tier
```

The function returns a string key. You register a mapping of keys to node names:

```python
g.add_conditional_edges("validate", route_after_validate, {
    "end_pass": "end_pass",
    "end_fail": "end_fail",
    "escalate": "escalate",
})
```

LangGraph calls `route_after_validate(state)`, gets back a string, looks it up in the map, and sends execution to that node.

---

### The Escalation Loop — How It Works Technically

This is the most interesting LangGraph pattern in the project.

After `validate`, if we need to escalate:
1. `escalate` node runs — increments `escalation_tier` by 1
2. `route_to_fixer` conditional edge reads the new tier value
3. Sends to `rag_retriever` (tier 1) or `llm_corrector` (tier 2)
4. That fixer runs → goes to `validate` again
5. Repeat until pass or max attempts

The loop is capped at 3 validation attempts (`MAX_VALIDATION_ATTEMPTS = 3`). This prevents infinite loops — if nothing can fix the error after all 3 tiers, we accept FAIL and stop.

```
validate → escalate → route_to_fixer → rag_retriever → validate (attempt 2)
         → escalate → route_to_fixer → llm_corrector → validate (attempt 3)
         → end_fail (attempts >= 3)
```

No explicit loop construct is needed. The graph's edges create the loop naturally.

---

### Why LangGraph and Not Just Python Functions?

You could write this as a plain Python function with if/else. The reason to use LangGraph:

1. **Visibility** — LangGraph can visualize the graph. You can literally draw it and show it in an interview.
2. **State management** — LangGraph handles merging state between steps. You don't write boilerplate.
3. **Checkpointing** — LangGraph supports saving state mid-run (useful for long-running agents). We're not using this yet but it's available.
4. **Interview signal** — for the Adobe P4 role, "I built a multi-tier agentic system using LangGraph" is a concrete answer to "tell me about your AI system design experience." It maps directly to what Adobe uses.

---

## The Three Node Tiers — Conceptual Explanation

**Tier 0: rule_fixer**

No AI at all. Pure pattern matching.
- "Is the routing reversed?" → flip it
- "Is the date missing a leading zero?" → pad it
- Fast, free, high confidence
- Can only fix errors it has explicit rules for

**Tier 1: rag_retriever (Sprint 2)**

Retrieves relevant chunks from the IATA Cargo-IMP specification stored in ChromaDB. Uses vector similarity search to find spec sections relevant to the error. Passes those chunks to the LLM with context. More expensive than rules, cheaper than raw LLM.

**Tier 2: llm_corrector (Sprint 2)**

Sends the error + original message + retrieved spec context to Claude API. Claude reasons about what the correct value should be and returns a structured JSON correction. Most expensive, most capable.

The escalation design means we only pay LLM cost when cheaper options fail. In production, most messages would be fixed at tier 0.

---

## File Structure Summary

```
src/
├── state.py          All data structures (TypedDicts)
├── graph.py          LangGraph graph wiring + routing functions
├── main.py           FastAPI web server
└── nodes/
    ├── parser.py     Reads raw text → ParsedMessage
    ├── classifier.py Reads ParsedMessage → list[IssueDetail]
    ├── rule_fixer.py Reads issues → list[AppliedFix] (deterministic)
    ├── rag_retriever.py STUB → Sprint 2
    ├── llm_corrector.py STUB → Sprint 2
    └── validator.py  Reads issues + fixes → ValidationResult

tests/
├── test_ffm_tc1.py   13 tests — clean message, PASS, no fixes
├── test_ffm_tc2.py   13 tests — 2 errors, rule_fixer fixes both
└── test_ffm_tc3.py    8 tests — unfixable error, FAIL after 3 tiers
```

---

## Sprint 2 Plan

1. **ChromaDB ingestion** — load IATA Cargo-IMP spec chunks into vector database
2. **rag_retriever_node** — embed the error context, retrieve relevant spec chunks, attach to state
3. **llm_corrector_node** — send error + spec chunks to Anthropic API, parse JSON correction response
4. **TC4** — an error that rule_fixer can't fix but RAG+LLM can (e.g. unknown airport with a known alternate)
5. **README.md** — repo goes fully public-ready

---

## Key Numbers to Remember for Interviews

- **33 tests, all passing**
- **3-tier escalation**: rule_fixer → rag_retriever → llm_corrector
- **Confidence threshold**: 0.60 — fixes below this don't count
- **Max validation attempts**: 3 — prevents infinite loops
- **TC2**: 2 errors fixed at tier 0, no LLM cost, confidence 0.90 and 0.95
- **TC3**: unfixable error, escalates through all 3 tiers, ends FAIL — proves the safety net works


[START]
   |
   ↓
( parse )
   |
   ↓
( classify )
   |
   |———— FFM only ————→ ( ffm_rule_fixer )
   |                            |
   |                            ↓
   |                     ( ffm_validate )
   |                      |           |
   |                    PASS         FAIL
   |                      |           |
   |                      ↓           ↓
   |             ( fwb_rule_fixer )  < tier? >
   |                      |           |        |
   |                      ↓          T0→T1    T2
   |             ( fwb_validate )     |        |
   |              |           |       ↓        ↓
   |            PASS         FAIL  (rag_retriever)  (llm_corrector)
   |              |           |       |        |
   |              ↓           |       |        |
   |           [END-PASS]     |       ↓        ↓
   |                          |  back to    ( human_escalate )
   |                         < tier? >          |
   |                          |                 ↓
   |                         T0→T1           [END-FAIL]
   |                          |
   |                          ↓
   |                    (rag_retriever)
   |                          |
   |                    (llm_corrector)
   |                          |
   |                    back to fwb_validate
   |
   |———— FWB only ————→ ( fwb_rule_fixer ) ← (same path as above)


All edges, labeled
| From | To | Condition |
| :--- | :--- | :--- |
| parse | classify | always |
| classify | ffm_rule_fixer | FFM present |
| classify | fwb_rule_fixer | FFM absent, FWB only |
| ffm_rule_fixer | ffm_validate | always |
| ffm_validate | fwb_rule_fixer | PASS |
| ffm_validate | rag_retriever | FAIL, tier < 2 |
| rag_retriever | ffm_rule_fixer | retry FFM with RAG context |
| rag_retriever | llm_corrector | RAG insufficient |
| llm_corrector | ffm_validate | retry |
| llm_corrector | human_escalate | tier 2 exhausted |
| fwb_rule_fixer | fwb_validate | always |
| fwb_validate | END | PASS |
| fwb_validate | rag_retriever | FAIL, tier < 2 |
| rag_retriever | fwb_rule_fixer | retry FWB with RAG context |
| human_escalate | END(FAIL) | always |
