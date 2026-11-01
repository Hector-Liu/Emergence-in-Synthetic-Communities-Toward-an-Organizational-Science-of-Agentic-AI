"use strict";
// Fake Moltbook web page. Plain JS, no build step. Talks to /api (fakemolt/api.py).
// Every visible string goes through t() (web/i18n.js); Chinese is the source language.

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt$ = (x) => (x == null ? "–" : "$" + (x > 0 && x < 0.01 ? x.toFixed(4) : x.toFixed(2)));
const pct = (x, d = 1) => (x == null ? "–" : (100 * x).toFixed(d) + "%");
const num = (x, d = 3) => (x == null ? "–" : Number(x).toFixed(d));
const icon = (id, cls = "icon") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`;
const debounce = (fn, ms) => { let tm; return (...a) => { clearTimeout(tm); tm = setTimeout(() => fn(...a), ms); }; };
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } } };

// The page can outlive its server (window closed, Mac asleep, app quit): say so instead of failing silently.
function serverDown(down) {
  const el = $("#offline"); if (!el) return;
  el.hidden = !down;
  clearTimeout(serverDown._h);
  if (down) serverDown._h = setTimeout(async () => { try { await fetch("/api/health", { cache: "no-store" }); location.reload(); } catch (e) { serverDown(true); } }, 5000);
}
async function api(path, opts = {}) {
  let r;
  try { r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined }); }
  catch (e) { serverDown(true); throw new Error(t("连不上服务器")); }
  serverDown(false);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) { const d = typeof data === "object" ? data.detail ?? data : data; const e = new Error(typeof d === "string" ? d : JSON.stringify(d)); e.status = r.status; throw e; }
  return data;
}
function toast(msg) { const el = $("#toast"); el.textContent = msg; el.classList.add("on"); clearTimeout(el._h); el._h = setTimeout(() => el.classList.remove("on"), 3800); }
async function busy(btn, fn) { if (!btn) return fn(); btn.setAttribute("aria-busy", "true"); try { return await fn(); } finally { btn.removeAttribute("aria-busy"); } }
function confirmDialog(title, html, yes) {
  return new Promise((resolve) => {
    const d = $("#confirmDlg"); $("#cd-title").textContent = title; $("#cd-body").innerHTML = html; $("#cd-yes").textContent = yes || t("确认运行");
    $("#cd-no").textContent = t("取消");
    const done = (v) => { d.close(); resolve(v); };
    $("#cd-yes").onclick = () => done(true); $("#cd-no").onclick = () => done(false); d.oncancel = () => resolve(false);
    d.showModal();
  });
}

const S = { meta: null, cfg: null, runs: [], current: store.get("fm-current") || "", es: null, page: "design", forumPage: 1 };
const STATUS = { done: ["good", "完成"], running: ["info", "运行中"], cancelled: ["warn", "已停止"], budget: ["warn", "预算停"],
  stopped: ["bad", "规则停"], interrupted: ["warn", "中断"], error: ["bad", "出错"], guard: ["bad", "词检拦截"], created: ["info", "准备中"] };
const statusPill = (m) => { const [c, l] = m.running ? STATUS.running : (STATUS[m.status] || ["", m.status]); return `<span class="pill ${c}">${esc(t(l))}</span>`; };
const cohortTag = (c) => (c ? `<span class="tag ${c}">${c === "founder" ? t("创始") : t("新成员")}</span>` : "");
const isMock = (models) => (models || []).length > 0 && models.every((x) => x.startsWith("mock"));
const runKind = (m) => t(m.mode === "smoke" ? "冒烟" : m.solo ? "先验独白" : isMock(m.models) ? "模拟" : "正式");

// ================================================================ theme and language
function setTheme(th) {
  store.set("fm-theme", th);
  const dark = th === "dark" || (th === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $$("[data-theme-set]").forEach((b) => b.classList.toggle("on", b.dataset.themeSet === th));
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => (store.get("fm-theme") || "system") === "system" && setTheme("system"));
function setLang(l) {
  I18N.setLang(l);
  $$("[data-lang-set]").forEach((b) => b.classList.toggle("on", b.dataset.langSet === l));
  if (S.cfg) { summaries(); renderPhases(); renderComms(); refreshPrior(); estimateSoon(); renderRunCard(); }
  if (S.meta) keyState();
  route();
}

// ================================================================ routing
const PAGES = {
  design: ["设计", "设定流程、Agent 和提示词,然后按步骤开始"],
  monitor: ["运行", "当前运行的实时进度"],
  forum: ["论坛", "像读论坛一样读这次运行;点编码看它的主页,以及它每一次访问时看到的论坛"],
  results: ["结果", "主要分析与描述性指标(由程序计算,不用模型打分)"],
  runs: ["记录", "所有运行;点一行设为当前运行"],
  models: ["模型与密钥", "API 密钥和价格"],
};
function route() { const [page, ...rest] = location.hash.slice(1).split("/"); show(page || "design", rest); }
function show(page, rest = []) {
  if (!PAGES[page]) page = "design";
  S.page = page;
  closeDrawer();
  $$("section.page").forEach((s) => s.classList.toggle("on", s.id === "page-" + page));
  $$(".nav-group a").forEach((a) => { a.classList.toggle("on", a.dataset.page === page); a.toggleAttribute("aria-current", a.dataset.page === page); });
  $("#pageTitle").textContent = t(PAGES[page][0]); $("#pageSub").textContent = t(PAGES[page][1]); $("#pageActions").innerHTML = "";
  document.title = t(PAGES[page][0]) + " · Fake Moltbook";
  ({ design: () => { refreshPrior(); renderSteps(); }, monitor: loadMonitor, forum: () => loadForum(rest), results: loadResults, runs: loadRuns, models: loadModels }[page])();
}
window.addEventListener("hashchange", route);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

// ================================================================ current run (sidebar)
async function refreshRuns() {
  S.runs = await api("/api/runs");
  if (!S.runs.some((m) => m.run_id === S.current)) S.current = S.runs[0]?.run_id || "";
  const sel = $("#runPick");
  sel.innerHTML = S.runs.length ? S.runs.map((m) => `<option value="${esc(m.run_id)}">${esc(m.run_id)}</option>`).join("") : `<option value="">${t("(还没有运行)")}</option>`;
  sel.value = S.current;
  renderRunCard();
  return S.runs;
}
function currentManifest() { return S.runs.find((m) => m.run_id === S.current); }
function setCurrent(id) { S.current = id; store.set("fm-current", id); $("#runPick").value = id; renderRunCard(); followCurrent(); }
function renderRunCard() {
  const m = currentManifest();
  if (!m) { $("#runCardBody").innerHTML = `<span class="muted">${t("还没有运行")}</span>`; return; }
  const frac = m.total_rounds ? m.rounds_done / m.total_rounds : 0;
  $("#runCardBody").innerHTML = `<div class="row between">${statusPill(m)}<span class="xs muted">${runKind(m)}</span></div>
    <div class="bar" style="margin-top:8px"><i style="width:${(100 * frac).toFixed(1)}%"></i></div>
    <div class="stats"><span>${t("第 {a}/{b} 轮", { a: m.rounds_done, b: m.total_rounds })}</span><span>${fmt$(m.cost)}</span></div>`;
}
function followCurrent() {
  if (S.es) { S.es.close(); S.es = null; }
  const m = currentManifest();
  if (!m || !m.running) return;
  S.es = new EventSource(`/api/runs/${m.run_id}/events`);
  S.es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "round") {
      Object.assign(m, e.manifest, { running: true }); renderRunCard();
      if (S.page === "monitor" && S.mon && S.mon.manifest.run_id === m.run_id) { S.mon.rounds.push(e.summary); S.mon.manifest = m; renderMonitor(); }
      if (S.page === "forum") forumLive();
    }
    if (e.type === "frozen") toast(t("阶段 1 结束:冻结了 {n} 个创始说法", { n: e.expressions }));
    if (e.type === "run_end") { S.es.close(); S.es = null; toast(t("运行结束:{s}", { s: t(STATUS[e.status]?.[1] || e.status) })); refreshRuns().then(() => (S.page === "design" ? renderSteps() : route())); }
  };
}

// ================================================================ design
const DRAFT = "fm-draft-v2";
function saveDraft() { store.set(DRAFT, JSON.stringify(S.cfg)); }
function bindNumber(id, get, set) { const el = $(id); el.value = get(); el.oninput = () => { set(el.value === "" ? 0 : Number(el.value)); changed(); }; }
function fillDesign() {
  const c = S.cfg, sw = c.switches;
  $("#d-name").value = c.name; $("#d-name").oninput = (e) => { c.name = e.target.value; changed(); };
  bindNumber("#d-seed", () => c.seed, (v) => (c.seed = v));
  bindNumber("#d-budget", () => c.budget_usd, (v) => (c.budget_usd = v));
  $("#d-tellai").checked = sw.tell_ai; $("#d-tellai").onchange = (e) => { sw.tell_ai = e.target.checked; changed(); };
  $("#d-memory").checked = sw.memory === "on"; $("#d-memory").onchange = (e) => { sw.memory = e.target.checked ? "on" : "off"; changed(); };
  $("#d-solo").checked = sw.solo; $("#d-solo").onchange = (e) => { sw.solo = e.target.checked; changed(); };
  $("#d-goal").value = sw.goal; $("#d-goal").onchange = (e) => { sw.goal = e.target.value; changed(); };
  $("#d-effort").value = c.llm.effort; $("#d-effort").onchange = (e) => { c.llm.effort = e.target.value; changed(); };
  $("#d-prior").onchange = (e) => { c.prior_run = [...e.target.selectedOptions].map((o) => o.value).filter(Boolean).join(","); changed(); };
  const dc = S.meta.default_config;
  for (const k of ["boards", "memory", "schedule", "order", "visit", "switches"]) {  // fill missing keys in place
    c[k] = c[k] || {};
    for (const [kk, vv] of Object.entries(dc[k])) if (!(kk in c[k])) c[k][kk] = vv;
  }
  const bindSel = (id, get, set) => { const el = $(id); el.value = get(); el.onchange = () => { set(el.value); changed(); }; };
  const bindChk = (id, get, set) => { const el = $(id); el.checked = !!get(); el.onchange = () => { set(el.checked); changed(); }; };
  bindSel("#s-mode", () => c.schedule.mode, (v) => (c.schedule.mode = v));
  bindNumber("#s-period", () => c.schedule.period, (v) => (c.schedule.period = Math.max(1, Math.round(v || 1))));
  bindNumber("#s-jitter", () => c.schedule.jitter, (v) => (c.schedule.jitter = Math.max(0, Math.round(v || 0))));
  bindNumber("#s-return", () => c.schedule.return_on_reply, (v) => (c.schedule.return_on_reply = Math.min(1, Math.max(0, v || 0))));
  bindSel("#o-mode", () => c.order.mode, (v) => (c.order.mode = v));
  bindNumber("#o-overlap", () => c.order.overlap, (v) => (c.order.overlap = Math.max(1, Math.round(v || 1))));
  bindSel("#b-order", () => c.boards.order, (v) => (c.boards.order = v));
  bindSel("#v-nav_effort", () => c.visit.nav_effort, (v) => (c.visit.nav_effort = v));
  bindChk("#v-two_step", () => c.visit.two_step, (v) => (c.visit.two_step = v));
  bindChk("#d-updates", () => c.switches.updates, (v) => (c.switches.updates = v));
  bindChk("#d-posthint", () => c.switches.post_hint, (v) => { c.switches.post_hint = v; if ($("#previewOut").innerHTML) $("#previewBtn").click(); });
  bindChk("#m-own_posts_sw", () => c.memory.own_posts, (v) => (c.memory.own_posts = v));
  $("#d-boards").checked = c.boards.on !== false; $("#d-boards").onchange = (e) => { c.boards.on = e.target.checked; changed(); };
  bindNumber("#b-per_agent", () => c.boards.per_agent, (v) => (c.boards.per_agent = v));
  $("#d-ownposts").checked = c.feed.own_posts !== false; $("#d-ownposts").onchange = (e) => { c.feed.own_posts = e.target.checked; changed(); };
  for (const k of Object.keys(c.feed)) if ($("#f-" + k)) bindNumber("#f-" + k, () => c.feed[k], (v) => (c.feed[k] = v));
  for (const k of Object.keys(c.memory)) if (typeof c.memory[k] === "number" && $("#m-" + k)) bindNumber("#m-" + k, () => c.memory[k], (v) => (c.memory[k] = v));
  bindNumber("#l-concurrency", () => c.llm.concurrency, (v) => (c.llm.concurrency = v));
  bindNumber("#d-opening", () => c.opening ?? -1, (v) => (c.opening = Math.max(-1, Math.round(v || 0))));
  bindNumber("#d-activation", () => c.activation ?? 1, (v) => (c.activation = Math.min(1, Math.max(0.05, v || 1))));
  for (const k of ["system", "visit"]) {
    const ta = $("#p-" + k);
    ta.value = c.prompts[k] === "default" ? S.meta.default_prompts[k] : c.prompts[k];
    ta.oninput = () => { c.prompts[k] = ta.value === S.meta.default_prompts[k] ? "default" : ta.value; changed(); };
  }
  renderPhases(); renderComms(); refreshPrior(); summaries(); bindPresets(); placeholderCheck();
}
const modelOptions = (sel) => S.meta.models.map((m) => `<option ${m === sel ? "selected" : ""}>${esc(m)}</option>`).join("");
// presets from the pilots: only visit mechanics and switches change; phases, models and budget stay
const PRESETS = {
  main: { note: "推荐设置:每 2 轮回访一次、一轮之内依次行动、全部创始者第 1 轮同时来访、两步访问、版块随机排序、可以更新自己的帖子、提示词里加入「可以开新帖」。",
    apply: (c) => { Object.assign(c.schedule, { mode: "heartbeat", period: 2, jitter: 1, return_on_reply: 0 }); Object.assign(c.order, { mode: "sequential", overlap: 1, opening_together: true });
      Object.assign(c.visit, { two_step: true }); Object.assign(c.boards, { on: true, order: "random", note: true }); Object.assign(c.switches, { updates: true, post_hint: true }); c.opening = -1; } },
  nocue: { note: "对照条件:与正式条件相同,只是不加「可以开新帖」那句话。",
    apply: (c) => { PRESETS.main.apply(c); c.switches.post_hint = false; } },
  v03: { note: "对照条件:回到 v0.3 的机制(每轮抛硬币、同一轮同时行动、一步访问、无更新、无提示)。",
    apply: (c) => { Object.assign(c.schedule, { mode: "coin" }); Object.assign(c.order, { mode: "simultaneous" }); Object.assign(c.visit, { two_step: false });
      Object.assign(c.boards, { order: "activity" }); Object.assign(c.switches, { updates: false, post_hint: false }); c.opening = 4; } },
};
// which template the current settings match (only the fields the templates set)
function presetMatch() {
  const keyOf = (c) => JSON.stringify([c.schedule.mode, c.schedule.mode === "heartbeat" ? [c.schedule.period, c.schedule.jitter] : 0, c.order.mode,
    c.order.mode === "sequential" ? c.order.overlap : 0, c.visit.two_step, c.boards.order, c.switches.updates, c.switches.post_hint, c.opening]);
  const now = keyOf(S.cfg);
  return Object.keys(PRESETS).find((k) => { const c = JSON.parse(JSON.stringify(S.cfg)); PRESETS[k].apply(c); return keyOf(c) === now; });
}
function bindPresets() {
  const hit = presetMatch();
  $$("[data-preset]").forEach((b) => {
    b.classList.toggle("primary", b.dataset.preset === hit);
    b.setAttribute("aria-pressed", String(b.dataset.preset === hit));
    b.onclick = () => { const p = PRESETS[b.dataset.preset]; p.apply(S.cfg); fillDesign(); changed(); toast(t("已套用设置模板")); };
  });
  $("#presetNote").textContent = hit ? t("当前设置 = ") + t(PRESETS[hit].note) : t("当前设置不完全等于任何模板(手动改过)。");
}

// an edited template must still carry the placeholders the switches fill, or their sentences silently vanish
function placeholderCheck() {
  const c = S.cfg, box = $("#phWarn"); if (!box || !c) return;
  const sys = c.prompts.system === "default" ? S.meta.default_prompts.system : c.prompts.system;
  const vis = c.prompts.visit === "default" ? S.meta.default_prompts.visit : c.prompts.visit;
  const need = [["{update_option}", sys, c.switches.updates, "可以更新自己的帖子"], ["{boards_note}", sys, c.boards.on, "版块是什么"],
    ["{post_hint}", vis, c.switches.post_hint, "可以开新帖"], ["{update_rule}", vis, c.switches.updates, "更新的规则"],
    ["{opened}", vis, c.visit.two_step, "打开了哪个版块"]].filter(([ph, txt, on]) => on && !txt.includes(ph));
  if (!need.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="note warn" style="margin-top:10px">${t("你改过的提示词缺少这些占位符,对应开关的句子不会出现在提示词里:")}
    ${need.map(([ph, , , what]) => `<code>${ph}</code>(${t(what)})`).join(" ")}
    <div style="margin-top:8px"><button id="phFix" class="xs">${t("补上缺少的占位符(保留你的措辞)")}</button></div></div>`;
  $("#phFix").onclick = () => {
    let s = sys, v = vis;
    if (!s.includes("{update_option}")) s = s.includes("{board_option}") ? s.replace("{board_option}", "{board_option}{update_option}") : s.replace(", and you may upvote", "{update_option}, and you may upvote");
    if (!s.includes("{boards_note}")) s = s.includes("{goal}") ? s.replace("{goal}", "{boards_note}{goal}") : s + "{boards_note}";
    if (!v.includes("{post_hint}")) v = v.replace("Set action to {actions}.", "Set action to {actions}.{post_hint}");
    if (!v.includes("{update_rule}")) v = v.includes("{board_rule}") ? v.replace("{board_rule}", "{board_rule}{update_rule}") : v;
    if (!v.includes("{opened}")) v = "{opened}" + v;
    c.prompts.system = s === S.meta.default_prompts.system ? "default" : s; c.prompts.visit = v === S.meta.default_prompts.visit ? "default" : v;
    $("#p-system").value = s; $("#p-visit").value = v; changed(); toast(t("已补上占位符"));
  };
}

