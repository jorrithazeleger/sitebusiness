/* Schoonschip: de app in het venster. Praat met server.py op deze computer. */
"use strict";

const TOKEN = new URLSearchParams(location.search).get("t") || "";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------------------------------------------------------------------
// Iconen (eenvoudige lijntekeningen)
const P = {
  home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  box: '<path d="M3 7l9-4 9 4-9 4z"/><path d="M3 7v10l9 4 9-4V7"/><path d="M12 11v10"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  doc: '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5M9 13h7M9 17h7"/>',
  code: '<path d="M8 8l-5 4 5 4M16 8l5 4-5 4M14 5l-4 14"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  phone: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  file: '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/>',
  big: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  map: '<circle cx="12" cy="12" r="9"/><path d="M12 3v9l6.5 6.2"/>',
  apps: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  power: '<path d="M12 3v9"/><path d="M6.3 7a8 8 0 1 0 11.4 0"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.8-.7-.7-2.8z"/>',
  folder: '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  chev: '<path d="M9 6l6 6-6 6"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  package: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10M7.5 5l9 4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  back: '<path d="M15 6l-6 6 6 6"/>',
};
const ic = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${P[name] || P.file}</svg>`;

// ---------------------------------------------------------------------------
// Opmaak

function fmtSize(b) {
  if (b == null) return "?";
  const u = ["bytes", "kB", "MB", "GB", "TB"];
  let i = 0, v = b;
  while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
  const d = i === 0 ? 0 : v >= 100 ? 0 : v >= 10 ? 1 : 1;
  return v.toLocaleString("nl-NL", { maximumFractionDigits: d, minimumFractionDigits: i > 1 && v < 10 ? 1 : 0 }) + " " + u[i];
}
function fmtAge(days) {
  if (days == null) return "";
  if (days < 1) return "vandaag";
  if (days < 2) return "gisteren";
  if (days < 31) return `${days} dagen`;
  if (days < 365) return `${Math.round(days / 30.4)} mnd`;
  const y = days / 365;
  return `${y.toLocaleString("nl-NL", { maximumFractionDigits: 1 })} jaar`;
}
function fmtDate(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" });
}
const plural = (n, one, many) => `${n.toLocaleString("nl-NL")} ${n === 1 ? one : many}`;

// ---------------------------------------------------------------------------
// Praten met de server

async function api(name, body, method) {
  const opts = { method: method || (body === undefined ? "GET" : "POST"), headers: { "X-Token": TOKEN } };
  if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const res = await fetch("/api/" + name, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Er ging iets mis.");
  return data;
}

const RUNNING = {}; // pagina -> lopende taak

async function runJob(page, kind, params) {
  const { job } = await api("start", { kind, params: params || {} });
  RUNNING[page] = { id: job, kind, progress: null, message: "" };
  if (S.page === page) render();
  try {
    for (;;) {
      await new Promise((r) => setTimeout(r, 280));
      const st = await api("job?id=" + job);
      const run = RUNNING[page];
      if (run && run.id === job) { run.progress = st.progress; run.message = st.message; }
      if (S.page === page) updateBusy(page);
      if (st.status === "done") return st.result;
      if (st.status === "cancelled") return null;
      if (st.status === "error") throw new Error(st.error);
    }
  } finally {
    if (RUNNING[page] && RUNNING[page].id === job) delete RUNNING[page];
  }
}

function cancelJob(page) {
  const run = RUNNING[page];
  if (run) api("cancel", { id: run.id }).catch(() => {});
}

function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), err ? 6000 : 3500);
}

function modal(html) {
  $("#modalCard").innerHTML = html;
  $("#modal").hidden = false;
}
function closeModal() { $("#modal").hidden = true; }

function confirmBox(title, html, okLabel, danger) {
  return new Promise((resolve) => {
    modal(`<h2>${esc(title)}</h2>${html}<div class="acts"><button class="btn" data-a="no">Annuleer</button>
      <button class="btn ${danger ? "primary" : "primary"}" data-a="yes">${esc(okLabel || "Doorgaan")}</button></div>`);
    $("#modalCard").onclick = (e) => {
      const a = e.target.closest("[data-a]");
      if (!a) return;
      closeModal();
      resolve(a.dataset.a === "yes");
    };
  });
}

// ---------------------------------------------------------------------------
// Toestand

const PAGES = [
  { key: "overview", title: "Overzicht", icon: "home" },
  { sect: "Opruimen" },
  { key: "junk", title: "Systeemrommel", icon: "sparkle" },
  { key: "large", title: "Grote bestanden", icon: "big" },
  { key: "downloads", title: "Downloads", icon: "download" },
  { key: "dupes", title: "Dubbele bestanden", icon: "copy" },
  { key: "space", title: "Ruimtekaart", icon: "map" },
  { sect: "Snelheid" },
  { key: "apps", title: "Programma's", icon: "apps" },
  { key: "startup", title: "Opstarten", icon: "power" },
  { key: "maint", title: "Onderhoud", icon: "wrench" },
];

const S = {
  page: "overview",
  data: {},          // resultaten per pagina
  sel: {},           // pagina -> Set met gekozen nummers
  open: {},          // pagina -> Set met opengeklapte groepen
  overview: null,
  filter: { large: "Alles", apps: "", appSort: "name" },
  largeMin: 100,
  dupeFolder: null, dupeMin: 1,
  app: null,         // gekozen programma om te verwijderen
};

function sel(page) { return S.sel[page] || (S.sel[page] = new Set()); }
function opened(page) { return S.open[page] || (S.open[page] = new Set()); }

function allItems(page) {
  const d = S.data[page];
  if (!d) return [];
  if (page === "space") return d.items.filter((i) => i.id);
  if (page === "large") return d.items;
  if (page === "leftovers") return d.items;
  return (d.groups || []).flatMap((g) => g.items);
}

function initSelection(page) {
  const s = new Set();
  for (const it of allItems(page)) if (it.selected && it.id) s.add(it.id);
  S.sel[page] = s;
}

function selectedItems(page) {
  const s = sel(page);
  return allItems(page).filter((i) => s.has(i.id));
}

// ---------------------------------------------------------------------------
// Opbouw

function renderNav() {
  $("#nav").innerHTML = PAGES.map((p) => p.sect ? `<div class="sect">${p.sect}</div>` :
    `<button data-page="${p.key}" class="${S.page === p.key ? "on" : ""}">${ic(p.icon)}<span>${p.title}</span>${badge(p.key)}</button>`).join("");
}

function badge(key) {
  if (RUNNING[key]) return `<span class="badge">…</span>`;
  const d = S.data[key];
  if (!d) return "";
  const n = key === "dupes" ? (d.wasted || 0) : allItems(key).reduce((a, i) => a + (i.size || 0), 0);
  if (["junk", "downloads", "dupes"].includes(key) && n > 0) return `<span class="badge">${fmtSize(n)}</span>`;
  return "";
}

function renderSideFoot() {
  const o = S.overview;
  if (!o) return;
  $("#sideFoot").innerHTML = o.history_total ? `Samen al opgeruimd<b>${fmtSize(o.history_total)}</b>` : "";
}

function render() {
  renderNav();
  const page = S.page;
  const el = $("#page");
  const run = RUNNING[page];
  $("#bar").hidden = true;
  if (run && page !== "overview" && page !== "maint") {
    el.innerHTML = head(page) + busyHtml(page, run);
    updateBusy(page);
    return;
  }
  const fn = RENDER[page];
  el.innerHTML = fn ? fn() : "";
  if (["junk", "downloads", "large", "dupes", "space", "startup"].includes(page) || (page === "apps" && S.app)) renderBar();
}

const TITLES = {
  overview: ["Overzicht", ""],
  junk: ["Systeemrommel", "Caches, logbestanden en andere tijdelijke bestanden die je Mac vanzelf opnieuw maakt."],
  large: ["Grote bestanden", "De grootste bestanden in je eigen mappen. Gaan naar de Prullenmand, dus je kunt ze terughalen."],
  downloads: ["Downloads", "Wat er in je map Downloads staat, met installatiebestanden en oude downloads apart."],
  dupes: ["Dubbele bestanden", "Bestanden die precies hetzelfde zijn. Steeds blijft er één staan."],
  space: ["Ruimtekaart", "Zie welke mappen de meeste ruimte innemen. Klik op een map om erin te kijken."],
  apps: ["Programma's", "Verwijder programma's helemaal, inclusief de bestanden die ze in je bibliotheek achterlaten."],
  startup: ["Opstarten", "Programma's en diensten die vanzelf starten. Minder is sneller."],
  maint: ["Onderhoud", "Handige klusjes die je Mac weer soepel laten lopen."],
};

function head(page, tools) {
  const [t, sub] = TITLES[page];
  return `<div class="head"><div><h1>${t}</h1>${sub ? `<p>${sub}</p>` : ""}</div>${tools ? `<div class="tools">${tools}</div>` : ""}</div>`;
}

function busyHtml(page, run) {
  const labels = { clean: "Bezig met opruimen", junk: "Rommel zoeken", large: "Grote bestanden zoeken", downloads: "Downloads bekijken",
    dupes: "Dubbele bestanden zoeken", space: "Mappen meten", apps: "Programma's bekijken", leftovers: "Bestanden van dit programma zoeken",
    startup: "Opstartonderdelen bekijken", smart: "Je Mac scannen" };
  return `<div class="busy"><div class="spinner"></div><h2>${labels[run.kind] || "Even geduld"}…</h2>
    <div class="msg" id="busyMsg"></div>
    <div class="prog"><div class="track" id="busyTrack"><div class="fill" id="busyFill"></div></div></div>
    ${run.kind === "clean" ? "" : `<button class="btn" data-act="cancel">Stop</button>`}</div>`;
}

function updateBusy(page) {
  const run = RUNNING[page];
  if (!run) return;
  const m = $("#busyMsg"), tr = $("#busyTrack"), f = $("#busyFill");
  if (m) m.textContent = run.message || "";
  if (tr && f) {
    tr.classList.toggle("indef", run.progress == null);
    if (run.progress != null) f.style.width = Math.round(run.progress * 100) + "%";
  }
  if (page === "overview") renderOverviewProgress();
}

function emptyState(icon, title, text, button) {
  return `<div class="empty"><div class="big-ic">${ic(icon)}</div><h2>${title}</h2><p>${text}</p>${button || ""}</div>`;
}

// ---------------------------------------------------------------------------
// Overzicht

function ring(pct, label, sub) {
  const r = 62, c = 2 * Math.PI * r;
  return `<div class="ring"><svg viewBox="0 0 150 150"><circle cx="75" cy="75" r="${r}" stroke="rgba(255,255,255,.25)" stroke-width="12" fill="none"/>
    <circle cx="75" cy="75" r="${r}" stroke="#fff" stroke-width="12" fill="none" stroke-linecap="round"
     stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - pct)}"/></svg>
    <div class="lbl"><b>${label}</b><span>${sub}</span></div></div>`;
}

function renderOverview() {
  const o = S.overview;
  if (!o) return `<div class="busy"><div class="spinner"></div></div>`;
  const d = o.disk, used = d.used / d.total;
  const smart = S.data.smart;
  const run = RUNNING.overview;
  let heroRight;
  if (run) {
    heroRight = `<h2>Je Mac wordt gescand…</h2><p id="ovMsg">${esc(run.message || "")}</p>
      <div class="hero-prog"><div class="track" id="ovTrack"><div class="fill" id="ovFill"></div></div></div>
      <p style="margin-top:14px"><button class="btn ghost" data-act="cancel">Stop</button></p>`;
  } else if (smart) {
    const junk = smartJunkTotal();
    heroRight = junk > 0
      ? `<h2>${fmtSize(junk)} rommel gevonden</h2><p>Veilig op te ruimen: caches, logbestanden en andere tijdelijke bestanden${S.data.junk && S.data.junk.groups.some((g) => g.key === "trash") ? ", plus je Prullenmand" : ""}.</p>
         <button class="btn big" data-act="smart-clean">Opruimen</button> <button class="btn ghost" data-go="junk">Bekijk details</button>`
      : `<h2>Je Mac is schoon</h2><p>Er is op dit moment niets dat veilig weg kan. Kijk hieronder voor meer.</p>
         <button class="btn big" data-act="smart">Opnieuw scannen</button>`;
  } else {
    heroRight = `<h2>Tijd voor een schone lei</h2><p>Eén scan zoekt naar rommel, vergeten downloads, grote bestanden en programma's die je niet meer gebruikt. Er wordt niets weggegooid zonder dat jij het ziet.</p>
      <button class="btn big" data-act="smart">Scan mijn Mac</button>`;
  }
  const mem = o.memory;
  const memPct = mem ? mem.used / mem.total : 0;
  const up = o.uptime_days;
  let html = `<div class="hero">${ring(used, Math.round(used * 100) + "%", "schijf vol")}<div style="position:relative;z-index:1">${heroRight}</div></div>`;
  html += `<div class="grid">
    <div class="card stat"><div class="k">Opslag</div><div class="v">${fmtSize(d.free)} vrij</div>
      <div class="meter"><i class="${used > .9 ? "hot" : ""}" style="width:${used * 100}%"></i></div>
      <div class="s" style="margin-top:6px">${fmtSize(d.used)} van ${fmtSize(d.total)} in gebruik${d.purgeable ? ` · nog ${fmtSize(d.purgeable)} vrij te maken door macOS` : ""}</div></div>
    ${mem ? `<div class="card stat"><div class="k">Werkgeheugen</div><div class="v">${fmtSize(mem.used)}</div>
      <div class="meter"><i class="${memPct > .85 ? "hot" : ""}" style="width:${memPct * 100}%"></i></div>
      <div class="s" style="margin-top:6px">in gebruik van ${fmtSize(mem.total)}</div></div>` : ""}
    <div class="card stat"><div class="k">Aan sinds</div><div class="v">${up == null ? "?" : up < 1 ? "vandaag" : plural(Math.floor(up), "dag", "dagen")}</div>
      <div class="s">${up != null && up > 14 ? '<span class="warn">Al lang niet herstart. Een herstart maakt je Mac vaak merkbaar sneller.</span>' : "Af en toe herstarten houdt je Mac fris."}</div></div>
    <div class="card stat"><div class="k">Opgeruimd met Schoonschip</div><div class="v">${fmtSize(o.history_total || 0)}</div>
      <div class="s">in totaal</div></div>
  </div>`;
  if (smart) html += renderSmartResults(smart);
  if (o.top && o.top.length) {
    html += `<h3 class="sub">Gebruikt nu het meeste geheugen</h3><div class="card proc">` + o.top.map((p) => `<div class="row">
      <div class="n">${esc(p.name)}</div><div class="c">${p.cpu.toLocaleString("nl-NL")}% cpu</div><div class="m">${fmtSize(p.memory)}</div>
      <div class="q">${p.can_quit ? `<button class="btn small" data-quit="${esc(p.bundle)}" data-name="${esc(p.name)}">Stop</button>` : ""}</div></div>`).join("") + `</div>`;
  }
  return html;
}

function renderOverviewProgress() {
  const run = RUNNING.overview;
  if (!run) return;
  const m = $("#ovMsg"), tr = $("#ovTrack"), f = $("#ovFill");
  if (m) m.textContent = run.message || "";
  if (tr && f) {
    tr.classList.toggle("indef", run.progress == null);
    if (run.progress != null) f.style.width = Math.round(run.progress * 100) + "%";
  }
}

function smartJunkTotal() {
  return selectedItems("junk").reduce((a, i) => a + (i.size || 0), 0);
}

function renderSmartResults(r) {
  const cards = [];
  const junkAll = allItems("junk").reduce((a, i) => a + i.size, 0);
  cards.push(["junk", "sparkle", fmtSize(junkAll), "Systeemrommel", "Bekijk wat er precies gevonden is"]);
  const dl = allItems("downloads");
  const inst = dl.filter((i) => i.selected);
  cards.push(["downloads", "download", fmtSize(dl.reduce((a, i) => a + i.size, 0)), "in Downloads",
    inst.length ? `${plural(inst.length, "installatiebestand", "installatiebestanden")} die weg kunnen` : plural(dl.length, "onderdeel", "onderdelen")]);
  if (r.large_count != null) cards.push(["large", "big", plural(r.large_count, "bestand", "bestanden"), "groter dan 1 GB", r.large_count ? `samen ${fmtSize(r.large_size)}` : "Niets gevonden"]);
  cards.push(["apps", "apps", plural(r.unused_apps, "programma", "programma's"), "langer dan een half jaar niet gebruikt", "Verwijder ze helemaal"]);
  return `<h3 class="sub">Uit de scan</h3><div class="results">` + cards.map(([go, icon, big, what, sub]) =>
    `<div class="card res" data-go="${go}"><div class="ic">${ic(icon)}</div><b>${big}</b><div>${what}</div><span>${sub}</span></div>`).join("") + `</div>`;
}

// ---------------------------------------------------------------------------
// Lijsten met groepen (rommel, downloads, opstarten)

function renderGroups(page, groups, opts = {}) {
  const s = sel(page), o = opened(page);
  return `<div class="groups">` + groups.map((g) => {
    const items = g.items;
    const selectable = items.filter((i) => i.id && (opts.canSelect ? opts.canSelect(i, g) : true));
    const nSel = selectable.filter((i) => s.has(i.id)).length;
    const total = items.reduce((a, i) => a + (i.size || 0), 0);
    const selSize = selectable.filter((i) => s.has(i.id)).reduce((a, i) => a + (i.size || 0), 0);
    const all = selectable.length > 0 && nSel === selectable.length;
    const some = nSel > 0 && !all;
    const unknown = items.some((i) => i.unknown);
    return `<div class="card grp ${o.has(g.key) ? "open" : ""}">
      <div class="grp-h" data-toggle="${esc(g.key)}">
        ${selectable.length ? `<input type="checkbox" data-gsel="${esc(g.key)}" ${all ? "checked" : ""} data-some="${some ? 1 : 0}">` : ""}
        <div class="ic">${ic(g.icon || "file")}</div>
        <div class="t"><b>${esc(g.title)}</b><span>${esc(g.desc || "")}</span></div>
        <div class="sz">${unknown ? "?" : opts.noSize ? plural(items.length, "onderdeel", "onderdelen") : (nSel && nSel < selectable.length ? `<span class="muted" style="font-weight:400">${fmtSize(selSize)} van </span>` : "") + fmtSize(total)}</div>
        <div class="chev">${ic("chev")}</div>
      </div>
      <div class="grp-b">${items.map((i) => itemRow(page, i, opts.canSelect ? opts.canSelect(i, g) : true, opts)).join("")}</div>
    </div>`;
  }).join("") + `</div>`;
}

function itemRow(page, it, selectable, opts = {}) {
  const s = sel(page);
  const tag = it.action === "trash" ? `<span class="tag trash">Prullenmand</span>` : it.action === "empty_trash" ? `<span class="tag">definitief</span>` : "";
  const sub = it.note || it.where || "";
  return `<div class="it">
    ${selectable && it.id ? `<input type="checkbox" data-isel="${it.id}" ${s.has(it.id) ? "checked" : ""}>` : `<span style="width:18px"></span>`}
    <div class="t"><div>${esc(it.name)}</div>${sub ? `<small>${esc(sub)}</small>` : ""}</div>
    ${it.age_days != null ? `<span class="age">${fmtAge(it.age_days)}</span>` : ""}
    ${opts.hideTag ? "" : tag}
    ${opts.noSize ? "" : `<span class="sz">${it.unknown ? "?" : fmtSize(it.size)}</span>`}
    ${it.action !== "empty_trash" ? `<button class="icon-btn" title="Toon in de Finder" data-reveal="${it.id}">${ic("eye")}</button>` : ""}
  </div>`;
}

function renderBar() {
  const page = S.page === "apps" ? "leftovers" : S.page;
  const items = selectedItems(page);
  const bar = $("#bar");
  if (!S.data[page]) { bar.hidden = true; return; }
  const size = items.reduce((a, i) => a + (i.size || 0), 0);
  const trash = items.filter((i) => i.action === "trash").length;
  const label = { junk: "Opruimen", downloads: "Naar Prullenmand", large: "Naar Prullenmand", dupes: "Naar Prullenmand",
    space: "Naar Prullenmand", startup: "Verwijder", leftovers: "Verwijder programma" }[page];
  const subtxt = items.length === 0 ? "Niets gekozen" :
    page === "junk" ? (trash ? `${plural(trash, "onderdeel gaat", "onderdelen gaan")} naar de Prullenmand, de rest wordt meteen verwijderd` : "Wordt meteen verwijderd; je Mac maakt het vanzelf opnieuw aan")
      : page === "startup" ? "Gaat naar de Prullenmand" : "Gaat naar de Prullenmand: terug te halen tot je die leegt";
  bar.innerHTML = `<div class="sum"><b>${page === "startup" ? plural(items.length, "onderdeel", "onderdelen") : fmtSize(size)}</b><span>${page === "startup" ? "" : plural(items.length, "onderdeel", "onderdelen") + " · "}${subtxt}</span></div>
    <div class="grow"></div>
    ${page === "leftovers" ? `<button class="btn" data-act="app-back">Annuleer</button>` : ""}
    <button class="btn primary" data-act="clean" ${items.length ? "" : "disabled"}>${label}</button>`;
  bar.hidden = false;
}

// ---------------------------------------------------------------------------
// Pagina's

function renderJunk() {
  const d = S.data.junk;
  const tools = d ? `<button class="btn" data-act="scan-junk">Opnieuw scannen</button>` : "";
  if (!d) return head("junk") + emptyState("sparkle", "Zoek naar rommel", "Schoonschip kijkt in caches, logbestanden, ontwikkeltools, mailbijlagen, oude reservekopieen van je iPhone en de Prullenmand. Je ziet alles eerst voordat er iets weggaat.", `<button class="btn primary big" data-act="scan-junk">Scan</button>`);
  if (!d.groups.length) return head("junk", tools) + emptyState("check", "Niets gevonden", "Er staat op dit moment geen rommel op je Mac.");
  return head("junk", tools) + renderGroups("junk", d.groups);
}

function renderDownloads() {
  const d = S.data.downloads;
  const tools = d ? `<button class="btn" data-act="scan-downloads">Opnieuw bekijken</button>` : "";
  if (!d) return head("downloads") + emptyState("download", "Bekijk je Downloads", "Vaak staat hier jaren aan vergeten installatiebestanden, zips en pdf's.", `<button class="btn primary big" data-act="scan-downloads">Bekijk</button>`);
  if (!d.groups.length) return head("downloads", tools) + emptyState("check", "Je map Downloads is leeg", "Mooi zo.");
  return head("downloads", tools) + renderGroups("downloads", d.groups, { hideTag: true });
}

function renderLarge() {
  const d = S.data.large;
  const minSel = `<select data-change="largeMin">${[50, 100, 250, 500, 1000].map((v) => `<option value="${v}" ${S.largeMin == v ? "selected" : ""}>${v >= 1000 ? v / 1000 + " GB" : v + " MB"} of groter</option>`).join("")}</select>`;
  const tools = `${minSel}<button class="btn ${d ? "" : "primary"}" data-act="scan-large">${d ? "Opnieuw zoeken" : "Zoek"}</button>`;
  if (!d) return head("large", tools) + emptyState("big", "Zoek grote bestanden", "Films, schijfkopieen, oude archieven: in een paar seconden zie je wat de meeste ruimte inneemt. Foto's- en Muziek-bibliotheken blijven buiten schot.", `<button class="btn primary big" data-act="scan-large">Zoek</button>`);
  const kinds = ["Alles", ...new Set(d.items.map((i) => i.kind))];
  const f = S.filter.large;
  const items = d.items.filter((i) => f === "Alles" || i.kind === f);
  const s = sel("large");
  let html = head("large", tools);
  html += `<div class="filters">${kinds.map((k) => `<button class="chip ${k === f ? "on" : ""}" data-filter="${esc(k)}">${esc(k)}</button>`).join("")}
    <span class="muted" style="margin-left:auto;font-size:12.5px">${plural(items.length, "bestand", "bestanden")}${d.deep ? "" : ` · <a href="#" data-act="scan-large-deep">Grondiger zoeken</a>`}</span></div>`;
  if (!items.length) return html + emptyState("check", "Niets gevonden", `Geen bestanden van ${S.largeMin} MB of groter in je eigen mappen.`);
  const allOn = items.every((i) => s.has(i.id));
  html += `<div class="card grp open"><div class="grp-h" style="cursor:default"><input type="checkbox" data-lall ${allOn ? "checked" : ""}><div class="t"><b>Alles kiezen</b></div></div><div class="grp-b" style="max-height:none">` +
    items.map((i) => `<div class="it"><input type="checkbox" data-isel="${i.id}" ${s.has(i.id) ? "checked" : ""}>
      <div class="t"><div>${esc(i.name)}</div><small>${esc(i.where)}</small></div>
      <span class="tag">${esc(i.kind)}</span><span class="age" title="Laatst gewijzigd">${fmtAge(i.age_days)}</span>
      <span class="sz">${fmtSize(i.size)}</span>
      <button class="icon-btn" title="Toon in de Finder" data-reveal="${i.id}">${ic("eye")}</button></div>`).join("") + `</div></div>`;
  return html;
}

function renderDupes() {
  const d = S.data.dupes;
  const folder = S.dupeFolder || "je thuismap";
  const minSel = `<select data-change="dupeMin">${[0.1, 1, 10, 100].map((v) => `<option value="${v}" ${S.dupeMin == v ? "selected" : ""}>vanaf ${v < 1 ? "100 kB" : v + " MB"}</option>`).join("")}</select>`;
  const tools = `<button class="btn" data-act="dupe-folder">${ic("folder").replace("<svg", '<svg style="width:15px;height:15px;vertical-align:-3px;margin-right:4px"')}${esc(folder.replace(/^\/Users\/[^/]+/, "~"))}</button>${minSel}
    <button class="btn ${d ? "" : "primary"}" data-act="scan-dupes">${d ? "Opnieuw zoeken" : "Zoek"}</button>`;
  if (!d) return head("dupes", tools) + emptyState("copy", "Zoek dubbele bestanden", "Schoonschip vergelijkt de inhoud van bestanden, niet alleen de naam. Kies eventueel eerst een map, zoals Documenten of Afbeeldingen.", `<button class="btn primary big" data-act="scan-dupes">Zoek in ${esc(folder.replace(/^\/Users\/[^/]+/, "~"))}</button>`);
  if (!d.groups.length) return head("dupes", tools) + emptyState("check", "Geen dubbele bestanden", `${plural(d.files, "bestand", "bestanden")} bekeken in ${esc(d.folder)}. Alles is uniek.`);
  const groups = d.groups.map((g) => ({ key: g.key, title: g.title, desc: `${g.items.length} keer · ${g.kind}`, icon: "copy", items: g.items }));
  return head("dupes", tools) + `<div class="filters"><span class="muted">${plural(d.groups.length, "groep", "groepen")} · ${fmtSize(d.wasted)} dubbel</span>
    <button class="btn small" style="margin-left:auto" data-act="dupe-auto">Kies automatisch (bewaar steeds de oudste)</button>
    <button class="btn small" data-act="dupe-none">Niets kiezen</button></div>` + renderGroups("dupes", groups, { hideTag: true });
}

function renderSpace() {
  const d = S.data.space;
  if (!d) return head("space") + emptyState("map", "Waar blijft mijn ruimte?", "Schoonschip meet hoe groot elke map in je thuismap is. Daarna klik je door naar wat je wilt bekijken.", `<button class="btn primary big" data-act="space-home">Meet mijn thuismap</button>`);
  const parts = [];
  const homeLbl = d.label.startsWith("~") ? d.label : d.label;
  const segs = homeLbl.split("/").filter(Boolean);
  let acc = d.label.startsWith("~") ? S.overview.home : "";
  const crumbs = segs.map((seg, n) => {
    if (n === 0 && seg === "~") return `<button data-space="${esc(acc)}">Thuismap</button>`;
    acc += "/" + seg;
    return `<span class="muted">›</span><button data-space="${esc(acc)}">${esc(seg)}</button>`;
  }).join("");
  const max = d.items.length ? d.items[0].size : 1;
  const s = sel("space");
  const tools = `<button class="btn" data-space="${esc(d.path)}">Opnieuw meten</button><button class="btn" data-act="space-apps">Programma's</button>`;
  let html = head("space", tools) + `<div class="crumbs">${d.parent ? `<button data-space="${esc(d.parent)}">${ic("back").replace("<svg", '<svg style="width:13px;height:13px;vertical-align:-2px"')}</button>` : ""}${crumbs}<span class="muted" style="margin-left:auto">${fmtSize(d.total)}</span></div>`;
  html += `<div class="card">` + (d.items.length ? d.items.map((i) => `<div class="space-row ${i.dir ? "dir" : ""}" ${i.dir ? `data-space="${esc(i.path)}"` : ""}>
     <span class="chk">${i.id ? `<input type="checkbox" data-isel="${i.id}" ${s.has(i.id) ? "checked" : ""}>` : ""}</span>
     <div class="n">${ic(i.dir ? "folder" : "file")}<span>${esc(i.name)}</span></div>
     <div class="b"><div class="meter"><i style="width:${max ? Math.max(0.5, (i.size / max) * 100) : 0}%"></i></div></div>
     <div class="sz">${fmtSize(i.size)}</div>
     <button class="icon-btn" title="Toon in de Finder" data-revealpath="${esc(i.path)}">${ic("eye")}</button></div>`).join("") : `<div class="empty"><p>Deze map is leeg.</p></div>`) + `</div>`;
  return html;
}

