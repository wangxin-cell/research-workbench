"""Input boundaries, output contract, and reference integrity checks.

Reference integrity is not semantic entailment or novelty verification.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


class ValidationError(ValueError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 5_000_000:
        raise ValidationError("JSON file exceeds the 5 MB input limit")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Expected a UTF-8 JSON file") from exc


def write_json(path, value):
    Path(path).write_text(encoded(value) + "\n", encoding="utf-8")


def safe_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                and not parsed.username and not parsed.password
                and not any(ord(c) < 32 for c in url))
    except (ValueError, TypeError):
        return False


def text(value, name, maximum=30000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError(f"{name}: expected non-empty text, at most {maximum} characters")
    return value


def load_case(path, case_id=None):
    data = read_json(path)
    if isinstance(data, dict) and "cases" in data:
        cases = data["cases"]
        if not isinstance(cases, list):
            raise ValidationError("cases must be a list")
        selected = [c for c in cases if isinstance(c, dict)
                    and (case_id is None or c.get("id") == case_id)]
        if len(selected) != 1:
            raise ValidationError("Select exactly one case using --case")
        data = selected[0]
    elif case_id is not None and (not isinstance(data, dict) or data.get("id") != case_id):
        raise ValidationError("Case ID does not match the input")
    return validate_case(data)


def validate_case(case):
    if not isinstance(case, dict):
        raise ValidationError("Case must be an object")
    allowed = {"id", "user_question", "resources", "sources"}
    if set(case) != allowed:
        raise ValidationError("Case fields must be id, user_question, resources, sources; evaluator fields are prohibited")
    text(case["id"], "case.id", 100)
    text(case["user_question"], "user_question")
    if not isinstance(case["resources"], dict):
        raise ValidationError("resources must be an object")
    # Only research conditions cross this boundary, not arbitrary evaluator data.
    resource_keys = {"skills", "gpu", "ram_gib", "time_weeks", "data", "cloud_budget",
                     "api_budget_cny", "target_model", "notes"}
    if set(case["resources"]) - resource_keys:
        raise ValidationError("Unknown resource field; use notes for research conditions")
    if len(encoded(case["resources"])) > 15000:
        raise ValidationError("Resource conditions exceed the size limit")
    if not isinstance(case["sources"], list) or not 1 <= len(case["sources"]) <= 50:
        raise ValidationError("Provide between 1 and 50 sources")
    source_keys = {"id", "title", "url", "locator", "summary", "read_scope", "checked_on",
                   "summary_author", "human_verified", "fulltext_snapshot_sha256", "evidence"}
    ids = []
    for source in case["sources"]:
        if not isinstance(source, dict) or set(source) - source_keys:
            raise ValidationError("Unknown source fields; evaluator metadata is prohibited")
        for key in ("id", "title", "url", "locator", "summary", "read_scope"):
            text(source.get(key), f"source.{key}")
        if not safe_url(source["url"]):
            raise ValidationError("Source URL must be an HTTP(S) URL without credentials")
        if "evidence" in source or source["read_scope"] == "pdf_excerpt":
            from .evidence import validate_excerpt
            validate_excerpt(source)
        ids.append(source["id"])
    if len(set(ids)) != len(ids):
        raise ValidationError("Source IDs must be unique within the case")
    # Return a detached JSON value so callers cannot mutate a shared fixture.
    return json.loads(encoded(case))


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items}


STRING = {"type": "string"}
STRINGS = arr(STRING)
REPORT_SCHEMA = obj({
    "decision": {"type": "string", "enum": ["explore", "revise", "stop", "need_evidence"]},
    "summary": STRING,
    "findings": arr(obj({
        "statement": STRING,
        "kind": {"type": "string", "enum": ["source_fact", "derived", "inference"]},
        "source_ids": STRINGS,
    })),
    "candidates": arr(obj({
        "title": STRING, "research_question": STRING, "potential_contribution": STRING,
        "status": {"type": "string", "enum": ["unverified", "covered", "not_feasible"]},
        "comparisons": arr(obj({"source_id": STRING, "overlap": STRING, "difference": STRING})),
        "first_test": obj({"baseline": STRING, "variable": STRING, "metric": STRING,
                           "failure_signal": STRING, "resource_check": STRING}),
        "uncertainties": STRINGS,
    })),
    "next_steps": STRINGS,
    "limitations": STRINGS,
})


def validate_schema(value, schema, location="report"):
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ValidationError(f"{location}: missing or unexpected fields")
        for key, child in schema["properties"].items():
            validate_schema(value[key], child, f"{location}.{key}")
    elif kind == "array":
        if not isinstance(value, list):
            raise ValidationError(f"{location}: expected array")
        for i, child in enumerate(value):
            validate_schema(child, schema["items"], f"{location}[{i}]")
    elif kind == "string":
        text(value, location)
        if "enum" in schema and value not in schema["enum"]:
            raise ValidationError(f"{location}: invalid enum value")


def validate_report(report, case):
    validate_schema(report, REPORT_SCHEMA)
    known = {source["id"] for source in case["sources"]}
    if len(report["candidates"]) > 3:
        raise ValidationError("At most three candidates may be returned")
    if not report["findings"] or not report["next_steps"] or not report["limitations"]:
        raise ValidationError("Findings, next steps and limitations must be non-empty")
    if report["decision"] == "explore" and not report["candidates"]:
        raise ValidationError("An explore decision must include a candidate")
    for finding in report["findings"]:
        refs = finding["source_ids"]
        if set(refs) - known:
            raise ValidationError("Finding cites an unknown source ID")
        if finding["kind"] == "source_fact" and not refs:
            raise ValidationError("A source fact requires at least one source ID")
    for candidate in report["candidates"]:
        if not candidate["comparisons"] or not candidate["uncertainties"]:
            raise ValidationError("Each candidate requires comparisons and uncertainties")
        for comparison in candidate["comparisons"]:
            if comparison["source_id"] not in known:
                raise ValidationError("Candidate cites an unknown source ID")
    return report
