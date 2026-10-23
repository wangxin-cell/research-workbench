"""Static local HTML. All model and source content is escaped."""
from html import escape

from .core import safe_url


STYLE = """
:root{--ink:#18302d;--muted:#586c67;--brand:#176b5b;--line:#dce5e0;--paper:#fff;
--bg:#f5f7f5;--tint:#eaf3ee;--amber:#85571b;--amber-tint:#fff5df}
*{box-sizing:border-box}html{scroll-padding-top:24px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 "Segoe UI","Microsoft YaHei","PingFang SC",system-ui,sans-serif}
main{max-width:1080px;margin:auto;padding:48px 40px 72px}p{margin:0 0 16px}
h1,h2,h3,h4{line-height:1.4;overflow-wrap:anywhere}h1{font-size:clamp(28px,4vw,40px);font-weight:650;letter-spacing:-.035em;margin:8px 0 24px}
h2{font-size:24px;font-weight:650;margin:0}h3{font-size:22px;font-weight:650;margin:8px 0 16px}h4{font-size:16px;margin:0 0 12px}
a{color:var(--brand);text-underline-offset:4px;overflow-wrap:anywhere}a:hover{text-decoration-thickness:2px}
a:focus-visible{outline:3px solid var(--brand);outline-offset:4px;border-radius:4px}
.eyebrow{color:var(--brand);font-size:13px;font-weight:650;letter-spacing:.12em;margin:0}
.report-header{margin-bottom:24px}.question-label{display:block;color:var(--muted);font-size:13px;font-weight:600;margin-bottom:8px}
.question{font-size:18px;max-width:48em;margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.summary-card{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:24px 32px;margin:24px 0}
.summary-top{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:16px}.summary-top h2{font-size:15px;color:var(--muted)}
.summary-copy{font-size:18px;font-weight:500;line-height:1.75;white-space:pre-wrap;margin:0;overflow-wrap:anywhere}
.badge{display:inline-flex;align-items:center;border-radius:6px;padding:4px 10px;background:var(--tint);color:var(--brand);font-size:13px;font-weight:650;line-height:1.6;max-width:100%}
.badge-warning{background:var(--amber-tint);color:var(--amber)}.badge-neutral{background:var(--bg);color:var(--muted)}
.notice{display:flex;gap:12px;font-size:13px;color:var(--muted);margin:0;line-height:1.75}
.notice:before{content:"";display:block;flex:0 0 3px;background:var(--amber);border-radius:3px}
.report-nav{display:flex;flex-wrap:wrap;gap:8px 24px;border-bottom:1px solid var(--line);padding:16px 0;margin-bottom:40px}
.report-nav a{display:inline-flex;align-items:center;min-height:44px;font-size:14px;font-weight:600;text-decoration:none}
.report-nav a:hover{text-decoration:underline}.report-section{margin-top:40px;scroll-margin-top:24px}
.section-heading{display:flex;align-items:baseline;gap:12px;margin-bottom:20px}.section-number{font-size:13px;color:var(--muted);font-weight:600;font-variant-numeric:tabular-nums}
.section-intro{color:var(--muted);font-size:14px;margin:-8px 0 24px}.findings{list-style:none;padding:0;margin:0;border-top:1px solid var(--line)}
.finding{display:grid;grid-template-columns:92px minmax(0,1fr);gap:16px;padding:20px 0;border-bottom:1px solid var(--line);margin:0}
.finding .badge{align-self:start;justify-self:start;white-space:nowrap}.finding p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.ref{display:inline-block;font-size:13px;line-height:1.8;margin:0 3px;padding:2px 5px;border-radius:4px;background:var(--tint);text-decoration:none;white-space:normal}
.ref:hover{background:#d9e9e1}.card{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:28px 32px;margin:24px 0}
.candidate-top{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}.candidate-index{font-size:13px;font-weight:600;color:var(--muted)}
.candidate-question{font-size:18px;white-space:pre-wrap;overflow-wrap:anywhere}.contribution{background:var(--bg);border-radius:12px;padding:16px 20px;margin:20px 0 28px}
.contribution strong{display:block;font-size:13px;color:var(--muted);margin-bottom:8px}.contribution p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.comparison{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:12px 0}.comparison-source{padding:12px 16px;background:var(--bg);margin:0;font-size:13px;color:var(--muted)}
.comparison-grid{display:grid;grid-template-columns:1fr 1fr}.comparison-grid>div{padding:16px 20px;min-width:0}.comparison-grid>div+div{border-left:1px solid var(--line)}
.comparison-grid h4{font-size:13px;color:var(--muted);margin-bottom:8px}.comparison-grid p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.candidate-section{margin-top:28px}.experiment-grid,.resource-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 24px;margin:0}
.experiment-grid>div,.resource-grid>div{min-width:0;border-top:1px solid var(--line);padding:16px 0}.experiment-grid>div:last-child{grid-column:1/-1}
dt{font-size:13px;color:var(--muted);font-weight:600;margin:0 0 8px}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.uncertainties{border-left:3px solid var(--amber);padding-left:20px;margin-top:24px}.uncertainties h4{color:var(--amber);font-size:14px}
ul,ol{padding-left:24px;margin:8px 0 0}li{padding-left:4px;margin:8px 0;overflow-wrap:anywhere}
.followup-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:40px}.followup-grid .report-section{margin:0;min-width:0}
.followup-grid .card{height:100%;margin:0;padding:24px}.followup-grid h2{font-size:21px}.followup-grid .section-heading{margin-bottom:16px}
.next-steps{padding-left:24px}.next-steps li{padding-left:8px;margin-bottom:16px}.next-steps li::marker{color:var(--brand);font-weight:650}
.boundary-card{background:#fffdf8}.boundary-card .section-number{color:var(--amber)}
.source-card{scroll-margin-top:24px}.source-card:target{border-color:var(--brand);outline:3px solid #b9d9c9;outline-offset:3px}
.source-top{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.source-number{font-size:13px;font-weight:650;color:var(--brand)}.source-title{font-size:18px;margin:0 0 16px}
.source-text{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin:0;padding:20px;background:var(--bg);border-radius:12px;line-height:1.75}
.source-meta{font-size:13px;color:var(--muted);margin:16px 0 0;overflow-wrap:anywhere}.source-meta span{display:block;margin-top:4px}
.source-meta code{font-family:ui-monospace,Consolas,monospace;font-size:13px;overflow-wrap:anywhere}
.download-evidence{display:inline-flex;align-items:center;min-height:44px;margin-top:12px;font-size:14px;font-weight:600}
.empty-state{padding:24px;border:1px dashed var(--line);border-radius:12px;color:var(--muted);background:var(--paper)}
.report-footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
@media(max-width:680px){main{padding:28px 20px 48px}.summary-card,.card{padding:20px}.summary-copy,.question,.candidate-question{font-size:16px}
.report-nav{gap:0 20px;margin-bottom:32px}.report-section{margin-top:32px}.section-heading{gap:8px}h2{font-size:22px}h3{font-size:20px}
.finding{grid-template-columns:1fr;gap:12px}.comparison-grid,.experiment-grid,.resource-grid,.followup-grid{grid-template-columns:1fr}
.comparison-grid>div+div{border-left:0;border-top:1px solid var(--line)}.comparison-grid>div{padding:16px}.followup-grid{margin-top:32px}
.source-text{padding:16px}.contribution{padding:16px}}
@media print{body{background:#fff;color:#000;font-size:11pt}main{max-width:none;padding:0}.report-nav{display:none}h1{font-size:24pt}h2{font-size:17pt}h3{font-size:15pt}
.report-section{margin-top:24px}.card,.summary-card{padding:16px;border-radius:0;box-shadow:none}.report-header,.summary-card,.comparison,.finding,.experiment-grid>div,.resource-grid>div{break-inside:avoid}
.card{break-inside:auto}.source-text{padding:12px}.followup-grid{display:block}.followup-grid .report-section{margin-top:24px}
h1,h2,h3,h4,dt{break-after:avoid}a{color:inherit}.source-card:target{outline:0}.report-footer{margin-top:24px}}
"""