function renderApps() {
  if (S.app) return renderAppDetail();
  const d = S.data.apps;
  if (!d) return head("apps") + emptyState("apps", "Programma's bekijken", "Zie hoe groot je programma's zijn en wanneer je ze voor het laatst gebruikte.", `<button class="btn primary big" data-act="scan-apps">Bekijk programma's</button>`);
  const q = S.filter.apps.toLowerCase();
  let apps = d.apps.filter((a) => !q || a.name.toLowerCase().includes(q));
  const sort = S.filter.appSort;
  if (sort === "size") apps = apps.slice().sort((a, b) => b.size - a.size);
  if (sort === "unused") apps = apps.slice().sort((a, b) => (b.unused_days ?? 1e9) - (a.unused_days ?? 1e9));
  const tools = `<input type="search" placeholder="Zoek een programma" value="${esc(S.filter.apps)}" data-input="apps">
    <select data-change="appSort"><option value="name" ${sort === "name" ? "selected" : ""}>Op naam</option><option value="size" ${sort === "size" ? "selected" : ""}>Grootste eerst</option><option value="unused" ${sort === "unused" ? "selected" : ""}>Langst niet gebruikt</option></select>
    <button class="btn" data-act="scan-apps">Vernieuw</button>`;
  return head("apps", tools) + `<div class="card apps">` + apps.map((a) => `<div class="app-row" data-app="${esc(a.path)}">
      <img src="/api/appicon?t=${encodeURIComponent(TOKEN)}&path=${encodeURIComponent(a.path)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=ph></div>'">
      <div class="n"><div>${esc(a.name)}${a.running ? '<span class="pill run">open</span>' : ""}${a.appstore ? '<span class="pill">App Store</span>' : ""}</div><small>${esc(a.version ? "Versie " + a.version : "")}</small></div>
      <div class="u">${a.unused_days == null ? "" : a.unused_days > 180 ? `<span class="warn">${fmtAge(a.unused_days)} niet gebruikt</span>` : "gebruikt " + (a.unused_days < 2 ? fmtAge(a.unused_days) : fmtAge(a.unused_days) + " geleden")}</div>
      <div class="sz">${fmtSize(a.size)}</div></div>`).join("") + `</div>`;
}

