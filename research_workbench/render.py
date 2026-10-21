"""Static local HTML. All model and source content is escaped."""
from html import escape

from .core import safe_url


STYLE = """
body{margin:0;background:#f5f4ef;color:#20332b;font:16px/1.7 system-ui,sans-serif}
main{max-width:1040px;margin:auto;padding:48px 24px}h1{font-size:34px;line-height:1.3}
h2{font-size:23px;margin-top:30px}h3{font-size:19px}a{color:#167254;overflow-wrap:anywhere}
.card{background:white;border:1px solid #dce3dc;border-radius:14px;padding:22px;margin:18px 0}
.badge{display:inline-block;background:#e3eee7;padding:3px 11px;border-radius:20px;font-size:13px}
.muted{color:#596b62;font-size:14px}.notice{border-left:4px solid #be8540;padding-left:15px}
dt{font-weight:650;margin-top:12px}dd{margin-left:0;white-space:pre-wrap}li{margin:6px 0}
.question{font-size:19px}.ref{font-size:13px;margin-left:5px}pre{white-space:pre-wrap;overflow-wrap:anywhere}
@media print{body{background:white}main{padding:0}.card{break-inside:avoid}a{color:inherit}}
"""


def e(value):
    return escape(str(value), quote=True)


def items(values):
    return "<ul>" + "".join(f"<li>{e(value)}</li>" for value in values) + "</ul>"


def document(title, body):
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'\">"
            f"<title>{e(title)}</title><style>{STYLE}</style><main>{body}</main></html>")


def report_body(case, report, label="选题分析", evidence_base=None):
    ids = {s["id"]: i for i, s in enumerate(case["sources"], 1)}
    # Numeric anchors prevent source IDs becoming HTML attributes.
    prefix = "source-" + str(abs(sum(ord(c) for c in label))) + "-"
    def refs(source_ids):
        return " ".join(f"<a class='ref' href='#{prefix}{ids[s]}'>[{e(s)}]</a>" for s in source_ids)
    decisions = {"explore": "继续探索", "revise": "修订想法", "stop": "停止当前方案", "need_evidence": "补充证据"}
    body = f"<h1>{e(label)}</h1><p class='question'>{e(case['user_question'])}</p>"
    body += "<p class='notice'>基于已提供材料的分析 · 引用关联检查不能证明论断成立，也不能证明创新。结论仍需原文核查与研究者判断。</p>"
    body += f"<span class='badge'>{e(decisions[report['decision']])}</span><p>{e(report['summary'])}</p>"
    body += "<h2>证据与判断</h2><ul>"
    kind_labels = {"source_fact": "文献事实", "derived": "推导", "inference": "推测"}
    for finding in report["findings"]:
        body += f"<li><span class='muted'>{kind_labels[finding['kind']]} · </span>{e(finding['statement'])}{refs(finding['source_ids'])}</li>"
    body += "</ul><h2>候选研究问题</h2>"
    if not report["candidates"]:
        body += "<p>本次未推荐候选方向。请结合判断理由与下一步行动阅读。</p>"
    labels = {"unverified": "创新性待核查", "covered": "已有工作覆盖", "not_feasible": "当前条件不匹配"}
    for c in report["candidates"]:
        body += f"<article class='card'><span class='badge'>{labels[c['status']]}</span><h3>{e(c['title'])}</h3>"
        body += f"<p>{e(c['research_question'])}</p><p><strong>候选贡献：</strong>{e(c['potential_contribution'])}</p>"
        for comparison in c["comparisons"]:
            body += f"<p>{refs([comparison['source_id']])}<br><strong>重合：</strong>{e(comparison['overlap'])}<br><strong>差异：</strong>{e(comparison['difference'])}</p>"
        body += "<dl>"
        for key, name in [("baseline", "基线"), ("variable", "变量"), ("metric", "指标"), ("failure_signal", "削弱假设的结果"), ("resource_check", "资源核查")]:
            body += f"<dt>{name}</dt><dd>{e(c['first_test'][key])}</dd>"
        body += "</dl><strong>尚未确认</strong>" + items(c["uncertainties"]) + "</article>"
    body += "<h2>下一步</h2>" + items(report["next_steps"])
    body += "<h2>结论边界</h2>" + items(report["limitations"])
    body += "<h2>提供的研究条件</h2><dl>"
    resource_labels = {"skills": "已有技能", "gpu": "可用算力", "ram_gib": "内存 / GiB",
                       "time_weeks": "可投入时间 / 周", "data": "可用数据", "cloud_budget": "计算预算",
                       "api_budget_cny": "API 预算 / 元", "target_model": "研究对象模型", "notes": "补充条件"}
    for key, value in case["resources"].items():
        if isinstance(value, list):
            value = "、".join(str(v) for v in value)
        body += f"<dt>{e(resource_labels.get(key, key))}</dt><dd>{e(value)}</dd>"
    body += "</dl><h2>材料来源</h2>"
    for source in case["sources"]:
        href = source["url"] if safe_url(source["url"]) else "#"
        material = "原始摘要" if source.get("summary_author") in {"arxiv_original_abstract", "user_provided_abstract"} else "摘要转述或阅读笔记"
        evidence = source.get("evidence")
        if evidence:
            material = "PDF 提取片段（未核对版面与含义，不代表已读全文）"
        body += f"<div class='card' id='{prefix}{ids[source['id']]}'><a rel='noreferrer noopener' href='{e(href)}'>{e(source['title'])}</a><pre>{e(source['summary'])}</pre><p class='muted'>提供内容：{material} · 来源定位：{e(source['locator'])}</p>"
        if evidence:
            identity = evidence["document_sha256"]
            body += f"<p class='muted'>文件 SHA-256：<code style='overflow-wrap:anywhere'>{e(identity)}</code><br>提取器：{e(evidence['extractor'])} · 页内字符 {e(evidence['start'])}–{e(evidence['end'])}（从 0 开始，右端不含）<br>论文链接由用户提供，未自动核实与文件对应。</p>"
            if evidence_base:
                body += f"<a href='{e(evidence_base + identity + '.pdf')}' download>下载此次分析保存的原 PDF</a>"
        body += "</div>"
    return body


def render_report(case, report, label="选题分析", evidence_base=None):
    return document(label, report_body(case, report, label, evidence_base))
