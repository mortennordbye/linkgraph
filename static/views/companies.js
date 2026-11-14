import { state, esc, fmtDate, debounce, openCompany, companyStatus, statusBadge, onChange, normQuery, matchWords } from "../app.js";

const ui = { q: "", sort: "count", dir: -1, mode: "table", status: "", hideGeneric: true, dmOnly: false };

const COLS = [
  { key: "name", label: "Company" },
  { key: "count", label: "Connections", num: true },
  { key: "decision_makers", label: "Decision-makers", num: true },
  { key: "max_warmth", label: "Best warmth", num: true },
  { key: "messages", label: "Messages", num: true },
  { key: "latest_connected", label: "Latest connection" },
  { key: "status", label: "Status" },
];

export function renderCompanies(root) {
  const max = Math.max(1, ...state.data.companies.map((c) => c.count));
  root.innerHTML = `<div class="toolbar">
      <input type="search" id="cq" placeholder="Search companies, people or titles…" value="${esc(ui.q)}">
      <select id="cstatus"><option value="">All statuses</option>${state.statuses.map((s) => `<option ${ui.status === s ? "selected" : ""}>${esc(s)}</option>`).join("")}<option value="__none" ${ui.status === "__none" ? "selected" : ""}>No status</option></select>
      <label class="inline"><input type="checkbox" id="cdm" ${ui.dmOnly ? "checked" : ""}> Has decision-makers</label>
      <label class="inline"><input type="checkbox" id="cgen" ${ui.hideGeneric ? "checked" : ""}> Hide "self-employed" etc.</label>
      <span class="spacer"></span>
      <span class="muted small" id="ccount"></span>
      <span class="seg"><button data-mode="table">Table</button><button data-mode="cards">Cards</button></span>
    </div>
    <div id="clist"></div>`;

  const list = root.querySelector("#clist");

  function filtered() {
    const q = normQuery(ui.q);
    let rows = state.data.companies.filter((c) => {
      if (ui.hideGeneric && c.is_generic) return false;
      if (ui.dmOnly && !c.decision_makers) return false;
      const st = companyStatus(c.key);
      if (ui.status === "__none" && st) return false;
      if (ui.status && ui.status !== "__none" && st !== ui.status) return false;
      if (!q) return true;
      if (c.key.includes(q) || normQuery(c.name).includes(q)) return true;
      return c.people.some((id) => {
        const p = state.peopleById.get(id);
        return matchWords(p.name, q) || matchWords(p.position, q);
      });
    });
    const k = ui.sort;
    rows.sort((a, b) => {
      let va = k === "status" ? companyStatus(a.key) || "" : a[k];
      let vb = k === "status" ? companyStatus(b.key) || "" : b[k];
      if (typeof va === "string" || va == null) {
        return ui.dir * String(va ?? "").localeCompare(String(vb ?? ""), undefined, { sensitivity: "base" }) || b.count - a.count;
      }
      return ui.dir * (va - vb) || a.name.localeCompare(b.name);
    });
    return rows;
  }

  function draw() {
    const rows = filtered();
    root.querySelector("#ccount").textContent = `${rows.length} of ${state.data.companies.length} companies`;
    root.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("on", b.dataset.mode === ui.mode));
    if (!rows.length) { list.innerHTML = `<div class="empty">No companies match.</div>`; return; }
    if (ui.mode === "cards") {
      list.innerHTML = `<div class="cards">${rows.map((c) => `<div class="card" data-key="${esc(c.key)}">
          <h3>${esc(c.name)}</h3>
          <div class="big">${c.count}</div>
          <div class="small muted">${c.decision_makers} decision-maker${c.decision_makers === 1 ? "" : "s"} · warmth ${c.max_warmth}</div>
          <div style="margin-top:6px">${c.is_employer ? '<span class="badge emp">employer</span> ' : ""}${statusBadge(companyStatus(c.key))}</div>
        </div>`).join("")}</div>`;
    } else {
      list.innerHTML = `<table class="grid"><thead><tr>${COLS.map((c) =>
        `<th class="${c.num ? "num" : ""}" data-sort="${c.key}">${c.label}${ui.sort === c.key ? (ui.dir < 0 ? " ↓" : " ↑") : ""}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((c) => `<tr data-key="${esc(c.key)}">
          <td>${esc(c.name)} ${c.is_employer ? '<span class="badge emp">employer</span>' : ""}${c.variants.length > 1 ? ` <span class="badge" title="${esc(c.variants.join(", "))}">${c.variants.length} spellings</span>` : ""}</td>
          <td class="num"><div style="display:flex;gap:8px;align-items:center;justify-content:flex-end">${c.count}<div class="bar" style="width:80px"><i style="width:${(100 * c.count) / max}%"></i></div></div></td>
          <td class="num">${c.decision_makers ? `<span class="badge dm">${c.decision_makers}</span>` : "0"}</td>
          <td class="num">${c.max_warmth}</td>
          <td class="num">${c.messages}</td>
          <td>${fmtDate(c.latest_connected)}</td>
          <td>${statusBadge(companyStatus(c.key))}</td></tr>`).join("")}</tbody></table>`;
      list.querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
        const k = th.dataset.sort;
        if (ui.sort === k) ui.dir *= -1; else { ui.sort = k; ui.dir = k === "name" || k === "status" ? 1 : -1; }
        draw();
      }));
    }
    list.querySelectorAll("[data-key]").forEach((el) => el.addEventListener("click", () => openCompany(el.dataset.key)));
    highlight();
  }

  function highlight() {
    const sel = document.querySelector("#panel.open") ? currentKey : null;
    list.querySelectorAll("tr[data-key]").forEach((tr) => tr.classList.toggle("sel", tr.dataset.key === sel));
  }
  let currentKey = null;
  const onSel = (e) => { currentKey = e.detail?.type === "company" ? e.detail.key : null; highlight(); };
  document.addEventListener("lg:selection", onSel);

  root.querySelector("#cq").addEventListener("input", debounce((e) => { ui.q = e.target.value; draw(); }));
  root.querySelector("#cstatus").addEventListener("change", (e) => { ui.status = e.target.value; draw(); });
  root.querySelector("#cdm").addEventListener("change", (e) => { ui.dmOnly = e.target.checked; draw(); });
  root.querySelector("#cgen").addEventListener("change", (e) => { ui.hideGeneric = e.target.checked; draw(); });
  root.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { ui.mode = b.dataset.mode; draw(); }));
  const off = onChange(draw);
  draw();
  root.querySelector("#cq").focus();
  return () => { off(); document.removeEventListener("lg:selection", onSel); };
}