function renderPhases() {
  const tb = $("#phaseTable tbody"), c = S.cfg; let start = 1, present = 0, html = "";
  c.phases.forEach((p, i) => {
    const end = start + p.rounds - 1; present += p.add.reduce((s, g) => s + g.n, 0);
    p.add.forEach((g, j) => {
      html += `<tr><td>${j === 0 ? `<input data-p="${i}" data-k="name" value="${esc(p.name)}" aria-label="${t("阶段名")}">` : `<span class="hint">${t("同一阶段 · 另一组")}</span>`}</td>
        <td><input type="number" min="0" data-p="${i}" data-g="${j}" data-k="n" value="${g.n}" aria-label="${t("新加入")}"></td>
        <td><select data-p="${i}" data-g="${j}" data-k="model" aria-label="${t("模型")}">${modelOptions(g.model)}</select></td>
        <td>${j === 0 ? `<input type="number" min="1" data-p="${i}" data-k="rounds" value="${p.rounds}" aria-label="${t("轮数")}">` : ""}</td>
        <td class="mono small">${j === 0 ? `${start}–${end}` : ""}</td><td class="num">${j === 0 ? present : ""}</td>
        <td>${j === 0 && c.phases.length > 1 ? `<button class="iconbtn danger" data-del="${i}" aria-label="${t("删除阶段 {n}", { n: esc(p.name) })}">${icon("x")}</button>` : ""}
            ${j > 0 ? `<button class="iconbtn danger" data-delg="${i}:${j}" aria-label="${t("删除这一组")}">${icon("x")}</button>` : ""}</td></tr>`;
    });
    start = end + 1;
  });
  tb.innerHTML = html;
  $$("input,select", tb).forEach((el) => {
    const apply = () => {
      const p = c.phases[+el.dataset.p], k = el.dataset.k;
      if (k === "name") p.name = el.value; else if (k === "rounds") p.rounds = Math.max(1, +el.value || 1);
      else if (k === "n") p.add[+el.dataset.g].n = Math.max(0, +el.value || 0); else p.add[+el.dataset.g].model = el.value;
    };
    el.oninput = () => { apply(); changed(false); };          // keep focus while typing
    el.onchange = () => { apply(); changed(el.dataset.k !== "name"); };  // refresh round ranges when done
  });
  $$("[data-del]", tb).forEach((b) => (b.onclick = () => { c.phases.splice(+b.dataset.del, 1); changed(true); }));
  $$("[data-delg]", tb).forEach((b) => (b.onclick = () => { const [i, j] = b.dataset.delg.split(":").map(Number); c.phases[i].add.splice(j, 1); changed(true); }));
}
function renderComms() {
  const tb = $("#commTable tbody"), c = S.cfg;
  tb.innerHTML = c.communities.map((m, i) => `<tr><td><input data-i="${i}" data-k="name" value="${esc(m.name)}" aria-label="${t("版块名")}"></td>
    <td><input data-i="${i}" data-k="description" value="${esc(m.description)}" aria-label="${t("说明")}"></td>
    <td>${c.communities.length > 1 ? `<button class="iconbtn danger" data-i="${i}" aria-label="${t("删除版块")}">${icon("x")}</button>` : ""}</td></tr>`).join("");
  $$("input", tb).forEach((el) => (el.oninput = () => { c.communities[+el.dataset.i][el.dataset.k] = el.value; changed(); }));
  $$("button", tb).forEach((b) => (b.onclick = () => { c.communities.splice(+b.dataset.i, 1); changed(true); }));
}
function summaries() {
  const c = S.cfg, agents = c.phases.reduce((s, p) => s + p.add.reduce((a, g) => a + g.n, 0), 0), rounds = c.phases.reduce((s, p) => s + p.rounds, 0);
  const models = [...new Set(c.phases.flatMap((p) => p.add.filter((g) => g.n).map((g) => g.model)))];
  $("#sum-flow").textContent = t("{p} 个阶段 · {a} 个 Agent · {r} 轮 · {m}", { p: c.phases.length, a: agents, r: rounds, m: models.join(", ") });
  $("#sum-agent").textContent = [t(c.switches.tell_ai ? "告知是 AI" : "不告知身份"), t(c.switches.memory === "on" ? "有记忆" : "无记忆"),
    c.switches.solo ? t("独白") : null, c.switches.goal === "none" ? t("无目标句") : t("目标:{g}", { g: c.switches.goal }), "effort " + c.llm.effort,
    t(c.prior_run ? "先验已选" : "未选先验")].filter(Boolean).join(" · ");
  $("#sum-prompt").textContent = t(c.prompts.system === "default" ? "默认 system" : "system 已改") + " · " + t(c.prompts.visit === "default" ? "默认访问提示词" : "访问提示词已改");
  $("#sum-comm").textContent = c.communities.map((m) => m.name).join(", ");
  const f = c.feed;
  $("#sum-adv").textContent = t("信息流 {n} 帖(新 {a} · 热 {b} · 随机 {c}+{d}) · 记忆全文 {m} 条", { n: f.new + f.hot + f.random + f.random_seeded, a: f.new, b: f.hot, c: f.random, d: f.random_seeded, m: c.memory.recent_full })
    + " · " + (c.schedule && c.schedule.mode === "heartbeat" ? t("每 {T} 轮回访", { T: c.schedule.period }) : t("访问概率 {p}", { p: c.activation ?? 1 }))
    + (c.order && c.order.mode === "sequential" ? " · " + t("依次行动 w={w}", { w: c.order.overlap }) : "");
  flowViz();
}
function flowViz() {
  const c = S.cfg, W = 300, H = 120, T = 6, B = 34;
  const total = c.phases.reduce((s, p) => s + p.rounds, 0) || 1;
  let present = 0, x = 0; const segs = c.phases.map((p) => { present += p.add.reduce((s, g) => s + g.n, 0); const w = (p.rounds / total) * W; const s = { x, w, n: present, p }; x += w; return s; });
  const maxN = Math.max(1, ...segs.map((s) => s.n));
  let start = 1;
  const g = segs.map((s, i) => { const h = (s.n / maxN) * (H - T - B - 12); const y = H - B - h; const from = start; start += s.p.rounds;
    return `<rect x="${s.x + 1}" y="${y}" width="${Math.max(2, s.w - 2)}" height="${h}" rx="4" fill="${i === 0 ? "var(--founder)" : "var(--newcomer)"}" opacity="${i === 0 ? 0.85 : 0.75}"><title>${esc(t("{p}:{n} 个 Agent,第 {a}–{b} 轮", { p: s.p.name, n: s.n, a: from, b: start - 1 }))}</title></rect>
      <text x="${s.x + s.w / 2}" y="${y - 5}" text-anchor="middle" style="fill:var(--ink-2);font-weight:600">${s.n}</text>
      <text x="${s.x + 4}" y="${H - B + 14}">${esc(s.p.name.slice(0, 12))}</text><text x="${s.x + 4}" y="${H - B + 28}">${t("{a}–{b} 轮", { a: from, b: start - 1 })}</text>`; }).join("");
  $("#flowViz").innerHTML = `<svg class="flow" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t("流程:各阶段在场的 Agent 数与轮次")}">${g}</svg>`;
  $("#flowNote").textContent = t("柱高 = 在场人数 · 宽 = 轮数");
}
function changed(rerender) {
  if (typeof bindPresets === "function" && S.cfg && S.cfg.schedule) { bindPresets(); placeholderCheck(); } if (rerender) { renderPhases(); renderComms(); } summaries(); saveDraft(); estimateSoon(); renderSteps(); }

