"""Local, evidence-anchored review records. No model calls or automatic judging."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import secrets

from .core import (ValidationError, digest, encoded, read_json, text,
                   validate_case, validate_report, write_json)


DIMENSIONS = {
    "evidence": "关键事实有依据，引用支持具体表述。",
    "prior_work": "准确解释最接近工作的重合与差异。",
    "research_value": "问题具体，并解释为何值得投入。",
    "constraints": "尊重硬约束，说明成本估计假设。",
    "validation_plan": "给出基线、变量、指标及可能削弱假设的结果。",
    "uncertainty": "说明未知条件及核查方法，不过度保证或一律拒绝。",
}
LABELS = {"pass", "partial", "fail", "unknown", "not_applicable"}
ASSETS = {"A.html", "B.html", "A.json", "B.json", "input.json",
          "criteria.json", "index.html", "review-instructions.txt"}
INSTRUCTIONS = """先阅读 A.html、B.html 和 criteria.json，再填写 rating.json。
不要查看上级目录的 organizer-mapping.json。身份隐藏不能消除文风泄漏。

每个判断填写 label、rationale、output_pointers 和 sources。
label 可用 pass、partial、fail、unknown；not_applicable 仅限规则快照预先排除的维度。
output_pointers 指向 A.json 或 B.json 的实际位置，例如 /findings/0/statement。
空字符串 "" 表示全文，可用于记录缺失内容；空数组不算依据。
sources 使用 [{"source_id": "论文ID", "locator": "章节或页码"}]；
无需文献支持的判断可填 []。程序检查位置和 ID，不验证理由是否正确。

逐项填写 dimensions、required_findings 和每个 candidates 条目。
severe_errors 填写 description、output_pointers、sources；确实未发现时保留 []。
完整填写 reviewer 的背景和接触情况，再给出 preference 和 reason。
保留原始分歧，不覆盖其他评审者的记录。

