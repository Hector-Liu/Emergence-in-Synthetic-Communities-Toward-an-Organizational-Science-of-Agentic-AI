"use strict";
// Forum pages: a Reddit-style reader for people, and each agent's own view of a visit.
// Routes: #forum · #forum/t/<post>[/<comment>] · #forum/u/<handle> · #forum/u/<handle>/v/<round> · #forum/activity
/* global S, $, $$, esc, t, api, icon, debounce, cohortTag, refreshRuns, currentManifest, emptyState, fmt$ */

const FO = { nav: 0, run: null, detail: null, data: null, round: null, live: true, sort: "hot", cohort: "", board: "", q: "", page: 1,
  hl: true, csort: "old", hits: 30, acts: null, akind: "", aq: "", apage: 1, ptab: "items", vtab: "prompt" };
const SLOT = { new: "最新", hot: "最热", other_hot: "他版最热", random: "随机", random_seeded: "随机·创始说法" };
const CSLOT = { new: "最新", top: "最高赞", random: "随机" };
const go = (h) => { location.hash = h; };
const handleLink = (h, cohort) => `<a class="handle" href="#forum/u/${esc(h)}">${esc(h)}</a>${cohort ? cohortTag(cohort) : ""}`;

// ---------------------------------------------------------------- expression highlighting
function exprRegex() {
  if (FO._re !== undefined) return FO._re;
  const ex = (FO.detail?.expressions?.expressions || []).map((e) => e.text).filter((x) => !x.includes("'"));
  FO._re = ex.length ? new RegExp("\\b(" + ex.sort((a, b) => b.length - a.length).map((x) => x.split(" ").map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[^a-z0-9_]+")).join("|") + ")\\b", "gi") : null;
  return FO._re;
}
function rich(text) {
  let s = esc(text);
  const re = FO.hl ? exprRegex() : null;
  if (re) s = s.replace(re, (m) => `<mark class="expr" title="${esc(t("创始说法"))}">${m}</mark>`);
  if (FO.q && S.page === "forum") { const k = esc(FO.q); const i = s.toLowerCase().indexOf(k.toLowerCase()); if (i >= 0 && !s.slice(0, i).includes("<mark")) s = s.slice(0, i) + "<mark>" + s.slice(i, i + k.length) + "</mark>" + s.slice(i + k.length); }
  return s;
}

// a piece of text around the first match, with the match marked
function snippet(text, q) {
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return esc(text.length > 200 ? text.slice(0, 200) + "…" : text);
  const a = Math.max(0, i - 80), b = Math.min(text.length, i + q.length + 160);
  return (a > 0 ? "…" : "") + esc(text.slice(a, i)) + "<mark>" + esc(text.slice(i, i + q.length)) + "</mark>" + esc(text.slice(i + q.length, b)) + (b < text.length ? "…" : "");
}
// every post, update and comment that contains the search text, oldest first, each linking to where it sits
function searchHits(f, q) {
  const has = (x) => String(x || "").toLowerCase().includes(q), out = [];
  for (const p of f.posts) {
    if (has(p.title) || has(p.body) || has(p.author) || p.id === q) out.push({ kind: "post", p, round: p.round, author: p.author, cohort: p.cohort, id: p.id, text: has(p.title) ? p.title : p.body, href: `#forum/t/${p.id}` });
    (p.updates || []).forEach((u) => { if (has(u.body)) out.push({ kind: "update", p, round: u.round, author: p.author, cohort: p.cohort, id: p.id, text: u.body, href: `#forum/t/${p.id}` }); });
    p.comments.forEach((c) => { if (has(c.body) || has(c.author) || c.id === q) out.push({ kind: "comment", p, round: c.round, author: c.author, cohort: c.cohort, id: c.id, text: c.body, href: `#forum/t/${p.id}/${c.id}` }); });
  }
  return out.sort((a, b) => a.round - b.round || +a.id.slice(2) - +b.id.slice(2));
}
function hitsHtml(hits, q) {
  if (!q) return "";
  const kind = { post: t("帖子"), update: t("更新"), comment: t("评论") };
  const rows = hits.slice(0, FO.hits).map((h) => `<a class="hit" href="${h.href}"><div class="meta xs">${esc(h.author)}${h.cohort ? cohortTag(h.cohort) : ""}<span>· ${t("第 {r} 轮", { r: h.round })}</span><span class="mono faint">${h.id}</span><span class="faint">· ${kind[h.kind]} · ${t("在「{t}」", { t: esc(h.p.title.length > 40 ? h.p.title.slice(0, 40) + "…" : h.p.title) })}</span></div>
      <div class="small">${snippet(h.text, q)}</div></a>`).join("");
  return `<div class="card hits"><div class="row between"><b>${t("找到 {n} 处,按时间先后排列", { n: hits.length })}</b><span class="xs muted">${t("点一条跳到它在讨论串里的位置")}</span></div>
    ${rows || `<p class="muted small" style="margin:8px 0 0">${t("没有找到")}</p>`}
    ${hits.length > FO.hits ? `<button class="btn ghost xs" id="hits-more" style="margin-top:8px">${t("再显示 {n} 条", { n: Math.min(30, hits.length - FO.hits) })}</button>` : ""}</div>`;
}

// ---------------------------------------------------------------- entry
async function loadForum(rest = []) {
  const tok = ++FO.nav;  // a newer navigation makes this one stale: it must not draw over the new page
  await refreshRuns();
  if (tok !== FO.nav) return;
  const m = currentManifest(), box = $("#fo");
  if (!m) { box.innerHTML = emptyState("chat", t("还没有运行"), t("先在「设计」页开始一次运行。")); return; }
  const fresh = FO.run !== m.run_id;
  if (fresh) { Object.assign(FO, { run: m.run_id, detail: null, data: null, round: null, acts: null, _re: undefined, page: 1, apage: 1 }); }
  if (!FO.detail || m.running) { FO.detail = await api(`/api/runs/${m.run_id}`); FO._re = undefined; }
  if (tok !== FO.nav) return;
  // without a prior run the frozen list is full of stock phrases, so highlighting starts off
  if (fresh) FO.hl = !!FO.detail.config?.prior_run;
  const [kind, a, b, c] = rest;
  if (kind === "t" && a) return renderThread(a, b);
  if (kind === "u" && a && b === "v" && c) return renderVisit(a, +c);
  if (kind === "u" && a) return renderProfile(a);
  if (kind === "activity") return renderActivity();
  return renderFront();
}
function forumLive() {
  if (S.page !== "forum" || !FO.live || (location.hash.split("/")[1] || "") !== "") return;
  clearTimeout(FO._lt); FO._lt = setTimeout(() => { FO.data = null; FO.round = null; FO.detail = null; loadForum([]); }, 1500);
}
async function getForum(round) {
  if (!FO.data || FO.data.round !== round) FO.data = await api(`/api/runs/${FO.run}/forum${round ? `?round=${round}` : ""}`);
  return FO.data;
}
const crumb = (html) => `<div class="crumb">${html}</div>`;
const backToForum = () => `<a href="#forum" class="btn ghost">${icon("chat")}${t("返回论坛")}</a>`;

// ---------------------------------------------------------------- front page
// an author's updates, shown under the post body
function updatesHtml(p) {
  return (p.updates || []).map((u) => `<div class="upd"><span class="xs muted">${t("更新 · 第 {r} 轮", { r: u.round })}</span><div class="body">${rich(u.body)}</div></div>`).join("");
}

// the two most upvoted comments under a post card, so the list already shows the conversation
function preview(p) {
  const top = p.comments.slice().sort((a, b) => b.upvotes - a.upvotes || +a.id.slice(2) - +b.id.slice(2)).slice(0, 2);
  if (!top.length) return "";
  return `<div class="cprev">${top.map((c) => `<a class="cprev-item" href="#forum/t/${p.id}/${c.id}"><span class="handle">${esc(c.author)}</span> <span class="faint">▲ ${c.upvotes}</span> ${esc(c.body.length > 160 ? c.body.slice(0, 160) + "…" : c.body)}</a>`).join("")}</div>`;
}

async function renderFront() {
  const tok = FO.nav;
  const m = currentManifest(), last = Math.max(1, m.rounds_done || 1);
  if (FO.live || FO.round == null || FO.round > last) FO.round = last;
  const f = await getForum(FO.round);
  if (tok !== FO.nav) return;
  const tabs = `<div class="seg" role="tablist"><button class="on" role="tab" aria-selected="true">${t("帖子")}</button><button role="tab" aria-selected="false" data-go="#forum/activity">${t("动态")}</button></div>`;
  $("#pageActions").innerHTML = `<a class="btn ghost" href="/api/runs/${esc(FO.run)}/export.html?download=1">${t("导出论坛网页")}</a><a class="btn ghost" href="/api/runs/${esc(FO.run)}/export.md">${t("导出 Markdown")}</a><a class="btn ghost" href="/api/runs/${esc(FO.run)}/export.csv">${t("导出 CSV")}</a>`;
  const boards = f.boards || [];
  if (FO.board && !boards.some((b) => b.name === FO.board)) FO.board = "";
  let posts = f.posts.filter((p) => (!FO.cohort || p.cohort === FO.cohort) && (!FO.board || p.community === FO.board));
  const q = FO.q.toLowerCase(), has = (s) => String(s).toLowerCase().includes(q);
  const hits = q ? searchHits(f, q) : [];
  if (q) posts = posts.filter((p) => has(p.title) || has(p.body) || has(p.author) || p.comments.some((c) => has(c.body) || has(c.author)));
  const key = { hot: (p) => p.upvotes + p.n_comments, new: (p) => p.round * 1e5 + +p.id.slice(2), top: (p) => p.upvotes, comments: (p) => p.n_comments }[FO.sort];
  posts = posts.slice().sort((a, b) => key(b) - key(a) || +b.id.slice(2) - +a.id.slice(2));
  const per = 15, pages = Math.max(1, Math.ceil(posts.length / per)); FO.page = Math.min(FO.page, pages);
  const shown = posts.slice((FO.page - 1) * per, FO.page * per), multi = new Set(f.posts.map((p) => p.community)).size > 1;
  const sortSeg = [["hot", "热门"], ["new", "最新"], ["top", "最多赞"], ["comments", "最多评论"]].map(([k, l]) => `<button data-sort="${k}" class="${FO.sort === k ? "on" : ""}">${t(l)}</button>`).join("");
  const cohSeg = [["", "全部"], ["founder", "创始"], ["newcomer", "新成员"]].map(([k, l]) => `<button data-coh="${k}" class="${FO.cohort === k ? "on" : ""}">${t(l)}</button>`).join("");
  const cards = shown.map((p) => `<article class="rpost" data-href="#forum/t/${p.id}" tabindex="0" aria-label="${esc(p.title)}">
      <div class="vote" title="${t("得赞")}">${icon("up")}<span class="tnum">${p.upvotes}</span></div>
      <div class="rpost-main"><div class="meta">${multi ? `<span>${esc(p.community)}</span>·` : ""}${handleLink(p.author, p.cohort)}<span>· ${t("第 {r} 轮", { r: p.round })}</span><span class="mono faint">${p.id}</span></div>
        <a class="title" href="#forum/t/${p.id}">${rich(p.title)}</a>
        <div class="body clamp">${rich(p.body)}</div>${(p.updates || []).length ? `<span class="pill info plain xs">${t("{n} 次更新", { n: p.updates.length })}</span>` : ""}
        ${preview(p)}
        <div class="actions"><a class="btn ghost xs" href="#forum/t/${p.id}">${icon("chat")}${t("{n} 条评论", { n: p.n_comments })}</a>
          ${p.voters.length ? `<span class="xs faint">${t("点赞:{v}", { v: esc(p.voters.slice(0, 4).join(", ")) + (p.voters.length > 4 ? " …" : "") })}</span>` : ""}</div></div></article>`).join("");
  const founders = f.agents.filter((a) => a.cohort === "founder").length;
  const top = f.agents.slice().sort((a, b) => b.items - a.items).slice(0, 8);
  const ex = FO.detail?.expressions?.expressions || [];
  $("#fo").innerHTML = `<div class="fo-grid"><div>
      <div class="card fo-bar"><div class="row between">${tabs}<label class="row small" style="gap:6px"><input type="checkbox" id="fo-live" ${FO.live ? "checked" : ""}>${t("跟随最新一轮")}</label></div>
        <div class="row" style="margin-top:10px"><span class="small muted">${t("看第")}</span><input type="range" id="fo-round" min="1" max="${last}" value="${FO.round}" style="flex:1" aria-label="${t("选择轮次")}"><span class="mono small" id="fo-round-l">${FO.round}</span><span class="small muted">${t("轮结束时")}</span></div>
        <div class="toolbar" style="margin-top:10px"><div class="seg" role="group" aria-label="${t("排序")}">${sortSeg}</div><div class="seg" role="group" aria-label="${t("筛选")}">${cohSeg}</div>
          <input type="search" id="fo-q" value="${esc(FO.q)}" placeholder="${t("搜索评论内容、编码或 c_123")}" aria-label="${t("搜索")}"></div></div>
      <p class="small muted" style="margin:12px 2px">${t("第 {r} 轮结束时 · {p} 篇帖子 · {a} 个 Agent", { r: f.round, p: f.posts.length, a: f.agents.length })}${posts.length !== f.posts.length ? " · " + t("筛出 {n} 篇", { n: posts.length }) : ""}</p>
      ${hitsHtml(hits, q)}
      ${cards || emptyState("inbox", q || FO.cohort ? t("没有符合条件的帖子") : t("这一轮之前还没有帖子"), q || FO.cohort ? t("换个关键词或筛选。") : t("把滑块拖到更后面的轮次。"))}
      ${pages > 1 ? `<div class="pager"><button ${FO.page === 1 ? "disabled" : ""} data-pg="${FO.page - 1}">${t("上一页")}</button><span class="small muted tnum">${FO.page} / ${pages}</span><button ${FO.page === pages ? "disabled" : ""} data-pg="${FO.page + 1}">${t("下一页")}</button></div>` : ""}
    </div><aside class="fo-side">
      ${boards.length > 1 ? `<div class="card"><div class="row between"><h2 style="margin:0">${t("版块")}</h2>${FO.board ? `<button class="btn ghost xs" data-board="">${t("全部")}</button>` : ""}</div>
        ${boards.map((b) => `<button class="board-row${FO.board === b.name ? " on" : ""}" data-board="${esc(b.name)}"><span class="row between"><b class="mono small">${esc(b.name)}</b><span class="xs muted tnum">${t("{p} 帖 · {c} 评", { p: b.posts, c: b.comments })}</span></span>
          <span class="xs muted">${b.author ? t("第 {r} 轮由 {h} 创建", { r: b.round, h: esc(b.author) }) + " · " : ""}${esc(b.description)}</span></button>`).join("")}</div>` : ""}
      <div class="card"><h2>${t("论坛")}</h2><dl class="kv"><dt>${t("轮次")}</dt><dd>${f.round} / ${f.last_round}</dd><dt>${t("成员")}</dt><dd>${f.agents.length} (${t("创始")} ${founders})</dd>
        <dt>${t("帖子")}</dt><dd>${f.posts.length}</dd><dt>${t("评论")}</dt><dd>${f.posts.reduce((s, p) => s + p.n_comments, 0)}</dd>
        <dt>${t("点赞")}</dt><dd>${f.posts.reduce((s, p) => s + p.upvotes + p.comments.reduce((a, c) => a + c.upvotes, 0), 0)}</dd></dl>
        <p class="hint" style="margin-top:10px">${t("点编码进入个人主页,能看到它每一次访问时眼中的论坛。")}</p></div>
      <div class="card"><h2>${t("最活跃")}</h2>${top.map((a) => `<div class="row between small" style="padding:3px 0">${handleLink(a.handle, a.cohort)}<span class="muted tnum">${t("{n} 条", { n: a.items })}</span></div>`).join("") || `<p class="muted small">–</p>`}</div>
      <div class="card"><div class="row between"><h2 style="margin:0">${t("创始说法")}</h2><label class="row xs" style="gap:4px"><input type="checkbox" id="fo-hl" ${FO.hl ? "checked" : ""}>${t("高亮")}</label></div>
        ${ex.length ? `<div class="xs muted" style="margin:6px 0">${t("阶段 1 结束时冻结,共 {n} 个", { n: ex.length })}</div>` + ex.slice(0, 14).map((e) => `<div class="row between small" style="padding:2px 0"><mark class="expr">${esc(e.text)}</mark><span class="faint tnum">${e.texts}</span></div>`).join("") : `<p class="hint" style="margin-top:8px">${t("阶段 1 结束时冻结")}</p>`}</div>
    </aside></div>`;
  $$("#fo [data-go]").forEach((b) => (b.onclick = () => go(b.dataset.go)));
  $$("#fo [data-sort]").forEach((b) => (b.onclick = () => { FO.sort = b.dataset.sort; FO.page = 1; renderFront(); }));
  $$("#fo [data-coh]").forEach((b) => (b.onclick = () => { FO.cohort = b.dataset.coh; FO.page = 1; renderFront(); }));
  $$("#fo [data-board]").forEach((b) => (b.onclick = () => { FO.board = b.dataset.board; FO.page = 1; renderFront(); }));
  $$("#fo [data-pg]").forEach((b) => (b.onclick = () => { FO.page = +b.dataset.pg; renderFront(); window.scrollTo({ top: 0 }); }));
  $$("#fo .rpost").forEach((el) => {
    el.onclick = (e) => { if (!e.target.closest("a,button")) go(el.dataset.href); };
    el.onkeydown = (e) => { if (e.key === "Enter" && e.target === el) go(el.dataset.href); };
  });
  if ($("#hits-more")) $("#hits-more").onclick = () => { FO.hits += 30; renderFront(); };
  $("#fo-q").oninput = debounce((e) => { FO.q = e.target.value.trim(); FO.page = 1; FO.hits = 30; renderFront().then(() => { const i = $("#fo-q"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 300);
  $("#fo-round").oninput = (e) => ($("#fo-round-l").textContent = e.target.value);
  $("#fo-round").onchange = (e) => { FO.round = +e.target.value; FO.live = FO.round === last; FO.page = 1; renderFront(); };
  $("#fo-live").onchange = (e) => { FO.live = e.target.checked; renderFront(); };
  $("#fo-hl").onchange = (e) => { FO.hl = e.target.checked; renderFront(); };
}

// ---------------------------------------------------------------- thread
async function renderThread(pid, focus) {
  const tok = FO.nav;
  const f = await getForum(FO.round || null);
  let p = f.posts.find((x) => x.id === pid);
  if (!p) { FO.data = null; const full = await getForum(null); p = full.posts.find((x) => x.id === pid); }
  if (tok !== FO.nav) return;
  if (!p) { $("#fo").innerHTML = emptyState("inbox", t("找不到这个帖子"), pid); return; }
  const kids = {};
  p.comments.forEach((c) => (kids[c.parent] = kids[c.parent] || []).push(c));
  const order = (arr) => (FO.csort === "top" ? arr.slice().sort((a, b) => b.upvotes - a.upvotes || +a.id.slice(2) - +b.id.slice(2)) : arr);
  // indentation stops at MAX_DEPTH (full-1 had chains 48 deep, which squeezed comments to nothing);
  // deeper replies line up under their ancestor and name what they answer
  const MAX_DEPTH = 6;
  const node = (c, depth = 1) => {
    const sub = order(kids[c.id] || []), deep = depth >= MAX_DEPTH;
    const subHtml = sub.map((x) => node(x, depth + 1)).join("");
    return `<div class="cnode${c.id === focus ? " focus" : ""}" id="${c.id}"><div class="cmeta"><button class="fold" aria-expanded="true" aria-label="${t("折叠")}">−</button>
      ${handleLink(c.author, c.cohort)}${c.author === p.author ? `<span class="tag op">${t("楼主")}</span>` : ""}${depth > MAX_DEPTH ? `<span class="reply-to">↳ ${t("回复 {h}", { h: esc(c.parent_author || "") })} <a class="mono" href="#forum/t/${p.id}/${c.parent}">${c.parent}</a></span>` : ""}<span>· ${t("第 {r} 轮", { r: c.round })}</span><span>· ▲ ${c.upvotes}</span><span class="mono faint">${c.id}</span>${sub.length ? `<span class="faint">· ${t("{n} 条回复", { n: sub.length })}</span>` : ""}</div>
      <div class="cbody">${rich(c.body)}</div>${c.voters.length ? `<div class="xs faint" style="margin-top:2px">${t("点赞:{v}", { v: esc(c.voters.join(", ")) })}</div>` : ""}
      ${sub.length && !deep ? `<div class="children">${subHtml}</div>` : ""}</div>${sub.length && deep ? subHtml : ""}`;
  };
  $("#pageActions").innerHTML = "";
  $("#fo").innerHTML = `${crumb(backToForum())}<div class="reader">
    <article class="rpost lg"><div class="vote">${icon("up")}<span class="tnum">${p.upvotes}</span></div><div class="rpost-main">
      <div class="meta">${handleLink(p.author, p.cohort)}<span>· ${t("第 {r} 轮", { r: p.round })}</span><span class="mono faint">${p.id}</span></div>
      <h2 class="title" style="margin:6px 0">${rich(p.title)}</h2><div class="body">${rich(p.body)}</div>${updatesHtml(p)}
      ${p.voters.length ? `<div class="xs faint" style="margin-top:8px">${t("点赞:{v}", { v: esc(p.voters.join(", ")) })}</div>` : ""}</div></article>
    <div class="row between" style="margin:16px 2px 6px;flex-wrap:wrap;gap:8px"><b>${t("{n} 条评论", { n: p.comments.length })}${FO.round && FO.round < (FO.data?.last_round || 0) ? ` <span class="xs muted">${t("(截至第 {r} 轮)", { r: FO.round })}</span>` : ""}</b>
      <div class="row" style="gap:6px"><span class="row tfind"><input type="search" id="th-q" value="${esc(FO.q)}" placeholder="${t("在本帖内查找")}" aria-label="${t("在本帖内查找")}"><button class="btn ghost xs" id="th-prev" aria-label="${t("上一个")}">↑</button><button class="btn ghost xs" id="th-next" aria-label="${t("下一个")}">↓</button><span class="xs muted tnum" id="th-n"></span></span><button class="btn ghost xs" id="fold-all">${t("全部折叠")}</button><button class="btn ghost xs" id="unfold-all">${t("全部展开")}</button>
      <div class="seg" role="group" aria-label="${t("排序")}"><button data-cs="old" class="${FO.csort === "old" ? "on" : ""}">${t("最早")}</button><button data-cs="top" class="${FO.csort === "top" ? "on" : ""}">${t("最多赞")}</button></div></div></div>
    <div class="tree card">${order(kids[p.id] || []).map(node).join("") || `<p class="muted small">${t("没有评论")}</p>`}</div></div>`;
  $$("#fo [data-cs]").forEach((b) => (b.onclick = () => { FO.csort = b.dataset.cs; renderThread(pid, focus); }));
  const setFold = (n, on) => { n.classList.toggle("folded", on); const b = n.querySelector(":scope > .cmeta > .fold"); b.textContent = on ? "+" : "−"; b.setAttribute("aria-expanded", String(!on)); };
  $$("#fo .fold").forEach((b) => (b.onclick = () => { const n = b.closest(".cnode"); setFold(n, !n.classList.contains("folded")); }));
  // fold all = keep the top-level comments, hide what is under them
  $("#fold-all").onclick = () => $$("#fo .tree > .cnode").forEach((n) => setFold(n, true));
  $("#unfold-all").onclick = () => $$("#fo .cnode").forEach((n) => setFold(n, false));
  // find in this thread: matching comments in page order; arrows step through them, opening folded branches
  let found = [], at = -1;
  const show = (n) => {
    $$("#fo .cnode.focus").forEach((x) => x.classList.remove("focus"));
    for (let a = n; a; a = a.parentElement?.closest(".cnode")) if (a.classList.contains("folded")) setFold(a, false);
    n.classList.add("focus"); n.scrollIntoView({ block: "center" });
  };
  const find = () => {
    const q = $("#th-q").value.trim().toLowerCase();
    found = q ? $$("#fo .cnode").filter((n) => n.querySelector(":scope > .cbody").textContent.toLowerCase().includes(q)) : [];
    at = focus ? found.findIndex((n) => n.id === focus) : -1;
    $("#th-n").textContent = q ? t("{i} / {n}", { i: at + 1, n: found.length }) : "";
  };
  const step = (d) => { if (!found.length) return; at = (at + d + found.length) % found.length; show(found[at]); $("#th-n").textContent = t("{i} / {n}", { i: at + 1, n: found.length }); };
  $("#th-q").oninput = debounce(() => { find(); if (found.length && at < 0) step(1); }, 250);
  $("#th-q").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); step(e.shiftKey ? -1 : 1); } };
  $("#th-prev").onclick = () => step(-1);
  $("#th-next").onclick = () => step(1);
  find();
  if (focus) { const n = $("#" + CSS.escape(focus)); if (n) show(n); } else window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------- profile
async function renderProfile(h) {
  const tok = FO.nav;
  const d = await api(`/api/runs/${FO.run}/profile/${h}`), a = d.agent, s = d.stats;
  if (tok !== FO.nav) return;
  const kp = (v, l) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`;
  const mix = (slots) => { const c = {}; slots.forEach((x) => (c[x] = (c[x] || 0) + 1)); return Object.entries(c).map(([k, n]) => `${t(SLOT[k] || k)} ${n}`).join(" · ") || "–"; };
  const act = { post: "发帖", comment: "评论", none: "不动" };
  const items = d.items.map((it) => `<div class="pitem"><div class="meta"><span class="tag ${it.kind === "post" ? "founder" : "newcomer"}">${t(it.kind === "post" ? "帖子" : "评论")}</span>
      <span>${t("第 {r} 轮", { r: it.round })}</span><span>· ▲ ${it.upvotes}</span>${it.kind === "comment" ? `<span>· ${t("回复 {p}", { p: `<a href="#forum/t/${it.post}/${it.id}">${it.parent}</a>` })}${it.parent_author ? " (" + esc(it.parent_author) + ")" : ""}</span>` : `<span>· ${t("{n} 条评论", { n: it.n_comments })}</span>`}</div>
      ${it.kind === "post" ? `<a class="title" href="#forum/t/${it.id}">${rich(it.title)}</a>` : ""}<div class="body clamp">${rich(it.body)}</div>
      <a class="xs" href="#forum/t/${it.kind === "post" ? it.id : it.post + "/" + it.id}">${t("在讨论串中查看")} →</a></div>`).join("") || `<p class="muted small">${t("还没写过东西")}</p>`;
  const visits = `<div class="table-wrap"><table><thead><tr><th class="num">${t("轮")}</th><th>${t("动作")}</th><th>${t("写了")}</th><th class="num">${t("点赞")}</th><th>${t("信息流构成")}</th><th class="num">${t("新回复")}</th><th></th></tr></thead><tbody>
    ${d.visits.map((v) => `<tr data-href="#forum/u/${esc(h)}/v/${v.round}" style="cursor:pointer"><td class="num">${v.round}</td><td>${v.status === "ok" ? esc(t(act[v.action] || v.action)) : `<span class="pill bad plain">${t("无效")}</span>`}</td>
      <td class="mono small">${v.item || "–"}</td><td class="num">${v.upvotes}</td><td class="xs muted">${mix(v.slots)}</td><td class="num">${v.notified}</td>
      <td><a class="btn ghost xs" href="#forum/u/${esc(h)}/v/${v.round}">${icon("eye")}${t("它的视角")}</a></td></tr>`).join("")}</tbody></table></div>`;
  $("#pageActions").innerHTML = "";
  $("#fo").innerHTML = `${crumb(backToForum())}<div class="card"><div class="row"><h2 class="mono" style="margin:0;font-size:20px">${esc(h)}</h2>${cohortTag(a.cohort)}</div>
      <p class="small muted" style="margin:6px 0 14px">${esc(a.model)} · ${t("第 {r} 轮加入", { r: a.joined_round })} · ${t("主版块 {h}", { h: esc(a.home) })}</p>
      <div class="kpis">${kp(s.visits, t("访问"))}${kp(s.posts, t("发帖"))}${kp(s.comments, t("评论"))}${kp(s.nothing, t("不动"))}${kp(s.upvotes_received, t("得赞"))}${kp(s.replies_received, t("被回复"))}${kp(s.upvotes_given, t("给出的赞"))}</div></div>
    <div class="tabs-in" role="tablist" style="margin-top:16px"><button role="tab" data-pt="items" class="${FO.ptab === "items" ? "on" : ""}">${t("发言")} (${d.items.length})</button><button role="tab" data-pt="visits" class="${FO.ptab === "visits" ? "on" : ""}">${t("访问记录")} (${d.visits.length})</button></div>
    <div class="reader">${FO.ptab === "items" ? items : visits}</div>`;
  $$("#fo [data-pt]").forEach((b) => (b.onclick = () => { FO.ptab = b.dataset.pt; renderProfile(h); }));
  $$("#fo tr[data-href]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("a")) go(tr.dataset.href); }));
  window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------- one visit, as the agent saw it
async function renderVisit(h, r) {
  const tok = FO.nav;
  const v = await api(`/api/runs/${FO.run}/view/${h}/${r}`);
  if (tok !== FO.nav) return;
  const up = new Set(v.did.upvoted), target = v.did.wrote?.parent;
  const mark = (id) => `${up.has(id) ? `<span class="did up">${icon("up")}${t("它点了赞")}</span>` : ""}${target === id ? `<span class="did re">${icon("chat")}${t("它回复了这条")}</span>` : ""}`;
  const cls = (id) => (up.has(id) || target === id ? " picked" : "");
  const cm = (c) => `<div class="cmt${cls(c.id)}"><div class="meta">${c.slot ? `<span class="slot ${c.slot === "random" ? "random" : "new"}">${t(CSLOT[c.slot])}</span>` : ""}${handleLink(c.author, c.cohort)}<span>· ▲ ${c.upvotes}</span>${c.parent !== c.post ? `<span>· ${t("回复 {p}", { p: c.parent })}</span>` : ""}<span class="mono faint">${c.id}</span>${mark(c.id)}</div><div class="body">${rich(c.body)}</div></div>`;
  const feed = v.feed.map((x) => `<article class="rpost${cls(x.post.id)}"><div class="vote">${icon("up")}<span class="tnum">${x.post.upvotes}</span></div><div class="rpost-main">
      <div class="meta"><span class="slot ${x.slot}">${t(SLOT[x.slot] || x.slot)}</span>${handleLink(x.post.author, x.post.cohort)}<span>· ${t("第 {r} 轮", { r: x.post.round })}</span><span>· ${t("{n} 条评论", { n: x.post.n_comments })}</span><span class="mono faint">${x.post.id}</span>${mark(x.post.id)}</div>
      <a class="title" href="#forum/t/${x.post.id}">${rich(x.post.title)}</a><div class="body">${rich(x.post.body)}</div>${updatesHtml(x.post)}${x.comments.map(cm).join("")}</div></article>`).join("") || `<p class="muted small">${t("信息流是空的:论坛里还没有别人的帖子。")}</p>`;
  const notes = v.notifications.length ? v.notifications.map(cm).join("") : `<p class="muted small">${t("没有新回复")}</p>`;
  const others = (v.other_threads || []).map((c) => `<div class="cmt${cls(c.id)}"><div class="meta"><span class="slot random">${t("随机")}</span>${handleLink(c.author, c.cohort)}<span>· ${t("在")} <a href="#forum/t/${c.post}/${c.id}">${c.post} “${esc(c.post_title)}”</a></span><span>· ▲ ${c.upvotes}</span><span class="mono faint">${c.id}</span>${mark(c.id)}</div><div class="body">${rich(c.body)}</div></div>`).join("");
  const w = v.did.wrote;
  const wrote = v.status !== "ok" ? `<div class="note bad">${t("这次访问无效:回答两次都不能用。")}</div>` : !w ? `<div class="note">${t("它这次什么都没写。")}</div>`
    : `<div class="meta small">${t(w.kind === "post" ? "发帖" : "评论")} <span class="mono">${w.id}</span>${w.parent ? " · " + t("回复 {p}", { p: w.parent }) : ""}</div>${w.title ? `<b>${rich(w.title)}</b>` : ""}<div class="body" style="margin-top:4px">${rich(w.body)}</div>`;
  const rec = v.memory_on ? v.record.map((it, i) => `<div class="ritem${i >= v.record_full ? " short" : ""}"><span class="mono xs faint">${it.id}</span> <span class="xs muted">${t("第 {r} 轮", { r: it.round })} · ▲ ${it.upvotes}</span>
      <div class="small">${it.kind === "post" ? `<b>${esc(it.title)}</b>` : ""}${i < v.record_full ? `<div class="body">${esc(it.body)}</div>` : ""}</div></div>`).join("") || `<p class="muted small">${t("还没有记录")}</p>` : `<p class="muted small">${t("这次运行关闭了记忆")}</p>`;
  const call = v.calls[v.calls.length - 1];
  const firsts = [1, 2, 0].map((st) => v.calls.find((c) => c.step === st && c.attempt === 0)).filter(Boolean);
  const choseTxt = { all: t("全部版块"), leave: t("离开(什么都没做)"), new_board: t("建一个新版块") };
  const navCard = v.chose ? `<div class="card"><h2>${t("第一步:选择去哪里")}</h2><p class="small">${t("它选择了")} <b class="mono">${esc(choseTxt[v.chose] || v.chose)}</b></p>
    ${(v.nav_boards || []).length ? `<div class="xs muted" style="margin-top:6px">${t("它看到的版块(按显示顺序)")}</div>` + v.nav_boards.map((b) => `<div class="small" style="padding:2px 0"><span class="mono${b.name === v.chose ? " picked" : ""}">${esc(b.name)}</span> <span class="muted">${esc(b.description)}</span></div>`).join("") : ""}</div>` : "";
  const tabs = { prompt: "原始提示词", answer: "模型回答", thinking: "思考摘要", system: "System prompt" };
  const stepHead = (c) => (c.step ? `<div class="xs muted" style="margin:8px 0 4px">${t(c.step === 1 ? "第一步(选择去哪里)" : "第二步(行动)")}</div>` : "");
  const tabBody = !call ? `<p class="muted small">${t("这一轮没有调用记录。")}</p>` : FO.vtab === "prompt" ? firsts.map((c) => `${stepHead(c)}<pre class="prompt">${esc(c.user)}</pre>`).join("") : FO.vtab === "system" ? `<pre class="prompt">${esc(call.system)}</pre>`
    : FO.vtab === "thinking" ? v.calls.map((c) => `${stepHead(c)}<pre class="prompt">${esc((c.thinking || []).join("\n\n") || "–")}</pre>`).join("") + `<p class="hint">${t("思考摘要(服务方生成,不是原始推理)")}</p>`
    : v.calls.map((c) => `<div class="xs muted">${t("第 {n} 次尝试", { n: c.attempt + 1 })} · ${esc(c.stop_reason)} · ${t("入 {a} / 出 {b} token", { a: c.usage?.input_tokens ?? "?", b: c.usage?.output_tokens ?? "?" })} · ${fmt$(c.cost)}</div><pre class="prompt">${esc(c.raw || c.error || "")}</pre>`).join("");
  const nav = `${v.prev ? `<a class="btn ghost" href="#forum/u/${esc(h)}/v/${v.prev}">◀ ${t("上一次访问")}</a>` : ""}${v.next ? `<a class="btn ghost" href="#forum/u/${esc(h)}/v/${v.next}">${t("下一次访问")} ▶</a>` : ""}`;
  $("#pageActions").innerHTML = "";
  $("#fo").innerHTML = `${crumb(`${backToForum()}<a class="btn ghost" href="#forum/u/${esc(h)}">${t("{h} 的主页", { h: esc(h) })}</a><span class="spacer"></span>${nav}`)}
    <div class="note" style="margin-bottom:14px">${t("下面是 {h} 第 {i}/{n} 次访问(第 {r} 轮)时看到的论坛,它只看得到这些。", { h: `<b class="mono">${esc(h)}</b>`, i: v.visit_no, n: v.visits, r: v.round })}
      ${v.did.upvoted.length ? " " + t("它点赞了 {n} 条。", { n: v.did.upvoted.length }) : ""}</div>
    <div class="fo-grid"><div>
      <h3>${t("新回复")}</h3><div class="card">${notes}</div>
      <h3>${t("信息流(按它看到的顺序)")}</h3>${feed}${others ? `<h3>${t("来自其他讨论串")}</h3><div class="card">${others}</div>` : ""}</div>
      <aside class="fo-side">${navCard}<div class="card"><h2>${t("它写的")}</h2>${wrote}</div>
        <div class="card"><h2>${t("它的记录(私有)")}</h2><div class="rec">${rec}</div></div>
        <div class="card"><div class="tabs-in" role="tablist" style="margin-top:0">${Object.entries(tabs).map(([k, l]) => `<button role="tab" data-vt="${k}" class="${FO.vtab === k ? "on" : ""}">${t(l)}</button>`).join("")}</div>${tabBody}</div></aside></div>`;
  $$("#fo [data-vt]").forEach((b) => (b.onclick = () => { FO.vtab = b.dataset.vt; renderVisit(h, r); }));
  window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------- activity stream
async function renderActivity() {
  const tok = FO.nav;
  if (!FO.acts || currentManifest()?.running) FO.acts = await api(`/api/runs/${FO.run}/activity`);
  if (tok !== FO.nav) return;
  const q = FO.aq.toLowerCase();
  let acts = FO.acts.filter((a) => (!FO.akind || a.kind === FO.akind) && (!q || [a.who, a.to, a.title, a.text].some((x) => x && String(x).toLowerCase().includes(q))));
  const rounds = [...new Set(acts.map((a) => a.round))].sort((a, b) => b - a);
  const per = 25, pages = Math.max(1, Math.ceil(rounds.length / per)); FO.apage = Math.min(FO.apage, pages);
  const showR = new Set(rounds.slice((FO.apage - 1) * per, FO.apage * per));
  const line = (a) => {
    if (a.kind === "update") return `${handleLink(a.who, a.cohort)} <span class="muted">${t("更新了帖子")}</span> <a href="#forum/t/${a.id}"><b>${rich(a.title)}</b></a><div class="snip">${rich(a.text)}</div>`;
    if (a.kind === "board") return `${handleLink(a.who, a.cohort)} <span class="muted">${t("创建版块")}</span> <b class="mono">${esc(a.title)}</b><div class="snip">${rich(a.text)}</div>`;
    if (a.kind === "join") return `${handleLink(a.who, a.cohort)} <span class="muted">${t("加入论坛")}</span>`;
    if (a.kind === "post") return `${handleLink(a.who, a.cohort)} <span class="muted">${t("发帖")}</span> <a href="#forum/t/${a.id}"><b>${rich(a.title)}</b></a><div class="snip">${rich(a.text)}</div>`;
    if (a.kind === "comment") return `${handleLink(a.who, a.cohort)} <span class="muted">${t("回复")}</span> ${a.to ? `<a class="handle" href="#forum/u/${esc(a.to)}">${esc(a.to)}</a>` : ""} <a class="mono xs" href="#forum/t/${a.post}/${a.id}">${a.parent}</a><div class="snip">${rich(a.text)}</div>`;
    return `${handleLink(a.who, a.cohort)} <span class="muted">${t("点赞了 {n} 条:", { n: a.targets.length })}</span> <span class="mono xs">${a.targets.join(", ")}</span>`;
  };
  const kinds = [["", "全部"], ["board", "版块"], ["post", "发帖"], ["update", "更新"], ["comment", "评论"], ["votes", "点赞"], ["join", "加入"]].map(([k, l]) => `<button data-ak="${k}" class="${FO.akind === k ? "on" : ""}">${t(l)}</button>`).join("");
  $("#pageActions").innerHTML = "";
  $("#fo").innerHTML = `<div class="card fo-bar reader"><div class="row between"><div class="seg" role="tablist"><button role="tab" data-go="#forum">${t("帖子")}</button><button class="on" role="tab">${t("动态")}</button></div></div>
      <div class="toolbar" style="margin-top:10px"><div class="seg" role="group">${kinds}</div><input type="search" id="fo-aq" value="${esc(FO.aq)}" placeholder="${t("搜索编码或文字")}" aria-label="${t("搜索")}"></div></div>
    <div class="reader">${[...showR].map((r) => `<div class="act-round"><div class="act-head">${t("第 {r} 轮", { r })}</div>${acts.filter((a) => a.round === r).map((a) => `<div class="act ${a.kind}">${line(a)}</div>`).join("")}</div>`).join("") || emptyState("inbox", t("没有符合条件的动态"), "")}
      ${pages > 1 ? `<div class="pager"><button ${FO.apage === 1 ? "disabled" : ""} data-ap="${FO.apage - 1}">${t("更新的")}</button><span class="small muted tnum">${FO.apage} / ${pages}</span><button ${FO.apage === pages ? "disabled" : ""} data-ap="${FO.apage + 1}">${t("更早的")}</button></div>` : ""}</div>`;
  $$("#fo [data-go]").forEach((b) => (b.onclick = () => go(b.dataset.go)));
  $$("#fo [data-ak]").forEach((b) => (b.onclick = () => { FO.akind = b.dataset.ak; FO.apage = 1; renderActivity(); }));
  $$("#fo [data-ap]").forEach((b) => (b.onclick = () => { FO.apage = +b.dataset.ap; renderActivity(); window.scrollTo({ top: 0 }); }));
  $("#fo-aq").oninput = debounce((e) => { FO.aq = e.target.value.trim(); FO.apage = 1; renderActivity().then(() => { const i = $("#fo-aq"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 300);
}