function renderAppDetail() {
  const a = S.app;
  const d = S.data.leftovers;
  let html = `<div class="head"><div><button class="btn small" data-act="app-back">${ic("back").replace("<svg", '<svg style="width:13px;height:13px;vertical-align:-2px"')} Alle programma's</button></div></div>`;
  html += `<div class="app-detail"><img src="/api/appicon?t=${encodeURIComponent(TOKEN)}&path=${encodeURIComponent(a.path)}" alt="" onerror="this.style.visibility='hidden'">
    <div><h1 style="margin:0;font-size:24px">${esc(a.name)}</h1><div class="muted">${esc(a.bundle || "")}${a.version ? " · versie " + esc(a.version) : ""}</div></div></div>`;
  if (!d) return html;
  if (d.running) html += `<div class="banner" style="margin:0 0 14px">${ic("lock").replace("<svg", '<svg style="width:18px;height:18px"')}<div class="grow">${esc(a.name)} is nog open. Stop het programma eerst (⌘Q).</div></div>`;
  if (d.appstore) html += `<p class="muted" style="margin-top:0">Dit programma komt uit de App Store. macOS vraagt misschien om je wachtwoord. Je kunt het later altijd opnieuw downloaden.</p>`;
  html += `<p class="muted">Alles hieronder gaat naar de Prullenmand. Haal vinkjes weg bij wat je wilt bewaren, bijvoorbeeld je voorkeuren als je het programma later opnieuw installeert.</p>`;
  const s = sel("leftovers");
  html += `<div class="card">` + d.items.map((i) => `<div class="it"><input type="checkbox" data-isel="${i.id}" ${s.has(i.id) ? "checked" : ""}>
     <div class="t"><div>${esc(i.name)}</div><small>${esc(i.note)}</small></div><span class="sz">${fmtSize(i.size)}</span>
     <button class="icon-btn" title="Toon in de Finder" data-reveal="${i.id}">${ic("eye")}</button></div>`).join("") + `</div>`;
  return html;
}

