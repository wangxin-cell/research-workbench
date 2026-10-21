"""Small, rate-limited arXiv metadata search. No novelty claims or arbitrary URL fetches."""
import copy
from datetime import datetime, timezone
import hashlib
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .core import ValidationError, digest, text
from .provider import NoRedirect

NS = {"a": "http://www.w3.org/2005/Atom", "o": "http://a9.com/-/spec/opensearch/1.1/"}
ID_PATTERN = r"(?:\d{4}\.\d{4,5}|[a-zA-Z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"


class RetrievalError(RuntimeError):
    pass


def arxiv_identifier(value):
    value = value.strip()
    if value.startswith("arXiv:"):
        value = value[6:]
    if value.startswith(("http://", "https://")):
        parts = urllib.parse.urlsplit(value)
        if parts.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            return None
        value = re.sub(r"^/(abs|pdf)/", "", parts.path)
        value = re.sub(r"\.pdf$", "", value)
    return value if re.fullmatch(ID_PATTERN, value) else None


def query_parameters(query, limit=5):
    query = text(query, "query", 300).strip()
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValidationError("Search limit must be an integer from 1 to 10")
    identity = arxiv_identifier(query)
    if identity:
        return {"id_list": identity, "max_results": 1}
    if "://" in query:
        raise ValidationError("Only arXiv URLs are supported; use keywords for other papers")
    terms = re.findall(r"[\w-]+", query, re.UNICODE)
    if not terms:
        raise ValidationError("Enter paper keywords or an arXiv identifier")
    return {"search_query": " AND ".join(f'all:"{term}"' for term in terms),
            "start": 0, "max_results": limit, "sortBy": "relevance"}


def parse_feed(payload):
    if len(payload) > 2_000_000 or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise RetrievalError("Unsupported or oversized arXiv feed")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise RetrievalError("arXiv returned an invalid Atom feed") from None
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise RetrievalError("arXiv returned an unexpected document")
    results, seen = [], set()
    for entry in root.findall("a:entry", NS):
        url = (entry.findtext("a:id", "", NS) or "").strip()
        identity = arxiv_identifier(url)
        if not identity:
            raise RetrievalError("arXiv returned an error or invalid paper identifier")
        if identity in seen:
            continue
        seen.add(identity)
        title = " ".join(entry.findtext("a:title", "", NS).split())
        abstract = " ".join(entry.findtext("a:summary", "", NS).split())
        if not title or not abstract:
            continue
        authors = [x.findtext("a:name", "", NS) for x in entry.findall("a:author", NS)]
        date = entry.findtext("a:published", "", NS)
        source = {"id": "arxiv-" + identity.replace("/", "-"), "title": title,
                  "url": "https://arxiv.org/abs/" + identity,
                  "summary": abstract, "locator": "arXiv abstract, " + identity,
                  "read_scope": "abstract", "summary_author": "arxiv_original_abstract",
                  "checked_on": datetime.now(timezone.utc).date().isoformat(),
                  "human_verified": False, "fulltext_snapshot_sha256": None}
        results.append({"source": source, "authors": authors, "published": date,
                        "arxiv_id": identity})
    try:
        total = int(root.findtext("o:totalResults", str(len(results)), NS))
    except ValueError:
        total = None
    return results, total


class ArxivSearch:
    def __init__(self, timeout=25):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.last_call = 0.0
        self.cache = {}
        self.opener = urllib.request.build_opener(NoRedirect())

    def search(self, query, limit=5):
        params = query_parameters(query, limit)
        key = digest(params)
        with self.lock:
            if key in self.cache and time.monotonic() - self.cache[key][0] < 900:
                result = copy.deepcopy(self.cache[key][1])
                result["cache_hit"] = True
                return result
            delay = 3.1 - (time.monotonic() - self.last_call)
            if delay > 0:
                time.sleep(delay)
            url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
            request = urllib.request.Request(url, headers={"User-Agent": "ResearchWorkbench/0.1 (local research tool)"})
            self.last_call = time.monotonic()
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    payload = response.read(2_000_001)
                results, total = parse_feed(payload)
            except urllib.error.HTTPError as exc:
                raise RetrievalError(f"arXiv returned HTTP {exc.code}; try later or add a paper manually") from None
            except (urllib.error.URLError, OSError, TimeoutError):
                raise RetrievalError("arXiv is unavailable or timed out; add paper materials manually") from None
            result = {"receipt_id": key[:16] + "-" + hashlib.sha256(payload).hexdigest()[:12],
                      "query": query, "provider": "arxiv", "parameters": params,
                      "retrieved_at": datetime.now(timezone.utc).isoformat(),
                      "response_sha256": hashlib.sha256(payload).hexdigest(),
                      "results": results, "total_reported": total, "cache_hit": False,
                      "scope": "arXiv metadata only; ranked subset, not an exhaustive novelty search"}
            if len(self.cache) >= 100:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (time.monotonic(), copy.deepcopy(result))
            return result
