// LinkGraph frontend: state, API, router, shared side panel.
import { renderCompanies } from "./views/companies.js";
import { renderGraph } from "./views/graph.js";
import { renderPaths } from "./views/paths.js";

export const TIER_LABELS = { 4: "C-level / Owner", 3: "VP / Director / Head", 2: "Manager / Lead / Senior", 1: "Other" };
export const STATUS_BOOST = { "Warm Intro": 15, "Target": 5, "Reached Out": 3 };

export const state = {
  data: null,
  notes: { person: {}, company: {} },
  peopleById: new Map(),
  companiesByKey: new Map(),
  statuses: [],
  logos: {},      // company key -> local logo URL (only after the user fetched logos)
  logoInfo: {},   // company key -> {domain, source, status}
  listeners: new Set(),
};

// ---------- helpers ----------
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
export function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
export function ago(iso) {
  if (!iso) return "";
  const days = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (days < 1) return "today";
  if (days < 31) return `${Math.round(days)}d ago`;
  if (days < 365) return `${Math.round(days / 30)}mo ago`;
  return `${(days / 365).toFixed(1)}y ago`;
}
export function debounce(fn, ms = 120) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
export function personStatus(id) { return state.notes.person[id]?.status || null; }
export function companyStatus(key) { return state.notes.company[key]?.status || null; }
export function effectiveRank(p) {
  const st = personStatus(p.id);
  if (st === "Ignore") return -1;
  return p.rank + (STATUS_BOOST[st] || 0);
}
export function isDM(p) { return p.tier >= 3; }
// Normalize a search string in the same spirit as the backend company key.
export function normQuery(s) {
  return (s || "").normalize("NFKC").toLowerCase().replace(/&/g, " and ").replace(/[^\p{L}\p{N}\s]+/gu, " ").replace(/\s+/g, " ").trim();
}

// ---------- company logos ----------
// Monogram tiles are the default and need no network. A real logo replaces the tile only when
// the user has fetched logos; it always loads from this server, never from the internet.
const SKIP_WORDS = /^(the|as|asa|ab|inc|ltd|llc|gmbh|plc|og|and|of|i)$/i;
export function initials(name) {
  const words = (name || "?").replace(/[^\p{L}\p{N}\s]+/gu, " ").split(/\s+/).filter((w) => w && !SKIP_WORDS.test(w));
  if (!words.length) return "?";
  return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toUpperCase();
}
export function monoColor(key) {
  let h = 0;
  for (const ch of key || "") h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return `hsl(${h % 360} 48% 40%)`;
}
export function companyLogo(key, name, size = 24) {
  const box = `width:${size}px;height:${size}px`;
  const url = state.logos[key];
  if (url) return `<img class="logo" src="${esc(url)}" alt="" style="${box}" loading="lazy">`;
  return `<span class="mono" aria-hidden="true" style="${box};background:${monoColor(key)};font-size:${Math.round(size * 0.4)}px">${esc(initials(name))}</span>`;
}

const TITLE_SYNONYMS = [
  ["cto", "chief technology officer", "chief technical officer", "teknisk direktør"],
  ["ceo", "chief executive officer", "daglig leder", "administrerende direktør", "adm dir"],
  ["cfo", "chief financial officer", "finansdirektør", "økonomidirektør"],
  ["coo", "chief operating officer"],
  ["cio", "chief information officer", "it direktør", "it-direktør"],
  ["ciso", "chief information security officer"],
  ["cpo", "chief product officer"],
  ["cmo", "chief marketing officer"],
  ["cdo", "chief digital officer", "chief data officer"],
  ["cco", "chief commercial officer"],
  ["cro", "chief revenue officer"],
  ["vp", "vice president", "svp", "evp"],
  ["md", "managing director"],
];
function expandQuery(nq) {
  const alts = new Set([nq]);
  for (const group of TITLE_SYNONYMS) {
    if (group.map(normQuery).includes(nq)) group.forEach((g) => alts.add(normQuery(g)));
  }
  return [...alts];
}