function renderStartup() {
  const d = S.data.startup;
  const tools = `<button class="btn" data-settings="login">Inlogonderdelen in Systeeminstellingen</button>${d ? `<button class="btn" data-act="scan-startup">Vernieuw</button>` : ""}`;
  if (!d) return head("startup", tools) + emptyState("power", "Wat start er vanzelf?", "Bekijk welke hulpprogramma's en diensten automatisch met je Mac meestarten.", `<button class="btn primary big" data-act="scan-startup">Bekijk</button>`);
  const groups = d.groups.map((g) => ({ ...g, desc: g.editable ? "Weghalen kan zonder wachtwoord. Het programma zelf blijft staan." : "Alleen bekijken. Wil je hier iets weghalen, verwijder dan het bijbehorende programma.", icon: g.editable ? "power" : "lock" }));
  const nonEmpty = groups.filter((g) => g.items.length);
  if (!nonEmpty.length) return head("startup", tools) + emptyState("check", "Niets gevonden", "Er starten geen extra diensten vanzelf.");
  return head("startup", tools) + renderGroups("startup", nonEmpty, { noSize: true, hideTag: true, canSelect: (i, g) => g.editable });
}

function renderMaint() {
  const d = S.data.maint;
  if (!d) { loadTasks(); return head("maint") + `<div class="busy"><div class="spinner"></div></div>`; }
  const out = S.taskOut || {};
  return head("maint") + (d.mac ? "" : `<div class="banner" style="margin:0 0 14px">Onderhoudstaken werken alleen op een Mac.</div>`) +
    `<div class="tasks">` + d.tasks.map((t) => {
      const run = RUNNING["task-" + t.key];
      return `<div class="card task"><b>${esc(t.title)}</b><p>${esc(t.desc)}${t.key === "snapshots" && t.count != null ? ` <br><span class="${t.count ? "warn" : "ok"}">${t.count ? plural(t.count, "snapshot", "snapshots") + " op je Mac" : "Geen snapshots op je Mac"}</span>` : ""}</p>
        ${out[t.key] ? `<pre>${esc(out[t.key])}</pre>` : ""}
        <div class="foot"><button class="btn ${run ? "" : "primary"}" data-task="${t.key}" ${run || !d.mac ? "disabled" : ""}>${run ? "Bezig…" : "Uitvoeren"}</button>
        ${t.admin ? `<small>${ic("lock").replace("<svg", '<svg style="width:12px;height:12px;vertical-align:-1px"')} vraagt je wachtwoord</small>` : ""}</div></div>`;
    }).join("") + `</div>`;
}

