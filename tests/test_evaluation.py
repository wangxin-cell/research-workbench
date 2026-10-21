import copy
import os
from pathlib import Path
import tempfile
import unittest

from research_workbench.core import ValidationError, read_json, write_json
from research_workbench.evaluation import create_review_plan, submit_review
from research_workbench.workflow import blind_pair, import_report, make_request, prepare
from test_workbench import case, report


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp_base = Path(os.environ.get("WORKBENCH_TEST_TEMP") or tempfile.gettempdir()).resolve()
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_base)
        self.root = Path(self.temp.name)
        self.criteria = self.root / "criteria-source.json"
        write_json(self.criteria, {
            "cases": [{"id": case()["id"], "criteria": [
                "Criterion one: private-curator-marker.",
                "Criterion two.", "Criterion three."],
                "failures": ["A known failure."], "ambiguities": ["Value is uncertain."]}]})

    def tearDown(self):
        if not self.root.resolve().is_relative_to(self.temp_base):
            raise RuntimeError("Refusing cleanup outside test root")
        self.temp.cleanup()

    def manual_run(self, output=None):
        path = prepare(self.root / "runs", case())
        answer = self.root / "answer.json"
        write_json(answer, output or report())
        import_report(path, answer, "private-model-label")
        return path

    def packet(self, output=None, predeclared=True):
        plan_path = self.root / "plan.json"
        if predeclared:
            create_review_plan(case(), self.criteria, plan_path)
        a, b = self.manual_run(output), self.manual_run(output)
        if not predeclared:
            create_review_plan(case(), self.criteria, plan_path)
        reviewer = blind_pair(a, b, self.root / "pair", plan_path)
        self.runs = (a, b)
        return reviewer, read_json(reviewer / "rating.json")

    def fill_rating(self, rating):
        filled = copy.deepcopy(rating)
        filled["reviewer"].update(id="synthetic-reviewer", domain_experience="Test fixture only",
                                  system_identity_known=False, saw_other_reviews=False)
        filled["preference"] = "tie"
        filled["reason"] = "Synthetic equal reports; not an actual quality evaluation."
        for side in ("A", "B"):
            for group in ("dimensions", "required_findings", "candidates"):
                for judgment in filled[side][group].values():
                    if judgment["label"] == "not_applicable":
                        continue
                    judgment.update(label="pass", rationale="Fixture judgment, not scientific evidence.",
                                    output_pointers=["/summary"], sources=[{"source_id": "s1", "locator": "Abstract"}])
        return filled

    def submit(self, reviewer, rating, name="receipt.json"):
        rating_path = self.root / "filled.json"
        write_json(rating_path, rating)
        return submit_review(reviewer, rating_path, self.root / name)

    def test_plan_requires_matching_case_specific_criteria(self):
        for change in ("id", "criteria"):
            raw = read_json(self.criteria)
            raw["cases"][0][change] = "different-case" if change == "id" else ["Only one."]
            write_json(self.root / "invalid.json", raw)
            with self.assertRaises(ValidationError):
                create_review_plan(case(), self.root / "invalid.json", self.root / "plan.json")
            self.assertFalse((self.root / "plan.json").exists())

    def test_plan_is_bound_to_input_and_cannot_be_overwritten(self):
        destination = create_review_plan(case(), self.criteria, self.root / "plan.json")
        original = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            create_review_plan(case(), self.criteria, destination)
        self.assertEqual(destination.read_bytes(), original)
        a, b = self.manual_run(), self.manual_run()
        changed = case()
        changed["resources"]["gpu"] = "different"
        other_plan = create_review_plan(changed, self.criteria, self.root / "other-plan.json")
        with self.assertRaises(ValidationError):
            blind_pair(a, b, self.root / "invalid-pair", other_plan)
        self.assertFalse((self.root / "invalid-pair").exists())

    def test_packet_hides_run_identity_and_keeps_rubric_out_of_model_request(self):
        reviewer, _ = self.packet()
        for path in reviewer.iterdir():
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("private-model-label", content)
            for run_dir in self.runs:
                self.assertNotIn(run_dir.name, content)
        self.assertNotIn("private-curator-marker", str(make_request(case())))
        self.assertIn("private-curator-marker", (reviewer / "criteria.json").read_text(encoding="utf-8"))
        self.assertTrue(read_json(reviewer / "packet.json")["rules_created_before_both_runs"])

    def test_posthoc_rules_remain_explicitly_posthoc(self):
        reviewer, rating = self.packet(predeclared=False)
        receipt = read_json(self.submit(reviewer, self.fill_rating(rating)))
        self.assertFalse(receipt["rules_created_before_both_runs"])

    def test_unfilled_template_never_becomes_a_pass(self):
        reviewer, rating = self.packet()
        with self.assertRaises(ValidationError):
            self.submit(reviewer, rating)
        self.assertFalse((self.root / "receipt.json").exists())

    def test_review_preserves_labels_and_does_not_mark_run_quality_verified(self):
        reviewer, rating = self.packet()
        rating = self.fill_rating(rating)
        rating["A"]["dimensions"]["evidence"]["label"] = "partial"
        rating["B"]["required_findings"]["R1"]["label"] = "unknown"
        receipt = read_json(self.submit(reviewer, rating))
        self.assertEqual(receipt["outcomes"], {"A": "needs_revision", "B": "unresolved"})
        self.assertEqual(receipt["rating"], rating)
        self.assertFalse(receipt["reviewer_identity_verified"])
        for run_dir in self.runs:
            self.assertFalse(read_json(run_dir / "manifest.json")["quality_evaluated"])
        with self.assertRaises(FileExistsError):
            self.submit(reviewer, rating)

    def test_severe_error_overrides_other_pass_labels(self):
        reviewer, rating = self.packet()
        rating = self.fill_rating(rating)
        rating["A"]["severe_errors"].append({
            "description": "A synthetic critical error.",
            "output_pointers": ["/findings/0/statement"],
            "sources": [{"source_id": "s1", "locator": "Abstract"}],
        })
        receipt = read_json(self.submit(reviewer, rating))
        self.assertEqual(receipt["outcomes"], {"A": "fail", "B": "pass"})

    def test_every_candidate_must_be_reviewed(self):
        output = report()
        output["candidates"] = [{
            "title": "Candidate", "research_question": "Question?", "potential_contribution": "Unverified",
            "status": "unverified", "comparisons": [{"source_id": "s1", "overlap": "Unknown", "difference": "Unknown"}],
            "first_test": {"baseline": "b", "variable": "v", "metric": "m",
                           "failure_signal": "f", "resource_check": "r"},
            "uncertainties": ["Unknown"],
        }] * 2
        reviewer, rating = self.packet(output)
        rating = self.fill_rating(rating)
        del rating["A"]["candidates"]["1"]
        with self.assertRaises(ValidationError):
            self.submit(reviewer, rating)

    def test_invalid_output_and_source_anchors_rejected(self):
        reviewer, blank = self.packet()
        for field, value in (("output_pointers", ["/findings/99/statement"]),
                             ("output_pointers", ["/findings/-1"]),
                             ("output_pointers", []),
                             ("sources", [{"source_id": "missing", "locator": "p1"}])):
            rating = self.fill_rating(blank)
            rating["A"]["dimensions"]["evidence"][field] = value
            with self.assertRaises(ValidationError):
                self.submit(reviewer, rating)
        rating = self.fill_rating(blank)
        rating["A"]["required_findings"]["R1"]["output_pointers"] = [""]
        self.submit(reviewer, rating)

    def test_not_applicable_cannot_be_added_after_seeing_outputs(self):
        reviewer, rating = self.packet()
        rating = self.fill_rating(rating)
        rating["A"]["dimensions"]["research_value"]["label"] = "not_applicable"
        with self.assertRaises(ValidationError):
            self.submit(reviewer, rating)

    def test_predeclared_not_applicable_is_supported(self):
        raw = read_json(self.criteria)
        raw["cases"][0]["not_applicable"] = {"research_value": "Only checks a fixed factual claim."}
        write_json(self.criteria, raw)
        reviewer, rating = self.packet()
        receipt = read_json(self.submit(reviewer, self.fill_rating(rating)))
        self.assertEqual(receipt["outcomes"]["A"], "pass")
        self.assertEqual(receipt["rating"]["A"]["dimensions"]["research_value"]["label"], "not_applicable")

    def test_changed_review_material_is_rejected(self):
        reviewer, rating = self.packet()
        for name in ("criteria.json", "A.json", "B.html"):
            path = reviewer / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.assertRaises(ValidationError):
                self.submit(reviewer, self.fill_rating(rating))
            path.write_bytes(original)

    def test_rating_cannot_be_submitted_for_another_packet(self):
        reviewer, rating = self.packet()
        rating = self.fill_rating(rating)
        rating["packet_id"] = "different-packet"
        with self.assertRaises(ValidationError):
            self.submit(reviewer, rating)

    def test_untrusted_manifest_cannot_read_paths_outside_packet(self):
        reviewer, rating = self.packet()
        packet = read_json(reviewer / "packet.json")
        packet["files"]["../../unrelated.json"] = "irrelevant"
        write_json(reviewer / "packet.json", packet)
        with self.assertRaises(ValidationError):
            self.submit(reviewer, self.fill_rating(rating))


if __name__ == "__main__":
    unittest.main()
