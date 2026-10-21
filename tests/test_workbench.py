import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_workbench.core import (ValidationError, load_case, read_json,
    validate_case, validate_report, write_json)
from research_workbench.provider import ProviderError, ResponsesProvider
from research_workbench.render import render_report
from research_workbench.workflow import (blind_pair, import_report, load_accepted,
    make_request, prepare, run)


def case():
    return {"id": "synthetic-unit-test", "user_question": "Can this claim be supported?",
            "resources": {"gpu": "none"}, "sources": [
                {"id": "s1", "title": "Synthetic source", "url": "https://example.org/paper",
                 "summary": "This source concerns a limited setting.", "locator": "Abstract",
                 "read_scope": "abstract"}]}


def report():
    return {"decision": "need_evidence", "summary": "More evidence is required.",
            "findings": [{"statement": "Evidence is limited.", "kind": "source_fact", "source_ids": ["s1"]}],
            "candidates": [], "next_steps": ["Check the full text."], "limitations": ["Only a summary is available."]}


class FakeProvider:
    model = "synthetic-test-double"
    max_output_tokens = 100
    timeout = 1

    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def generate(self, request):
        self.calls.append(request)
        if len(self.calls) == self.fail_at:
            raise ProviderError("secret-like upstream error must not enter the manifest")
        return report(), {"model": self.model, "usage": {"input_tokens": 1, "output_tokens": 2}}


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("WORKBENCH_TEST_TEMP")
        self.temp_base = Path(base or tempfile.gettempdir()).resolve()
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_base)
        self.root = Path(self.temp.name)

    def tearDown(self):
        if not self.root.resolve().is_relative_to(self.temp_base):
            raise RuntimeError("Refusing cleanup outside the test temporary root")
        self.temp.cleanup()

    def manual_run(self, case_value=None, output=None):
        path = prepare(self.root / "runs", case_value or case())
        output_path = self.root / "answer.json"
        write_json(output_path, output or report())
        import_report(path, output_path, "human-authored unit fixture")
        return path

    def test_case_selection_requires_exactly_one_match(self):
        path = self.root / "cases.json"
        other = case()
        other["id"] = "other"
        write_json(path, {"cases": [case(), other], "evaluator": "must never be forwarded"})
        with self.assertRaises(ValidationError):
            load_case(path)
        selected = load_case(path, "other")
        self.assertNotIn("evaluator", make_request(selected)["input"])

    def test_evaluator_fields_rejected_at_case_source_and_resource_boundaries(self):
        for location in ("case", "source", "resource"):
            value = case()
            target = value if location == "case" else value["sources"][0] if location == "source" else value["resources"]
            target["criteria"] = ["expected answer"]
            with self.assertRaises(ValidationError):
                validate_case(value)

    def test_duplicate_source_id_rejected(self):
        value = case()
        value["sources"].append(copy.deepcopy(value["sources"][0]))
        with self.assertRaises(ValidationError):
            validate_case(value)

    def test_unsafe_and_credential_urls_rejected(self):
        for url in ("javascript:alert(1)", "file:///private", "https://user:secret@example.org"):
            value = case()
            value["sources"][0]["url"] = url
            with self.assertRaises(ValidationError):
                validate_case(value)

    def test_unknown_reference_and_uncited_fact_rejected(self):
        for refs in (["fabricated"], []):
            output = report()
            output["findings"][0]["source_ids"] = refs
            with self.assertRaises(ValidationError):
                validate_report(output, case())

    def test_explore_without_candidate_rejected(self):
        output = report()
        output["decision"] = "explore"
        with self.assertRaises(ValidationError):
            validate_report(output, case())

    def test_render_escapes_model_and_source_html(self):
        value, output = case(), report()
        value["sources"][0]["title"] = '<img src=x onerror="alert(1)">'
        output["summary"] = "<script>alert(2)</script>"
        html = render_report(value, output)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src", html)
        self.assertIn("&lt;script&gt;", html)

    def test_prepared_request_contains_no_scoring_material(self):
        path = prepare(self.root, case())
        self.assertEqual(read_json(path / "manifest.json")["status"], "prepared")
        self.assertEqual(set(json.loads(read_json(path / "request.json")["input"])), {"research_material"})
        self.assertFalse((path / "report.html").exists())
        self.assertNotIn(case()["id"], read_json(path / "request.json")["input"])

    def test_import_detects_changed_input(self):
        path = prepare(self.root, case())
        changed = case()
        changed["user_question"] = "Changed question"
        write_json(path / "input.json", changed)
        write_json(self.root / "report.json", report())
        with self.assertRaises(ValidationError):
            import_report(path, self.root / "report.json", "fixture")

    def test_import_is_immutable_and_not_quality_evaluation(self):
        path = self.manual_run()
        manifest, _, _ = load_accepted(path)
        self.assertFalse(manifest["quality_evaluated"])
        self.assertIsNone(manifest["cost_amount"])
        self.assertEqual(manifest["checks"]["semantic_entailment"], "not_evaluated")
        with self.assertRaises(ValidationError):
            import_report(path, self.root / "answer.json", "overwrite")

    def test_import_detects_changed_exported_prompt(self):
        path = prepare(self.root, case())
        (path / "prompt.txt").write_text("Different instructions", encoding="utf-8")
        write_json(self.root / "report.json", report())
        with self.assertRaises(ValidationError):
            import_report(path, self.root / "report.json", "fixture")

    def test_modified_completed_report_rejected(self):
        path = self.manual_run()
        changed = report()
        changed["summary"] = "Modified later"
        write_json(path / "report.json", changed)
        with self.assertRaises(ValidationError):
            load_accepted(path)

    def test_reviewed_workflow_uses_two_calls_without_extra_evidence(self):
        provider = FakeProvider()
        path = run(self.root, case(), provider)
        self.assertEqual(len(provider.calls), 2)
        second = json.loads(provider.calls[1]["input"])
        self.assertEqual(second["research_material"], {k: v for k, v in case().items() if k != "id"})
        self.assertIn("draft_to_review", second)
        self.assertEqual(read_json(path / "manifest.json")["status"], "completed")

    def test_baseline_uses_one_call(self):
        provider = FakeProvider()
        run(self.root, case(), provider, "baseline")
        self.assertEqual(len(provider.calls), 1)

    def test_stage_two_failure_is_retained_without_success_report_or_retry(self):
        provider = FakeProvider(fail_at=2)
        with self.assertRaises(RuntimeError):
            run(self.root, case(), provider)
        path = next(self.root.iterdir())
        manifest = read_json(path / "manifest.json")
        self.assertEqual([s["status"] for s in manifest["stages"]], ["completed", "failed"])
        self.assertEqual(manifest["status"], "failed")
        self.assertNotIn("secret-like", (path / "manifest.json").read_text())
        self.assertFalse((path / "report.html").exists())
        self.assertTrue((path / "output-1.json").exists())
        self.assertEqual(len(provider.calls), 2)

    def test_blind_packet_hides_mapping_and_rejects_different_inputs(self):
        a, b = self.manual_run(), self.manual_run()
        reviewer = blind_pair(a, b, self.root / "pair")
        self.assertTrue((reviewer.parent / "organizer-mapping.json").exists())
        for file in reviewer.iterdir():
            self.assertNotIn("human-authored unit fixture", file.read_text(encoding="utf-8"))
            self.assertNotIn(a.name, file.read_text(encoding="utf-8"))
        other = case()
        other["resources"]["gpu"] = "one gpu"
        c = self.manual_run(other)
        with self.assertRaises(ValidationError):
            blind_pair(a, c, self.root / "invalid-pair")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "fake-test-key"})
    def test_responses_adapter_sends_schema_and_no_storage(self):
        raw = {"status": "completed", "id": "test", "model": "fixture-model", "usage": {},
               "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(report())}]}]}
        provider = ResponsesProvider("explicit-model")
        with patch.object(provider.opener, "open") as transport:
            transport.return_value.__enter__.return_value.read.return_value = json.dumps(raw).encode()
            answer, metadata = provider.generate(make_request(case()))
            req = transport.call_args.args[0]
            body = json.loads(req.data)
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            self.assertEqual(req.full_url, "https://api.openai.com/v1/responses")
            self.assertEqual(answer, report())
            self.assertEqual(metadata["model"], "fixture-model")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "fake-test-key"})
    def test_incomplete_and_refusal_outputs_are_not_accepted(self):
        payloads = [{"status": "incomplete"}, {"status": "completed", "output": [
            {"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]}]
        for payload in payloads:
            provider = ResponsesProvider("explicit-model")
            with patch.object(provider.opener, "open") as transport:
                transport.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()
                with self.assertRaises(ProviderError):
                    provider.generate(make_request(case()))
                self.assertEqual(transport.call_count, 1)

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_key_makes_no_network_call(self):
        provider = ResponsesProvider("explicit-model")
        with patch.object(provider.opener, "open") as transport:
            with self.assertRaises(ProviderError):
                provider.generate(make_request(case()))
            transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