const RENDER = { overview: renderOverview, junk: renderJunk, downloads: renderDownloads, large: renderLarge, dupes: renderDupes,
  space: renderSpace, apps: renderApps, startup: renderStartup, maint: renderMaint };

// ---------------------------------------------------------------------------
// Acties

async function scan(page, kind, params) {
  try {
    const res = await runJob(page, kind, params);
    if (res) {
      S.data[page] = res;
      initSelection(page);
      if (page === "junk" || page === "downloads") openBiggest(page);
    }
  } catch (e) { toast(e.message, true); }
  render();
  if (page === "junk") checkBanner();
}

function openBiggest(page) {
  const d = S.data[page];
  const o = opened(page);
  o.clear();
  if (d && d.groups && d.groups.length === 1) o.add(d.groups[0].key);
}

async function smartScan() {
  try {
    const res = await runJob("overview", "smart");
    if (res) {
      S.data.smart = res;
      S.data.junk = res.junk; initSelection("junk"); openBiggest("junk");
      S.data.downloads = res.downloads; initSelection("downloads");
    }
  } catch (e) { toast(e.message, true); }
  render();
  checkBanner();
}

async function doClean(page, items, after) {
  const size = items.reduce((a, i) => a + (i.size || 0), 0);
  const del = items.filter((i) => i.action === "delete");
  const trash = items.filter((i) => i.action === "trash");
  const empty = items.find((i) => i.action === "empty_trash");
  let html = `<p>${plural(items.length, "onderdeel", "onderdelen")}, samen ${fmtSize(size)}${empty && empty.unknown ? " plus je Prullenmand" : ""}.</p><ul>`;
  if (del.length) html += `<li>${plural(del.length, "onderdeel wordt", "onderdelen worden")} meteen verwijderd (${fmtSize(del.reduce((a, i) => a + i.size, 0))}). Dit maakt je Mac vanzelf opnieuw aan.</li>`;
  if (trash.length) html += `<li>${plural(trash.length, "onderdeel gaat", "onderdelen gaan")} naar de Prullenmand (${fmtSize(trash.reduce((a, i) => a + i.size, 0))}). Daar kun je ze terughalen.</li>`;
  if (empty) html += `<li><b>De Prullenmand wordt definitief geleegd.</b></li>`;
  html += `</ul>`;
  if (del.some((i) => i.note && i.note.startsWith("Programma is open"))) html += `<p class="warn">Sommige programma's zijn nog open. Sluit ze voor het beste resultaat.</p>`;
  if (page === "startup") html = `<p>${plural(items.length, "onderdeel gaat", "onderdelen gaan")} naar de Prullenmand en ${items.length === 1 ? "start" : "starten"} niet meer vanzelf.</p>`;
  const titles = { leftovers: `${S.app ? S.app.name : "Programma"} verwijderen?`, startup: "Weghalen uit opstarten?" };
  const ok = await confirmBox(titles[page] || "Opruimen?", html, page === "leftovers" ? "Verwijder" : page === "startup" ? "Weghalen" : "Opruimen");
  if (!ok) return;
  const runPage = page === "leftovers" ? "apps" : page;
  let res;
  try {
    const { job } = await api("clean", { module: page, ids: items.map((i) => i.id) });
    RUNNING[runPage] = { id: job, kind: "clean", progress: 0, message: "" };
    render();
    for (;;) {
      await new Promise((r) => setTimeout(r, 250));
      const st = await api("job?id=" + job);
      RUNNING[runPage].progress = st.progress; RUNNING[runPage].message = st.message;
      if (S.page === runPage) updateBusy(runPage);
      if (st.status === "done") { res = st.result; break; }
      if (st.status === "error") throw new Error(st.error);
      if (st.status === "cancelled") break;
    }
  } catch (e) {
    delete RUNNING[runPage];
    toast(e.message, true);
    render();
    return;
  }
  delete RUNNING[runPage];
  if (!res) { render(); return; }
  removeDone(page, new Set(res.done));
  if (after) after(res);
  refreshOverview();
  render();
  showDone(res);
}

