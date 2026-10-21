import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from research_workbench.core import ValidationError, read_json
from research_workbench.retrieval import (ArxivSearch, RetrievalError, arxiv_identifier,
                                          parse_feed, query_parameters)
from research_workbench.server import Application, make_handler
from test_workbench import case, report

FEED = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"
 xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
 <opensearch:totalResults>1</opensearch:totalResults><entry>
 <id>http://arxiv.org/abs/2006.10726v3</id><title>Tent: A test fixture</title>
 <summary>This abstract is synthetic test data.</summary><published>2020-06-18T00:00:00Z</published>
 <author><name>Test Author</name></author></entry></feed>'''


class RetrievalTests(unittest.TestCase):
    def test_identifiers_and_fixed_query_host(self):
        self.assertEqual(arxiv_identifier("https://arxiv.org/pdf/2006.10726v3.pdf"), "2006.10726v3")
        self.assertEqual(arxiv_identifier("hep-th/9901001"), "hep-th/9901001")
        self.assertIsNone(arxiv_identifier("https://attacker.example/abs/2006.10726"))
        with self.assertRaises(ValidationError):
            query_parameters("https://attacker.example/private")

    def test_search_query_treats_input_as_terms(self):
        params = query_parameters("retrieval augmented", 5)
        self.assertEqual(params["search_query"], 'all:"retrieval" AND all:"augmented"')
        self.assertEqual(query_parameters("2006.10726")["id_list"], "2006.10726")

    def test_feed_keeps_version_and_abstract_provenance(self):
        entries, total = parse_feed(FEED)
        self.assertEqual(total, 1)
        self.assertEqual(entries[0]["source"]["url"], "https://arxiv.org/abs/2006.10726v3")
        self.assertEqual(entries[0]["source"]["summary_author"], "arxiv_original_abstract")
        self.assertFalse(entries[0]["source"]["human_verified"])

    def test_errors_and_entities_are_not_empty_successes(self):
        for data in (b"<html>service down</html>", b"<!DOCTYPE feed []><feed/>", FEED.replace(b"http://arxiv.org/abs/2006.10726v3", b"http://arxiv.org/api/errors#bad_query")):
            with self.assertRaises(RetrievalError):
                parse_feed(data)

    def test_cache_does_not_refetch_or_expose_mutable_state(self):
        search = ArxivSearch()
        with patch.object(search.opener, "open") as transport:
            transport.return_value.__enter__.return_value.read.return_value = FEED
            first = search.search("2006.10726")
            first["results"].clear()
            second = search.search("2006.10726")
            self.assertEqual(len(second["results"]), 1)
            self.assertTrue(second["cache_hit"])
            self.assertEqual(transport.call_count, 1)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp_base = Path(os.environ.get("WORKBENCH_TEST_TEMP", tempfile.gettempdir())).resolve()
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_base)
        self.root = Path(self.temp.name)
        self.app = Application(self.root / "runs")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.app.pool.shutdown(wait=True)
        if not self.root.resolve().is_relative_to(self.temp_base):
            raise RuntimeError("Unsafe test cleanup path")
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        merged = {"Origin": self.base}
        if data is not None:
            merged.update({"Content-Type": "application/json", "X-Workbench-Request": "local-ui"})
        merged.update(headers or {})
        request = urllib.request.Request(self.base + path,
                    data=None if data is None else json.dumps(data).encode(), headers=merged)
        with self.client.open(request, timeout=3) as response:
            return response.status, response.headers, response.read()

    def test_app_and_assets_are_served_without_directory_access(self):
        for route in ("/", "/app.js", "/styles.css", "/demo", "/api/examples"):
            status, _, body = self.request(route)
            self.assertEqual(status, 200)
            self.assertTrue(body)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.request("/../evaluator.json")
        self.assertEqual(exc.exception.code, 404)

    def test_host_origin_and_json_guards(self):
        for headers in ({"Host": "untrusted.example"}, {"Origin": "https://untrusted.example"}, {"X-Workbench-Request": ""}, {"Content-Type": "text/plain"}):
            with self.assertRaises(urllib.error.HTTPError) as exc:
                self.request("/api/prepare", {"case": case()}, headers)
            self.assertEqual(exc.exception.code, 403)
        self.assertEqual(list(self.app.runs_root.iterdir()), [])

    def test_rejected_post_consumes_body_and_returns_http_error(self):
        # urllib sends headers and body separately. An early socket close used
        # to intermittently hide the 403 with WinError 10053.
        for _ in range(12):
            with self.assertRaises(urllib.error.HTTPError) as exc:
                self.request("/api/prepare", {"case": case()}, {"Origin": "https://untrusted.example"})
            self.assertEqual(exc.exception.code, 403)
            self.assertIn(b"Local JSON requests only", exc.exception.read())
        self.assertEqual(list(self.app.runs_root.iterdir()), [])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "hidden-test-secret"})
    def test_config_never_returns_key(self):
        _, _, body = self.request("/api/config")
        self.assertNotIn(b"hidden-test-secret", body)
        self.assertTrue(json.loads(body)["api_key_configured"])

    def test_prepare_import_and_report_over_http(self):
        _, _, body = self.request("/api/prepare", {"case": case()})
        identity = json.loads(body)["run_id"]
        _, _, prompt = self.request(f"/files/{identity}/prompt.txt")
        self.assertNotIn(case()["id"].encode(), prompt)
        self.request("/api/import", {"run_id": identity, "report": report(), "model_label": "manual unit fixture"})
        _, headers, html = self.request("/reports/" + identity)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("导入的选题分析".encode(), html)
        _, _, history = self.request("/api/history")
        self.assertEqual(json.loads(history)[0]["status"], "imported")

    def test_import_rejects_unknown_source_and_path_traversal(self):
        _, _, body = self.request("/api/prepare", {"case": case()})
        identity = json.loads(body)["run_id"]
        output = report()
        output["findings"][0]["source_ids"] = ["invented"]
        with self.assertRaises(urllib.error.HTTPError):
            self.request("/api/import", {"run_id": identity, "report": output, "model_label": "fixture"})
        self.assertEqual(read_json(self.app.runs_root / identity / "manifest.json")["status"], "prepared")
        with self.assertRaises(ValidationError):
            self.app.run_path("../../secrets")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_key_does_not_start_paid_job(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.request("/api/run", {"case": case(), "model": "test", "workflow": "baseline"})
        self.assertEqual(self.app.jobs, {})

    def test_search_provenance_is_saved_with_prepared_snapshot(self):
        sources, total = parse_feed(FEED)
        receipt = {"receipt_id": "test-receipt", "results": sources, "total_reported": total, "provider": "arxiv"}
        with patch.object(self.app.search, "search", return_value=receipt):
            self.request("/api/search", {"query": "test"})
        _, _, body = self.request("/api/prepare", {"case": case(), "receipt_ids": ["test-receipt"]})
        saved = read_json(self.app.runs_root / json.loads(body)["run_id"] / "retrieval.json")
        self.assertEqual(saved["searches"][0]["provider"], "arxiv")


if __name__ == "__main__":
    unittest.main()