使用 review-submit 命令保存一份新的结果文件。模板中的 null 都是未填写，
不能作为无错误或已通过。程序根据人工填写的标签归纳状态，不自行评审科研质量。
"""


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def exact_keys(value, expected, location):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValidationError(f"{location}: missing or unexpected fields")


def text_list(value, location, minimum=0):
    if not isinstance(value, list) or len(value) < minimum:
        raise ValidationError(f"{location}: expected at least {minimum} text items")
    for item in value:
        text(item, location)
    return value


def date_value(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("Timezone is required")
        return parsed
    except (TypeError, ValueError):
        raise ValidationError("Expected an ISO timestamp with timezone") from None


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded(value) + "\n")
    return path


def create_review_plan(case, criteria_path, destination):
    """Snapshot curator-authored criteria before running either system."""
    case = validate_case(case)
    raw = read_json(criteria_path)
    records = raw.get("cases") if isinstance(raw, dict) and "cases" in raw else [raw]
    if not isinstance(records, list):
        raise ValidationError("Criteria must contain a list of cases")
    matches = [r for r in records if isinstance(r, dict) and r.get("id") == case["id"]]
    if len(matches) != 1:
        raise ValidationError("Criteria must match exactly one input case")
    selected = matches[0]
    requirements = text_list(selected.get("criteria"), "criteria", 3)
    if len(set(requirements)) != len(requirements):
        raise ValidationError("Required findings must not be duplicates")
    failures = text_list(selected.get("failures"), "failures", 1)
    ambiguities = text_list(selected.get("ambiguities", []), "ambiguities")
    exclusions = selected.get("not_applicable", {})
    if not isinstance(exclusions, dict) or set(exclusions) - set(DIMENSIONS):
        raise ValidationError("not_applicable must map known dimensions to reasons")
    for reason in exclusions.values():
        text(reason, "not_applicable reason")
    plan = {
        "schema_version": 1, "created_at": timestamp(), "case_id": case["id"],
        "input_sha256": digest(case), "criteria_source_sha256": digest(selected),
        "material_mode": "fixed_provided_material",
        "requirements": {f"R{i + 1}": item for i, item in enumerate(requirements)},
        "dimensions": DIMENSIONS, "not_applicable": exclusions,
        "known_failure_modes": failures, "ambiguities": ambiguities,
        "curator_reported_reviewers": text_list(selected.get("reviewer_ids", []), "reviewer_ids"),
        "reviewer_credentials_verified": False,
        "criteria_status": selected.get("readiness", "unreviewed"),
        "assessment_status": "not_run",
    }
    return write_new(destination, {"plan": plan, "sha256": digest(plan)})


def load_review_plan(path, case):
    envelope = read_json(path)
    exact_keys(envelope, {"plan", "sha256"}, "Review plan")
    plan = envelope["plan"]
    if not isinstance(plan, dict) or envelope["sha256"] != digest(plan):
        raise ValidationError("Review plan changed; create a new snapshot")
    if plan.get("schema_version") != 1 or plan.get("dimensions") != DIMENSIONS:
        raise ValidationError("Unsupported review plan version or dimensions")
    if plan.get("input_sha256") != digest(case) or plan.get("case_id") != case["id"]:
        raise ValidationError("Review plan does not match these case inputs")
    requirements = plan.get("requirements")
    if not isinstance(requirements, dict) or len(requirements) < 3:
        raise ValidationError("Review plan requires at least three findings")
    if set(requirements) != {f"R{i + 1}" for i in range(len(requirements))}:
        raise ValidationError("Invalid requirement identifiers")
    text_list(list(requirements.values()), "requirements", 3)
    exclusions = plan.get("not_applicable")
    if not isinstance(exclusions, dict) or set(exclusions) - set(DIMENSIONS):
        raise ValidationError("Invalid not_applicable dimensions")
    for reason in exclusions.values():
        text(reason, "not_applicable reason")
    date_value(plan.get("created_at"))
    return envelope


def blank_judgment():
    return {"label": None, "rationale": None, "output_pointers": [], "sources": []}


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attach_review_packet(reviewer, ordered_runs, envelope):
    """Add rating materials; ordered_runs has the actual randomized A/B order."""
    reviewer = Path(reviewer)
    plan = envelope["plan"]
    case = ordered_runs[0][1]
    write_json(reviewer / "input.json", case)
    write_json(reviewer / "criteria.json", envelope)
    packet_id = secrets.token_hex(12)
    rating = {
        "schema_version": 1, "packet_id": packet_id,
        "reviewer": {"id": None, "domain_experience": None,
                     "system_identity_known": None, "saw_other_reviews": None},
        "preference": None, "reason": None,
    }
    for label, (_, _, report) in zip(("A", "B"), ordered_runs):
        write_json(reviewer / f"{label}.json", report)
        rating[label] = {
            "dimensions": {name: blank_judgment() for name in DIMENSIONS},
            "required_findings": {name: blank_judgment() for name in plan["requirements"]},
            "candidates": {str(i): blank_judgment() for i in range(len(report["candidates"]))},
            "severe_errors": [],
        }
        for name, reason in plan["not_applicable"].items():
            rating[label]["dimensions"][name].update(label="not_applicable", rationale=reason)
    write_json(reviewer / "rating.json", rating)
    (reviewer / "review-instructions.txt").write_text(INSTRUCTIONS, encoding="utf-8")
    predeclared = all(date_value(plan["created_at"]) <= date_value(m["created_at"])
                      for m, _, _ in ordered_runs)
    packet = {
        "schema_version": 1, "packet_id": packet_id,
        "plan_sha256": envelope["sha256"], "input_sha256": digest(case),
        "rules_created_before_both_runs": predeclared,
        "timing_basis": "local_recorded_timestamps_not_external_preregistration",
        "files": {name: file_digest(reviewer / name) for name in sorted(ASSETS)},
    }
    write_json(reviewer / "packet.json", packet)


def resolve_pointer(report, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValidationError("Output pointer must be a JSON pointer; use an empty string for the whole report")
    value = report
    if not pointer:
        return value
    for raw in pointer.split("/")[1:]:
        if re.search(r"~(?![01])", raw):
            raise ValidationError(f"Invalid output pointer escape: {pointer}")
        key = raw.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(value, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", key):
                    raise ValueError("Expected array index")
                value = value[int(key)]
            elif isinstance(value, dict):
                value = value[key]
            else:
                raise TypeError("Not a container")
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValidationError(f"Output pointer does not exist: {pointer}") from None
    return value


def validate_anchors(judgment, report, source_ids, allow_empty=False):
    pointers = judgment.get("output_pointers")
    if not isinstance(pointers, list) or (not pointers and not allow_empty):
        raise ValidationError("Each judgment needs an output pointer; use [\"\"] for an omission")
    for pointer in pointers:
        resolve_pointer(report, pointer)
    sources = judgment.get("sources")
    if not isinstance(sources, list):
        raise ValidationError("sources must be a list")
    for source in sources:
        exact_keys(source, {"source_id", "locator"}, "Source anchor")
        if not isinstance(source["source_id"], str) or source["source_id"] not in source_ids:
            raise ValidationError("Review cites an unknown source ID")
        text(source["locator"], "source locator")


def validate_judgment(judgment, report, source_ids, excluded=False):
    exact_keys(judgment, {"label", "rationale", "output_pointers", "sources"}, "Judgment")
    label = judgment["label"]
    if not isinstance(label, str) or label not in LABELS:
        raise ValidationError("Every judgment needs an allowed label; null is not a judgment")
    if (label == "not_applicable") != excluded:
        raise ValidationError("not_applicable must match the rule snapshot")
    text(judgment["rationale"], "judgment rationale")
    validate_anchors(judgment, report, source_ids, allow_empty=excluded)
    return label


def outcome(labels, errors):
    if errors or "fail" in labels:
        return "fail"
    if "unknown" in labels:
        return "unresolved"
    if "partial" in labels:
        return "needs_revision"
    return "pass"


def submit_review(reviewer_dir, rating_path, destination):
    reviewer = Path(reviewer_dir)
    packet = read_json(reviewer / "packet.json")
    if (not isinstance(packet, dict) or packet.get("schema_version") != 1
            or not isinstance(packet.get("files"), dict) or set(packet["files"]) != ASSETS):
        raise ValidationError("Use a review packet created by blind --plan")
    for name in ASSETS:
        path = reviewer / name
        if not path.resolve().is_relative_to(reviewer.resolve()) or file_digest(path) != packet["files"][name]:
            raise ValidationError(f"Review material changed: {name}")
    case = validate_case(read_json(reviewer / "input.json"))
    from .evidence import verify_archive
    verify_archive(reviewer, case)
    envelope = load_review_plan(reviewer / "criteria.json", case)
    if (packet.get("plan_sha256") != envelope["sha256"]
            or packet.get("input_sha256") != digest(case)):
        raise ValidationError("Packet does not match its plan or input")
    rating = read_json(rating_path)
    exact_keys(rating, {"schema_version", "packet_id", "reviewer", "preference", "reason", "A", "B"}, "Rating")
    if rating["schema_version"] != 1 or rating["packet_id"] != packet["packet_id"]:
        raise ValidationError("Rating belongs to a different packet")
    person = rating["reviewer"]
    exact_keys(person, {"id", "domain_experience", "system_identity_known", "saw_other_reviews"}, "Reviewer")
    text(person["id"], "reviewer.id", 200)
    text(person["domain_experience"], "reviewer.domain_experience")
    for flag in ("system_identity_known", "saw_other_reviews"):
        if type(person[flag]) is not bool:
            raise ValidationError(f"reviewer.{flag} must be true or false")
    if (not isinstance(rating["preference"], str)
            or rating["preference"] not in {"A", "B", "tie", "neither", "unknown"}):
        raise ValidationError("Preference must be A, B, tie, neither or unknown")
    text(rating["reason"], "preference reason")
    plan = envelope["plan"]
    sources = {s["id"] for s in case["sources"]}
    outcomes = {}
    for side in ("A", "B"):
        report = validate_report(read_json(reviewer / f"{side}.json"), case)
        review = rating[side]
        exact_keys(review, {"dimensions", "required_findings", "candidates", "severe_errors"}, side)
        groups = {
            "dimensions": DIMENSIONS, "required_findings": plan["requirements"],
            "candidates": {str(i) for i in range(len(report["candidates"]))},
        }
        labels = []
        for group, keys in groups.items():
            exact_keys(review[group], keys, f"{side}.{group}")
            for key, judgment in review[group].items():
                excluded = group == "dimensions" and key in plan["not_applicable"]
                labels.append(validate_judgment(judgment, report, sources, excluded))
        if not isinstance(review["severe_errors"], list):
            raise ValidationError("severe_errors must be a list")
        for error in review["severe_errors"]:
            exact_keys(error, {"description", "output_pointers", "sources"}, "Severe error")
            text(error["description"], "severe error description")
            validate_anchors(error, report, sources)
        outcomes[side] = outcome(labels, review["severe_errors"])
    receipt = {
        "schema_version": 1, "submitted_at": timestamp(), "packet_id": packet["packet_id"],
        "packet_sha256": digest(packet), "plan_sha256": packet["plan_sha256"],
        "input_sha256": packet["input_sha256"],
        "rules_created_before_both_runs": packet.get("rules_created_before_both_runs"),
        "rating_sha256": digest(rating), "rating": rating, "outcomes": outcomes,
        "assessment_basis": "reviewer_entered_judgments_not_automated_scientific_verification",
        "reviewer_identity_verified": False,
        "criteria_status": plan.get("criteria_status"),
        "interpretation": "Outcomes describe this review only; no claim of novelty, consensus or general superiority.",
    }
    return write_new(destination, receipt)
