"""Loopback-only UI for the local workbench; no arbitrary file serving."""
from concurrent.futures import ThreadPoolExecutor
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit

from .core import ValidationError, read_json, text, validate_case, validate_report, write_json
from .provider import ResponsesProvider
from .evidence import DocumentStore, pdf_available
from .render import render_report
from .retrieval import ArxivSearch, RetrievalError
from .workflow import import_report, load_accepted, prepare, run

ASSETS = Path(__file__).parent / "web"
DATA = Path(__file__).parent / "data"
RUN_ID = re.compile(r"\d{8}T\d{6}-[0-9a-f]{8}")


class Application:
    def __init__(self, runs_root, search=None):
        self.runs_root = Path(runs_root).resolve()
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.search = search or ArxivSearch()
        self.documents = DocumentStore(self.runs_root)
        self.receipts = {}
        self.jobs = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-analysis")

    def run_path(self, identity):
        if not isinstance(identity, str) or not RUN_ID.fullmatch(identity):
            raise ValidationError("Invalid run identifier")
        path = self.runs_root / identity
        if not path.resolve().is_relative_to(self.runs_root) or path.is_symlink():
            raise ValidationError("Run path is outside the local workspace")
        return path

    def get_receipts(self, ids):
        if not isinstance(ids, list) or len(ids) > 50:
            raise ValidationError("Invalid search receipts")
        with self.lock:
            if any(not isinstance(i, str) or i not in self.receipts for i in ids):
                raise ValidationError("Search history expired; run the search again or omit its receipt")
            return copy.deepcopy([self.receipts[i] for i in dict.fromkeys(ids)])

    def save_receipts(self, path, receipts):
        write_json(path / "retrieval.json", {"searches": receipts,
                   "note": "User-selected supplemental literature; not an exhaustive novelty check"})

    def start_job(self, case, model, workflow, receipts):
        text(model, "model", 150)
        if workflow not in {"baseline", "reviewed"}:
            raise ValidationError("Invalid workflow")
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValidationError("本机未设置 OPENAI_API_KEY。可先使用导出提示与导入回答。")
        with self.lock:
            if any(j["status"] == "running" for j in self.jobs.values()):
                raise ValidationError("已有分析正在运行，请等待完成。")
            if len(self.jobs) >= 100:
                self.jobs.pop(next(iter(self.jobs)))
            identity = secrets.token_hex(8)
            self.jobs[identity] = {"job_id": identity, "status": "running", "run_id": None, "error": None}

        def work():
            try:
                path = run(self.runs_root, case, ResponsesProvider(model), workflow, search_receipts=receipts)
                result = {"status": "completed", "run_id": path.name}
            except Exception:
                result = {"status": "failed", "error": "分析未完成。失败记录已保留；请检查模型权限、连接与运行记录，不会自动重试。"}
            with self.lock:
                self.jobs[identity].update(result)

        self.pool.submit(work)
        return identity


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ResearchWorkbench/0.1"

        def log_message(self, fmt, *args):
            # Avoid logging user queries and project content.
            pass

        def trusted(self, mutation=False):
            port = self.server.server_port
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in allowed:
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + h for h in allowed}:
                return False
            if mutation:
                return (self.headers.get("X-Workbench-Request") == "local-ui"
                        and self.headers.get("Content-Type", "").split(";")[0] == "application/json")
            return True

        def send(self, status, body, content_type="application/json; charset=utf-8", download=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_OPTIONS(self):
            self.send(403, {"error": "Cross-origin requests are not supported"})

        def do_GET(self):
            if not self.trusted():
                return self.send(403, {"error": "Local access only"})
            route = urlsplit(self.path).path
            try:
                if route in {"/", "/app.js", "/styles.css"}:
                    name = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}[route]
                    mime = {"index.html": "text/html", "app.js": "text/javascript", "styles.css": "text/css"}[name]
                    return self.send(200, (ASSETS / name).read_bytes(), mime + "; charset=utf-8")
                if route == "/api/config":
                    return self.send(200, {"api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
                                          "default_model": os.environ.get("RESEARCH_WORKBENCH_MODEL", ""),
                                          "pdf_available": pdf_available(),
                                          "version": "0.1.0"})
                if route == "/api/examples":
                    return self.send(200, read_json(DATA / "exploration.json"))
                if route == "/demo":
                    cases = read_json(DATA / "exploration.json")["cases"]
                    case = next(c for c in cases if c["id"] == "EXP-C-GRAPH")
                    output = validate_report(read_json(DATA / "demo-report.json"), case)
                    return self.send(200, render_report(case, output, "人工编写的报告示例"), "text/html; charset=utf-8")
                if route == "/api/history":
                    records = []
                    for folder in sorted(app.runs_root.iterdir(), reverse=True):
                        if not RUN_ID.fullmatch(folder.name) or folder.is_symlink():
                            continue
                        try:
                            m = read_json(folder / "manifest.json")
                            records.append({k: m.get(k) for k in ["run_id", "case_id", "status", "created_at", "workflow", "requested_model"]})
                        except (OSError, ValueError):
                            continue
                        if len(records) == 30:
                            break
                    return self.send(200, records)
                if route.startswith("/api/jobs/"):
                    with app.lock:
                        job = copy.deepcopy(app.jobs.get(route.rsplit("/", 1)[-1]))
                    return self.send(200 if job else 404, job or {"error": "Job not found"})
                if route.startswith("/api/runs/"):
                    path = app.run_path(route.rsplit("/", 1)[-1])
                    return self.send(200, {"manifest": read_json(path / "manifest.json"),
                                          "input": read_json(path / "input.json")})
                if route.startswith("/reports/"):
                    path = app.run_path(route.rsplit("/", 1)[-1])
                    manifest, case, output = load_accepted(path)
                    label = "导入的选题分析" if manifest["status"] == "imported" else "选题分析"
                    return self.send(200, render_report(case, output, label, f"/evidence/{path.name}/"), "text/html; charset=utf-8")
                pdf_match = re.fullmatch(r"/evidence/([^/]+)/([0-9a-f]{64})\.pdf", route)
                if pdf_match:
                    path = app.run_path(pdf_match[1])
                    _, case, _ = load_accepted(path)
                    identities = {s["evidence"]["document_sha256"] for s in case["sources"] if "evidence" in s}
                    if pdf_match[2] not in identities:
                        return self.send(404, {"error": "Document not in this run"})
                    filename = pdf_match[2] + ".pdf"
                    return self.send(200, (path / "evidence" / filename).read_bytes(), "application/pdf", filename)
                match = re.fullmatch(r"/files/([^/]+)/(prompt\.txt|report\.json|input\.json)", route)
                if match:
                    path = app.run_path(match[1]) / match[2]
                    return self.send(200, path.read_bytes(), "application/octet-stream", match[2])
                self.send(404, {"error": "Not found"})
            except (OSError, ValueError, KeyError, StopIteration) as exc:
                self.send(400, {"error": "无法读取该材料或运行记录；请检查文件是否完整。"})

        def do_POST(self):
            try:
                route = urlsplit(self.path).path
                length = int(self.headers.get("Content-Length", "0"))
                limit = 11_000_000 if route == "/api/pdf" else 1_000_000
                if not 0 < length <= limit:
                    return self.send(413, {"error": f"Request must be at most {limit} bytes"})
                # Consume a bounded body before rejecting headers. Closing with
                # unread request bytes can reset the socket on Windows, hiding
                # the intended 403 response. Never parse or act on untrusted data.
                self.connection.settimeout(10)
                payload = self.rfile.read(length)
                if not self.trusted(mutation=True):
                    return self.send(403, {"error": "Local JSON requests only"})
                if len(payload) != length:
                    raise ValidationError("Incomplete request body")
                body = json.loads(payload)
                if not isinstance(body, dict):
                    raise ValidationError("Expected an object")
                route = urlsplit(self.path).path
                if route == "/api/pdf":
                    return self.send(201, app.documents.ingest(body.get("data")))
                if route == "/api/excerpt":
                    source = app.documents.excerpt(body.get("document_sha256"), body.get("page"),
                        body.get("start"), body.get("end"), body.get("title"), body.get("url"))
                    return self.send(201, source)
                if route == "/api/search":
                    receipt = app.search.search(body.get("query"), 5)
                    with app.lock:
                        if len(app.receipts) >= 100:
                            app.receipts.pop(next(iter(app.receipts)))
                        app.receipts[receipt["receipt_id"]] = receipt
                    return self.send(200, receipt)
                if route in {"/api/prepare", "/api/run"}:
                    case = validate_case(body.get("case"))
                    app.documents.verify_sources(case)
                    receipts = app.get_receipts(body.get("receipt_ids", []))
                    if route == "/api/prepare":
                        path = prepare(app.runs_root, case)
                        app.save_receipts(path, receipts)
                        return self.send(201, {"run_id": path.name, "status": "prepared"})
                    identity = app.start_job(case, body.get("model", ""), body.get("workflow", "reviewed"), receipts)
                    return self.send(202, {"job_id": identity, "status": "running"})
                if route == "/api/import":
                    path = app.run_path(body.get("run_id"))
                    if read_json(path / "manifest.json").get("status") != "prepared":
                        raise ValidationError("Only a prepared run can receive a response")
                    model_label = text(body.get("model_label"), "model_label", 150)
                    report = validate_report(body.get("report"), read_json(path / "input.json"))
                    incoming = path / ("incoming-" + secrets.token_hex(4) + ".json")
                    write_json(incoming, report)
                    import_report(path, incoming, model_label)
                    return self.send(200, {"run_id": path.name, "status": "imported"})
                self.send(404, {"error": "Not found"})
            except (ValidationError, ValueError, TypeError) as exc:
                self.send(400, {"error": str(exc)})
            except RetrievalError as exc:
                self.send(502, {"error": str(exc)})
            except OSError:
                self.send(500, {"error": "本地文件读写失败，请检查工作目录权限。"})
    return Handler


def serve(runs_root, port=8765):
    if not 1 <= port <= 65535:
        raise ValidationError("Port must be from 1 to 65535")
    app = Application(runs_root)
    try:
        with ThreadingHTTPServer(("127.0.0.1", port), make_handler(app)) as server:
            print(f"Research Workbench: http://127.0.0.1:{server.server_port}", flush=True)
            print("Local access only. Press Ctrl+C to stop.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        app.pool.shutdown(wait=False, cancel_futures=True)
