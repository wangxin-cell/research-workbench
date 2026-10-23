"use strict";
const $ = (id) => document.getElementById(id);
const state = { sources: [], receipts: [], examples: [], id: "", prepared: null, busy: false, configured: false };
const fields = ["question", "skills", "weeks", "ram", "gpu", "data", "budget", "api-budget", "target-model", "notes"];
const friendly = { prepared: "待导入回答", imported: "已导入", completed: "已完成", failed: "运行失败", running: "正在运行" };
const pdfState = { document: null, loading: false };

function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
  $("notice").hidden = !message;
}
function dialogError(id, message = "") {
  if (message && !$(id).closest("dialog").open) { notice(message, true); return; }
  $(id).textContent = message;
  $(id).hidden = !message;
  if (message) $(id).scrollIntoView({ block: "nearest" });
}
function selectView(view) {
  for (const [id, selected] of [["nav-work", view === "work"], ["show-demo", view === "demo"]]) {
    $(id).classList.toggle("active", selected);
    if (selected) $(id).setAttribute("aria-current", "page");
    else $(id).removeAttribute("aria-current");
  }
}
function node(tag, content, className) {
  const result = document.createElement(tag);
  if (content !== undefined) result.textContent = content;
  if (className) result.className = className;
  return result;
}
function link(title, url) {
  const result = node("a", title);
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) throw Error();
    result.href = parsed.href;
  } catch { result.removeAttribute("href"); }
  result.target = "_blank";
  result.rel = "noreferrer noopener";
  return result;
}
async function api(path, body) {
  const options = { signal: AbortSignal.timeout(35000) };
  if (body !== undefined) {
    options.method = "POST";
    options.headers = { "Content-Type": "application/json", "X-Workbench-Request": "local-ui" };
    options.body = JSON.stringify(body);
  }
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error("无法连接本地服务或请求超时。请确认工作台仍在运行；模型分析不会因此自动重试。"); }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "操作未完成");
  return data;
}
function dirty() {
  state.prepared = null;
  $("prepared-actions").hidden = true;
}
function setBusy(busy) {
  state.busy = busy;
  $("analyze").disabled = busy || !state.configured;
  $("prepare").disabled = busy;
  $("analyze").textContent = busy ? "正在分析…" : "生成选题分析 →";
}
function collectCase(requireSources = true) {
  if (!$("question").value.trim()) throw new Error("请先描述研究方向或已有想法。");
  if (requireSources && !state.sources.length) throw new Error("请至少添加一条摘要、阅读笔记或 PDF 证据片段。");
  const resources = {};
  for (const [field, key] of [["gpu", "gpu"], ["data", "data"], ["budget", "cloud_budget"], ["target-model", "target_model"], ["notes", "notes"]]) {
    if ($(field).value.trim()) resources[key] = $(field).value.trim();
  }
  for (const [field, key] of [["weeks", "time_weeks"], ["ram", "ram_gib"], ["api-budget", "api_budget_cny"]]) {
    if ($(field).value !== "") {
      const value = Number($(field).value);
      if (!Number.isFinite(value) || value < 0 || (field !== "api-budget" && value === 0)) throw new Error("时间、内存与预算应填写有效数值。");
      resources[key] = value;
    }
  }
  if ($("skills").value.trim()) resources.skills = $("skills").value.split(/[,，、]/).map(x => x.trim()).filter(Boolean);
  if (!state.id) state.id = "project-" + Date.now();
  return { id: state.id, user_question: $("question").value.trim(), resources, sources: structuredClone(state.sources) };
}
function fillCase(value) {
  if (!value || typeof value.user_question !== "string" || !Array.isArray(value.sources) || !value.resources) throw new Error("项目应包含 user_question、resources 和 sources。");
  if (value.sources.length > 50) throw new Error("一个项目最多包含 50 条材料。");
  for (const source of value.sources) {
    if (!["id", "title", "url", "summary", "locator", "read_scope"].every(key => typeof source[key] === "string" && source[key].trim())) throw new Error("论文材料缺少来源、摘要或阅读范围。");
  }
  for (const field of fields) $(field).value = "";
  $("question").value = value.user_question;
  const r = value.resources;
  for (const [field, key] of [["weeks", "time_weeks"], ["ram", "ram_gib"], ["gpu", "gpu"], ["data", "data"], ["budget", "cloud_budget"], ["api-budget", "api_budget_cny"], ["target-model", "target_model"], ["notes", "notes"]]) $(field).value = r[key] ?? "";
  $("skills").value = Array.isArray(r.skills) ? r.skills.join("，") : "";
  state.sources = structuredClone(value.sources);
  state.id = value.id || "project-" + Date.now();
  state.receipts = [];
  $("search-results").replaceChildren();
  dirty(); renderSources(); showWork();
}
function showWork() {
  $("workspace").hidden = false; $("result-view").hidden = true;
  $("view-label").textContent = "研究材料";
  selectView("work");
  window.scrollTo(0, 0);
}
function showReport(runId = null) {
  $("workspace").hidden = true; $("result-view").hidden = false;
  $("view-label").textContent = runId ? "选题分析" : "报告示例";
  selectView(runId ? "report" : "demo");
  const url = runId ? "/reports/" + encodeURIComponent(runId) : "/demo";
  $("report-frame").src = url; $("open-report").href = url;
  $("result-label").textContent = runId ? "结论仍需核查原文与研究者判断" : "人工编写的展示案例，不代表模型效果";
  $("download-report").hidden = !runId;
  if (runId) $("download-report").href = "/files/" + runId + "/report.json";
  window.scrollTo(0, 0);
}
function renderSources() {
  for (const button of document.querySelectorAll(".search-result button")) {
    const added = state.sources.some(s => s.id === button.dataset.sourceId || (s.url === button.dataset.sourceUrl && s.read_scope !== "pdf_excerpt"));
    button.disabled = added; button.textContent = added ? "已添加" : "＋ 添加";
  }
  $("source-count").textContent = state.sources.length + " 条材料";
  const host = $("sources"); host.replaceChildren();
  if (!state.sources.length) {
    const empty = node("div", undefined, "empty");
    const symbol = node("span", undefined, "empty-symbol");
    symbol.setAttribute("aria-hidden", "true");
    symbol.append($("add-pdf").querySelector("svg").cloneNode(true));
    empty.append(symbol, node("strong", "把读过的论文，放到一起。"), node("p", "从 3—5 篇关键论文开始，逐步勾勒研究边界。"));
    host.append(empty); return;
  }
  state.sources.forEach((source, index) => {
    const card = node("article", undefined, "source-card");
    const content = node("div", undefined, "source-content");
    const details = node("details"); details.append(node("summary", "查看材料内容"), node("p", source.summary, "abstract"));
    const actions = node("div", undefined, "source-actions");
    const remove = node("button", "移除"); remove.type = "button";
    remove.setAttribute("aria-label", "移除材料：" + source.title);
    remove.addEventListener("click", () => { state.sources.splice(index, 1); dirty(); renderSources(); });
    const original = source.summary_author === "arxiv_original_abstract" || source.summary_author === "user_provided_abstract";
    const isExcerpt = source.read_scope === "pdf_excerpt";
    content.append(node("h3", source.title), node("p", (isExcerpt ? "PDF 提取片段" : original ? "原始摘要" : "摘要转述 / 阅读笔记") + " · " + source.locator), details);
    if (isExcerpt) details.append(node("p", "文件 SHA-256：" + source.evidence?.document_sha256 + " · 选取片段不代表已阅读全文", "help fingerprint"));
    actions.append(link("打开来源 ↗", source.url), remove); content.append(actions);
    card.append(node("span", String(index + 1).padStart(2, "0"), "source-index"), content); host.append(card);
  });
}
async function history() {
  const records = await api("/api/history");
  $("history").replaceChildren();
  if (!records.length) { $("history").append(node("p", "完成一次探索后，记录会显示在这里。", "small")); return; }
  for (const item of records) {
    const button = node("button", item.case_id || "未命名研究");
    button.append(node("small", (friendly[item.status] || item.status) + " · " + new Date(item.created_at).toLocaleDateString("zh-CN")));
    button.addEventListener("click", async () => {
      try {
        if (state.busy) throw new Error("请等待当前分析完成。");
        const saved = await api("/api/runs/" + item.run_id);
        fillCase(saved.input);
        if (["completed", "imported"].includes(saved.manifest.status)) showReport(item.run_id);
        else if (saved.manifest.status === "prepared") setPrepared(item.run_id);
        else notice("已载入该次研究材料。运行状态：" + (friendly[saved.manifest.status] || saved.manifest.status), true);
      } catch (error) { notice(error.message, true); }
    });
    $("history").append(button);
  }
}
function setPrepared(runId) {
  state.prepared = runId;
  $("download-prompt").href = "/files/" + runId + "/prompt.txt";
  $("prepared-actions").hidden = false;
}
$("search-form").addEventListener("submit", async event => {
  event.preventDefault();
  $("search-button").disabled = true; $("search-button").textContent = "检索中…";
  $("search-results").replaceChildren();
  try {
    const result = await api("/api/search", { query: $("search-query").value.trim() });
    const host = $("search-results");
    host.append(node("h3", "本次返回 " + result.results.length + " 篇 · arXiv 摘要检索" + (result.cache_hit ? " · 使用近期缓存" : "")));
    if (!result.results.length) host.append(node("p", "没有返回匹配论文。尝试更短的英文关键词，或手动添加材料。", "help"));
    for (const paper of result.results) {
      const row = node("article", undefined, "search-result"), content = node("div");
      content.append(link(paper.source.title, paper.source.url), node("p", paper.authors.slice(0, 3).join(", ") + " · " + paper.published.slice(0, 4)));
      const details = node("details"); details.append(node("summary", "查看摘要"), node("p", paper.source.summary, "result-abstract")); content.append(details);
      const add = node("button", "＋ 添加"); add.type = "button";
      add.dataset.sourceId = paper.source.id; add.dataset.sourceUrl = paper.source.url;
      add.disabled = state.sources.some(s => s.id === paper.source.id || (s.url === paper.source.url && s.read_scope !== "pdf_excerpt"));
      if (add.disabled) add.textContent = "已添加";
      add.addEventListener("click", () => {
        if (state.sources.some(s => s.id === paper.source.id || (s.url === paper.source.url && s.read_scope !== "pdf_excerpt"))) { notice("这篇论文的摘要已经在材料中。"); return; }
        if (state.sources.length >= 50) { notice("一个项目最多包含 50 条材料。", true); return; }
        state.sources.push(structuredClone(paper.source));
        if (!state.receipts.includes(result.receipt_id)) state.receipts.push(result.receipt_id);
        dirty(); renderSources(); add.disabled = true; add.textContent = "已添加";
      });
      row.append(content, add); host.append(row);
    }
    notice("");
  } catch (error) { notice(error.message, true); }
  finally { $("search-button").disabled = false; $("search-button").textContent = "检索文献"; }
});
$("add-manual").addEventListener("click", () => { dialogError("paper-error"); $("paper-dialog").showModal(); });
$("close-paper").addEventListener("click", () => $("paper-dialog").close());
$("paper-form").addEventListener("submit", event => {
  event.preventDefault();
  try {
    const url = new URL($("paper-url").value);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) throw new Error("请提供不含凭据的 HTTP 或 HTTPS 来源链接。");
    if (state.sources.length >= 50) throw new Error("一个项目最多包含 50 条材料。");
    if (state.sources.some(s => s.url === url.href && s.read_scope !== "pdf_excerpt")) throw new Error("这个来源链接已经在材料中。");
    const abstract = $("paper-scope").value === "abstract";
    state.sources.push({ id: "paper-" + crypto.randomUUID(), title: $("paper-title").value.trim(), url: url.href,
      summary: $("paper-text").value.trim(), locator: $("paper-locator").value.trim(), read_scope: abstract ? "abstract" : "user_notes",
      summary_author: abstract ? "user_provided_abstract" : "user_notes", human_verified: false,
      checked_on: new Date().toISOString().slice(0, 10), fulltext_snapshot_sha256: null });
    dirty(); renderSources(); $("paper-dialog").close(); $("paper-form").reset(); notice("论文材料已添加。");
  } catch (error) { dialogError("paper-error", error.message); }
});
function pdfSelection() {
  const area = $("pdf-page-text");
  const start = Array.from(area.value.slice(0, area.selectionStart)).length;
  const end = Array.from(area.value.slice(0, area.selectionEnd)).length;
  const count = end - start;
  $("pdf-selection").textContent = count ? `已选 ${count} 字` : "在下方选中需要引用的文字";
  $("add-excerpt").disabled = pdfState.loading || !count || count > 30000;
  return { start, end };
}
function showPdfPage() {
  const page = pdfState.document?.pages[Number($("pdf-page").value) - 1];
  $("pdf-page-text").value = page?.text || "";
  $("pdf-page-text").setSelectionRange(0, 0);
  pdfSelection();
}
$("add-pdf").addEventListener("click", () => $("pdf-dialog").showModal());
$("close-pdf").addEventListener("click", () => $("pdf-dialog").close());
$("pdf-page").addEventListener("change", showPdfPage);
for (const event of ["select", "keyup", "mouseup"]) $("pdf-page-text").addEventListener(event, pdfSelection);
$("pdf-file").addEventListener("change", async event => {
  const file = event.target.files[0]; if (!file) return;
  pdfState.document = null; pdfState.loading = true;
  $("excerpt-form").hidden = true; $("pdf-file").disabled = true;
  $("pdf-status").textContent = "正在本机提取页面文字…";
  try {
    if (file.size > 8000000) throw new Error("PDF 文件不能超过 8 MB。");
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("无法读取这个文件。"));
      reader.readAsDataURL(file);
    });
    const result = await api("/api/pdf", { data: dataUrl.split(",")[1] });
    pdfState.document = result;
    $("pdf-title").value = file.name.replace(/\.pdf$/i, "");
    $("pdf-url").value = "";
    $("pdf-page").replaceChildren();
    for (const page of result.pages) {
      const option = node("option", `第 ${page.page} / ${result.page_count} 页${page.text.trim() ? "" : " · 无可提取文字"}`);
      option.value = page.page; $("pdf-page").append(option);
    }
    $("pdf-status").textContent = `已提取 ${result.page_count} 页。可选择多个片段，逐条添加。`;
    $("excerpt-form").hidden = false;
    showPdfPage();
  } catch (error) { $("pdf-status").textContent = error.message; }
  finally { pdfState.loading = false; $("pdf-file").disabled = false; event.target.value = ""; pdfSelection(); }
});
$("excerpt-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    if (!pdfState.document || pdfState.loading) return;
    if (state.sources.length >= 50) throw new Error("一个项目最多包含 50 条材料。");
    const range = pdfSelection();
    if (range.end <= range.start) throw new Error("请在页面文字中选中一段内容。");
    pdfState.loading = true; $("add-excerpt").disabled = true;
    const source = await api("/api/excerpt", {
      document_sha256: pdfState.document.document_sha256,
      page: Number($("pdf-page").value), ...range,
      title: $("pdf-title").value.trim(), url: $("pdf-url").value.trim()
    });
    if (state.sources.some(s => s.id === source.id)) throw new Error("这一片段已经在材料中。");
    state.sources.push(source); dirty(); renderSources();
    $("pdf-status").textContent = "片段已添加。可以继续选择，或关闭此窗口返回研究材料。";
  } catch (error) { $("pdf-status").textContent = error.message; }
  finally { pdfState.loading = false; pdfSelection(); }
});
$("prepare").addEventListener("click", async () => {
  try {
    $("prepare").disabled = true;
    const payload = { case: collectCase(), receipt_ids: [...state.receipts] };
    const result = await api("/api/prepare", payload);
    let unchanged = false;
    try { unchanged = JSON.stringify(payload.case) === JSON.stringify(collectCase(false)); } catch {}
    if (!unchanged) { await history(); notice("提示已保存到最近记录，但当前材料已有变化。请为当前材料重新导出。"); return; }
    setPrepared(result.run_id); await history();
    notice("已保存材料快照。下载提示后，可在你使用的模型中生成回答，再导入此处。");
  } catch (error) { notice(error.message, true); }
  finally { $("prepare").disabled = state.busy; }
});
$("import-answer").addEventListener("click", () => { dialogError("answer-error"); $("answer-dialog").showModal(); });
$("close-answer").addEventListener("click", () => $("answer-dialog").close());
$("answer-form").addEventListener("submit", async event => {
  event.preventDefault();
  const submit = $("answer-form").querySelector("button[type=submit]"); submit.disabled = true;
  try {
    if (!state.prepared) throw new Error("材料已变化，请重新导出分析提示。");
    const result = await api("/api/import", { run_id: state.prepared, report: JSON.parse($("answer-text").value), model_label: $("answer-model").value.trim() });
    $("answer-dialog").close(); $("answer-form").reset(); state.prepared = null;
    $("prepared-actions").hidden = true; showReport(result.run_id); await history(); notice("回答已导入。引用 ID 已检查，论断是否成立仍需核查原文。");
  } catch (error) { dialogError("answer-error", error instanceof SyntaxError ? "回答不是有效 JSON，请粘贴完整对象，不要包含代码围栏。" : error.message); }
  finally { submit.disabled = false; }
});
$("analyze").addEventListener("click", async () => {
  let accepted = false;
  try {
    const payload = { case: collectCase(), receipt_ids: [...state.receipts], model: $("model").value.trim(), workflow: $("workflow").value };
    if (!payload.model) throw new Error("请填写已开通的分析模型名称。");
    setBusy(true); notice("正在提交材料并生成分析。可以留在此页等待；不会自动重试付费调用。");
    const job = await api("/api/run", payload); accepted = true;
    for (;;) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const status = await api("/api/jobs/" + job.job_id);
      if (status.status === "completed") { showReport(status.run_id); await history(); notice("分析已完成。请先检查候选与已有工作的差异及来源依据。"); break; }
      if (status.status === "failed") { await history(); throw new Error(status.error); }
    }
  } catch (error) { notice(error.message + (accepted ? " 如果连接中断，可从最近记录确认运行状态，避免重复提交。" : ""), true); }
  finally { setBusy(false); }
});
$("save-project").addEventListener("click", () => {
  try {
    const blob = new Blob([JSON.stringify(collectCase(false), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url; a.download = "research-project.json"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    notice("项目已导出，包含问题和材料文字。PDF 原件保留在本机；换一台电脑时，需另行导入同一份 PDF。");
  } catch (error) { notice(error.message, true); }
});
$("load-project").addEventListener("click", () => $("project-file").click());
$("project-file").addEventListener("change", async event => {
  try {
    const file = event.target.files[0]; if (!file) return;
    if (file.size > 1_000_000) throw new Error("项目文件不能超过 1 MB。");
    fillCase(JSON.parse(await file.text())); notice("项目已载入；原有运行记录仍保存在本机。");
  } catch (error) { notice(error.message, true); }
  event.target.value = "";
});
$("example-picker").addEventListener("change", event => {
  const chosen = state.examples.find(c => c.id === event.target.value);
  if (chosen) { fillCase(chosen); notice("已载入文献构造的探索案例。它用于校准与演示，不是真实用户效果证据。"); }
});
for (const field of fields) $(field).addEventListener("input", dirty);
$("show-demo").addEventListener("click", () => { showReport(); notice(""); });
$("back-to-work").addEventListener("click", showWork);
$("nav-work").addEventListener("click", showWork);
$("refresh-history").addEventListener("click", () => history().catch(error => notice(error.message, true)));
async function init() {
  try {
    const [config, examples] = await Promise.all([api("/api/config"), api("/api/examples")]);
    state.configured = config.api_key_configured; $("model").value = config.default_model; setBusy(false);
    $("analysis-mode").textContent = state.configured ? "模型密钥已配置" : "可使用自己的模型";
    $("model-settings-panel").open = state.configured;
    $("analyze").classList.toggle("primary", state.configured);
    $("analyze").classList.toggle("secondary", !state.configured);
    $("prepare").classList.toggle("primary", !state.configured);
    $("prepare").classList.toggle("secondary", state.configured);
    $("add-pdf").disabled = !config.pdf_available;
    if (!config.pdf_available) $("pdf-help").textContent = 'PDF 功能尚未安装。请在项目目录执行 python -m pip install ".[pdf]"，然后重启工作台。摘要和笔记仍可使用。';
    $("connection").textContent = state.configured ? "本机已配置模型密钥。点击生成会将当前材料发送到 OpenAI 并产生 API 费用。" : "无需在这里配置密钥：导出提示，在你使用的模型中分析，再导入回答。直接生成需在启动服务前设置 OPENAI_API_KEY。";
    state.examples = examples.cases;
    const names = { "EXP-A-GRAPH": "图学习 · 从论文收敛问题", "EXP-B-VISION": "视觉 · 检查想法是否重复", "EXP-C-GRAPH": "大图 · 检查资源是否可行", "EXP-D-NLP": "检索 · 理解不同研究结论" };
    for (const c of state.examples) { const option = node("option", names[c.id] || c.id); option.value = c.id; $("example-picker").append(option); }
    await history();
  } catch (error) { setBusy(false); notice(error.message, true); }
}
// Keep research history reachable on phones without filling the first screen.
if (window.matchMedia("(max-width: 760px)").matches) document.querySelector(".history-section").open = false;
init();
