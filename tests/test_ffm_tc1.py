import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.graph import compile_graph

FFM_TC1 = """\
FFM/1
1/LH8234/15OCT/FRA/ORD
/1/125-99887766FRAORD/T10K550.5MC1.2/FLOWERS
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


class TestTC1ParseCleanFFM:
    def setup_method(self):
        self.result = run(FFM_TC1)

    def test_status_pass(self):
        assert self.result["status"] == "PASS"

    def test_message_type_ffm(self):
        assert self.result["message_type"] == "FFM"

    def test_no_parse_errors(self):
        assert self.result["parse_errors"] == []

    def test_flight_parsed(self):
        f = self.result["parsed"]["flight"]
        assert f["flight_number"] == "LH8234"
        assert f["flight_date"]   == "15OCT"
        assert f["origin"]        == "FRA"
        assert f["destination"]   == "ORD"

    def test_four_shipments(self):
        assert len(self.result["parsed"]["shipments"]) == 4

    def test_piece_counts(self):
        shipments = self.result["parsed"]["shipments"]
        assert shipments[0]["piece_count"] == 10
        assert shipments[1]["piece_count"] == 2
        assert shipments[2]["piece_count"] == 5
        assert shipments[3]["piece_count"] == 8

    def test_weights(self):
        shipments = self.result["parsed"]["shipments"]
        assert shipments[0]["weight_kg"] == 550.5
        assert shipments[1]["weight_kg"] == 45.0
        assert shipments[2]["weight_kg"] == 120.0
        assert shipments[3]["weight_kg"] == 210.0

    def test_descriptions(self):
        descs = [s["description"] for s in self.result["parsed"]["shipments"]]
        assert descs == ["FLOWERS", "MACHINE PARTS", "ELECTRONICS", "TEXTILES"]

    def test_uld_association(self):
        shipments = self.result["parsed"]["shipments"]
        assert shipments[0]["uld"] is None
        assert shipments[1]["uld"] is None
        assert shipments[2]["uld"] == "AKE12345LH"
        assert shipments[3]["uld"] == "AKE12345LH"

    def test_awb_prefixes(self):
        shipments = self.result["parsed"]["shipments"]
        assert shipments[0]["awb_prefix"] == "125"
        assert shipments[1]["awb_prefix"] == "020"

    def test_no_issues_on_clean_message(self):
        assert self.result["issues"] == []

    def test_no_fixes_on_clean_message(self):
        assert self.result["fixes_applied"] == []

    def test_validation_passed(self):
        vr = self.result["validation_result"]
        assert vr["passed"] is True
        assert vr["score"] == 1.0