function removeDone(page, done) {
  const d = S.data[page];
  if (!d) return;
  const keep = (i) => !done.has(i.id);
  if (d.groups) {
    d.groups.forEach((g) => (g.items = g.items.filter(keep)));
    d.groups = d.groups.filter((g) => g.items.length > (page === "dupes" ? 1 : 0));
    if (page === "dupes") d.wasted = d.groups.reduce((a, g) => a + g.size * (g.items.length - 1), 0);
  }
  if (d.items) d.items = d.items.filter(keep);
  const s = sel(page);
  done.forEach((id) => s.delete(id));
}

function showDone(res) {
  const total = res.freed + res.trashed;
  let html = `<div class="center"><div class="done-ic">${ic("check")}</div><h2>${total ? fmtSize(total) + " opgeruimd" : "Klaar"}</h2>`;
  if (res.trashed) html += `<p>${fmtSize(res.trashed)} staat nu in de Prullenmand. Leeg die om de ruimte echt vrij te maken.</p>`;
  else if (res.freed) html += `<p>Meteen vrijgemaakt.</p>`;
  html += `</div>`;
  if (res.failed.length) {
    html += `<p class="warn" style="margin-top:8px">Niet alles lukte:</p><ul>` + res.failed.slice(0, 8).map((f) => `<li>${esc(f.name)}: ${esc(f.reason)}</li>`).join("") +
      (res.failed.length > 8 ? `<li>en nog ${res.failed.length - 8}</li>` : "") + `</ul>`;
  }
  html += `<div class="acts">${res.trashed ? `<button class="btn" data-a="emptytrash">Prullenmand legen</button>` : ""}<button class="btn primary" data-a="ok">OK</button></div>`;
  modal(html);
  $("#modalCard").onclick = async (e) => {
    const a = e.target.closest("[data-a]");
    if (!a) return;
    closeModal();
    if (a.dataset.a === "emptytrash") {
      S.page = "junk";
      await scan("junk", "junk");
      const t = S.data.junk && S.data.junk.groups.find((g) => g.key === "trash");
      if (t) { S.sel.junk = new Set(t.items.map((i) => i.id)); render(); doClean("junk", t.items); }
    }
  };
}