const estimateSoon = debounce(async () => {
  const out = $("#estOut");
  try {
    const r = await api("/api/estimate", { method: "POST", body: { config: S.cfg } });
    S.est = r;
    if (!r.ok) { out.innerHTML = `<div class="note bad">${r.errors.map(esc).join("<br>")}</div>`; renderSteps(); return; }
    const f = r.full, s = r.smoke;
    out.innerHTML = `<div class="big">${fmt$(f.cost_low)}–${fmt$(f.cost_high)}</div><div class="hint" style="margin-bottom:10px">${t(f.basis.startsWith("assumed") ? "正式运行 · token 为假设值,冒烟测试会实测" : "正式运行 · 输出 token 按冒烟测试实测,输入 token 为估算")}</div>
      <dl class="kv"><dt>${t("访问 / 调用")}</dt><dd>${f.visits.toLocaleString()} / ~${f.calls.toLocaleString()}</dd>
      <dt>${t("预计运行时间")}</dt><dd>${f.minutes >= 90 ? t("约 {h} 小时", { h: (f.minutes / 60).toFixed(1) }) : t("约 {m} 分钟", { m: f.minutes })}</dd>
      <dt>${t("每次 token(入 / 出)")}</dt><dd>${f.input_per_call.toLocaleString()} / ${f.output_per_call.toLocaleString()}</dd>
      <dt>${t("冒烟测试")}</dt><dd>${fmt$(s.cost_low)}–${fmt$(s.cost_high)}</dd><dt>${t("预算上限")}</dt><dd>${fmt$(S.cfg.budget_usd)}</dd></dl>
      <div style="margin-top:12px">${r.guard.length ? `<div class="note bad">${t("禁用词:")}${r.guard.map((h) => t("「{w}」在 {where}", { w: esc(h.word), where: esc(h.where) })).join("; ")}</div>` : `<span class="pill good">${t("禁用词检查通过")}</span>`}
      ${f.unknown_prices.length ? `<div class="note warn" style="margin-top:8px">${t("缺少价格:")}${esc(f.unknown_prices.join(", "))}</div>` : ""}</div>`;
  } catch (e) { out.innerHTML = `<div class="errors">${esc(e.message)}</div>`; }
  renderSteps();
}, 300);

function refreshPrior() {
  const sel = $("#d-prior"); if (!sel || !S.cfg) return;
  // several runs may be chosen: independent replicates' founder phases, or a solo run
  const cur = (S.cfg.prior_run || "").split(",").filter(Boolean);
  const done = S.runs.filter((m) => m.status === "done");
  sel.innerHTML = done.map((m) => `<option value="${esc(m.run_id)}" ${cur.includes(m.run_id) ? "selected" : ""}>${esc(m.run_id)}${m.solo ? " · solo" : ""}</option>`).join("") +
    cur.filter((id) => !done.some((m) => m.run_id === id)).map((id) => `<option value="${esc(id)}" selected>${esc(id)}${t("(未完成或不存在)")}</option>`).join("");
}
function renderSteps() {
  if (!S.cfg || !S.meta) return;
  const models = S.cfg.phases.flatMap((p) => p.add.filter((g) => g.n).map((g) => g.model));
  const paidModels = [...new Set(models.filter((m) => !m.startsWith("mock")))];
  const done = (pred) => S.runs.some((m) => m.status === "done" && pred(m));
  const priorIds = (S.cfg.prior_run || "").split(",").filter(Boolean);
  const priorOk = priorIds.length > 0 && priorIds.every((id) => done((m) => m.run_id === id));
  const priorCandidate = S.runs.find((m) => m.status === "done" && m.solo && m.run_id !== S.cfg.prior_run);
  const ok = !S.est || (S.est.ok && !S.est.guard.length);
  const steps = [
    { t: t("免费试跑"), d: t("所有模型换成 mock,把流程和网页走一遍,不花钱"), done: done((m) => isMock(m.models) && !m.solo),
      btn: `<button data-go="mock">${icon("play")}${t("免费试跑")}</button>` },
    { t: t("先验语料"), d: priorOk ? t("已选用 {r}", { r: S.cfg.prior_run }) : t("选 2–3 次独立的重复运行(只用它们的创始阶段),或一次独白运行。这些论坛里写过的词组是模型自带的,不算创始说法"), done: priorOk,
      btn: priorCandidate ? `<button data-pick="${esc(priorCandidate.run_id)}">${t("选用 {r}", { r: esc(priorCandidate.run_id.slice(0, 15)) + "…" })}</button>` : `<button data-go="prior">${icon("play")}${t("创建先验运行")}</button>` },
    { t: t("冒烟测试"), d: t("5+5 个 Agent、5 轮,实测 token 和无效率"), done: done((m) => m.mode === "smoke" && !isMock(m.models)), btn: `<button class="accent" data-go="smoke">${icon("play")}${t("冒烟测试")}</button>` },
    { t: t("正式运行"), d: t("按左边的设定完整运行"), done: false, btn: `<button class="primary block" data-go="full">${icon("play")}${t("正式运行")}</button>` },
  ];
  const next = steps.findIndex((s) => !s.done);
  $("#steps").innerHTML = steps.map((s, i) => `<li class="${s.done ? "done" : i === next ? "next" : ""}"><span class="dot" aria-hidden="true">${s.done ? "✓" : i + 1}</span>
    <div><div class="t">${s.t}${s.done ? ` <span class="sr">${t("已完成")}</span>` : ""}</div><div class="d">${esc(s.d)}</div>${s.done && i < 3 ? "" : s.btn}</div></li>`).join("") +
    (!paidModels.length ? `<li><span></span><div class="note">${t("流程里只有 mock 模型:正式运行也不花钱。")}</div></li>` : "") +
    (!S.meta.key_set && paidModels.length ? `<li><span></span><div class="note warn">${t("还没有 API 密钥。到「模型与密钥」添加,或在启动前设置 ANTHROPIC_API_KEY。")}</div></li>` : "") +
    (!ok ? `<li><span></span><div class="note bad">${t("设定有误或没过禁用词检查,看上面的费用估算。")}</div></li>` : "");
  $$("#steps [data-go]").forEach((b) => (b.onclick = () => busy(b, () => startRun(b.dataset.go))));
  $$("#steps [data-pick]").forEach((b) => (b.onclick = () => { S.cfg.prior_run = b.dataset.pick; refreshPrior(); changed(); toast(t("已选用先验运行")); }));
}