def e(value):
    return escape(str(value), quote=True)


def items(values):
    return "<ul>" + "".join(f"<li>{e(value)}</li>" for value in values) + "</ul>"


def document(title, body):
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'\">"
            f"<title>{e(title)}</title><style>{STYLE}</style></head><body><main>{body}</main></body></html>")


def report_body(case, report, label="选题分析", evidence_base=None):
    ids = {s["id"]: i for i, s in enumerate(case["sources"], 1)}
    sources = {s["id"]: s for s in case["sources"]}
    # Numeric anchors prevent source IDs becoming HTML attributes.
    prefix = "source-" + str(abs(sum(ord(c) for c in label))) + "-"

    def refs(source_ids):
        return " ".join(
            f"<a class='ref' href='#{prefix}{ids[s]}' aria-label='查看来源 {ids[s]}：{e(sources[s]['title'])}'>来源 {ids[s]:02d}</a>"
            for s in source_ids)

    def heading(number, title):
        return f"<div class='section-heading'><span class='section-number' aria-hidden='true'>{number}</span><h2>{title}</h2></div>"

    decisions = {"explore": "继续探索", "revise": "修订想法", "stop": "停止当前方案", "need_evidence": "补充证据"}
    decision_style = "badge-warning" if report["decision"] in {"revise", "stop", "need_evidence"} else ""
    body = (f"<article class='report'><header class='report-header'><p class='eyebrow'>研究选题工作台 / RESEARCH NOTE</p>"
            f"<h1>{e(label)}</h1><span class='question-label'>你的研究问题</span><p class='question'>{e(case['user_question'])}</p></header>"
            f"<section class='summary-card' aria-label='本次判断'><div class='summary-top'><h2>本次判断</h2>"
            f"<span class='badge {decision_style}'>{e(decisions[report['decision']])}</span></div><p class='summary-copy'>{e(report['summary'])}</p></section>"
            "<p class='notice'>基于已提供材料的分析 · 引用关联检查不能证明论断成立，也不能证明创新。结论仍需原文核查与研究者判断。</p>"
            f"<nav class='report-nav' aria-label='报告章节'><a href='#{prefix}findings'>证据与判断</a><a href='#{prefix}candidates'>候选问题</a>"
            f"<a href='#{prefix}next'>下一步</a><a href='#{prefix}materials'>材料来源</a></nav>"
            f"<section class='report-section' id='{prefix}findings'>{heading('01', '证据与判断')}<ul class='findings'>")
    kind_labels = {"source_fact": "文献事实", "derived": "推导", "inference": "推测"}
    kind_styles = {"source_fact": "", "derived": "badge-neutral", "inference": "badge-warning"}
    for finding in report["findings"]:
        body += (f"<li class='finding'><span class='badge {kind_styles[finding['kind']]}'>{kind_labels[finding['kind']]}</span>"
                 f"<p>{e(finding['statement'])} {refs(finding['source_ids'])}</p></li>")
    body += (f"</ul></section><section class='report-section' id='{prefix}candidates'>{heading('02', '候选研究问题')}"
             "<p class='section-intro'>先看与已有工作的关系，再判断第一步实验是否值得投入。</p>")
    if not report["candidates"]:
        body += "<p class='empty-state'>本次未推荐候选方向。请结合判断理由与下一步行动阅读。</p>"
    labels = {"unverified": "创新性待核查", "covered": "已有工作覆盖", "not_feasible": "当前条件不匹配"}
    for index, c in enumerate(report["candidates"], 1):
        body += (f"<article class='card candidate'><div class='candidate-top'><span class='candidate-index'>候选方向 {index:02d}</span>"
                 f"<span class='badge badge-warning'>{labels[c['status']]}</span></div><h3>{e(c['title'])}</h3>"
                 f"<p class='candidate-question'>{e(c['research_question'])}</p><div class='contribution'><strong>候选贡献</strong><p>{e(c['potential_contribution'])}</p></div>"
                 "<div class='candidate-section'><h4>与已有工作的关系</h4>")
        for comparison in c["comparisons"]:
            body += (f"<div class='comparison'><p class='comparison-source'>对照材料 {refs([comparison['source_id']])}</p><div class='comparison-grid'>"
                     f"<div><h4>已有重合</h4><p>{e(comparison['overlap'])}</p></div>"
                     f"<div><h4>潜在差异</h4><p>{e(comparison['difference'])}</p></div></div></div>")
        body += "</div><div class='candidate-section'><h4>第一步验证</h4><dl class='experiment-grid'>"
        for key, name in [("baseline", "基线"), ("variable", "变量"), ("metric", "指标"), ("failure_signal", "削弱假设的结果"), ("resource_check", "资源核查")]:
            body += f"<div><dt>{name}</dt><dd>{e(c['first_test'][key])}</dd></div>"
        body += "</dl></div><div class='uncertainties'><h4>尚未确认</h4>" + items(c["uncertainties"]) + "</div></article>"
    body += (f"</section><div class='followup-grid'><section class='report-section' id='{prefix}next'><div class='card'>"
             f"{heading('03', '下一步')}<ol class='next-steps'>" + "".join(f"<li>{e(value)}</li>" for value in report["next_steps"]) + "</ol></div></section>"
             f"<section class='report-section'><div class='card boundary-card'>{heading('04', '结论边界')}" + items(report["limitations"]) + "</div></section></div>"
             f"<section class='report-section'>{heading('05', '提供的研究条件')}<dl class='resource-grid'>")
    resource_labels = {"skills": "已有技能", "gpu": "可用算力", "ram_gib": "内存 / GiB",
                       "time_weeks": "可投入时间 / 周", "data": "可用数据", "cloud_budget": "计算预算",
                       "api_budget_cny": "API 预算 / 元", "target_model": "研究对象模型", "notes": "补充条件"}
    for key, value in case["resources"].items():
        if isinstance(value, list):
            value = "、".join(str(v) for v in value)
        body += f"<div><dt>{e(resource_labels.get(key, key))}</dt><dd>{e(value)}</dd></div>"
    body += (f"</dl></section><section class='report-section' id='{prefix}materials'>{heading('06', '材料来源')}"
             "<p class='section-intro'>以下是此次分析实际提供的内容；摘要、笔记或选取片段均不代表已阅读全文。</p>")
    for source in case["sources"]:
        href = source["url"] if safe_url(source["url"]) else "#"
        material = "原始摘要" if source.get("summary_author") in {"arxiv_original_abstract", "user_provided_abstract"} else "摘要转述或阅读笔记"
        if source.get("summary_author") == "assistant_curated_abstract":
            material = "助手整理的入门摘要转述（不代表用户已阅读或人工核验）"
        evidence = source.get("evidence")
        if evidence:
            material = "PDF 提取片段（未核对版面与含义，不代表已读全文）"
        body += (f"<article class='card source-card' id='{prefix}{ids[source['id']]}'><div class='source-top'>"
                 f"<span class='source-number'>来源 {ids[source['id']]:02d}</span><span class='badge badge-neutral'>{material}</span></div>"
                 f"<h3 class='source-title'><a rel='noreferrer noopener' href='{e(href)}'>{e(source['title'])}</a></h3><pre class='source-text'>{e(source['summary'])}</pre>"
                 f"<p class='source-meta'>来源定位：{e(source['locator'])}<span>材料 ID：{e(source['id'])}</span></p>")
        if evidence:
            identity = evidence["document_sha256"]
            body += (f"<p class='source-meta'>文件 SHA-256：<code>{e(identity)}</code>"
                     f"<span>提取器：{e(evidence['extractor'])} · 页内字符 {e(evidence['start'])}–{e(evidence['end'])}（从 0 开始，右端不含）</span>"
                     "<span>论文链接由用户提供，未自动核实与文件对应。</span></p>")
            if evidence_base:
                body += f"<a class='download-evidence' href='{e(evidence_base + identity + '.pdf')}' download>下载此次分析保存的原 PDF</a>"
        body += "</article>"
    body += "</section><footer class='report-footer'>研究选题工作台 · 从提供的证据出发，把候选问题推进到可验证的下一步。</footer></article>"
    return body


def render_report(case, report, label="选题分析", evidence_base=None):
    return document(label, report_body(case, report, label, evidence_base))
