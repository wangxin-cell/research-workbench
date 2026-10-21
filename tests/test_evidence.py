import base64
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from research_workbench.core import ValidationError, read_json, validate_case, write_json
from research_workbench.evidence import DocumentStore, pdf_available, sha256, verify_archive
from research_workbench.pdf_worker import extract
from research_workbench.render import render_report
from research_workbench.workflow import prepare, import_report, load_accepted, make_request, run, blind_pair
from test_workbench import case, report
import test_web


def pdf_fixture(blank=False, encrypted=False, pages=2):
    """Synthetic parser fixture, not a paper or an effectiveness example."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    for index in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        if not blank:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 700 Td (Synthetic page {index + 1}. Evidence is limited to selected text.) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("unit-fixture-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_base = Path(os.environ.get("WORKBENCH_TEST_TEMP", tempfile.gettempdir())).resolve()
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_base)
        self.root = Path(self.temp.name)
        self.store = DocumentStore(self.root)
        # A mock extraction snapshot isolates integrity tests from the optional parser.
        self.raw = b"%PDF-1.4\nsynthetic cache fixture, not a parsed PDF"
        self.identity = sha256(self.raw)
        self.page_text = "Synthetic 🙂 first. Evidence is limited."
        record = {"document_sha256": self.identity, "extractor": "unit-fixture",
                  "page_count": 1, "pages": [{"page": 1, "text": self.page_text,
                  "text_sha256": sha256(self.page_text.encode())}]}
        folder = self.store.path(self.identity)
        folder.mkdir(parents=True)
        (folder / "original.pdf").write_bytes(self.raw)
        write_json(folder / "pages.json", record)

    def tearDown(self):
        if not self.root.resolve().is_relative_to(self.temp_base):
            raise RuntimeError("Unsafe test cleanup path")
        self.temp.cleanup()

    def source(self):
        return self.store.excerpt(self.identity, 1, 10, len(self.page_text),
                                  "Synthetic paper", "https://example.org/paper")

    def input(self):
        result = case()
        result["sources"] = [self.source()]
        return result

    def output(self):
        result = report()
        result["findings"][0]["source_ids"] = [self.source()["id"]]
        for candidate in result["candidates"]:
            for comparison in candidate["comparisons"]:
                comparison["source_id"] = self.source()["id"]
        return result

    def test_exact_quote_unicode_offsets_and_metadata_reach_prompt(self):
        source = self.source()
        self.assertEqual(source["summary"], self.page_text[10:])
        self.assertIn("🙂", source["summary"])
        validated = validate_case(self.input())
        payload = json.loads(make_request(validated)["input"])
        self.assertEqual(payload["research_material"]["sources"][0]["evidence"]["page"], 1)
        self.assertNotIn(base64.b64encode(self.raw).decode(), make_request(validated)["input"])

    def test_changed_quote_or_provenance_is_rejected(self):
        for key, value in (("summary", "edited text"), ("human_verified", True),
                           ("read_scope", "fulltext"), ("fulltext_snapshot_sha256", "0" * 64)):
            with self.subTest(key=key):
                material = self.input()
                material["sources"][0][key] = value
                with self.assertRaises(ValidationError):
                    validate_case(material)

    def test_fabricated_page_hash_is_rejected_against_local_snapshot(self):
        material = self.input()
        material["sources"][0]["evidence"]["page_text_sha256"] = "a" * 64
        with self.assertRaises(ValidationError):
            prepare(self.root, material)
        self.assertEqual([p.name for p in self.root.iterdir()], ["_documents"])

    def test_snapshot_survives_upload_cache_unavailable_and_tamper_is_rejected(self):
        path = prepare(self.root, self.input())
        output = self.root / "answer.json"
        write_json(output, self.output())
        # Move only a verified, exact fixture file within this test workspace.
        original = self.store.path(self.identity) / "original.pdf"
        destination = self.root / "cache-unavailable.pdf"
        for target in (original.resolve(), destination.resolve()):
            self.assertTrue(target.is_relative_to(self.root))
        original.rename(destination)
        import_report(path, output, "synthetic test")
        load_accepted(path)
        (path / "evidence" / (self.identity + ".pdf")).write_bytes(b"changed")
        with self.assertRaises(ValidationError):
            load_accepted(path)

    def test_missing_pdf_does_not_start_provider(self):
        material = self.input()
        # A distinct root has no upload cache.
        with patch("research_workbench.provider.ResponsesProvider") as provider:
            provider.model = "fixture"
            with self.assertRaises(ValidationError):
                run(self.root / "another", material, provider)
            provider.generate.assert_not_called()

    def test_blind_packet_keeps_same_original_for_both_reports(self):
        answer = self.root / "answer.json"
        write_json(answer, self.output())
        first = prepare(self.root, self.input())
        second = prepare(self.root, self.input())
        import_report(first, answer, "synthetic first")
        import_report(second, answer, "synthetic second")
        reviewer = blind_pair(first, second, self.root / "comparison")
        verify_archive(reviewer, self.input())
        self.assertEqual((reviewer / "evidence" / (self.identity + ".pdf")).read_bytes(), self.raw)
        for label in ("A", "B"):
            html = (reviewer / (label + ".html")).read_text(encoding="utf-8")
            self.assertIn("evidence/" + self.identity + ".pdf", html)
            self.assertNotIn("synthetic first", html)

    def test_page_offsets_url_and_path_guards(self):
        for page, start, end in ((0, 0, 10), (2, 0, 10), (True, 0, 10), (1, -1, 10), (1, 0, 999), (1, 4, 4)):
            with self.assertRaises(ValidationError):
                self.store.excerpt(self.identity, page, start, end, "title", "https://example.org")
        with self.assertRaises(ValidationError):
            self.store.excerpt(self.identity, 1, 0, 5, "title", "file:///private")
        with self.assertRaises(ValidationError):
            self.store.load("../../secret")

    def test_invalid_upload_missing_dependency_and_timeout(self):
        for data in ("not-base64", base64.b64encode(b"not PDF").decode()):
            with self.assertRaises(ValidationError):
                self.store.ingest(data)
        data = base64.b64encode(b"%PDF-1.4\nnew fixture").decode()
        with patch("research_workbench.evidence.pdf_available", return_value=False):
            with self.assertRaisesRegex(ValidationError, "可选依赖"):
                self.store.ingest(data)
        with patch("research_workbench.evidence.pdf_available", return_value=True), patch(
                "research_workbench.evidence.subprocess.run", side_effect=subprocess.TimeoutExpired("fixture", 20)):
            with self.assertRaisesRegex(ValidationError, "20 秒"):
                self.store.ingest(data)

    def test_report_retains_exact_excerpt_page_fingerprint_and_safe_markup(self):
        material = self.input()
        material["sources"][0]["title"] = "<script>alert(1)</script>"
        html = render_report(material, self.output(), evidence_base="evidence/")
        self.assertIn("PDF 提取片段", html)
        self.assertIn("PDF 第 1 页", html)
        self.assertIn(self.identity + ".pdf", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)


@unittest.skipUnless(pdf_available(), "Install the optional [pdf] extra for parser tests")
class ParserTests(unittest.TestCase):
    def test_real_parser_keeps_pages_and_does_not_claim_ocr(self):
        result = extract(pdf_fixture())
        self.assertEqual(result["page_count"], 2)
        self.assertIn("Synthetic page 1", result["pages"][0]["text"])
        self.assertIn("Synthetic page 2", result["pages"][1]["text"])
        self.assertIn("OCR", result["notice"])

    def test_blank_encrypted_overlong_and_malformed_are_not_successes(self):
        for payload in (pdf_fixture(blank=True), pdf_fixture(encrypted=True),
                        pdf_fixture(pages=81), b"%PDF-1.4\nbroken"):
            with self.subTest(size=len(payload)):
                with self.assertRaises(Exception):
                    extract(payload)


# Reuse only the HTTP harness; do not inherit and rerun the existing web suite.
@unittest.skipUnless(pdf_available(), "Install the optional [pdf] extra for upload tests")
class PdfWebTests(unittest.TestCase):
    setUp = test_web.WebTests.setUp
    tearDown = test_web.WebTests.tearDown
    request = test_web.WebTests.request

    def test_upload_select_prepare_import_download_and_reject_tampering(self):
        raw = pdf_fixture()
        _, _, body = self.request("/api/pdf", {"data": base64.b64encode(raw).decode()})
        document = json.loads(body)
        quote_end = len(document["pages"][1]["text"])
        _, _, body = self.request("/api/excerpt", {"document_sha256": document["document_sha256"],
            "page": 2, "start": 0, "end": quote_end, "title": "Synthetic fixture", "url": "https://example.org/paper"})
        source = json.loads(body)
        material = case()
        material["sources"] = [source]
        _, _, body = self.request("/api/prepare", {"case": material})
        identity = json.loads(body)["run_id"]
        saved = self.app.runs_root / identity
        verify_archive(saved, material)
        output = report()
        output["findings"][0]["source_ids"] = [source["id"]]
        for candidate in output["candidates"]:
            for comparison in candidate["comparisons"]:
                comparison["source_id"] = source["id"]
        self.request("/api/import", {"run_id": identity, "report": output, "model_label": "synthetic test"})
        _, _, html = self.request("/reports/" + identity)
        self.assertIn("PDF 第 2 页".encode(), html)
        _, headers, downloaded = self.request(f"/evidence/{identity}/{document['document_sha256']}.pdf")
        self.assertEqual(downloaded, raw)
        self.assertIn("attachment", headers["Content-Disposition"])
        material["sources"][0]["summary"] += " altered"
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.request("/api/prepare", {"case": material})
        self.assertEqual(exc.exception.code, 400)
        _, _, history = self.request("/api/history")
        self.assertEqual(len(json.loads(history)), 1)


if __name__ == "__main__":
    unittest.main()