async function startRun(kind) {
  let cfg = JSON.parse(JSON.stringify(S.cfg)), mode = kind;
  if (kind === "mock") { cfg.phases.forEach((p) => p.add.forEach((g) => (g.model = "mock"))); cfg.name = (cfg.name ? cfg.name + " " : "") + "mock"; mode = "full"; }
  if (kind === "prior") {
    const model = cfg.phases[0].add.find((g) => g.n)?.model || "claude-haiku-5-5";
    cfg = { ...cfg, name: "prior " + model, prior_run: "", switches: { ...cfg.switches, solo: true }, phases: [{ name: "prior", add: [{ n: 10, model }], rounds: 20 }] };
    mode = "full";
  }
  const paid = cfg.phases.some((p) => p.add.some((g) => g.n > 0 && !g.model.startsWith("mock")));
  const body = { config: cfg, mode, confirm: false };
  const r = await api("/api/estimate", { method: "POST", body: { config: cfg } }).catch(() => null);
  if (!r || !r.ok) return toast(t("设定有误,先看费用估算里的提示。"));
  if (r.guard.length) return toast(t("禁用词检查没有通过。"));
  if (paid) {
    const e = mode === "smoke" ? r.smoke : r.full;
    const title = t({ smoke: "确认冒烟测试", prior: "确认先验独白运行", full: "确认正式运行" }[kind] || "确认运行");
    const models = [...new Set(cfg.phases.flatMap((p) => p.add.map((g) => g.model)))].join(", ");
    const ok = await confirmDialog(title, `<p>${t("将调用 {m} 约 {n} 次,推理强度 {e}。", { m: `<b>${esc(models)}</b>`, n: e.calls.toLocaleString(), e: esc(cfg.llm.effort) })}</p>
      <p class="big">${fmt$(e.cost_low)} – ${fmt$(e.cost_high)}</p><p class="hint">${t("预算上限 {b}:快到上限时自动停下,可以加预算后继续。单价请先在官网核对。", { b: fmt$(cfg.budget_usd) })}</p>`);
    if (!ok) return;
    body.confirm = true;
  }
  try {
    const res = await api("/api/runs", { method: "POST", body });
    toast(t("已开始:{r}", { r: res.run_id })); await refreshRuns(); setCurrent(res.run_id); location.hash = "#monitor";
  } catch (e) { toast(t("没有开始:{e}", { e: e.message })); }
}