async function refreshOverview() {
  try {
    S.overview = await api("overview");
    renderSideFoot();
    if (S.page === "overview") render();
  } catch (e) { /* stil */ }
}

async function loadTasks() {
  if (loadTasks.busy) return;
  loadTasks.busy = true;
  try { S.data.maint = await api("tasks"); } catch (e) { toast(e.message, true); }
  loadTasks.busy = false;
  if (S.page === "maint") render();
}

async function runTask(key) {
  const page = "task-" + key;
  S.taskOut = S.taskOut || {};
  try {
    const p = runJob(page, "task", { key });
    render();
    const res = await p;
    if (res) { S.taskOut[key] = res.output || "Klaar."; toast(res.title + ": klaar"); }
  } catch (e) {
    S.taskOut[key] = e.message;
    if (e.message !== "Geannuleerd.") toast(e.message, true);
  }
  if (key === "snapshots") { S.data.maint = null; }
  render();
}

async function openApp(path) {
  const a = S.data.apps.apps.find((x) => x.path === path);
  if (!a) return;
  S.app = a;
  S.data.leftovers = null;
  render();
  try {
    const res = await runJob("apps", "leftovers", { path });
    if (res && S.app === a) { S.data.leftovers = res; initSelection("leftovers"); }
  } catch (e) { toast(e.message, true); S.app = null; }
  render();
}

function checkBanner() {
  const o = S.overview;
  const junk = S.data.junk;
  const noFda = (junk && junk.full_disk_access === false) || (o && o.full_disk_access === false);
  $("#banner").innerHTML = noFda && !S.hideBanner ? `<div class="banner">${ic("lock").replace("<svg", '<svg style="width:20px;height:20px;flex:none;color:var(--accent-ink)"')}
    <div class="grow"><b>Grondiger opruimen?</b> Geef Schoonschip 'Volledige schijftoegang', dan kan het ook bij Mail en de Prullenmand kijken. Zet daarna Schoonschip even uit en weer aan.</div>
    <button class="btn small" data-settings="fda">Open instellingen</button><button class="icon-btn" data-act="hide-banner" title="Verberg">✕</button></div>` : "";
}

// ---------------------------------------------------------------------------
// Klikken

