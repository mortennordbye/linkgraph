import { state, esc, debounce, openCompany, openPerson, isDM, TIER_LABELS, personStatus, matchWords, initials } from "../app.js";

const ui = { min: 2, kw: "", months: 0, hideEmployer: true, hideGeneric: true, group: "company", labels: true };

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function renderGraph(root) {
  root.innerHTML = `<div class="toolbar pad">
      <label class="inline">Min connections/company <input type="number" id="gmin" min="1" max="50" value="${ui.min}" style="width:64px"></label>
      <label class="inline">Title keyword <input type="search" id="gkw" placeholder="CTO, Product, Engineering…" value="${esc(ui.kw)}" style="min-width:200px"></label>
      <label class="inline">Connected within
        <select id="gmonths">${[[0, "any time"], [3, "3 months"], [6, "6 months"], [12, "1 year"], [24, "2 years"], [60, "5 years"]]
          .map(([v, l]) => `<option value="${v}" ${ui.months === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="inline">Cluster by <select id="ggroup">
        <option value="company" ${ui.group === "company" ? "selected" : ""}>Company</option>
        <option value="tier" ${ui.group === "tier" ? "selected" : ""}>Role seniority</option></select></label>
      <label class="inline"><input type="checkbox" id="gemp" ${ui.hideEmployer ? "checked" : ""}> Hide my employers</label>
      <label class="inline"><input type="checkbox" id="ggen" ${ui.hideGeneric ? "checked" : ""}> Hide "self-employed"</label>
      <label class="inline"><input type="checkbox" id="glab" ${ui.labels ? "checked" : ""}> Labels</label>
      <span class="spacer"></span><span class="muted small" id="gcount"></span>
    </div>
    <div id="graph"><div class="legend">
      <span><i style="background:var(--me)"></i>Me</span>
      <span><i style="background:var(--company)"></i>Company / cluster</span>
      <span><i style="background:var(--person)"></i>Person</span>
      <span><i style="background:var(--dm)"></i>Decision-maker</span>
    </div></div>`;

  const el = root.querySelector("#graph");
  if (typeof window.ForceGraph !== "function") {
    el.innerHTML = `<div class="error">force-graph library did not load.</div>`;
    return;
  }
  const colors = {
    me: cssVar("--me"), company: cssVar("--company"), person: cssVar("--person"), dm: cssVar("--dm"),
    text: cssVar("--text"), muted: cssVar("--muted"), border: cssVar("--border"), warm: cssVar("--warm"),
  };
  let selected = null;

  // Logo images for company nodes. All URLs point at this server (logo-cache/).
  const images = new Map();
  function logoImage(key) {
    const url = state.logos[key];
    if (!url) return null;
    let im = images.get(url);
    if (!im) {
      im = new Image();
      im.onload = () => graph.zoom(graph.zoom()); // repaint once the image is ready
      im.src = url;
      images.set(url, im);
    }
    return im.complete && im.naturalWidth ? im : null;
  }

  function drawCompanyBadge(n, ctx, scale) {
    const r = Math.sqrt(n.val) * 3;
    const im = logoImage(n.key);
    if (im && r * scale >= 6) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = "#fff";
      ctx.fill();
      ctx.clip();
      const s = r * 1.25;
      ctx.drawImage(im, n.x - s / 2, n.y - s / 2, s, s);
      ctx.restore();
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.strokeStyle = colors.company; ctx.lineWidth = 2 / scale; ctx.stroke();
    } else if (r * scale >= 9) {
      ctx.font = `700 ${r * 0.8}px ui-sans-serif, sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#fff";
      ctx.fillText(initials(n.label), n.x, n.y + r * 0.04);
    }
  }

  const graph = window.ForceGraph()(el)
    .backgroundColor("rgba(0,0,0,0)")
    .nodeId("id")
    .nodeVal((n) => n.val)
    .nodeRelSize(3)
    .nodeColor((n) => n.color)
    .nodeLabel((n) => n.tip)
    .linkColor((l) => (selected && (l.source.id === selected || l.target.id === selected)) ? colors.warm : colors.border)
    .linkWidth((l) => (selected && (l.source.id === selected || l.target.id === selected)) ? 2 : 0.6)
    .onNodeClick((n) => {
      selected = n.id;
      if (n.kind === "company") openCompany(n.key);
      else if (n.kind === "person") openPerson(n.pid);
      graph.centerAt(n.x, n.y, 600);
    })
    .nodeCanvasObjectMode(() => "after")
    .nodeCanvasObject((n, ctx, scale) => {
      if (n.kind === "company") drawCompanyBadge(n, ctx, scale);
      if (n.id === selected) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, Math.sqrt(n.val) * 3 + 3, 0, 2 * Math.PI);
        ctx.strokeStyle = colors.warm; ctx.lineWidth = 2 / scale; ctx.stroke();
      }
      if (!ui.labels) return;
      const show = n.kind === "me" || n.kind === "company" && (n.count >= 4 || scale > 1.5) || n.kind === "person" && scale > 2.5;
      if (!show) return;
      const fs = (n.kind === "person" ? 10 : 12) / scale;
      ctx.font = `${n.kind === "person" ? "" : "600 "}${fs}px ui-sans-serif, sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      ctx.fillStyle = n.kind === "person" ? colors.muted : colors.text;
      ctx.fillText(n.label, n.x, n.y + Math.sqrt(n.val) * 3 + 2 / scale);
    });
  graph.d3Force("charge").strength(-40);
  graph.d3Force("link").distance((l) => (l.source.kind === "me" ? 80 : 24));

  function build() {
    const kw = ui.kw.trim().toLowerCase();
    const cutoff = ui.months ? Date.now() - ui.months * 30.44 * 86400000 : 0;
    const personOk = (p) => personStatus(p.id) !== "Ignore" &&
      (!kw || matchWords(p.position, kw)) &&
      (!cutoff || (p.connected_on && new Date(p.connected_on).getTime() >= cutoff));

    const nodes = [{ id: "me", kind: "me", label: state.data.me.name, tip: esc(state.data.me.name), val: 18, color: colors.me, fx: 0, fy: 0 }];
    const links = [];
    const personNode = (p) => ({
      id: "p:" + p.id, pid: p.id, kind: "person", label: p.name, val: isDM(p) ? 3 : 1.5,
      color: isDM(p) ? colors.dm : colors.person,
      tip: `<b>${esc(p.name)}</b><br>${esc(p.position || "")}<br>${esc(p.company_name || "")}<br>warmth ${p.warmth}`,
    });

    if (ui.group === "company") {
      for (const c of state.data.companies) {
        if (c.count < ui.min) continue;
        if (ui.hideEmployer && c.is_employer) continue;
        if (ui.hideGeneric && c.is_generic) continue;
        const members = c.people.map((id) => state.peopleById.get(id)).filter(personOk);
        if (!members.length) continue;
        const cid = "c:" + c.key;
        nodes.push({ id: cid, key: c.key, kind: "company", label: c.name, count: c.count, val: 3 + 4 * Math.sqrt(c.count), color: colors.company,
          tip: `<b>${esc(c.name)}</b><br>${c.count} connections · ${c.decision_makers} decision-makers` });
        links.push({ source: "me", target: cid });
        for (const p of members) { nodes.push(personNode(p)); links.push({ source: cid, target: "p:" + p.id }); }
      }
      if (ui.min <= 1) {
        // People with no company link straight to me.
        for (const p of state.data.people) {
          if (!p.company_key && personOk(p)) { nodes.push(personNode(p)); links.push({ source: "me", target: "p:" + p.id }); }
        }
      }
    } else {
      const byTier = new Map();
      for (const p of state.data.people) {
        if (!personOk(p)) continue;
        const c = state.companiesByKey.get(p.company_key);
        if (c && ((ui.hideEmployer && c.is_employer) || (ui.hideGeneric && c.is_generic) || c.count < ui.min)) continue;
        if (!byTier.has(p.tier)) byTier.set(p.tier, []);
        byTier.get(p.tier).push(p);
      }
      for (const [tier, members] of [...byTier.entries()].sort((a, b) => b[0] - a[0])) {
        const tid = "t:" + tier;
        nodes.push({ id: tid, kind: "tier", label: TIER_LABELS[tier], count: 99, val: 3 + 4 * Math.sqrt(members.length), color: tier >= 3 ? colors.dm : colors.company,
          tip: `<b>${esc(TIER_LABELS[tier])}</b><br>${members.length} people` });
        links.push({ source: "me", target: tid });
        for (const p of members) { nodes.push(personNode(p)); links.push({ source: tid, target: "p:" + p.id }); }
      }
    }
    const nPeople = nodes.filter((n) => n.kind === "person").length;
    const nHubs = nodes.length - nPeople - 1;
    root.querySelector("#gcount").textContent = `${nHubs} ${ui.group === "company" ? "companies" : "clusters"} · ${nPeople} people`;
    graph.graphData({ nodes, links });
  }

  function resize() { graph.width(el.clientWidth).height(el.clientHeight); }
  const ro = new ResizeObserver(resize);
  ro.observe(el);
  resize();

  const rebuild = debounce(build, 200);
  root.querySelector("#gmin").addEventListener("input", (e) => { ui.min = Math.max(1, +e.target.value || 1); rebuild(); });
  root.querySelector("#gkw").addEventListener("input", (e) => { ui.kw = e.target.value; rebuild(); });
  root.querySelector("#gmonths").addEventListener("change", (e) => { ui.months = +e.target.value; build(); });
  root.querySelector("#ggroup").addEventListener("change", (e) => { ui.group = e.target.value; build(); });
  root.querySelector("#gemp").addEventListener("change", (e) => { ui.hideEmployer = e.target.checked; build(); });
  root.querySelector("#ggen").addEventListener("change", (e) => { ui.hideGeneric = e.target.checked; build(); });
  root.querySelector("#glab").addEventListener("change", (e) => { ui.labels = e.target.checked; });
  const onSel = (e) => { if (!e.detail) selected = null; };
  document.addEventListener("lg:selection", onSel);

  build();
  setTimeout(() => graph.zoomToFit(600, 40), 1500);

  return () => {
    ro.disconnect();
    document.removeEventListener("lg:selection", onSel);
    graph.pauseAnimation();
    if (typeof graph._destructor === "function") graph._destructor();
  };
}