// ================================================================ monitor
async function loadMonitor() {
  await refreshRuns();
  const m = currentManifest(), box = $("#mon");
  if (!m) { box.innerHTML = emptyState("activity", t("还没有运行"), t("到「设计」页按步骤开始。")); return; }
  box.innerHTML = `<div class="card"><div class="skeleton"></div><div class="skeleton" style="width:60%"></div></div>`;
  S.mon = await api(`/api/runs/${m.run_id}`);
  renderMonitor(); followCurrent();
}
function renderMonitor() {
  const d = S.mon, m = d.manifest, rs = d.rounds, cfg = d.config;
  const tr = m.total_rounds || 1, done = m.rounds_done || 0;
  const phaseBar = cfg.phases.map((p, i) => { const prev = cfg.phases.slice(0, i).reduce((s, q) => s + q.rounds, 0); const fill = Math.max(0, Math.min(p.rounds, done - prev));
    return `<i style="width:${(100 * fill) / tr}%;background:${i === 0 ? "var(--founder)" : "var(--newcomer)"}"></i>`; }).join("");
  $("#pageActions").innerHTML = m.running ? `<button class="danger" id="mon-stop">${icon("stop")}${t("停止")}</button>` : (m.status !== "done" ? `<button class="primary" id="mon-resume">${icon("play")}${t("继续运行")}</button>` : "");
  const kp = (v, l, ref = "") => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div>${ref ? `<div class="ref">${ref}</div>` : ""}</div>`;
  $("#mon").innerHTML = `<div class="card"><div class="row between"><div class="row"><span class="mono small">${esc(m.run_id)}</span>${statusPill(m)}<span class="tag ${m.solo ? "newcomer" : "founder"}">${runKind(m)}</span></div>
      <span class="small muted">${esc((m.models || []).join(", "))}</span></div>
      <div class="bar phases" style="margin:14px 0 6px;height:10px" role="progressbar" aria-valuemin="0" aria-valuemax="${tr}" aria-valuenow="${done}" aria-label="${t("进度")}">${phaseBar}</div>
      <div class="row between xs muted"><span>${t("第 {a} / {b} 轮", { a: done, b: tr })}${rs.length ? " · " + t("阶段 {p}", { p: rs[rs.length - 1].phase + 1 }) : ""}</span><span>${cfg.phases.map((p) => esc(p.name)).join(" → ")}</span></div>
      ${m.message ? `<div class="note ${m.status === "done" ? "" : "warn"}" style="margin-top:12px">${esc(m.message)}</div>` : ""}</div>
    <div class="kpis" style="margin-top:14px">${kp(fmt$(m.cost), t("已花费 / 上限 {b}", { b: fmt$(m.budget_usd) }))}${kp(m.calls, t("模型调用"))}
      ${kp(m.void, t("无效访问"), t("3 轮内超过 10% 自动停"))}${kp(m.refusals, t("被拒调用"), t("超过 3% 自动停"))}
      ${kp(d.expressions ? d.expressions.expressions.length : "–", t("冻结的创始说法"), d.expressions ? t("{n} 篇进入随机池", { n: d.expressions.seeded_posts.length }) : t("阶段 1 结束时冻结"))}</div>
    ${usageCard(d)}
    <div class="card" style="margin-top:14px"><h2>${t("每轮活动")}</h2>${rs.length ? lineChart(rs.map((r) => r.round), [
      { name: t("发帖"), color: "var(--primary)", values: rs.map((r) => r.posts) }, { name: t("版块"), color: "var(--warn)", values: rs.map((r) => r.boards ?? 0) }, { name: t("评论"), color: "var(--accent)", values: rs.map((r) => r.comments) },
      { name: t("点赞"), color: "var(--good)", values: rs.map((r) => r.votes) }, { name: t("不动"), color: "var(--faint)", values: rs.map((r) => r.none) }], phaseMarks(cfg)) : `<p class="muted small">${t("还没有完成的轮次。")}</p>`}</div>
    <div class="card" style="margin-top:14px;padding:0"><div class="table-wrap" style="max-height:420px"><table><thead><tr><th class="num" style="padding-left:20px">${t("轮")}</th><th>${t("阶段")}</th>
      <th class="num">${t("在场")}</th><th class="num">${t("发帖")}</th><th class="num">${t("版块")}</th><th class="num">${t("评论")}</th><th class="num">${t("点赞")}</th><th class="num">${t("不动")}</th><th class="num">${t("无效")}</th><th class="num" style="padding-right:20px">${t("费用")}</th></tr></thead><tbody>
      ${rs.slice().reverse().map((r) => `<tr><td class="num" style="padding-left:20px">${r.round}</td><td>${r.phase + 1}</td><td class="num">${r.active}</td><td class="num">${r.posts}</td><td class="num">${r.boards ?? 0}</td>
        <td class="num">${r.comments}</td><td class="num">${r.votes}</td><td class="num">${r.none}</td><td class="num">${r.void ? `<span class="pill bad plain">${r.void}</span>` : 0}</td>
        <td class="num" style="padding-right:20px">${fmt$(r.cost)}</td></tr>`).join("")}</tbody></table></div></div>`;
  $("#mon-stop")?.addEventListener("click", (e) => busy(e.currentTarget, async () => { await api(`/api/runs/${m.run_id}/cancel`, { method: "POST" }).catch((x) => toast(x.message)); toast(t("正在停止:这一轮不写入,继续时从上一整轮接着跑。")); }));
  $("#mon-resume")?.addEventListener("click", () => resumeRun(m.run_id));
}
function usageCard(d) {
  const u = d.usage;
  if (!u || !u.calls) return "";
  const kp = (v, l) => `<div><div class="tnum" style="font-weight:650">${v}</div><div class="xs muted">${l}</div></div>`;
  return `<div class="card" style="margin-top:14px"><div class="row between"><h2 style="margin:0">${t("实测用量")}</h2><span class="hint">${t("来自已记录的 {n} 次调用", { n: u.calls })}</span></div>
    <div class="cols-4" style="margin-top:10px">${kp(Math.round(u.input_per_call).toLocaleString(), t("每次输入 token"))}${kp(Math.round(u.output_per_call).toLocaleString(), t("每次输出 token(含思考)"))}
      ${kp(fmt$(u.cost_per_call), t("每次费用"))}${kp(u.seconds_per_call.toFixed(1) + " s", t("每次耗时"))}</div></div>`;
}
const phaseMarks = (cfg) => { let s = 1; return cfg.phases.slice(0, -1).map((p) => (s += p.rounds)); };
async function resumeRun(id) {
  const d = await api(`/api/runs/${id}`);
  const paid = d.config.phases.some((p) => p.add.some((g) => g.n > 0 && !g.model.startsWith("mock")));
  let budget = d.config.budget_usd;
  if (paid) {
    const ok = await confirmDialog(t("确认继续运行"), `<p>${t("已花费 {c},预算上限 {b}。已记录的调用不会重发。", { c: fmt$(d.manifest.cost), b: fmt$(budget) })}</p>
      <label class="f">${t("新的预算上限 (USD)")}<input type="number" id="cd-budget" value="${budget}" min="0" step="0.5"></label>`, t("继续运行"));
    if (!ok) return;
    budget = Number($("#cd-budget")?.value || budget);
  }
  try { await api(`/api/runs/${id}/resume`, { method: "POST", body: { confirm: true, budget_usd: budget } }); toast(t("已继续")); await refreshRuns(); setCurrent(id); location.hash = "#monitor"; loadMonitor(); }
  catch (e) { toast(t("没有继续:{e}", { e: e.message })); }
}

// ================================================================ charts (inline SVG)
function lineChart(xs, series, marks = [], { h = 220 } = {}) {
  const W = 760, H = h, L = 40, R = 12, T = 12, B = 26;
  const ymax = Math.max(1, ...series.flatMap((s) => s.values.filter((v) => v != null)));
  const x0 = xs[0], x1 = xs[xs.length - 1] === x0 ? x0 + 1 : xs[xs.length - 1];
  const X = (x) => L + ((x - x0) / (x1 - x0)) * (W - L - R), Y = (y) => T + (1 - y / ymax) * (H - T - B);
  let g = [0, 0.25, 0.5, 0.75, 1].map((f) => f * ymax).map((v) => `<line class="grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${Math.round(v)}</text>`).join("");
  const step = Math.max(1, Math.ceil(xs.length / 10));
  g += xs.filter((_, i) => i % step === 0).map((x) => `<text x="${X(x)}" y="${H - 8}" text-anchor="middle">${x}</text>`).join("");
  g += marks.map((mk) => `<line x1="${X(mk - 0.5)}" x2="${X(mk - 0.5)}" y1="${T}" y2="${H - B}" stroke="var(--newcomer)" stroke-dasharray="4 4"/><text x="${X(mk - 0.5) + 5}" y="${T + 10}" style="fill:var(--newcomer)">${t("新成员加入")}</text>`).join("");
  g += series.map((s) => `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" points="${s.values.map((v, i) => (v == null ? "" : `${X(xs[i])},${Y(v)}`)).join(" ")}"><title>${esc(s.name)}</title></polyline>`).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("{s}随轮次变化", { s: series.map((s) => s.name).join(", ") }))}">${g}<line class="axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/></svg>
    <div class="legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}<span>${t("横轴:轮")}</span></div>`;
}
function barChart(rows, key, colorOf, { h = 200 } = {}) {
  const W = 760, H = h, L = 36, B = 18, T = 8, ymax = Math.max(1, ...rows.map((r) => r[key])), bw = (W - L - 8) / Math.max(1, rows.length);
  const g = rows.map((r, i) => { const y = T + (1 - r[key] / ymax) * (H - T - B); return `<rect x="${L + i * bw + 1}" y="${y}" width="${Math.max(1, bw - 2)}" height="${H - B - y}" rx="1.5" fill="${colorOf(r)}"><title>${esc(r.handle)}: ${r[key]}</title></rect>`; }).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t("每个 Agent 的得赞,从高到低")}">${g}<line class="axis" x1="${L}" x2="${W}" y1="${H - B}" y2="${H - B}"/><text x="${L - 6}" y="${T + 10}" text-anchor="end">${ymax}</text><text x="${L - 6}" y="${H - B}" text-anchor="end">0</text></svg>`;
}
function histChart(hist) {
  const W = 420, H = 190, L = 10, R = 10, T = 24, B = 26, c = hist.counts, e = hist.edges, cmax = Math.max(1, ...c);
  const X = (v) => L + ((v - e[0]) / (e[e.length - 1] - e[0])) * (W - L - R), Y = (n) => T + (1 - n / cmax) * (H - T - B);
  const bars = c.map((n, i) => `<rect x="${X(e[i]) + 0.5}" y="${Y(n)}" width="${Math.max(1, X(e[i + 1]) - X(e[i]) - 1)}" height="${H - B - Y(n)}" fill="var(--line-2)"><title>${esc(t("{n} 次重抽落在 {a}–{b}", { n, a: e[i].toFixed(1), b: e[i + 1].toFixed(1) }))}</title></rect>`).join("");
  const xo = X(hist.observed);
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${t("重抽分布与实际值")}">${bars}<line class="axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>
    <line x1="${xo}" x2="${xo}" y1="${T - 6}" y2="${H - B}" stroke="var(--accent)" stroke-width="2.5"/>
    <text x="${xo > W - 130 ? xo - 6 : xo + 6}" y="${T - 8}" text-anchor="${xo > W - 130 ? "end" : "start"}" style="fill:var(--accent);font-weight:600;font-size:12px">${t("实际值 T = {v}", { v: hist.observed.toFixed(1) })}</text>
    <text x="${L}" y="${H - 8}">${e[0].toFixed(1)}</text><text x="${W - R}" y="${H - 8}" text-anchor="end">${e[e.length - 1].toFixed(1)}</text></svg>
    <div class="legend"><span><i style="background:var(--line-2)"></i>${t("假如「看到」没有作用:随机位重抽后的 T")}</span><span><i style="background:var(--accent)"></i>${t("实际的 T")}</span></div>`;
}
const emptyState = (ic, ti, d) => `<div class="card empty">${icon(ic)}<div style="font-weight:600;color:var(--ink-2)">${esc(ti)}</div><div class="small">${esc(d)}</div></div>`;

// ================================================================ forum (web/forum.js)
function openDrawer() { $("#drawer").classList.add("on"); $("#drawer").setAttribute("aria-hidden", "false"); $("#scrim").classList.add("on"); }
function closeDrawer() { $("#drawer")?.classList.remove("on"); $("#drawer")?.setAttribute("aria-hidden", "true"); $("#scrim")?.classList.remove("on"); }

// ================================================================ results
async function loadResults(refresh = false) {
  await refreshRuns();
  const m = currentManifest(), out = $("#re-out");
  if (!m) { out.innerHTML = emptyState("chart", t("还没有运行"), t("先在「设计」页开始一次运行。")); return; }
  $("#pageActions").innerHTML = `<label class="f" style="flex-direction:row;align-items:center;gap:6px">${t("重抽次数")}<input type="number" id="re-redraws" value="${S.redraws || 2000}" min="100" step="500" style="width:96px"></label><button id="re-go">${t("重新计算")}</button>`;
  $("#re-go").onclick = (e) => { S.redraws = +$("#re-redraws").value || 2000; busy(e.currentTarget, () => loadResults(true)); };
  out.innerHTML = `<div class="card"><div class="skeleton"></div><div class="skeleton" style="width:85%"></div><div class="skeleton" style="width:65%"></div><p class="hint">${t("计算中(重抽次数越多越慢)…")}</p></div>`;
  try {
    const [M, d] = await Promise.all([api(`/api/runs/${m.run_id}/measures?redraws=${S.redraws || 2000}${refresh ? "&refresh=true" : ""}`), api(`/api/runs/${m.run_id}`)]);
    renderResults(M, d);
    renderCompare();
  } catch (e) { out.innerHTML = `<div class="note bad">${t("计算失败:{e}", { e: esc(e.message) })}</div>`; }
}
// ---- several runs side by side (the pilot yardsticks; /api/compare)
const CMP_ROWS = [["settings", "post_hint", "提示开新帖"], ["settings", "tell_ai", "告知是 AI"], ["settings", "order", "一轮之内"],
  ["settings", "schedule", "回访"], ["settings", "two_step", "两步访问"], ["settings", "models", "模型"], ["settings", "agents", "Agent 数"],
  ["settings", "rounds", "轮数"], ["settings", "cost", "费用"], ["metrics", "visits", "访问"], ["metrics", "posts_after_round_1", "第 1 轮后的新帖"],
  ["metrics", "posts", "帖子"], ["metrics", "comments", "评论"], ["metrics", "boards_started", "成员建的版块"], ["metrics", "updates", "帖子更新"],
  ["metrics", "share_nothing", "什么都不做"], ["metrics", "biggest_thread_share", "最大讨论串占评论"], ["metrics", "largest_board_share", "最大版块占帖子"],
  ["metrics", "near_duplicate_comment_pairs", "近似重复评论对"], ["metrics", "share_replies_to_comments", "回复评论(而非帖子)"],
  ["metrics", "replies_within_round", "同一轮内的回复"], ["metrics", "deepest_reply", "最深来回"], ["metrics", "title_template_share", "标题套用模板"]];
function cmpCell(k, v) {
  if (v == null) return "–";
  if (typeof v === "boolean") return v ? t("是") : t("否");
  if (Array.isArray(v)) return esc(v.join(", "));
  if (k === "cost") return fmt$(v);
  if (typeof v === "number" && (k.startsWith("share") || k.endsWith("_share"))) return (100 * v).toFixed(0) + "%";
  return esc(String(v));
}
function renderCompare() {
  const done = S.runs.filter((m) => !m.running && m.rounds_done > 0);
  S.cmp = S.cmp && S.cmp.length ? S.cmp.filter((id) => done.some((m) => m.run_id === id)) : [S.current];
  const box = document.createElement("div");
  box.className = "card"; box.style.marginTop = "16px"; box.id = "cmpCard";
  box.innerHTML = `<h2>${t("多次运行对比")}</h2><p class="small muted">${t("勾选要并排比较的运行(最多 8 个),比如同一设置的重复运行,或只差一个开关的两次运行。")}</p>
    <div class="cmp-pick">${done.map((m) => `<label class="small"><input type="checkbox" value="${esc(m.run_id)}" ${S.cmp.includes(m.run_id) ? "checked" : ""}> <span class="mono">${esc(m.run_id)}</span></label>`).join("")}</div>
    <button id="cmpGo" class="primary" style="margin-top:8px">${t("对比")}</button><div id="cmpOut" style="margin-top:12px"></div>`;
  $("#re-out").appendChild(box);
  $("#cmpGo").onclick = async (e) => {
    S.cmp = $$("#cmpCard input:checked").map((x) => x.value).slice(0, 8);
    if (!S.cmp.length) return toast(t("至少勾选一个运行"));
    await busy(e.currentTarget, async () => {
      const rows = await api(`/api/compare?ids=${encodeURIComponent(S.cmp.join(","))}`);
      $("#cmpOut").innerHTML = `<div class="table-wrap"><table><thead><tr><th style="padding-left:12px">${t("指标")}</th>${rows.map((r) => `<th class="mono xs">${esc(r.run_id)}</th>`).join("")}</tr></thead><tbody>
        ${CMP_ROWS.map(([g, k, l]) => `<tr><td style="padding-left:12px" class="small">${t(l)}</td>${rows.map((r) => `<td class="small tnum">${cmpCell(k, r[g][k])}</td>`).join("")}</tr>`).join("")}
        <tr><td style="padding-left:12px" class="small">${t("版块")}</td>${rows.map((r) => `<td class="xs">${esc(r.boards.map((b) => b.name).join(", ") || "–")}</td>`).join("")}</tr></tbody></table></div>`;
    });
  };
}

// ---- "the run at a glance": plain-language answers and two labelled 100% bars, for readers new to the study
function stackBar(segs, label) {
  const total = segs.reduce((a, x) => a + x.value, 0) || 1;
  const shown = segs.filter((x) => x.value > 0);
  return `<div class="sbar" role="img" aria-label="${esc(label)}">${shown.map((x) => { const p = (100 * x.value) / total;
    return `<div class="seg" style="width:${p}%;background:${x.color}" title="${esc(x.label)} ${p.toFixed(0)}%">${p >= 9 ? `<span>${p.toFixed(0)}%</span>` : ""}</div>`; }).join("")}</div>
    <ul class="sbar-legend">${shown.map((x) => `<li><i style="background:${x.color}"></i>${esc(x.label)} <b class="tnum">${((100 * x.value) / total).toFixed(0)}%</b> <span class="muted">(${x.value})</span></li>`).join("")}</ul>`;
}
function glance(M, d) {
  const D = M.describe, P = M.primary, T = D.totals, R = D.rounds || [];
  const sum = (k) => R.reduce((a, r) => a + (r[k] || 0), 0);
  const left = sum("left"), none = sum("none") - left;
  const acts = [{ label: t("发帖"), value: sum("posts"), color: "var(--primary)" }, { label: t("评论"), value: sum("comments"), color: "var(--accent)" },
    { label: t("建版块"), value: sum("boards"), color: "var(--good)" }, { label: t("更新自己的帖子"), value: sum("updates"), color: "var(--founder)" },
    { label: t("只看看(可能点赞),没写东西"), value: none, color: "var(--faint)" }, { label: t("看完版块列表就离开"), value: left, color: "var(--line-2)" },
    { label: t("回答无效"), value: sum("void"), color: "var(--bad)" }];
  const th = D.threads || [], nC = T.comments || 0, top = th.slice(0, 4).filter((x) => x.comments > 0);
  const rest = nC - top.reduce((a, x) => a + x.comments, 0);
  const palette = ["var(--primary)", "var(--accent)", "var(--good)", "var(--founder)"];
  const threads = [...top.map((x, i) => ({ label: `${x.id} “${x.title.length > 48 ? x.title.slice(0, 48) + "…" : x.title}”`, value: x.comments, color: palette[i] })),
    { label: t("其余所有讨论串"), value: Math.max(0, rest), color: "var(--faint)" }];
  const big = nC && th[0] ? th[0].comments / nC : 0;
  const conc = big >= 0.5 ? t("高度集中:一个讨论串拿走了一半以上的评论") : big >= 0.2 ? t("比较集中:最热的讨论串拿走了五分之一以上的评论") : t("比较分散:评论分布在许多讨论串里");
  let spread;
  if (P.note) spread = { tone: "warn", head: t("还不能判断"), body: t("需要阶段 1 冻结的创始说法,并且有新成员通过随机位置看到过它们。") };
  else { const r = P.results.beyond_echo, sig = r.p_value != null && r.p_value < 0.05;
    spread = sig ? { tone: "good", head: t("是,有证据"), body: t("新成员碰巧看到某个创始者的说法后,更可能在同一次访问里用上它(多 {e} 个百分点;p = {p},即偶然出现这么大差别的机会约 {pp})。", { e: (100 * r.effect).toFixed(2), p: num(r.p_value, 3), pp: pct(r.p_value, 1) }) }
      : { tone: "", head: t("没有发现可靠证据"), body: t("看到与没看到某个说法的新成员,用上它的比例差别不大(p = {p},这么大的差别偶然出现的机会约 {pp})。", { p: num(r.p_value, 3), pp: pct(r.p_value, 0) }) }; }
  if (!d.config.prior_run) spread.body += " " + t("这次没有选先验语料,所以「创始说法」里混着模型的常用词组,结论要打折扣。");
  const boards = (D.navigation ? null : null), nb = T.boards || 0, nu = D.navigation ? D.navigation.updates : 0;
  const inst = nb || nu ? t("成员自己建了 {b} 个版块,作者更新了 {u} 次自己的帖子(常被用来写下规则或结果)。", { b: nb, u: nu }) : t("这次没有成员建版块,也没有人更新自己的帖子。");
  const fr = D.frame, frTxt = fr && (fr.public_frame_count || fr.instruction_like_count || Object.keys(fr.thinking_frame_terms || {}).length)
    ? t("有 {n} 处值得去读的线索(谈到运营者、被观察、像指令的发言等),见下方「边界与框架线索」。", { n: (fr.public_frame_count || 0) + (fr.instruction_like_count || 0) + Object.values(fr.thinking_frame_terms || {}).reduce((a, b) => a + b, 0) })
    : t("没有发现谈论「谁在运营这个论坛」「是不是在被观察」或试图给别人下指令的发言。");
  const idTxt = D.identity ? t(D.identity.told ? "告诉了它们「成员都是 AI」;{s} 的发言提到 AI 或训练。" : "没有告诉它们成员是 AI;{s} 的发言自己提到了 AI 或训练。", { s: pct(D.identity.share) }) : "";
  const card = (head, value, body, tone = "") => `<div class="gcard ${tone}"><div class="gq">${head}</div><div class="gv">${value}</div><p>${body}</p></div>`;
  return `<section class="glance card"><h2>${t("一眼看懂这次运行")}</h2>
    <p class="small muted">${t("{a} 个 AI 成员在一个只有它们的论坛里待了 {r} 轮(对它们显示为 {r} 小时),一共访问 {v} 次,写了 {p} 篇帖子和 {c} 条评论。", { a: T.agents, r: T.rounds_done, v: R.reduce((x, y) => x + (y.active || 0), 0), p: T.posts, c: T.comments })}</p>
    <div class="gcards">
      ${card(t("看到别人的说法,会跟着用吗?"), spread.head, spread.body, spread.tone)}
      ${card(t("讨论集中在少数帖子吗?"), th[0] ? pct(big, 0) : "–", (th[0] ? conc + "。" : "") + t("数字 = 最热的讨论串占全部评论的比例。"))}
      ${card(t("有没有自己定规则、建结构?"), t("{b} 个版块 · {u} 次更新", { b: nb, u: nu }), inst)}
      ${card(t("有没有越界或谈论身份?"), fr ? (fr.public_frame_count + fr.instruction_like_count) : "–", frTxt + " " + idTxt)}
    </div>
    <div class="cols-2" style="margin-top:14px">
      <div><h3>${t("每次访问做了什么")}</h3>${stackBar(acts, t("每次访问做了什么"))}</div>
      <div><h3>${t("评论落在哪些讨论串")}</h3>${nC ? stackBar(threads, t("评论落在哪些讨论串")) : `<p class="muted small">${t("还没有评论")}</p>`}</div>
    </div>
    <details class="gloss"><summary class="small">${t("术语说明")}</summary><dl class="kv small">
      <dt>${t("创始说法")}</dt><dd>${t("第一批成员在阶段 1 里共同用过的 2–4 词短语,阶段 1 结束时固定下来,之后看新成员会不会用。")}</dd>
      <dt>${t("随机位置")}</dt><dd>${t("信息流里有几个位置是抽签决定放什么的,所以谁看到什么带有随机性,可以像实验一样比较「看到」和「没看到」。")}</dd>
      <dt>p ${t("值")}</dt><dd>${t("如果其实没有任何影响,偶然出现这么大差别的机会。小于 5% 通常算有证据。")}</dd>
      <dt>Gini</dt><dd>${t("不平等程度:0 = 每个人得到的一样多,1 = 全给了一个人。")}</dd>
      <dt>${t("先验语料")}</dt><dd>${t("几次互不相干的运行,用来找出模型自己本来就爱说的词组,把它们从「创始说法」里去掉。")}</dd></dl></details>
  </section>`;
}

function renderResults(M, d) {
  const D = M.describe, P = M.primary, kp = (v, l, ref = "") => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div>${ref ? `<div class="ref">${ref}</div>` : ""}</div>`;
  const outName = { beyond_echo: "同一次访问 · 非回声(主要)", any_same_visit: "同一次访问 · 任何使用", any_within_3: "之后 3 次访问内 · 任何使用" };
  let prim;
  if (P.note) prim = `<div class="note warn">${P.note.startsWith("Nothing") ? t("还不能检验:需要阶段 1 冻结的创始说法,以及至少一轮新成员访问。") : P.note.startsWith("No exposure") ? t("新成员还没有通过随机位置看到过任何创始说法。") : esc(P.note)}</div>`;
  else {
    const r = P.results.beyond_echo, sig = r.p_value != null && r.p_value < 0.05, eff = r.effect == null ? "–" : (100 * r.effect).toFixed(2);
    prim = `<div class="cols-2" style="align-items:center">
      <div><div class="hint">${t("主要结果 · 同一次访问、排除回声")}</div><div class="big" style="color:${sig ? "var(--good)" : "var(--ink)"}">${r.effect == null ? "–" : (r.effect >= 0 ? "+" : "") + eff} ${t("个百分点")}</div>
        <div class="small">p = ${num(r.p_value, 4)} · ${t(sig ? "看到之后更可能使用" : "没有发现「看到才会用」的证据")}</div>
        <p class="small muted" style="margin-top:10px">${t("{e} 个创始说法 · 新成员 {v} 次带随机位的访问 · 重抽 {r} 次。另有 {b} 个单位同时从非随机渠道看到,不进主要分析。", { e: P.expressions, v: P.visits_with_random_slots, r: P.redraws, b: P.stratum_B.units })}</p>
        ${d.config.prior_run ? "" : `<div class="note warn">${t("这次运行没有选先验语料:创始说法里混有模型的常用词组,检验力会很低。")}</div>`}</div>
      <div>${P.null_hist ? histChart(P.null_hist) : ""}</div></div>
      <div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>${t("结果口径")}</th><th class="num">${t("效应(百分点)")}</th><th class="num">p</th><th class="num">${t("看到过:用了 / 次数")}</th><th class="num">${t("比例")}</th><th class="num">${t("没看到:用了 / 次数")}</th><th class="num">${t("比例")}</th></tr></thead><tbody>
      ${Object.entries(P.results).map(([k, x]) => `<tr><td>${t(outName[k] || k)}</td><td class="num">${x.effect == null ? "–" : (100 * x.effect).toFixed(2)}</td><td class="num">${num(x.p_value, 4)}</td>
        <td class="num">${x.exposed_used} / ${x.exposed}</td><td class="num">${pct(x.rate_exposed, 2)}</td><td class="num">${x.unexposed_used} / ${x.unexposed}</td><td class="num">${pct(x.rate_unexposed, 2)}</td></tr>`).join("")}</tbody></table></div>
      <details style="margin-top:10px"><summary class="small">${t("这些数字怎么读")}</summary><p class="small muted" style="margin-top:8px">${t("单位是「新成员的一次访问 × 一个它此前没用过、这次只可能从随机位置看到的说法」。Z = 随机位置是否显示了它,p = 按引擎的抽签规则被显示的概率(精确已知),Y = 这次访问里是否用了它。效应 = Σ(Z−p)Y ÷ Σp(1−p)。p 值:把随机位置按同样规则重抽,看实际的 T 比多少次重抽结果更大。")}</p></details>`;
  }
  const rounds = D.rounds, agents = D.agents.slice().sort((a, b) => b.upvotes_received - a.upvotes_received);
  $("#re-out").innerHTML = `${glance(M, d)}
    <h2 class="section-h">${t("详细结果")}</h2>
    <div class="card"><h2>${t("主要分析:看到了才会用吗?")}</h2>${prim}</div>
    <div class="kpis" style="margin-top:16px">${kp(D.totals.posts, t("帖子"))}${D.totals.boards ? kp(D.totals.boards, t("成员创建的版块")) : ""}${D.identity ? kp((100 * (D.identity.share || 0)).toFixed(1) + "%", t("提到 AI / 训练的发言"), D.identity.told ? t("告知了是 AI") : t("没有告知身份")) : ""}${kp(D.totals.comments, t("评论"))}${kp(D.totals.upvotes, t("点赞"))}
      ${kp(num(D.attention.gini_upvotes, 2), t("得赞 Gini"))}${D.attention.gini_upvotes_per_impression != null ? kp(num(D.attention.gini_upvotes_per_impression, 2), t("按曝光算的得赞不平等"), t("得赞 ÷ 被展示次数")) : ""}${kp(num(D.attention.gini_replies, 2), t("被回复 Gini"), t("Moltbook 样本 0.91"))}
      ${kp(pct(D.reciprocity.share_mutual), t("互相回复的对子"), t("文献 1–4%"))}${kp(pct(D.conversation.share_unanswered), t("无人回复的评论"), t("Moltbook 早期 93.5%"))}${kp(D.conversation.longest_back_and_forth, t("最长来回链"))}</div>
    ${D.navigation ? `<div class="card" style="margin-top:16px"><h2>${t("去哪里、版块与更新")}</h2>
      <dl class="kv"><dt>${t("第一步的选择")}</dt><dd>${Object.entries(D.navigation.choices).map(([k, v]) => `<span class="mono">${esc(k)}</span> ×${v}`).join(", ") || "–"}</dd>
      <dt>${t("离开(什么都没看)")}</dt><dd>${pct(D.navigation.share_leave)}</dd><dt>${t("选「全部版块」")}</dt><dd>${pct(D.navigation.share_all)}</dd>
      <dt>${t("最常去的版块占比")}</dt><dd>${pct(D.navigation.top_board_share)}</dd>
      <dt>${t("帖子更新")}</dt><dd>${t("{n} 次,涉及 {p} 篇帖子", { n: D.navigation.updates, p: D.navigation.posts_updated })}</dd></dl></div>` : ""}
    ${D.frame ? `<div class="card" style="margin-top:16px"><h2>${t("边界与框架线索")}</h2><p class="small muted">${t("按规则找出的线索,只是阅读的入口,不是结论。")}</p>
      <dl class="kv"><dt>${t("思考摘要里提到框架")}</dt><dd>${Object.entries(D.frame.thinking_frame_terms).map(([k, v]) => `${esc(k)} ×${v}`).join(", ") || "0"}</dd>
      <dt>${t("公开发言里提到框架")}</dt><dd>${D.frame.public_frame_count}${D.frame.public_frame_items.length ? " · " + D.frame.public_frame_items.map((i) => i.startsWith("p_") ? `<a class="mono" href="#forum/t/${i}">${i}</a>` : `<span class="mono">${esc(i)}</span>`).join(", ") : ""}</dd>
      <dt>${t("像指令的发言")}</dt><dd>${D.frame.instruction_like_count}${D.frame.instruction_like_items.length ? " · " + D.frame.instruction_like_items.map(esc).join(", ") : ""}</dd>
      <dt>${t("被丢弃或无效的尝试")}</dt><dd>${Object.entries(D.frame.flags).map(([k, v]) => `${esc(k)} ×${v}`).join(", ") || "0"}</dd></dl></div>` : ""}
    <div class="cols-2" style="margin-top:16px">
      <div class="card"><h2>${t("每轮活动")}</h2>${lineChart(rounds.map((r) => r.round), [{ name: t("发帖"), color: "var(--primary)", values: rounds.map((r) => r.posts) },
        { name: t("评论"), color: "var(--accent)", values: rounds.map((r) => r.comments) }, { name: t("点赞"), color: "var(--good)", values: rounds.map((r) => r.votes) }], phaseMarks(d.config))}</div>
      <div class="card"><h2>${t("每个 Agent 的得赞(从高到低)")}</h2>${barChart(agents, "upvotes_received", (r) => (r.cohort === "founder" ? "var(--founder)" : "var(--newcomer)"))}
        <div class="legend"><span><i style="background:var(--founder)"></i>${t("创始")}</span><span><i style="background:var(--newcomer)"></i>${t("新成员")}</span></div></div></div>
    <div class="cols-2" style="margin-top:16px">
      <div class="card" style="padding:0"><h2 style="padding:18px 20px 0">${t("创始说法的扩散")}</h2><div class="table-wrap" style="max-height:380px"><table><thead><tr><th style="padding-left:20px">${t("说法")}</th><th class="num">${t("阶段 1 文本")}</th><th class="num">${t("创始使用者")}</th><th class="num">${t("总使用者")}</th><th class="num">${t("新成员使用者")}</th><th class="num" title="${t("第一次用之前在提示词里见过")}">${t("先见过")}</th><th class="num" style="padding-right:20px" title="${t("第一次用之前没见过:自己想到的")}">${t("自己想到")}</th></tr></thead><tbody>
        ${M.expressions.map((e) => `<tr><td class="mono" style="padding-left:20px">${esc(e.expression)}</td><td class="num">${e.texts ?? "–"}</td><td class="num">${e.founders ?? "–"}</td><td class="num">${e.users}</td><td class="num">${e.newcomer_users}</td><td class="num">${e.newcomer_exposed_first ?? "–"}</td><td class="num" style="padding-right:20px">${e.newcomer_unexposed ?? "–"}</td></tr>`).join("") || `<tr><td colspan="7" class="muted" style="padding-left:20px">${t("没有冻结的说法")}</td></tr>`}</tbody></table></div></div>
      <div class="card"><h2>${t("其他指标")}</h2><table><tbody>
        <tr><td>${t("前 10% Agent 的得赞占比")}</td><td class="num">${pct(D.attention.top10_share_upvotes)}</td></tr>
        <tr><td>${t("前 10% Agent 的被回复占比")}</td><td class="num">${pct(D.attention.top10_share_replies)}</td></tr>
        <tr><td>${t("有回复关系的对子 / 互相回复")}</td><td class="num">${D.reciprocity.pairs_with_replies} / ${D.reciprocity.mutual_pairs}</td></tr>
        <tr><td>${t("开头 4 个词重复的评论")}</td><td class="num">${pct(D.stock_phrases.share_repeated_opening)}</td></tr>
        <tr><td>${t("近似重复的标题对")}</td><td class="num">${D.stock_phrases.near_duplicate_title_pairs}</td></tr>
        ${D.homogeneity ? `<tr><td colspan="2" class="small" style="font-weight:600;padding-top:14px">${t("同质化(词重合,0–1)")}</td></tr>
        <tr><td>${t("同一轮写的文字之间 / 不同轮之间")}</td><td class="num">${num(D.homogeneity.jaccard_same_round, 3)} / ${num(D.homogeneity.jaccard_other_rounds, 3)}</td></tr>
        <tr><td>${t("回复同一条的评论之间 / 回复不同条之间")}</td><td class="num">${num(D.homogeneity.jaccard_same_target, 3)} / ${num(D.homogeneity.jaccard_other_targets, 3)}</td></tr>
        <tr><td>${t("回复同一条的评论开头 4 词相同")}</td><td class="num">${pct(D.homogeneity.same_target_identical_opening)}</td></tr>
        <tr><td>${t("标题前 3 词与别的帖子相同")}</td><td class="num">${pct(D.homogeneity.title_template_share)}</td></tr>` : ""}
        <tr><td>${t("回复与被回复内容的词重合")}</td><td class="num">${num(D.accommodation.similarity_to_parent)}</td></tr>
        <tr><td>${t("对照:与同轮随机一条的词重合")}</td><td class="num">${num(D.accommodation.similarity_to_random)}</td></tr></tbody></table>
        <p class="hint" style="margin-top:8px">${t("Moltbook 参照只作大致对比:规模、时长和成员都不同。")}</p></div></div>
    <div class="card" style="margin-top:16px;padding:0"><h2 style="padding:18px 20px 0">Agent</h2><div class="table-wrap" style="max-height:460px"><table><thead><tr><th style="padding-left:20px">${t("编码")}</th><th>${t("身份")}</th><th>${t("模型")}</th><th class="num">${t("加入")}</th><th class="num">${t("发帖")}</th><th class="num">${t("评论")}</th><th class="num">${t("得赞")}</th><th class="num">${t("被回复")}</th><th class="num" style="padding-right:20px">${t("给出的赞")}</th></tr></thead><tbody>
      ${agents.map((a) => `<tr><td class="mono" style="padding-left:20px">${esc(a.handle)}</td><td>${cohortTag(a.cohort)}</td><td class="small">${esc(a.model)}</td><td class="num">${a.joined}</td><td class="num">${a.posts}</td><td class="num">${a.comments}</td><td class="num">${a.upvotes_received}</td><td class="num">${a.replies_received}</td><td class="num" style="padding-right:20px">${a.upvotes_given}</td></tr>`).join("")}</tbody></table></div></div>`;
}

