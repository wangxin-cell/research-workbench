"""Minimal Responses API adapter, with no automatic retries or key persistence."""
import json
import os
import urllib.error
import urllib.request

from .core import REPORT_SCHEMA


class ProviderError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an Authorization header to a redirect destination.
        return None


class ResponsesProvider:
    def __init__(self, model, timeout=120, max_output_tokens=6000):
        if not model.strip() or timeout <= 0 or max_output_tokens <= 0:
            raise ValueError("Model, positive timeout, and positive token limit are required")
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.opener = urllib.request.build_opener(NoRedirect())

    def generate(self, request):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("Set OPENAI_API_KEY in your local environment, or use prepare/import offline")
        payload = {
            "model": self.model, "store": False,
            "instructions": request["instructions"], "input": request["input"],
            "max_output_tokens": self.max_output_tokens,
            "text": {"format": {"type": "json_schema", "name": "research_report",
                                "strict": True, "schema": REPORT_SCHEMA}},
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                body = response.read(5_000_001)
                if len(body) > 5_000_000:
                    raise ProviderError("Provider response exceeds size limit")
                raw = json.loads(body)
        except urllib.error.HTTPError as exc:
            # Do not persist arbitrary upstream bodies, headers, or secrets.
            raise ProviderError(f"Provider returned HTTP {exc.code}; no automatic retry") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError("Provider connection failed or timed out; billing may have occurred; no automatic retry") from None
        except (ValueError, UnicodeError):
            raise ProviderError("Provider returned invalid JSON") from None
        if not isinstance(raw, dict) or raw.get("status") != "completed":
            raise ProviderError("Provider did not complete the response; no report was accepted")
        texts = []
        for item in raw.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise ProviderError("Provider refused the request; no report was accepted")
                if content.get("type") == "output_text":
                    texts.append(content.get("text", ""))
        try:
            report = json.loads("".join(texts))
        except (ValueError, TypeError):
            raise ProviderError("Provider output is not a JSON report") from None
        metadata = {"response_id": raw.get("id"), "model": raw.get("model", self.model),
                    "usage": raw.get("usage"), "cost_amount": None, "cost_currency": None,
                    "cost_note": "Not calculated; token usage is not a price quote"}
        return report, metadata