document.addEventListener("click", async (e) => {
  const t = e.target;
  const navBtn = t.closest("[data-page]");
  if (navBtn) { S.page = navBtn.dataset.page; render(); if (S.page === "overview") refreshOverview(); return; }
  const go = t.closest("[data-go]");
  if (go) { S.page = go.dataset.go; render(); if (S.page === "apps" && !S.data.apps) scan("apps", "apps"); return; }

  // vinkjes
  if (t.matches("input[data-isel]")) {
    const page = S.page === "apps" ? "leftovers" : S.page;
    const s = sel(page);
    t.checked ? s.add(t.dataset.isel) : s.delete(t.dataset.isel);
    e.stopPropagation();
    render();
    return;
  }
  if (t.matches("input[data-gsel]")) {
    e.stopPropagation();
    const page = S.page;
    const g = (page === "dupes" ? S.data.dupes.groups : S.data[page].groups).find((x) => x.key === t.dataset.gsel);
    const s = sel(page);
    const ids = g.items.map((i) => i.id).filter(Boolean);
    const allOn = ids.every((id) => s.has(id));
    ids.forEach((id) => (allOn ? s.delete(id) : s.add(id)));
    render();
    return;
  }
  if (t.matches("input[data-lall]")) {
    const f = S.filter.large;
    const ids = S.data.large.items.filter((i) => f === "Alles" || i.kind === f).map((i) => i.id);
    const s = sel("large");
    t.checked ? ids.forEach((id) => s.add(id)) : ids.forEach((id) => s.delete(id));
    render();
    return;
  }
  const tog = t.closest("[data-toggle]");
  if (tog && !t.closest("input")) {
    const o = opened(S.page);
    const k = tog.dataset.toggle;
    o.has(k) ? o.delete(k) : o.add(k);
    tog.parentElement.classList.toggle("open");
    return;
  }
  const rv = t.closest("[data-reveal]");
  if (rv) {
    e.stopPropagation();
    const module = S.page === "apps" ? "leftovers" : S.page;
    api("reveal", { module, id: rv.dataset.reveal }).catch((err) => toast(err.message, true));
    return;
  }
  const rvp = t.closest("[data-revealpath]");
  if (rvp) { e.stopPropagation(); api("reveal", { path: rvp.dataset.revealpath }).catch((err) => toast(err.message, true)); return; }
  const sp = t.closest("[data-space]");
  if (sp) { scan("space", "space", { path: sp.dataset.space }); return; }
  const fl = t.closest("[data-filter]");
  if (fl) { S.filter.large = fl.dataset.filter; render(); return; }
  const appRow = t.closest("[data-app]");
  if (appRow) { openApp(appRow.dataset.app); return; }
  const st = t.closest("[data-settings]");
  if (st) { api("settings", { pane: st.dataset.settings }).catch((err) => toast(err.message, true)); return; }
  const tk = t.closest("[data-task]");
  if (tk) { runTask(tk.dataset.task); return; }
  const q = t.closest("[data-quit]");
  if (q) {
    if (await confirmBox(`${q.dataset.name} stoppen?`, `<p>Het programma wordt netjes afgesloten. Heb je nog iets niet bewaard, dan vraagt het programma dat zelf.</p>`, "Stop")) {
      try { await api("quit_app", { bundle: q.dataset.quit }); toast(q.dataset.name + " wordt gestopt"); setTimeout(refreshOverview, 1500); }
      catch (err) { toast(err.message, true); }
    }
    return;
  }

  const act = t.closest("[data-act]");
  if (!act) return;
  if (act.tagName === "A") e.preventDefault();
  const a = act.dataset.act;
  const page = S.page;
  switch (a) {
    case "cancel": cancelJob(page); break;
    case "smart": smartScan(); break;
    case "smart-clean": {
      const items = selectedItems("junk");
      if (!items.length) { S.page = "junk"; render(); break; }
      doClean("junk", items, () => { S.data.smart = null; });
      break;
    }
    case "scan-junk": scan("junk", "junk"); break;
    case "scan-downloads": scan("downloads", "downloads"); break;
    case "scan-large": scan("large", "large", { min_mb: S.largeMin }); break;
    case "scan-large-deep": scan("large", "large", { min_mb: S.largeMin, deep: true }); break;
    case "scan-dupes": scan("dupes", "dupes", { folder: S.dupeFolder, min_mb: S.dupeMin }); break;
    case "dupe-folder":
      try { const r = await api("choose_folder", {}); if (r.folder) { S.dupeFolder = r.folder.replace(/\/$/, ""); S.data.dupes = null; render(); } }
      catch (err) { toast(err.message, true); }
      break;
    case "dupe-auto": initSelection("dupes"); render(); break;
    case "dupe-none": S.sel.dupes = new Set(); render(); break;
    case "space-home": scan("space", "space", {}); break;
    case "space-apps": scan("space", "space", { path: "/Applications" }); break;
    case "scan-apps": S.app = null; scan("apps", "apps"); break;
    case "scan-startup": scan("startup", "startup"); break;
    case "app-back": S.app = null; S.data.leftovers = null; render(); break;
    case "hide-banner": S.hideBanner = true; checkBanner(); break;
    case "clean": {
      const module = page === "apps" ? "leftovers" : page;
      const items = selectedItems(module);
      if (!items.length) break;
      if (module === "leftovers") {
        const path = S.app.path;
        doClean("leftovers", items, (res) => {
          const appItem = items.find((i) => i.is_app);
          if (appItem && res.done.includes(appItem.id)) {
            S.data.apps.apps = S.data.apps.apps.filter((x) => x.path !== path);
            S.app = null; S.data.leftovers = null;
          }
        });
      } else {
        doClean(module, items);
      }
      break;
    }
  }
});

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.change === "largeMin") { S.largeMin = Number(t.value); }
  if (t.dataset.change === "dupeMin") { S.dupeMin = Number(t.value); }
  if (t.dataset.change === "appSort") { S.filter.appSort = t.value; render(); }
});

document.addEventListener("input", (e) => {
  const t = e.target;
  if (t.dataset.input === "apps") {
    S.filter.apps = t.value;
    const pos = t.selectionStart;
    render();
    const n = $('input[data-input="apps"]');
    if (n) { n.focus(); n.setSelectionRange(pos, pos); }
  }
});

// gedeeltelijk aangevinkte groepen
const mo = new MutationObserver(() => {
  document.querySelectorAll('input[data-some="1"]').forEach((el) => (el.indeterminate = true));
});
mo.observe($("#page"), { childList: true, subtree: true });

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#modal").hidden) { const no = $('#modalCard [data-a="no"], #modalCard [data-a="ok"]'); if (no) no.click(); }
});

// ---------------------------------------------------------------------------
// Start

(async function start() {
  render();
  await refreshOverview();
  checkBanner();
  render();
  setInterval(() => { if (S.page === "overview" && !RUNNING.overview) refreshOverview(); }, 8000);
})();
