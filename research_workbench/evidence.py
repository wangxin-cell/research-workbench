"""Local PDF snapshots and exact excerpts; integrity is not scientific validity."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

from .core import ValidationError, read_json, safe_url, text, write_json

MAX_PDF_BYTES = 8_000_000
SHA256 = re.compile(r"[0-9a-f]{64}")
_extraction_lock = threading.Lock()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def pdf_available():
    return importlib.util.find_spec("pypdf") is not None


def validate_excerpt(source):
    """Validate portable metadata without pretending the original file is present."""
    evidence = source.get("evidence")
    keys = {"document_sha256", "page", "start", "end", "page_text_sha256",
            "quote_sha256", "extractor"}
    if not isinstance(evidence, dict) or set(evidence) != keys:
        raise ValidationError("PDF excerpt evidence metadata is incomplete")
    for key in ("document_sha256", "page_text_sha256", "quote_sha256"):
        if not isinstance(evidence[key], str) or not SHA256.fullmatch(evidence[key]):
            raise ValidationError("Invalid PDF evidence fingerprint")
    for key in ("page", "start", "end"):
        if type(evidence[key]) is not int:
            raise ValidationError("PDF page and character offsets must be integers")
    if not (1 <= evidence["page"] <= 80 and 0 <= evidence["start"] < evidence["end"] <= 100_000):
        raise ValidationError("PDF page or character range is outside supported limits")
    if evidence["end"] - evidence["start"] != len(source["summary"]):
        raise ValidationError("PDF excerpt length does not match its character range")
    if sha256(source["summary"].encode("utf-8")) != evidence["quote_sha256"]:
        raise ValidationError("PDF excerpt text changed; select the passage again")
    if (source.get("read_scope") != "pdf_excerpt"
            or source.get("summary_author") != "pdf_extracted_passage"
            or source.get("fulltext_snapshot_sha256") != evidence["document_sha256"]
            or source.get("human_verified") is not False):
        raise ValidationError("PDF extraction must retain its scope and unverified status")
    text(evidence["extractor"], "evidence.extractor", 100)


class DocumentStore:
    def __init__(self, runs_root):
        self.root = Path(runs_root).resolve() / "_documents"

    def path(self, identity):
        if not isinstance(identity, str) or not SHA256.fullmatch(identity):
            raise ValidationError("Invalid document fingerprint")
        path = self.root / identity
        if not path.resolve().is_relative_to(self.root.parent) or path.is_symlink() or self.root.is_symlink():
            raise ValidationError("Document path is outside the workspace")
        return path

    def load(self, identity):
        path = self.path(identity)
        try:
            if (path / "original.pdf").is_symlink() or (path / "pages.json").is_symlink():
                raise ValidationError("Document snapshot must use regular local files")
            pdf = path / "original.pdf"
            if pdf.stat().st_size > MAX_PDF_BYTES:
                raise ValidationError("PDF snapshot exceeds the size limit")
            if sha256(pdf.read_bytes()) != identity:
                raise ValidationError("PDF snapshot changed; import the original PDF again")
            record = read_json(path / "pages.json")
            self.check_record(record, identity)
            return record
        except FileNotFoundError as exc:
            raise ValidationError("本机缺少该 PDF 快照。请重新导入同一份 PDF，再导出提示或分析。") from exc

    @staticmethod
    def check_record(record, identity):
        if (not isinstance(record, dict) or record.get("document_sha256") != identity
                or not isinstance(record.get("pages"), list)
                or not 1 <= len(record["pages"]) <= 80
                or record.get("page_count") != len(record["pages"])):
            raise ValidationError("Invalid PDF extraction snapshot")
        text(record.get("extractor"), "extractor", 100)
        for number, page in enumerate(record["pages"], 1):
            if (not isinstance(page, dict) or page.get("page") != number or not isinstance(page.get("text"), str)
                    or sha256(page["text"].encode("utf-8")) != page.get("text_sha256")):
                raise ValidationError("PDF page text snapshot changed")

    def ingest(self, encoded_pdf):
        if not isinstance(encoded_pdf, str) or len(encoded_pdf) > 10_666_668:
            raise ValidationError("PDF 文件不能超过 8 MB。")
        try:
            data = base64.b64decode(encoded_pdf, validate=True)
        except (ValueError, UnicodeError) as exc:
            raise ValidationError("Invalid PDF upload encoding") from exc
        if not data or len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
            raise ValidationError("请提供不超过 8 MB 的 PDF 文件。")
        identity = sha256(data)
        path = self.path(identity)
        if path.exists():
            return self.load(identity)
        if not pdf_available():
            raise ValidationError('PDF 功能需要可选依赖。请在启动服务的 Python 环境执行：python -m pip install ".[pdf]"，然后重启。')
        if not _extraction_lock.acquire(blocking=False):
            raise ValidationError("已有 PDF 正在提取，请稍后再试。")
        try:
            # A separate process bounds runtime and keeps parser failure out of
            # the HTTP process. This is not an OS sandbox or a hard RAM limit.
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "research_workbench.pdf_worker"],
                    input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    timeout=20, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except subprocess.TimeoutExpired as exc:
                raise ValidationError("PDF 提取超过 20 秒。请使用较小的 PDF，或手动添加阅读笔记。") from exc
            try:
                result = json.loads(completed.stdout.decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise ValidationError("PDF 提取失败。请检查文件，或手动添加阅读笔记。") from exc
            if completed.returncode or "error" in result:
                raise ValidationError(result.get("error", "PDF 提取失败。"))
            result["document_sha256"] = identity
            self.check_record(result, identity)
            self.root.mkdir(parents=True, exist_ok=True)
            # Complete a snapshot before making its permanent name visible.
            with tempfile.TemporaryDirectory(dir=self.root) as temp:
                staged = Path(temp) / identity
                staged.mkdir()
                (staged / "original.pdf").write_bytes(data)
                write_json(staged / "pages.json", result)
                staged.rename(path)
            return result
        finally:
            _extraction_lock.release()

    def excerpt(self, identity, page, start, end, title, url):
        text(title, "论文标题", 500)
        if not safe_url(url):
            raise ValidationError("请填写不含凭据的 HTTP(S) 论文来源链接。")
        record = self.load(identity)
        if (type(page) is not int or not 1 <= page <= len(record["pages"])
                or type(start) is not int or type(end) is not int):
            raise ValidationError("请先选中一个页面中的证据文字。")
        content = record["pages"][page - 1]
        if not 0 <= start < end <= len(content["text"]) or end - start > 30_000:
            raise ValidationError("请选中 1—30000 字的连续片段。")
        quote = text(content["text"][start:end], "选中片段")
        source = {
            "id": f"pdf-{identity[:16]}-p{page}-{start}-{end}",
            "title": title, "url": url, "locator": f"PDF 第 {page} 页（文件页序，从 1 开始）",
            "summary": quote, "read_scope": "pdf_excerpt",
            "summary_author": "pdf_extracted_passage", "human_verified": False,
            "fulltext_snapshot_sha256": identity,
            "evidence": {"document_sha256": identity, "page": page, "start": start, "end": end,
                         "page_text_sha256": content["text_sha256"],
                         "quote_sha256": sha256(quote.encode("utf-8")), "extractor": record["extractor"]},
        }
        validate_excerpt(source)
        return source

    def verify_sources(self, case):
        records = {}
        for source in case["sources"]:
            if source.get("read_scope") != "pdf_excerpt":
                continue
            validate_excerpt(source)
            evidence = source["evidence"]
            identity = evidence["document_sha256"]
            if identity not in records:
                records[identity] = self.load(identity)
            record = records[identity]
            if evidence["page"] > len(record["pages"]):
                raise ValidationError("PDF excerpt page is missing")
            page = record["pages"][evidence["page"] - 1]
            if (page["text_sha256"] != evidence["page_text_sha256"]
                    or page["text"][evidence["start"]:evidence["end"]] != source["summary"]
                    or record["extractor"] != evidence["extractor"]):
                raise ValidationError("PDF 片段与本机页文本不一致，请重新选择片段。")
        return records


def archive_evidence(root, destination, records):
    """Copy verified local snapshots into each run, before any model call."""
    from shutil import copyfile
    if not records:
        return
    store = DocumentStore(root)
    archive = destination / "evidence"
    archive.mkdir()
    for identity, record in records.items():
        copyfile(store.path(identity) / "original.pdf", archive / (identity + ".pdf"))
        if sha256((archive / (identity + ".pdf")).read_bytes()) != identity:
            raise ValidationError("PDF changed while archiving; prepare again")
        write_json(archive / (identity + ".json"), record)
    write_json(destination / "evidence.json", {
        "documents": list(records),
        "checks": "Selected text matches saved extracted page text; original PDF bytes match fingerprint.",
        "limits": "Not a visual transcription check, link-to-file identity check, semantic review, or full-paper reading.",
    })


def verify_archive(path, case):
    """Verify saved PDFs and the quoted page text without needing the upload cache."""
    records = {}
    archive = Path(path) / "evidence"
    for source in case["sources"]:
        if source.get("read_scope") != "pdf_excerpt":
            continue
        evidence = source["evidence"]
        identity = evidence["document_sha256"]
        if identity not in records:
            pdf = archive / (identity + ".pdf")
            metadata = archive / (identity + ".json")
            if archive.is_symlink() or pdf.is_symlink() or metadata.is_symlink():
                raise ValidationError("PDF archive must use regular local files")
            if pdf.stat().st_size > MAX_PDF_BYTES or sha256(pdf.read_bytes()) != identity:
                raise ValidationError("Archived PDF fingerprint changed")
            record = read_json(metadata)
            DocumentStore.check_record(record, identity)
            records[identity] = record
        record = records[identity]
        if evidence["page"] > len(record["pages"]):
            raise ValidationError("Archived PDF page is missing")
        page = record["pages"][evidence["page"] - 1]
        if (page["text_sha256"] != evidence["page_text_sha256"]
                or page["text"][evidence["start"]:evidence["end"]] != source["summary"]
                or record["extractor"] != evidence["extractor"]):
            raise ValidationError("Archived PDF excerpt changed")