// Word-prefix match, so "cto" finds "CTO" and "Chief Technology Officer" but not "Director".
export function matchWords(text, q) {
  const nq = normQuery(q);
  if (!nq) return true;
  const hay = " " + normQuery(text);
  return expandQuery(nq).some((alt) => hay.includes(" " + alt));
}

export function warmthHTML(p) {
  const parts = Object.entries(p.warmth_parts || {}).map(([k, v]) => `${k.replace(/_/g, " ")}: +${v}`).join("\n") || "no interaction data";
  return `<span class="warmth" title="${esc(parts)}"><span class="meter"><i style="width:${p.warmth}%"></i></span>${p.warmth}</span>`;
}
export function statusBadge(status) {
  return status ? `<span class="badge st-${status.replace(/ /g, "-")}">${esc(status)}</span>` : "";
}
export function tierBadge(p) {
  if (p.tier === 4) return `<span class="badge t4">${TIER_LABELS[4]}</span>`;
  if (p.tier === 3) return `<span class="badge dm">${TIER_LABELS[3]}</span>`;
  return "";
}

// ---------- API ----------
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export async function saveNote(kind, key, { status, note, label }) {
  const cur = state.notes[kind][key] || {};
  const body = {
    status: status !== undefined ? status : cur.status || null,
    note: note !== undefined ? note : cur.note ?? null,
    label,
  };
  const r = await api(`/api/notes/${kind}/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify(body) });
  if (r.entry && Object.keys(r.entry).length) state.notes[kind][key] = r.entry;
  else delete state.notes[kind][key];
  emit();
}

export async function setAlias(fromKey, toKey) {
  await api(`/api/aliases/${encodeURIComponent(fromKey)}`, { method: "PUT", body: JSON.stringify({ to: toKey || null }) });
  await loadData();
  route();
  openCompany(toKey && state.companiesByKey.has(toKey) ? toKey : fromKey);
}

export function onChange(fn) { state.listeners.add(fn); return () => state.listeners.delete(fn); }
function emit() { state.listeners.forEach((fn) => fn()); }

async function loadData() {
  const d = await api("/api/data");
  state.data = d;
  state.notes = d.notes;
  state.statuses = d.statuses;
  state.peopleById = new Map(d.people.map((p) => [p.id, p]));
  state.companiesByKey = new Map(d.companies.map((c) => [c.key, c]));
  state.logos = d.logos || {};
  state.logoInfo = d.logo_info || {};
  const s = d.stats;
  document.getElementById("stats").textContent =
    `${s.connections} connections · ${s.companies} companies · ${s.decision_makers} decision-makers · ${s.people_with_messages} with messages`;
}

async function loadSources() {
  const r = await api("/api/sources");
  const sel = document.getElementById("source-select");
  sel.innerHTML = r.candidates.map((c) =>
    `<option value="${esc(c.path)}" ${c.path === r.active ? "selected" : ""}>${esc(c.name)} (${c.kind}, ${fmtDate(new Date(c.mtime * 1000).toISOString())})</option>`).join("");
  if (r.active && !r.candidates.some((c) => c.path === r.active)) {
    sel.insertAdjacentHTML("afterbegin", `<option value="${esc(r.active)}" selected>${esc(r.active)}</option>`);
  }
  if (!r.candidates.length && !r.active) sel.innerHTML = `<option>No export found in ${esc(r.downloads)}</option>`;
}

async function switchSource(path) {
  document.getElementById("view").innerHTML = `<div class="empty">Parsing ${esc(path)}…</div>`;
  try {
    await api("/api/source", { method: "POST", body: JSON.stringify({ path }) });
    await loadData();
    await loadSources();
    closePanel();
    route();
  } catch (e) {
    showError(e);
  }
}

function showError(e) {
  document.getElementById("view").innerHTML = `<div class="error">${esc(e.message || e)}</div>`;
}

// ---------- side panel ----------
const panel = () => document.getElementById("panel");
let panelCtx = null;

export function closePanel() {
  panel().classList.remove("open");
  panel().innerHTML = "";
  panelCtx = null;
  emitSelection();
}
function emitSelection() { document.dispatchEvent(new CustomEvent("lg:selection", { detail: panelCtx })); }

function statusCtl(kind, key, label) {
  const entry = state.notes[kind][key] || {};
  const opts = [`<option value="">— status —</option>`].concat(
    state.statuses.map((s) => `<option ${entry.status === s ? "selected" : ""}>${esc(s)}</option>`)).join("");
  return `<div class="status-ctl" data-kind="${kind}" data-key="${esc(key)}" data-label="${esc(label)}">
    <select class="st">${opts}</select>
    <input class="nt" type="text" placeholder="Note…" value="${esc(entry.note || "")}">
  </div>`;
}

export function bindStatusCtls(root) {
  root.querySelectorAll(".status-ctl").forEach((el) => {
    const { kind, key, label } = el.dataset;
    el.querySelector(".st").addEventListener("change", (e) => saveNote(kind, key, { status: e.target.value || null, label }));
    el.querySelector(".nt").addEventListener("change", (e) => saveNote(kind, key, { note: e.target.value, label }));
    el.addEventListener("click", (e) => e.stopPropagation());
  });
}

export function personCardHTML(p, { showCompany = false } = {}) {
  const st = personStatus(p.id);
  const company = showCompany && p.company_name
    ? `<a href="#" class="go-company co" data-key="${esc(p.company_key)}">${companyLogo(p.company_key, p.company_name, 14)}${esc(p.company_name)}</a>` : "";
  const msgs = p.msg_total
    ? `<a href="#" class="toggle-thread" data-id="${esc(p.id)}">${p.msg_total} message${p.msg_total > 1 ? "s" : ""}</a>` : `<span>no messages</span>`;
  return `<div class="person ${isDM(p) ? "dm" : ""} ${st === "Ignore" ? "ignored" : ""}" data-id="${esc(p.id)}">
    <div class="row1"><span class="name">${esc(p.name)}</span>${tierBadge(p)}${statusBadge(st)}
      ${p.url ? `<a class="small" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer" title="Opens LinkedIn in your browser">profile ↗</a>` : ""}</div>
    <div class="small">${esc(p.position || "—")}${company ? " · " + company : ""}</div>
    <div class="meta"><span>connected ${fmtDate(p.connected_on)}</span><span>warmth ${warmthHTML(p)}</span>${msgs}
      ${p.last_msg ? `<span>last contact ${ago(p.last_msg)}</span>` : ""}
      ${p.invitation ? `<span>${p.invitation.direction === "OUTGOING" ? "I invited" : "they invited"}${p.invitation.has_message ? " (with note)" : ""}</span>` : ""}
      ${p.endorse_given || p.endorse_received ? `<span>endorsements ${p.endorse_given}↑ ${p.endorse_received}↓</span>` : ""}
      ${p.email ? `<span>${esc(p.email)}</span>` : ""}</div>
    ${statusCtl("person", p.id, p.name)}
    <div class="thread" hidden></div>
  </div>`;
}

export function bindPersonCards(root) {
  bindStatusCtls(root);
  root.querySelectorAll(".toggle-thread").forEach((a) => a.addEventListener("click", async (e) => {
    e.preventDefault(); e.stopPropagation();
    const card = a.closest(".person");
    const box = card.querySelector(".thread");
    if (!box.hidden) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<span class="muted small">Loading…</span>`;
    const r = await api(`/api/people/${encodeURIComponent(a.dataset.id)}/messages`);
    box.innerHTML = r.messages.map((m) => `<div class="msg ${m.from_me ? "me" : ""}">
      <span class="when">${esc(m.from)} · ${fmtDate(m.date)}${m.group ? ` · group: ${esc(m.conversation_title || "")}` : ""}</span>${esc(m.subject ? m.subject + "\n" : "")}${esc(m.content)}</div>`).join("")
      || `<span class="muted small">No messages.</span>`;
    box.scrollTop = box.scrollHeight;
  }));
  root.querySelectorAll(".go-company").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation(); openCompany(a.dataset.key);
  }));
}

