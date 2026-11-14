import {
  state, esc, ago, debounce, openCompany, openPerson, effectiveRank, isDM, personStatus, companyStatus,
  statusBadge, bindStatusCtls, onChange, normQuery, matchWords, TIER_LABELS, warmthHTML,
} from "../app.js";

const ui = { q: "", showIgnored: false };
const PER_COMPANY = 5;

function why(p) {
  const out = [];
  if (p.tier >= 3) out.push(`<span class="badge ${p.tier === 4 ? "t4" : "dm"}">${esc(TIER_LABELS[p.tier])}</span>`);
  else out.push(`<span class="badge">${esc(TIER_LABELS[p.tier])}</span>`);
  if (p.msg_total) out.push(`<span class="badge warm">${p.msg_total} msgs${p.msg_from_them && p.msg_from_me ? ", two-way" : ""}</span>`);
  if (p.last_msg) out.push(`<span class="badge">last contact ${ago(p.last_msg)}</span>`);
  if (p.invitation?.has_message) out.push(`<span class="badge">invite with note</span>`);
  if (p.endorse_given || p.endorse_received) out.push(`<span class="badge">endorsements</span>`);
  return out.join("");
}

function pathHTML(p) {
  const st = personStatus(p.id);
  const entry = state.notes.person[p.id] || {};
  return `<div class="path" data-id="${esc(p.id)}">
    <div class="score" title="rank = seniority + warmth + status">${Math.round(effectiveRank(p))}</div>
    <div class="body">
      <div class="chain">Me → <b><a href="#" class="op" data-id="${esc(p.id)}">${esc(p.name)}</a></b> · ${esc(p.position || "—")} @
        <a href="#" class="oc" data-key="${esc(p.company_key)}">${esc(p.company_name || "—")}</a> ${statusBadge(st)}</div>
      <div class="why">${why(p)} <span class="small muted">warmth</span> ${warmthHTML(p)}</div>
      <div class="status-ctl" data-kind="person" data-key="${esc(p.id)}" data-label="${esc(p.name)}">
        <select class="st"><option value="">— status —</option>${state.statuses.map((s) => `<option ${st === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
        <input class="nt" type="text" placeholder="Note…" value="${esc(entry.note || "")}">
      </div>
    </div></div>`;
}

function companyBlock(c, people) {
  const st = companyStatus(c.key);
  return `<div class="group-title">${esc(c.name)} · ${c.count} connection${c.count > 1 ? "s" : ""} ${statusBadge(st)}
      <a href="#" class="oc small" data-key="${esc(c.key)}" style="text-transform:none;letter-spacing:0">all people →</a></div>
    ${people.map(pathHTML).join("")}`;
}

export function renderPaths(root) {
  root.innerHTML = `<div class="paths-wrap">
    <input class="big" type="search" id="pq" placeholder="Target company or role, e.g. “Equinor”, “CTO”, “Head of Data”" value="${esc(ui.q)}" autocomplete="off">
    <div class="hint">Ranked by seniority, message history and lead status. “Warm Intro” raises a person; “Ignore” hides them.
      <label class="inline" style="margin-left:8px"><input type="checkbox" id="pign" ${ui.showIgnored ? "checked" : ""}> show ignored</label></div>
    <div id="pres"></div></div>`;
  const res = root.querySelector("#pres");

  const visible = (p) => ui.showIgnored || personStatus(p.id) !== "Ignore";
  const rankSort = (a, b) => effectiveRank(b) - effectiveRank(a);

  function draw() {
    const q = normQuery(ui.q);
    let html = "";
    if (!q) {
      const targets = state.data.companies.filter((c) => companyStatus(c.key) === "Target");
      if (targets.length) {
        html += `<h3>Your target companies</h3>`;
        for (const c of targets) {
          const ppl = c.people.map((id) => state.peopleById.get(id)).filter(visible).sort(rankSort).slice(0, PER_COMPANY);
          html += companyBlock(c, ppl);
        }
      }
      const flagged = state.data.people.filter((p) => ["Target", "Warm Intro", "Reached Out"].includes(personStatus(p.id))).sort(rankSort);
      if (flagged.length) html += `<h3>People you flagged</h3>${flagged.map(pathHTML).join("")}`;
      const warmDM = state.data.people.filter((p) => isDM(p) && visible(p) && p.warmth > 0)
        .filter((p) => !state.companiesByKey.get(p.company_key)?.is_employer)
        .sort((a, b) => b.warmth - a.warmth || rankSort(a, b)).slice(0, 15);
      html += `<h3>Warmest decision-makers outside your employers</h3>${warmDM.map(pathHTML).join("") || `<div class="empty">No interaction data yet.</div>`}`;
    } else {
      const companies = state.data.companies.filter((c) => c.key.includes(q) || normQuery(c.name).includes(q) ||
        c.variants.some((v) => normQuery(v).includes(q)));
      companies.sort((a, b) => (b.key.startsWith(q) - a.key.startsWith(q)) || b.count - a.count);
      const companyKeys = new Set(companies.map((c) => c.key));
      const roleHits = state.data.people.filter((p) => visible(p) && !companyKeys.has(p.company_key) &&
        matchWords(p.position, q)).sort(rankSort);
      if (companies.length) {
        html += `<h3>Paths into ${companies.length === 1 ? esc(companies[0].name) : `${companies.length} matching companies`}</h3>`;
        for (const c of companies.slice(0, 12)) {
          const ppl = c.people.map((id) => state.peopleById.get(id)).filter(visible).sort(rankSort).slice(0, PER_COMPANY);
          if (ppl.length) html += companyBlock(c, ppl);
        }
      }
      if (roleHits.length) html += `<h3>People with “${esc(ui.q)}” in their title (${roleHits.length})</h3>${roleHits.slice(0, 40).map(pathHTML).join("")}`;
      if (!companies.length && !roleHits.length) html = `<div class="empty">No company or title matches “${esc(ui.q)}”. You have no direct path in your first-degree network.</div>`;
    }
    res.innerHTML = html;
    bindStatusCtls(res);
    res.querySelectorAll(".op").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); openPerson(a.dataset.id); }));
    res.querySelectorAll(".oc").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); if (a.dataset.key) openCompany(a.dataset.key); }));
  }

  const input = root.querySelector("#pq");
  input.addEventListener("input", debounce((e) => { ui.q = e.target.value; draw(); }, 100));
  root.querySelector("#pign").addEventListener("change", (e) => { ui.showIgnored = e.target.checked; draw(); });
  // Keep focus and caret in the search box when notes trigger a redraw.
  const off = onChange(() => {
    const active = document.activeElement;
    if (active && res.contains(active) && active.classList.contains("nt")) return;
    draw();
  });
  draw();
  input.focus();
  return off;
}
