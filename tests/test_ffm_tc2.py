import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.graph import compile_graph

FFM_TC2 = """\
FFM/1
1/LH8234/5OCT/FRA/ORD
/1/125-99887766ORDFRA/T10K550.5MC1.2/FLOWERS
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


class TestTC2RuleFixerFires:
    def setup_method(self):
        self.result = run(FFM_TC2)

    def test_status_pass(self):
        assert self.result["status"] == "PASS"

    def test_no_escalation(self):
        assert self.result["escalation_tier"] == 0

    def test_two_issues_detected(self):
        assert len(self.result["issues"]) == 2

    def test_issue_codes(self):
        codes = {i["issue_code"] for i in self.result["issues"]}
        assert codes == {"INVALID_DATE_FORMAT", "ROUTING_MISMATCH"}

    def test_both_issues_are_errors(self):
        severities = {i["severity"] for i in self.result["issues"]}
        assert severities == {"ERROR"}

    def test_two_fixes_applied(self):
        assert len(self.result["fixes_applied"]) == 2

    def test_all_fixes_from_rule_fixer(self):
        nodes = {f["node"] for f in self.result["fixes_applied"]}
        assert nodes == {"rule_fixer"}

    def test_date_fix(self):
        date_fix = next(f for f in self.result["fixes_applied"] if f["field"] == "flight_date")
        assert date_fix["old_value"] == "5OCT"
        assert date_fix["new_value"] == "05OCT"
        assert date_fix["confidence"] == 0.95

    def test_routing_fix(self):
        routing_fix = next(f for f in self.result["fixes_applied"] if f["field"] == "routing")
        assert routing_fix["old_value"] == "ORDFRA"
        assert routing_fix["new_value"] == "FRAORD"
        assert routing_fix["confidence"] == 0.90

    def test_validation_passed(self):
        vr = self.result["validation_result"]
        assert vr["passed"] is True
        assert vr["score"] == 1.0
        assert vr["remaining_issues"] == []

    def test_four_shipments_still_parsed(self):
        assert len(self.result["parsed"]["shipments"]) == 4

    def test_parse_errors_empty(self):
        assert self.result["parse_errors"] == []