export function openCompany(key) {
  const c = state.companiesByKey.get(key);
  if (!c) return;
  panelCtx = { type: "company", key };
  const members = c.people.map((id) => state.peopleById.get(id)).sort((a, b) => effectiveRank(b) - effectiveRank(a));
  const dms = members.filter(isDM);
  panel().innerHTML = `<div class="panel-head">
      <button class="close" title="Close">✕</button>
      <h2 class="co">${companyLogo(key, c.name, 36)}<span>${esc(c.name)}</span> ${statusBadge(companyStatus(key))}</h2>
      <div class="small muted">${c.count} connection${c.count > 1 ? "s" : ""} · ${dms.length} decision-maker${dms.length === 1 ? "" : "s"} · ${c.messages} messages
        ${c.is_employer ? ' · <span class="badge emp">your employer</span>' : ""}
        ${c.variants.length > 1 ? `<br>Also listed as: ${c.variants.map(esc).join(", ")}` : ""}</div>
      ${statusCtl("company", key, c.name)}
      <div class="merge-ctl">
        <input class="mg" type="text" list="company-names" placeholder="Merge into another company…">
        <button class="mgb">Merge</button>
        ${c.merged_keys.map((k) => `<button class="unmerge small" data-key="${esc(k)}" title="Split this spelling out again">✕ ${esc(k)}</button>`).join("")}
      </div>
      <div class="merge-ctl domain-ctl" title="Saving a domain downloads its icon from icons.duckduckgo.com">
        <input class="dm" type="text" placeholder="Website for the logo, e.g. acme.no" value="${esc(state.notes.domains?.[key] || state.logoInfo[key]?.domain || "")}">
        <button class="dmb">Set logo</button>
        <span class="small muted">${esc(logoStatusText(key))}</span>
      </div>
      <datalist id="company-names">${state.data.companies.filter((x) => x.key !== key).map((x) => `<option value="${esc(x.name)}">`).join("")}</datalist>
    </div>
    <div class="panel-body">${members.map((p) => personCardHTML(p)).join("")}</div>`;
  wirePanel();
  const el = panel();
  const doMerge = async () => {
    const v = el.querySelector(".mg").value.trim();
    const target = state.data.companies.find((x) => x.name === v) || state.companiesByKey.get(normQuery(v));
    if (!target || target.key === key) { el.querySelector(".mg").setCustomValidity("Pick a company from the list"); el.querySelector(".mg").reportValidity(); return; }
    try { await setAlias(key, target.key); } catch (e) { alert(e.message); }
  };
  el.querySelector(".mgb").addEventListener("click", doMerge);
  el.querySelector(".mg").addEventListener("keydown", (e) => { if (e.key === "Enter") doMerge(); });
  el.querySelector(".mg").addEventListener("input", (e) => e.target.setCustomValidity(""));
  const saveDomain = async () => {
    const v = el.querySelector(".dm").value.trim();
    try {
      const r = await api(`/api/domains/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify({ domain: v || null }) });
      state.notes.domains = state.notes.domains || {};
      if (r.domain) state.notes.domains[key] = r.domain; else delete state.notes.domains[key];
      if (r.entry) state.logoInfo[key] = { domain: r.entry.domain, source: r.entry.source, status: r.entry.status };
      if (r.url) state.logos[key] = r.url;
      emit();
    } catch (e) { alert(e.message); }
  };
  el.querySelector(".dmb").addEventListener("click", saveDomain);
  el.querySelector(".dm").addEventListener("keydown", (e) => { if (e.key === "Enter") saveDomain(); });
  el.querySelectorAll(".unmerge").forEach((b) => b.addEventListener("click", () => setAlias(b.dataset.key, null).then(() => openCompany(key))));
}

export function openPerson(id) {
  const p = state.peopleById.get(id);
  if (!p) return;
  panelCtx = { type: "person", id };
  panel().innerHTML = `<div class="panel-head"><button class="close" title="Close">✕</button>
      <h2>${esc(p.name)}</h2><div class="small muted">${esc(TIER_LABELS[p.tier])}</div></div>
    <div class="panel-body">${personCardHTML(p, { showCompany: true })}</div>`;
  wirePanel();
  const t = panel().querySelector(".toggle-thread");
  if (t) t.click();
}

function wirePanel() {
  const el = panel();
  el.classList.add("open");
  el.querySelector(".close").addEventListener("click", closePanel);
  bindPersonCards(el);
  el.scrollTop = 0;
  emitSelection();
}

// Re-render panel badges after a status change without losing scroll.
onChange(() => {
  if (!panelCtx) return;
  const scroll = panel().scrollTop;
  const openThreads = [...panel().querySelectorAll(".thread:not([hidden])")].map((t) => t.closest(".person").dataset.id);
  if (panelCtx.type === "company") openCompany(panelCtx.key); else openPerson(panelCtx.id);
  panel().scrollTop = scroll;
  openThreads.forEach((id) => panel().querySelector(`.person[data-id="${CSS.escape(id)}"] .toggle-thread`)?.click());
});

// ---------- router ----------
let cleanup = null;
const views = { companies: renderCompanies, graph: renderGraph, paths: renderPaths };

function route() {
  if (!state.data) return;
  const name = (location.hash.replace(/^#\//, "").split("?")[0]) || "companies";
  const view = views[name] ? name : "companies";
  document.querySelectorAll("nav.tabs a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  if (cleanup) { cleanup(); cleanup = null; }
  const root = document.getElementById("view");
  root.className = view === "graph" ? "full" : "";
  root.innerHTML = "";
  cleanup = views[view](root) || null;
}

window.addEventListener("hashchange", route);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel(); });
document.getElementById("source-select").addEventListener("change", (e) => switchSource(e.target.value));
function logoStatusText(key) {
  const i = state.logoInfo[key];
  if (!i) return "";
  if (i.status === "ok") return `logo via ${i.source === "manual" ? "your domain" : i.source}`;
  if (i.status === "no_icon") return `no icon found for ${i.domain}`;
  return "no website found";
}

// "Fetch logos": the one action that sends anything off this machine, so it always asks first.
const logoBtn = document.getElementById("logo-btn");
logoBtn.addEventListener("click", async () => {
  const haveAll = Object.keys(state.logoInfo).length > 0;
  const ok = confirm(
    "Fetch company logos?\n\n" +
    "LinkGraph sends company names (never people) to data.brreg.no and wikidata.org to find each " +
    "company's website, and those domains to icons.duckduckgo.com for the icon. Logos are saved in " +
    "logo-cache/ on this machine, so this runs once.\n\n" +
    (haveAll ? "Companies done before are skipped, except ones with no logo yet, which are tried again." : ""));
  if (!ok) return;
  try {
    await api("/api/logos/fetch", { method: "POST", body: JSON.stringify({ retry_missing: haveAll }) });
  } catch (e) { alert(e.message); return; }
  logoBtn.disabled = true;
  const poll = async () => {
    const s = await api("/api/logos/status");
    logoBtn.textContent = `Logos ${s.done}/${s.total}`;
    if (s.running) { setTimeout(poll, 800); return; }
    logoBtn.disabled = false;
    logoBtn.textContent = "Fetch logos";
    logoBtn.title = `Last run: ${s.found} logos found for ${s.total} companies`;
    await loadData();
    const ctx = panelCtx;
    route();
    if (ctx?.type === "company") openCompany(ctx.key); else if (ctx?.type === "person") openPerson(ctx.id);
  };
  poll();
});

document.getElementById("source-other").addEventListener("click", () => {
  const p = prompt("Path to a LinkedIn export folder or .zip file:");
  if (p) switchSource(p.trim());
});

(async function init() {
  try {
    await loadSources();
    await loadData();
    route();
  } catch (e) {
    showError(e);
  }
})();
