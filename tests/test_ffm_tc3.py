import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.graph import compile_graph

FFM_TC3 = """\
FFM/1
1/LH8234/15OCT/FRA/ORD
/1/125-99887766FRAORD/T0K0.0MC1.2/FLOWERS
/1/020-12345678FRAORD/P2K45.0MC0.5/MACHINE PARTS
/ULD/AKE12345LH
/1/125-11223344FRAORD/T5K120.0MC0.8/ELECTRONICS
/1/125-55667788FRAORD/T8K210.0MC1.0/TEXTILES
LAST"""

GRAPH = compile_graph()


def run(raw: str):
    return GRAPH.invoke({
        "raw_message": raw, "parsed": None, "parse_errors": [],
        "message_type": "", "issues": [], "escalation_tier": 0,
        "fixes_applied": [], "corrected_message": "", "validation_result": None,
        "validation_attempts": 0, "status": "ESCALATED", "final_message": "",
    })


class TestTC3EscalationToFail:
    def setup_method(self):
        self.result = run(FFM_TC3)

    def test_status_fail(self):
        assert self.result["status"] == "FAIL"

    def test_escalated_to_tier_2(self):
        assert self.result["escalation_tier"] == 2

    def test_three_validation_attempts(self):
        assert self.result["validation_attempts"] == 3

    def test_one_error_issue(self):
        assert len(self.result["issues"]) == 1
        assert self.result["issues"][0]["issue_code"] == "INVALID_WEIGHT"
        assert self.result["issues"][0]["severity"] == "ERROR"

    def test_no_fixes_applied(self):
        assert self.result["fixes_applied"] == []

    def test_validation_not_passed(self):
        vr = self.result["validation_result"]
        assert vr["passed"] is False
        assert vr["score"] == 0.0

    def test_remaining_issue_persists(self):
        remaining = self.result["validation_result"]["remaining_issues"]
        assert len(remaining) == 1
        assert remaining[0]["issue_code"] == "INVALID_WEIGHT"

    def test_other_shipments_parsed_correctly(self):
        shipments = self.result["parsed"]["shipments"]
        assert len(shipments) == 4
        assert shipments[1]["weight_kg"] == 45.0
        assert shipments[0]["weight_kg"] == 0.0