// ================================================================ runs
async function loadRuns() {
  await refreshRuns();
  const tb = $("#runsTable tbody");
  if (!S.runs.length) { tb.innerHTML = `<tr><td colspan="8">${emptyState("archive", t("还没有运行"), t("在「设计」页开始第一次运行。"))}</td></tr>`; return; }
  tb.innerHTML = S.runs.map((m) => { const frac = m.total_rounds ? m.rounds_done / m.total_rounds : 0;
    return `<tr data-id="${esc(m.run_id)}" style="cursor:pointer" ${m.run_id === S.current ? 'aria-current="true"' : ""}>
      <td style="padding-left:20px"><span class="mono small">${esc(m.run_id)}</span>${m.run_id === S.current ? ` <span class="pill info plain">${t("当前")}</span>` : ""}</td>
      <td class="small">${runKind(m)}</td><td>${statusPill(m)}</td>
      <td style="min-width:120px"><div class="bar"><i style="width:${(100 * frac).toFixed(0)}%"></i></div><div class="xs muted tnum">${t("{a}/{b} 轮", { a: m.rounds_done, b: m.total_rounds })}</div></td>
      <td class="num">${m.calls}</td><td class="num">${fmt$(m.cost)}</td><td class="small">${esc((m.models || []).join(", "))}</td>
      <td style="padding-right:12px"><details class="menu"><summary class="btn ghost" aria-label="${t("更多操作")}">${icon("more")}</summary><div class="items">
        <button data-a="monitor">${t("查看运行")}</button><button data-a="forum">${t("打开论坛")}</button><button data-a="results">${t("查看结果")}</button>
        ${!m.running && m.status !== "done" ? `<button data-a="resume">${t("继续运行")}</button>` : ""}<button data-a="copy">${t("复制设置到「设计」")}</button>
        ${!m.running ? `<button data-a="archive">${t("保存到存档")}</button>` : ""}<a class="btn" href="/api/runs/${esc(m.run_id)}/export.html" target="_blank" rel="noopener">${t("打开论坛网页(可另存)")}</a>
        <a class="btn" href="/api/runs/${esc(m.run_id)}/export.html?download=1">${t("下载论坛网页 (HTML)")}</a>
        <a class="btn" href="/api/runs/${esc(m.run_id)}/download">${t("下载记录 (zip)")}</a>${!m.running ? `<button data-a="delete" class="danger">${t("删除")}</button>` : ""}</div></details></td></tr>`; }).join("");
  $$("#runsTable tbody tr").forEach((tr) => (tr.onclick = (e) => { if (e.target.closest("details.menu")) return; setCurrent(tr.dataset.id); loadRuns(); toast(t("已设为当前运行")); }));
  $$("#runsTable [data-a]").forEach((b) => (b.onclick = async () => {
    const id = b.closest("tr").dataset.id, a = b.dataset.a; b.closest("details").open = false;
    if (["monitor", "forum", "results"].includes(a)) { setCurrent(id); location.hash = "#" + a; return; }
    if (a === "resume") return resumeRun(id);
    if (a === "archive") { const r = await api(`/api/runs/${id}/archive`, { method: "POST" }); toast(t("已保存到 {p}", { p: r.path })); loadArchives(); return; }
    if (a === "copy") { const d = await api(`/api/runs/${id}`); S.cfg = { ...S.meta.default_config, ...d.config }; saveDraft(); fillDesign(); estimateSoon(); location.hash = "#design"; toast(t("已载入这次运行的设置。可以在流程表里换模型做对照。")); return; }
    if (a === "delete" && (await confirmDialog(t("删除运行"), `<p>${t("永久删除 {r} 的全部记录?这一步不能撤销。", { r: `<span class="mono">${esc(id)}</span>` })}</p>`, t("删除")))) { await api(`/api/runs/${id}`, { method: "DELETE" }); toast(t("已删除")); loadRuns(); }
  }));
  document.addEventListener("click", (e) => $$("details.menu[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; }), { once: true });
  loadArchives();
  $("#importZip").onchange = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    try {
      const r = await fetch("/api/runs/import", { method: "POST", headers: { "content-type": "application/zip" }, body: file });
      const d = await r.json(); if (!r.ok) throw new Error(d.detail || r.statusText);
      setCurrent(d.run_id); toast(t("已导入为 {r},已设为当前运行", { r: d.run_id })); loadRuns();
    } catch (err) { toast(t("导入失败:{e}", { e: err.message })); }
    e.target.value = "";
  };
}

async function loadArchives() {
  const d = await api("/api/archives"), tb = $("#archiveTable tbody");
  $("#archiveDir").dataset.dir = d.dir;
  tb.innerHTML = d.archives.length ? d.archives.map((a) => `<tr><td class="mono small" style="padding-left:20px">${esc(a.name)}</td><td class="mono small">${esc(a.run_id || "–")}</td>
      <td>${a.broken ? `<span class="pill bad plain">${t("损坏")}</span>` : esc(t(STATUS[a.status]?.[1] || a.status || "–"))}</td><td class="num">${a.cost != null ? fmt$(a.cost) : "–"}</td>
      <td class="small">${esc(a.saved)}</td><td class="num small">${(a.bytes / 1e6).toFixed(1)} MB</td>
      <td style="padding-right:12px">${a.broken ? "" : `<button class="btn ghost xs" data-restore="${esc(a.name)}">${t("恢复到平台")}</button>`}</td></tr>`).join("")
    : `<tr><td colspan="7" class="muted small" style="padding-left:20px">${t("还没有存档。在上面任一运行的菜单里点「保存到存档」。")} <span class="mono">${esc(d.dir)}</span></td></tr>`;
  $$("#archiveTable [data-restore]").forEach((b) => (b.onclick = async () => {
    const r = await api(`/api/archives/${encodeURIComponent(b.dataset.restore)}/restore`, { method: "POST" });
    setCurrent(r.run_id); toast(t("已恢复为 {r},已设为当前运行", { r: r.run_id })); loadRuns();
  }));
}

// ================================================================ models
async function loadModels() {
  S.meta = await api("/api/meta"); keyState();
  $("#keyBox").innerHTML = S.meta.key_set ? `<div class="note good">${t("密钥已设置。要更换,在下面粘贴新的密钥。")}</div>` : `<div class="note warn">${t("还没有密钥。粘贴后保存;或在启动前设置环境变量 ANTHROPIC_API_KEY。")}</div>`;
  $("#priceTable tbody").innerHTML = Object.entries(S.meta.prices).filter(([m]) => m !== "mock").map(([m, p]) => `<tr><td class="mono small">${esc(m)}</td>
    <td><input type="number" step="0.01" min="0" value="${p ? p[0] : ""}" data-m="${esc(m)}" aria-label="${t("{m} 输入价格", { m: esc(m) })}"></td>
    <td><input type="number" step="0.01" min="0" value="${p ? p[1] : ""}" data-m="${esc(m)}" aria-label="${t("{m} 输出价格", { m: esc(m) })}"></td>
    <td><button class="ghost" data-save="${esc(m)}">${t("保存")}</button></td></tr>`).join("");
  $$("[data-save]").forEach((b) => (b.onclick = () => busy(b, async () => { const ins = $$(`input[data-m="${CSS.escape(b.dataset.save)}"]`);
    await api("/api/prices", { method: "POST", body: { model: b.dataset.save, input: +ins[0].value, output: +ins[1].value } }); toast(t("已保存价格")); estimateSoon(); })));
}
function keyState() { const k = $("#keyState"); k.className = "pill " + (S.meta.key_set ? "good" : "warn"); k.textContent = t(S.meta.key_set ? "密钥已设置" : "未设置密钥"); }

// ================================================================ init
async function init() {
  setTheme(store.get("fm-theme") || "system");
  I18N.setLang(I18N.lang);
  $$("[data-lang-set]").forEach((b) => { b.classList.toggle("on", b.dataset.langSet === I18N.lang); b.onclick = () => setLang(b.dataset.langSet); });
  $$("[data-theme-set]").forEach((b) => (b.onclick = () => setTheme(b.dataset.themeSet)));
  S.meta = await api("/api/meta"); keyState();
  let draft = null; try { draft = JSON.parse(store.get(DRAFT)); } catch (e) { draft = null; }
  const dc = S.meta.default_config;
  S.cfg = draft ? { ...dc, ...draft, feed: { ...dc.feed, ...(draft.feed || {}) }, switches: { ...dc.switches, ...(draft.switches || {}) } } : dc;
  S.cfg.feed.comments_per_post = null;  // pre-v0.3 drafts: comments are now newest + most upvoted + random
  if (store.get("fm-draft-ver") !== "3.1" && store.get("fm-draft-ver") !== "4") {  // v0.3.1 defaults
    S.cfg.switches.tell_ai = dc.switches.tell_ai; S.cfg.opening = dc.opening;
  }
  if (store.get("fm-draft-ver") === "4") { S.cfg.opening = dc.opening; S.cfg.order = { ...dc.order, ...(S.cfg.order || {}), opening_together: true }; store.set("fm-draft-ver", "4.1"); }
  if (store.get("fm-draft-ver") !== "4" && store.get("fm-draft-ver") !== "4.1") {  // v0.4: heartbeat, in turn, two-step, updates
    Object.assign(S.cfg, { schedule: dc.schedule, order: dc.order, visit: dc.visit });
    S.cfg.switches = { ...S.cfg.switches, updates: dc.switches.updates };
    S.cfg.memory = { ...dc.memory, ...(S.cfg.memory || {}), own_posts: dc.memory.own_posts };
    S.cfg.boards = { ...dc.boards, ...(S.cfg.boards || {}), order: dc.boards.order, note: dc.boards.note };
    S.cfg.opening = dc.opening;
    store.set("fm-draft-ver", "4.1");
  }
  if (store.get("fm-draft-ver") !== "4.3") {  // v0.4.3: the post cue is part of the main condition
    S.cfg.switches = { ...S.cfg.switches, post_hint: true }; S.cfg.opening = S.cfg.opening ?? dc.opening; store.set("fm-draft-ver", "4.3");
  }
  await refreshRuns();
  fillDesign(); estimateSoon(); followCurrent();
  $("#runPick").onchange = (e) => { setCurrent(e.target.value); if (["monitor", "forum", "results"].includes(S.page)) show(S.page); };
  $("#addPhase").onclick = () => { S.cfg.phases.push({ name: "phase " + (S.cfg.phases.length + 1), add: [{ n: 0, model: S.cfg.phases[0].add[0].model }], rounds: 10 }); changed(true); };
  $("#addGroup").onclick = () => { S.cfg.phases[S.cfg.phases.length - 1].add.push({ n: 5, model: "claude-sonnet-5-5" }); changed(true); };
  $("#resetPhases").onclick = () => { S.cfg.phases = JSON.parse(JSON.stringify(dc.phases)); changed(true); };
  $("#addComm").onclick = () => { S.cfg.communities.push({ name: "introductions", description: "new members say hello" }); changed(true); };
  $$("[data-reset]").forEach((b) => (b.onclick = () => { const k = b.dataset.reset; S.cfg.prompts[k] = "default"; $("#p-" + k).value = S.meta.default_prompts[k]; changed(); }));
  $("#previewBtn").onclick = (e) => busy(e.currentTarget, async () => {
    try { const r = await api("/api/preview", { method: "POST", body: { config: S.cfg } });
      const mark = (txt) => (r.inserted || []).reduce((h, s) => h.split(esc(s)).join(`<mark class="ins">${esc(s)}</mark>`), esc(txt));
      $("#previewOut").innerHTML = `${r.guard.length ? `<div class="note bad" style="margin-top:10px">${t("禁用词:")}${r.guard.map((h) => esc(h.word)).join(", ")}</div>` : ""}
        <p class="small muted" style="margin-top:12px"><mark class="ins">${t("黄色")}</mark> ${t("= 由开关插入的句子。论坛内容是虚构的示例。")}</p>
        <div class="cols-2" style="margin-top:8px"><div><h3>System prompt</h3><pre class="prompt">${mark(r.system)}</pre></div>
        <div>${r.nav ? `<h3>${t("第一步:选择去哪里")}</h3><pre class="prompt">${mark(r.nav)}</pre>` : ""}<h3>${t(r.nav ? "第二步:看帖子并行动" : "访问提示词")}</h3><pre class="prompt">${mark(r.user)}</pre></div></div>`;
    } catch (err) { $("#previewOut").innerHTML = `<div class="errors">${esc(err.message)}</div>`; } });
  $("#exportCfg").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(S.cfg, null, 2)], { type: "application/json" })); a.download = (S.cfg.name || "fake-moltbook") + ".json"; a.click(); };
  $("#importCfg").onclick = () => $("#importFile").click();
  $("#importFile").onchange = async (e) => { try { S.cfg = { ...dc, ...JSON.parse(await e.target.files[0].text()) }; fillDesign(); changed(); toast(t("已导入设置")); } catch (err) { toast(t("文件无法读取")); } };
  $("#keySave").onclick = (e) => busy(e.currentTarget, async () => { try { await api("/api/key", { method: "POST", body: { key: $("#keyInput").value } }); $("#keyInput").value = ""; await loadModels(); toast(t("密钥已保存到本机 .env")); estimateSoon(); renderSteps(); } catch (err) { toast(err.message); } });
  $("#addModel").onclick = () => { const m = $("#newModel").value.trim(); if (!m) return; api("/api/prices", { method: "POST", body: { model: m, input: 0, output: 0 } }).then(async () => { $("#newModel").value = ""; await loadModels(); toast(t("已添加,请填写价格")); }); };
  $("#scrim").onclick = closeDrawer; $("#drawerClose").onclick = closeDrawer;
  setInterval(() => { if (!S.es && S.runs.some((m) => m.running)) refreshRuns(); }, 5000);
  route();
}
window.addEventListener("DOMContentLoaded", () => init().catch((e) => document.body.insertAdjacentHTML("afterbegin", `<div class="note bad" style="margin:12px">${t("无法连接后端:{e}", { e: esc(e.message) })}</div>`)));
