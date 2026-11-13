"use strict";
/* Notulist: venster. Praat met de lokale server van Notulist (server.py). */

const TOKEN = new URLSearchParams(location.search).get("t") || "";

const staat = {
  status: null,
  meetings: [],
  versie: -1,
  zoek: "",
  weergave: "start",   // start | meeting | instellingen
  gekozen: null,       // id van de gekozen meeting
  detail: null,
  tab: "notulen",
  instellingen: null,
  toestemmingen: null,
  volgOpname: false,   // na "Neem nu op" meteen naar de opname gaan
};

// ---------------------------------------------------------------- hulpjes

async function api(pad, opties = {}) {
  const r = await fetch(pad, {
    ...opties,
    headers: { "X-Notulist-Token": TOKEN, "Content-Type": "application/json" },
    body: opties.body !== undefined ? JSON.stringify(opties.body) : undefined,
  });
  let data = {};
  try { data = await r.json(); } catch (e) { /* geen JSON */ }
  if (!r.ok) throw new Error(data.fout || "Er ging iets mis (" + r.status + ")");
  return data;
}

function el(tag, attrs, ...kinderen) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else if (k === "checked") e.checked = !!v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kind of kinderen.flat(Infinity)) {
    if (kind === null || kind === undefined || kind === false) continue;
    e.append(kind instanceof Node ? kind : document.createTextNode(String(kind)));
  }
  return e;
}

const ICONEN = {
  zoek: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="7" cy="7" r="5"/><path d="M11 11l3.5 3.5" stroke-linecap="round"/></svg>',
  tandwiel: '<svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="2.6"/><path d="M10 1.8v2.4M10 15.8v2.4M18.2 10h-2.4M4.2 10H1.8M15.8 4.2l-1.7 1.7M5.9 14.1l-1.7 1.7M15.8 15.8l-1.7-1.7M5.9 5.9L4.2 4.2" stroke-linecap="round"/></svg>',
  speel: '<svg width="14" height="14" viewBox="0 0 14 14"><path d="M3.5 1.8v10.4L12 7z" fill="currentColor"/></svg>',
  pauze: '<svg width="14" height="14" viewBox="0 0 14 14"><rect x="2.5" y="2" width="3.2" height="10" rx="1" fill="currentColor"/><rect x="8.3" y="2" width="3.2" height="10" rx="1" fill="currentColor"/></svg>',
  kopieer: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="5" width="9" height="9" rx="2"/><path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5"/></svg>',
  export: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v8M4.5 6.5L8 10l3.5-3.5M2.5 11v1.5A1.5 1.5 0 0 0 4 14h8a1.5 1.5 0 0 0 1.5-1.5V11"/></svg>',
  meer: '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="3.5" cy="8" r="1.4" fill="currentColor"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/><circle cx="12.5" cy="8" r="1.4" fill="currentColor"/></svg>',
  vink: '<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.2l2.4 2.4 4.6-5"/></svg>',
  let_op: '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M8 1.8L1.5 13.5h13z" stroke-linejoin="round"/><path d="M8 6.2v3.4M8 11.6v.2"/></svg>',
  ster: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
  map: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M1.8 4A1.5 1.5 0 0 1 3.3 2.5h3l1.5 1.8h4.9A1.5 1.5 0 0 1 14.2 5.8v6.7a1.5 1.5 0 0 1-1.5 1.5H3.3a1.5 1.5 0 0 1-1.5-1.5z"/></svg>',
};

function icoon(naam, cls) {
  const s = el("span", { class: cls || "icoon", "aria-hidden": "true" });
  s.innerHTML = ICONEN[naam];
  s.style.display = "inline-flex";
  return s;
}

const DAGEN = ["zondag", "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag"];
const MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"];

function klok(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const u = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  return (u ? u + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
}

function duur(sec) {
  if (sec === null || sec === undefined) return "";
  if (sec < 60) return "< 1 min";
  const m = Math.round(sec / 60);
  return m < 60 ? m + " min" : Math.floor(m / 60) + " u " + (m % 60 ? (m % 60) + " min" : "");
}

function uurMin(d) { return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); }
function dagStart(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); }

function datumLang(ts) {
  const d = new Date(ts * 1000);
  return DAGEN[d.getDay()] + " " + d.getDate() + " " + MAANDEN[d.getMonth()] + " " + d.getFullYear() + ", " + uurMin(d);
}

function groepVan(ts) {
  const d = new Date(ts * 1000), nu = new Date();
  const dagen = Math.round((dagStart(nu) - dagStart(d)) / 86400000);
  if (dagen <= 0) return "Vandaag";
  if (dagen === 1) return "Gisteren";
  if (dagen < 7) return "Afgelopen week";
  return MAANDEN[d.getMonth()] + (d.getFullYear() !== nu.getFullYear() ? " " + d.getFullYear() : "");
}

function itemTijd(ts) {
  const d = new Date(ts * 1000), nu = new Date();
  const dagen = Math.round((dagStart(nu) - dagStart(d)) / 86400000);
  if (dagen < 7 && dagen > 1) return DAGEN[d.getDay()].slice(0, 2) + " " + uurMin(d);
  if (dagen <= 1) return uurMin(d);
  return d.getDate() + " " + MAANDEN[d.getMonth()].slice(0, 3) + ", " + uurMin(d);
}

function markeer(tekst, vraag) {
  const woorden = (vraag || "").toLowerCase().split(/\s+/).filter(Boolean);
  if (!woorden.length) return [tekst];
  const uit = [];
  const laag = tekst.toLowerCase();
  let i = 0;
  while (i < tekst.length) {
    let beste = -1, lengte = 0;
    for (const w of woorden) {
      const p = laag.indexOf(w, i);
      if (p >= 0 && (beste < 0 || p < beste)) { beste = p; lengte = w.length; }
    }
    if (beste < 0) { uit.push(tekst.slice(i)); break; }
    if (beste > i) uit.push(tekst.slice(i, beste));
    uit.push(el("mark", {}, tekst.slice(beste, beste + lengte)));
    i = beste + lengte;
  }
  return uit;
}

function vraag(titel, uitleg, ja) {
  // Eigen dialoog: het Mac-venster (WKWebView) toont geen confirm() van de browser.
  return new Promise((klaar) => {
    const sluit = (antwoord) => { achter.remove(); document.removeEventListener("keydown", toets, true); klaar(antwoord); };
    const toets = (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); sluit(false); }
      if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); sluit(true); }
    };
    const jaKnop = el("button", { class: "knop primair gevaar-vol", onclick: () => sluit(true) }, ja);
    const achter = el("div", { class: "dialoog-achter", onclick: (e) => { if (e.target === achter) sluit(false); } },
      el("div", { class: "dialoog", role: "dialog", "aria-modal": "true" },
        el("h2", {}, titel), el("p", {}, uitleg),
        el("div", { class: "dialoog-knoppen" }, el("button", { class: "knop", onclick: () => sluit(false) }, "Annuleer"), jaKnop)));
    document.body.append(achter);
    document.addEventListener("keydown", toets, true);
    jaKnop.focus();
  });
}

let meldingTimer = null;
function meld(tekst, fout) {
  const m = document.getElementById("melding");
  m.textContent = tekst;
  m.className = "melding zichtbaar" + (fout ? " fout" : "");
  clearTimeout(meldingTimer);
  meldingTimer = setTimeout(() => { m.className = "melding" + (fout ? " fout" : ""); }, fout ? 5000 : 2600);
}

async function probeer(fn, okTekst) {
  try {
    const r = await fn();
    if (okTekst) meld(okTekst);
    return r;
  } catch (e) {
    meld(e.message, true);
    return null;
  }
}

// ---------------------------------------------------------------- gegevens

async function laadStatus() {
  try {
    staat.status = await api("/api/status");
  } catch (e) {
    return;
  }
  if (staat.status.versie !== staat.versie) {
    staat.versie = staat.status.versie;
    await laadMeetings();
    if (staat.weergave === "meeting" && staat.gekozen) await laadDetail(false);
  }
  tekenOpnameBlok();
  tekenVoet();
  if (staat.volgOpname && staat.status.opname) {
    staat.volgOpname = false;
    kies(staat.status.opname.id);
    return;
  }
  werkLiveBij();
  tekenLijst();
}

async function laadMeetings() {
  const q = staat.zoek.trim();
  try {
    staat.meetings = await api("/api/meetings" + (q ? "?q=" + encodeURIComponent(q) : ""));
  } catch (e) { /* volgende keer */ }
  tekenLijst();
}

async function laadDetail(opnieuwTekenen = true) {
  if (!staat.gekozen) return;
  const vorige = staat.detail;
  try {
    staat.detail = await api("/api/meetings/" + encodeURIComponent(staat.gekozen));
  } catch (e) {
    staat.detail = null;
    staat.gekozen = null;
    staat.weergave = "start";
    tekenInhoud();
    return;
  }
  // Niet opnieuw tekenen als er niets veranderd is (anders springt de speler terug).
  if (!opnieuwTekenen && vorige && JSON.stringify(vorige) === JSON.stringify(staat.detail)) return;
  tekenInhoud();
}

function kies(id) {
  staat.weergave = "meeting";
  if (staat.gekozen !== id) staat.tab = "notulen";
  staat.gekozen = id;
  staat.detail = null;
  tekenLijst();
  tekenInhoud();
  laadDetail();
}

// ---------------------------------------------------------------- zijbalk

function tekenOpnameBlok() {
  const blok = document.getElementById("opnameBlok");
  const s = staat.status;
  if (!s) return;
  const o = s.opname;
  const knop = o
    ? el("button", { class: "opnameknop loopt", onclick: stopOpname },
        el("span", { class: "punt" }), "Stop opname", el("span", { class: "rechts", id: "zijKlok" }, klok(o.duur)))
    : el("button", { class: "opnameknop", onclick: startOpname, disabled: s.starten },
        el("span", { class: "punt" }), s.starten ? "Opname starten…" : "Neem nu op");
  const sub = el("label", { class: "schakelaar opname-sub", title: s.herkent ? "" : "Werkt vanaf macOS 14 (Sonoma)" },
    el("input", { type: "checkbox", checked: s.automatisch && s.herkent, disabled: !s.herkent, onchange: wisselAutomatisch }),
    el("span", { class: "baan" }),
    el("span", {}, "Meetings vanzelf opnemen"));
  blok.replaceChildren(knop, sub);
}

function tekenVoet() {
  const s = staat.status;
  const voet = document.getElementById("voetStatus");
  if (!s) return;
  let stip = "stip", tekst;
  if (s.opname) { stip = "stip rood"; tekst = "Neemt op: " + (s.opname.app === "handmatig" ? "handmatig" : s.opname.app); }
  else if (s.voortgang) {
    tekst = s.voortgang.wat === "samenvatten" ? "Notulen maken…" :
      "Uitschrijven " + Math.round((s.voortgang.fractie || 0) * 100) + "%";
  } else if (!s.herkent) { stip = "stip uit"; tekst = "Herkennen niet beschikbaar"; }
  else if (s.automatisch) {
    tekst = s.gezien && s.gezien.length ? "Microfoon in gebruik: " + s.gezien.join(", ") : "Wacht op een meeting";
  } else { stip = "stip uit"; tekst = "Vanzelf opnemen staat uit"; }
  if (s.wachtrij) tekst += " (+" + s.wachtrij + ")";
  voet.replaceChildren(el("span", { class: stip }), el("span", { title: tekst }, tekst));
  document.getElementById("knopInstellingen").classList.toggle("actief", staat.weergave === "instellingen");
}

function labelVoor(m) {
  const s = staat.status || {};
  if (s.opname && s.opname.id === m.id) return el("span", { class: "label rood" }, el("span", { class: "bol" }), "Opname");
  if (s.voortgang && s.voortgang.id === m.id) {
    return el("span", { class: "label" }, s.voortgang.wat === "samenvatten" ? "Notulen…" :
      "Uitschrijven " + Math.round((s.voortgang.fractie || 0) * 100) + "%");
  }
  if (!m.transcript && (m.status === "opgenomen" || m.status === "transcriberen")) return el("span", { class: "label oranje" }, "Wachtrij");
  return null;
}

function tekenLijst() {
  const nav = document.getElementById("lijst");
  const kinderen = [];
  let groep = null;
  for (const m of staat.meetings) {
    const g = groepVan(m.start);
    if (g !== groep && !staat.zoek) { kinderen.push(el("div", { class: "groep" }, g)); groep = g; }
    const meta = [itemTijd(m.start)];
    if (m.duur) meta.push(duur(m.duur));
    if (m.app && m.app !== "handmatig") meta.push(m.app);
    kinderen.push(el("button", {
      class: "item" + (staat.weergave === "meeting" && staat.gekozen === m.id ? " gekozen" : ""),
      onclick: () => kies(m.id),
    },
      el("div", { class: "item-titel" }, m.titel),
      el("div", { class: "item-meta" }, meta.join(" · "), labelVoor(m)),
      m.fragment ? el("div", { class: "item-fragment" }, markeer(m.fragment, staat.zoek)) : null));
  }
  if (!kinderen.length) {
    kinderen.push(el("div", { class: "lijst-leeg" }, staat.zoek ? "Niets gevonden voor “" + staat.zoek + "”." : "Nog geen meetings."));
  }
  nav.replaceChildren(...kinderen);
}

// ---------------------------------------------------------------- acties

async function startOpname() {
  staat.volgOpname = true;
  await probeer(() => api("/api/opname/start", { method: "POST" }));
  setTimeout(laadStatus, 400);
}

async function stopOpname() {
  await probeer(() => api("/api/opname/stop", { method: "POST" }), "Opname gestopt. Notulist schrijft hem nu uit.");
  setTimeout(laadStatus, 400);
}

async function wisselAutomatisch(e) {
  await probeer(() => api("/api/instellingen", { method: "PATCH", body: { automatisch_opnemen: e.target.checked } }),
    e.target.checked ? "Meetings worden vanzelf opgenomen" : "Vanzelf opnemen staat uit");
  if (staat.instellingen) staat.instellingen.instellingen.automatisch_opnemen = e.target.checked;
  laadStatus();
}

async function meetingActie(actie, okTekst) {
  const id = staat.gekozen;
  const r = await probeer(() => api("/api/meetings/" + encodeURIComponent(id) + "/" + actie, { method: "POST" }), okTekst);
  if (r && actie === "kopieer" && r.ok === false && r.tekst) {
    try { await navigator.clipboard.writeText(r.tekst); meld("Gekopieerd"); } catch (e) { meld("Kopiëren lukte niet", true); }
  }
  laadStatus();
  return r;
}

async function verwijder() {
  const d = staat.detail;
  if (!d) return;
  const ja = await vraag("“" + d.titel + "” naar de prullenmand verplaatsen?",
    "Je kunt hem vanuit de prullenmand in de Finder terugzetten.", "Verplaats");
  if (!ja) return;
  const r = await probeer(() => api("/api/meetings/" + encodeURIComponent(d.id), { method: "DELETE" }), "Naar de prullenmand verplaatst");
  if (r) {
    staat.gekozen = null; staat.detail = null; staat.weergave = "start";
    await laadMeetings();
    tekenInhoud();
  }
}

async function bewaarTitel(invoer) {
  const d = staat.detail;
  const nieuw = invoer.value.trim();
  if (!d || nieuw === d.titel) return;
  const r = await probeer(() => api("/api/meetings/" + encodeURIComponent(d.id), { method: "PATCH", body: { titel: nieuw } }));
  if (r) { staat.detail = r; invoer.value = r.titel; laadMeetings(); }
}

async function wisselActie(index, li, knop) {
  const d = staat.detail;
  const gedaan = new Set(d.gedaan || []);
  if (gedaan.has(index)) gedaan.delete(index); else gedaan.add(index);
  const lijst = [...gedaan].sort((a, b) => a - b);
  const r = await probeer(() => api("/api/meetings/" + encodeURIComponent(d.id), { method: "PATCH", body: { gedaan: lijst } }));
  if (r) {
    d.gedaan = lijst;
    const aan = gedaan.has(index);
    li.classList.toggle("gedaan", aan);
    knop.classList.toggle("aan", aan);
    knop.replaceChildren(aan ? icoon("vink") : "");
  }
}

// ---------------------------------------------------------------- inhoud

let speler = null;     // <audio>
let segmentRijen = [];

function tekenInhoud() {
  const main = document.getElementById("inhoud");
  if (speler) { speler.pause(); speler = null; }
  segmentRijen = [];
  let pagina;
  if (staat.weergave === "instellingen") pagina = tekenInstellingen();
  else if (staat.weergave === "meeting" && staat.detail) pagina = tekenMeeting(staat.detail);
  else if (staat.weergave === "meeting") pagina = el("div", { class: "pagina" });
  else pagina = tekenStart();
  main.replaceChildren(pagina);
  tekenVoet();
}

function tekenStart() {
  const s = staat.status || {};
  return el("div", { class: "leeg" }, el("div", { class: "leeg-binnen" },
    el("img", { src: "/web/icoon.png", alt: "" }),
    el("h1", {}, staat.meetings.length ? "Kies een meeting" : "Welkom bij Notulist"),
    el("p", {}, staat.meetings.length
      ? "Links staan je meetings. Klik er een aan voor de notulen, het transcript en de opname."
      : "Notulist neemt je meetings op en schrijft ze uit, op je eigen Mac."),
    staat.meetings.length ? null : el("div", { class: "stappen" },
      stap(1, "Start een meeting in Zoom, Teams, Meet of een andere app.", s.herkent ? null : " (Vanzelf opnemen werkt vanaf macOS 14.)"),
      stap(2, "Notulist begint vanzelf met opnemen en stopt als de meeting klaar is."),
      stap(3, "Daarna verschijnen hier het transcript en, met Claude, de notulen met actiepunten."))));
}

function stap(nr, tekst, extra) {
  return el("div", { class: "stap" }, el("span", { class: "stap-nr" }, nr), el("span", {}, tekst, extra || ""));
}

function tekenMeeting(d) {
  const s = staat.status || {};
  const pagina = el("div", { class: "pagina" });
  const lopend = s.opname && s.opname.id === d.id;

  // kop
  const metaDelen = [datumLang(d.start)];
  if (d.duur) metaDelen.push(duur(d.duur));
  if (d.app && d.app !== "handmatig") metaDelen.push(d.app);
  const titel = el("input", {
    class: "titel", value: d.titel, "aria-label": "Titel", spellcheck: "false",
    onkeydown: (e) => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") { e.target.value = d.titel; e.target.blur(); } },
    onblur: (e) => bewaarTitel(e.target),
  });
  const meta = el("div", { class: "meta" });
  metaDelen.forEach((t, i) => { if (i) meta.append(el("span", { class: "scheiding" }, "·")); meta.append(el("span", {}, t)); });

  const knoppen = el("div", { class: "kop-knoppen" });
  if (!lopend) {
    if (d.transcript) {
      knoppen.append(
        el("button", { class: "knop", onclick: () => meetingActie("kopieer", "Notulen en transcript gekopieerd") }, icoon("kopieer"), "Kopieer"),
        el("button", { class: "knop", onclick: () => meetingActie("exporteer", "Bewaard in Downloads") }, icoon("export"), "Exporteer"));
    }
    const menu = el("div", { class: "menu verborgen" },
      el("button", { onclick: () => meetingActie("finder") }, icoon("map"), "Toon in Finder"),
      d.transcript || d.audio ? el("button", { onclick: () => meetingActie("uitschrijven", "Komt in de wachtrij om opnieuw uit te schrijven") }, "Opnieuw uitschrijven") : null,
      d.segmenten && s.samenvatten ? el("button", { onclick: () => maakNotulen() }, "Notulen opnieuw maken") : null,
      el("hr"),
      el("button", { class: "gevaar", onclick: verwijder }, "Verplaats naar prullenmand"));
    const meer = el("button", { class: "knop-icoon", title: "Meer", "aria-label": "Meer", onclick: (e) => {
      e.stopPropagation();
      menu.classList.toggle("verborgen");
    } }, icoon("meer"));
    knoppen.append(meer, menu);
  }
  pagina.append(el("div", { class: "kop" }, el("div", { class: "kop-tekst" }, titel, meta), knoppen));

  if (lopend) { pagina.append(tekenLive(s.opname)); return pagina; }
  if (d.waarschuwing) pagina.append(waarschuwing(d.waarschuwing));

  const bezig = s.voortgang && s.voortgang.id === d.id && s.voortgang.wat === "uitschrijven";
  if (!d.transcript) {
    pagina.append(el("div", { class: "kaart uitnodiging" },
      el("h2", {}, bezig ? "Notulist schrijft deze meeting uit" : "Deze meeting staat in de wachtrij"),
      el("p", {}, bezig ? "Dat gebeurt op je eigen Mac. Bij een lange meeting kan het even duren." : "Hij wordt uitgeschreven zodra de meetings ervoor klaar zijn."),
      el("div", { class: "voortgang" + (bezig ? "" : " onbepaald") }, el("div", { id: "voortgangBalk", style: bezig ? "width:" + Math.round((s.voortgang.fractie || 0) * 100) + "%" : "" }))));
    if (d.audio) pagina.append(tekenSpeler(d));
    return pagina;
  }

  if (d.audio) pagina.append(tekenSpeler(d));

  const aantal = d.segmenten ? d.segmenten.length : null;
  const tabs = el("div", { class: "tabs", role: "tablist" },
    el("button", { class: "tab" + (staat.tab === "notulen" ? " actief" : ""), role: "tab", onclick: () => { staat.tab = "notulen"; tekenInhoudBehoudSpeler(); } }, "Notulen"),
    el("button", { class: "tab" + (staat.tab === "transcript" ? " actief" : ""), role: "tab", onclick: () => { staat.tab = "transcript"; tekenInhoudBehoudSpeler(); } },
      "Transcript", aantal !== null ? el("span", { class: "teller" }, aantal) : null));
  pagina.append(tabs, el("div", { id: "tabInhoud" }, staat.tab === "notulen" ? tekenNotulen(d) : tekenTranscript(d)));
  return pagina;
}

function tekenInhoudBehoudSpeler() {
  // Alleen de tab-inhoud vervangen, zodat de opname gewoon doorspeelt.
  const plek = document.getElementById("tabInhoud");
  const d = staat.detail;
  if (!plek || !d) return tekenInhoud();
  document.querySelectorAll(".tab").forEach((t, i) => t.classList.toggle("actief", (i === 0) === (staat.tab === "notulen")));
  segmentRijen = [];
  plek.replaceChildren(staat.tab === "notulen" ? tekenNotulen(d) : tekenTranscript(d));
  werkActiefSegmentBij(true);
}

function waarschuwing(tekst, fout) {
  return el("div", { class: "waarschuwing" + (fout ? " foutkaart" : "") }, icoon("let_op", "icoon"), el("div", {}, tekst));
}

function tekenSpeler(d) {
  speler = new Audio("/api/meetings/" + encodeURIComponent(d.id) + "/audio?t=" + encodeURIComponent(TOKEN));
  speler.preload = "metadata";
  const knop = el("button", { class: "speel", "aria-label": "Afspelen" }, icoon("speel"));
  const nu = el("span", { class: "tijd" }, "0:00");
  const totaal = el("span", { class: "tijd rechts" }, d.duur ? klok(d.duur) : "–");
  const schuif = el("input", { class: "schuif", type: "range", min: "0", max: "1000", value: "0", "aria-label": "Positie" });
  const snelheden = [1, 1.25, 1.5, 2];
  const snel = el("button", { class: "snelheid", title: "Afspeelsnelheid" }, "1×");
  let slepen = false;
  const a = speler;
  knop.onclick = () => { if (a.paused) a.play(); else a.pause(); };
  a.addEventListener("play", () => knop.replaceChildren(icoon("pauze")));
  a.addEventListener("pause", () => knop.replaceChildren(icoon("speel")));
  a.addEventListener("loadedmetadata", () => { if (isFinite(a.duration)) totaal.textContent = klok(a.duration); });
  a.addEventListener("timeupdate", () => {
    nu.textContent = klok(a.currentTime);
    if (!slepen && isFinite(a.duration) && a.duration) schuif.value = String(Math.round(a.currentTime / a.duration * 1000));
    werkActiefSegmentBij(false);
  });
  schuif.addEventListener("input", () => { slepen = true; if (isFinite(a.duration)) nu.textContent = klok(schuif.value / 1000 * a.duration); });
  schuif.addEventListener("change", () => { slepen = false; if (isFinite(a.duration)) a.currentTime = schuif.value / 1000 * a.duration; });
  snel.onclick = () => {
    const i = (snelheden.indexOf(a.playbackRate) + 1) % snelheden.length;
    a.playbackRate = snelheden[i];
    snel.textContent = String(snelheden[i]).replace(".", ",") + "×";
  };
  return el("div", { class: "speler" }, knop, nu, schuif, totaal, snel);
}

function speelVanaf(sec) {
  if (!speler) return;
  speler.currentTime = Math.max(0, sec - 0.3);
  speler.play();
}

let actiefIndex = -1;
function werkActiefSegmentBij(forceer) {
  if (!speler || !segmentRijen.length) return;
  const t = speler.currentTime;
  let index = -1;
  for (let i = 0; i < segmentRijen.length; i++) {
    if (segmentRijen[i].start <= t + 0.2) index = i; else break;
  }
  if (index === actiefIndex && !forceer) return;
  if (actiefIndex >= 0 && segmentRijen[actiefIndex]) segmentRijen[actiefIndex].rij.classList.remove("actief");
  actiefIndex = index;
  if (index >= 0 && (!speler.paused || forceer)) {
    const rij = segmentRijen[index].rij;
    rij.classList.add("actief");
    const box = rij.getBoundingClientRect();
    if (!speler.paused && (box.top < 80 || box.bottom > window.innerHeight - 40)) rij.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function tekenTranscript(d) {
  if (!d.segmenten) return el("div", { class: "tekst-oud" }, d.tekst || "");
  if (!d.segmenten.length) return el("div", { class: "kaart" }, el("p", {}, "Er is geen gesproken tekst gevonden in deze opname."));
  const box = el("div", { class: "transcript" });
  const ik = (staat.instellingen && staat.instellingen.instellingen.naam_ik) || "Ik";
  let treffers = 0;
  d.segmenten.forEach((seg) => {
    const klasse = seg.spreker === ik ? "ik" : "anderen";
    const tekst = markeer(seg.tekst, staat.zoek);
    if (tekst.length > 1) treffers++;
    const rij = el("div", { class: "seg" },
      el("button", { class: "seg-tijd", title: "Speel vanaf hier", onclick: () => speelVanaf(seg.start) }, klok(seg.start)),
      el("div", {}, el("div", { class: "seg-spreker " + klasse }, seg.spreker), el("div", { class: "seg-tekst" }, tekst)));
    segmentRijen.push({ start: seg.start, rij });
    box.append(rij);
  });
  const kop = staat.zoek.trim() ? el("div", { class: "transcript-zoek" }, treffers + " " + (treffers === 1 ? "stuk" : "stukken") + " met “" + staat.zoek.trim() + "”") : null;
  return el("div", {}, kop, box);
}

function tekenNotulen(d) {
  const s = staat.status || {};
  const bezig = s.voortgang && s.voortgang.id === d.id && s.voortgang.wat === "samenvatten";
  const inWachtrij = !bezig && d.segmenten && !d.samenvatting_data && s.samenvatten && s.wachtrij > 0;
  if (bezig || inWachtrij) {
    return el("div", { class: "kaart uitnodiging" },
      el("div", { class: "groot-icoon" }, icoon("ster")),
      el("h2", {}, bezig ? "Claude maakt de notulen" : "Notulen staan in de wachtrij"),
      el("p", {}, "Samenvatting, besluiten en actiepunten verschijnen hier zo."),
      el("div", { class: "voortgang onbepaald" }, el("div")));
  }
  const n = d.samenvatting_data;
  if (!n) {
    const kinderen = [];
    if (d.fout_samenvatting) kinderen.push(waarschuwing(d.fout_samenvatting, true));
    if (!d.segmenten) {
      kinderen.push(el("div", { class: "kaart uitnodiging" }, el("h2", {}, "Ouder transcript"),
        el("p", {}, "Schrijf deze meeting opnieuw uit om notulen te kunnen maken en in het transcript te kunnen klikken."),
        el("button", { class: "knop primair", onclick: () => meetingActie("uitschrijven", "Komt in de wachtrij") }, "Opnieuw uitschrijven")));
    } else if (!s.samenvatten) {
      kinderen.push(el("div", { class: "kaart uitnodiging" },
        el("div", { class: "groot-icoon" }, icoon("ster")),
        el("h2", {}, "Notulen met actiepunten"),
        el("p", {}, "Laat Claude een samenvatting maken met besluiten, actiepunten en open vragen. Daarvoor gaat het transcript naar Anthropic; de opname zelf blijft op je Mac."),
        el("button", { class: "knop primair", onclick: () => openInstellingen("claude") }, "API-sleutel instellen")));
    } else {
      kinderen.push(el("div", { class: "kaart uitnodiging" },
        el("div", { class: "groot-icoon" }, icoon("ster")),
        el("h2", {}, "Nog geen notulen"),
        el("p", {}, "Claude maakt een samenvatting met besluiten, actiepunten en open vragen."),
        el("button", { class: "knop primair", onclick: maakNotulen }, d.fout_samenvatting ? "Opnieuw proberen" : "Maak notulen")));
    }
    return el("div", {}, kinderen);
  }

  const kaarten = [el("div", { class: "kaart" }, el("h3", {}, "Samenvatting"), el("p", { class: "samenvatting-tekst" }, n.samenvatting))];
  if (n.actiepunten && n.actiepunten.length) {
    const gedaan = new Set(d.gedaan || []);
    const lijst = el("ul", { class: "acties" });
    n.actiepunten.forEach((a, i) => {
      const aan = gedaan.has(i);
      const knop = el("button", { class: "vinkje" + (aan ? " aan" : ""), "aria-label": "Gedaan" }, aan ? icoon("vink") : "");
      const li = el("li", { class: aan ? "gedaan" : "" }, knop,
        el("span", { class: "actie-wat" }, a.wat),
        el("span", { class: "actie-extra" }, a.wie ? el("span", { class: "chip wie" }, a.wie) : null, a.wanneer ? el("span", { class: "chip" }, a.wanneer) : null));
      knop.onclick = () => wisselActie(i, li, knop);
      lijst.append(li);
    });
    kaarten.push(el("div", { class: "kaart" }, el("h3", {}, "Actiepunten"), lijst));
  }
  for (const [kop, veld] of [["Besluiten", "besluiten"], ["Belangrijkste punten", "punten"], ["Open vragen", "open_vragen"]]) {
    if (n[veld] && n[veld].length) kaarten.push(el("div", { class: "kaart" }, el("h3", {}, kop), el("ul", {}, n[veld].map((p) => el("li", {}, p)))));
  }
  kaarten.push(el("div", { class: "bron" }, "Gemaakt door Claude op basis van het transcript. Controleer namen en bedragen.",
    s.samenvatten ? el("button", { class: "link", onclick: maakNotulen }, "Opnieuw maken") : null));
  return el("div", {}, kaarten);
}

async function maakNotulen() {
  const r = await meetingActie("samenvatten");
  if (r) setTimeout(() => laadDetail(true), 300);
}

function tekenLive(o) {
  const ik = (staat.instellingen && staat.instellingen.instellingen.naam_ik) || "Ik";
  const anderen = (staat.instellingen && staat.instellingen.instellingen.naam_anderen) || "Anderen";
  const meters = el("div", { class: "meters" },
    el("span", { class: "meter-naam" }, ik), el("div", { class: "meter ik" }, el("div", { id: "meterIk" })),
    el("span", { class: "meter-naam" }, anderen), el("div", { class: "meter anderen" + (o.systeem ? "" : " uit"), id: "meterAnderenBak" }, el("div", { id: "meterAnderen" })));
  return el("div", {},
    o.waarschuwing ? waarschuwing(o.waarschuwing) : null,
    el("div", { class: "live" },
      el("div", { class: "opname-stip" }),
      el("div", { class: "klok", id: "liveKlok" }, klok(o.duur)),
      el("div", { class: "onder" }, o.automatisch
        ? "Stopt vanzelf zodra de meeting in " + o.app + " voorbij is."
        : "Handmatige opname. Stopt als je op Stop klikt."),
      meters,
      el("button", { class: "knop groot", onclick: stopOpname }, "Stop opname")));
}

function werkLiveBij() {
  const s = staat.status;
  const o = s && s.opname;
  const zijKlok = document.getElementById("zijKlok");
  if (o && zijKlok) zijKlok.textContent = klok(o.duur);
  const live = document.getElementById("liveKlok");
  if (staat.weergave === "meeting" && staat.detail) {
    const lopendHier = o && o.id === staat.gekozen;
    // Opname net begonnen of gestopt: pagina opnieuw opbouwen.
    if (!!live !== !!lopendHier) { tekenInhoud(); return; }
  }
  if (live && o) {
    live.textContent = klok(o.duur);
    const ik = document.getElementById("meterIk");
    const an = document.getElementById("meterAnderen");
    const schaal = (v) => Math.min(100, Math.round(Math.sqrt(Math.max(0, v || 0)) * 140)) + "%";
    if (ik) ik.style.width = schaal(o.niveaus.ik);
    if (an) an.style.width = schaal(o.niveaus.anderen);
  }
  const balk = document.getElementById("voortgangBalk");
  if (balk && s && s.voortgang && s.voortgang.id === staat.gekozen && s.voortgang.fractie !== null) {
    balk.style.width = Math.round(s.voortgang.fractie * 100) + "%";
  }
}

// ---------------------------------------------------------------- instellingen

async function openInstellingen(focus) {
  staat.weergave = "instellingen";
  staat.toestemmingen = null;
  tekenLijst();
  if (!staat.instellingen) await laadInstellingen();
  tekenInhoud();
  if (focus === "claude") {
    const v = document.getElementById("sleutelInvoer");
    if (v) { v.scrollIntoView({ block: "center" }); v.focus(); }
  }
}

async function laadInstellingen() {
  try { staat.instellingen = await api("/api/instellingen"); } catch (e) { /* later */ }
}

async function zet(sleutel, waarde) {
  const r = await probeer(() => api("/api/instellingen", { method: "PATCH", body: { [sleutel]: waarde } }), "Bewaard");
  if (r) { staat.instellingen.instellingen = r.instellingen; laadStatus(); }
}

function schakel(sleutel, titel, uitleg, uit) {
  const w = staat.instellingen.instellingen[sleutel];
  return el("div", { class: "rij" }, el("div", { class: "rij-tekst" }, el("strong", {}, titel), uitleg ? el("span", {}, uitleg) : null),
    el("label", { class: "schakelaar" }, el("input", { type: "checkbox", checked: w && !uit, disabled: uit, onchange: (e) => zet(sleutel, e.target.checked) }), el("span", { class: "baan" })));
}

function getal(sleutel, titel, uitleg, eenheid) {
  const w = staat.instellingen.instellingen[sleutel];
  return el("div", { class: "rij" }, el("div", { class: "rij-tekst" }, el("strong", {}, titel), uitleg ? el("span", {}, uitleg) : null),
    el("input", { class: "invoer getal", type: "number", min: "1", value: String(w), onchange: (e) => {
      const n = parseInt(e.target.value, 10);
      if (n > 0) zet(sleutel, n); else e.target.value = String(w);
    } }), el("span", { class: "rij-tekst", style: "flex:none;color:var(--zacht)" }, eenheid));
}

function tekstveld(sleutel, titel, uitleg) {
  const w = staat.instellingen.instellingen[sleutel];
  return el("div", { class: "rij" }, el("div", { class: "rij-tekst" }, el("strong", {}, titel), uitleg ? el("span", {}, uitleg) : null),
    el("input", { class: "invoer", type: "text", value: w, onchange: (e) => { if (e.target.value.trim()) zet(sleutel, e.target.value.trim()); } }));
}

function keuze(sleutel, titel, uitleg, opties) {
  const w = staat.instellingen.instellingen[sleutel];
  return el("div", { class: "rij" }, el("div", { class: "rij-tekst" }, el("strong", {}, titel), uitleg ? el("span", {}, uitleg) : null),
    el("select", { class: "keuze", onchange: (e) => zet(sleutel, e.target.value) },
      opties.map(([waarde, label]) => el("option", { value: waarde, selected: waarde === w ? true : null }, label))));
}

function tekenInstellingen() {
  const i = staat.instellingen;
  if (!i) return el("div", { class: "pagina" }, "Laden…");
  const s = staat.status || {};
  const modellen = i.modellen.map((m) => [m, {
    "large-v3-turbo": "Large v3 Turbo (aanbevolen)", "large-v3": "Large v3 (nauwkeurigst, traag)",
    medium: "Medium (sneller)", small: "Small (snel)", base: "Base (snelst, minst nauwkeurig)",
  }[m] || m]);
  const talen = Object.entries(i.talen);

  const sleutelInvoer = el("input", { class: "invoer breed", type: "password", id: "sleutelInvoer", placeholder: i.sleutel ? "••••••••••••••••" : "sk-ant-…", autocomplete: "off" });
  const sleutelRij = el("div", { class: "rij" },
    el("div", { class: "rij-tekst" }, el("strong", {}, "Anthropic API-sleutel"),
      el("span", {}, i.sleutel ? el("span", { class: "ok" }, icoon("vink"), "Ingesteld, staat in je sleutelhanger")
        : i.sleutel_omgeving ? "Gebruikt ANTHROPIC_API_KEY uit je omgeving." : "Maak er een op console.anthropic.com. Hij komt in de sleutelhanger van je Mac.")),
    el("div", { class: "sleutel-rij" }, sleutelInvoer,
      el("button", { class: "knop primair", onclick: async () => {
        const r = await probeer(() => api("/api/sleutel", { method: "POST", body: { sleutel: sleutelInvoer.value } }), "Sleutel bewaard");
        if (r) { await laadInstellingen(); laadStatus(); tekenInhoud(); }
      } }, "Bewaar"),
      i.sleutel ? el("button", { class: "knop gevaar", onclick: async () => {
        const r = await probeer(() => api("/api/sleutel", { method: "POST", body: {} }), "Sleutel verwijderd");
        if (r) { await laadInstellingen(); laadStatus(); tekenInhoud(); }
      } }, "Wis") : null));

  const hulpUitslag = staat.toestemmingen ? el("div", { class: "uitslag" }, staat.toestemmingen) : null;

  return el("div", { class: "pagina instellingen" },
    el("h1", {}, "Instellingen"),
    el("p", {}, "Wijzigingen worden meteen bewaard."),

    el("div", { class: "sectie" },
      el("div", { class: "sectie-kop" }, el("h2", {}, "Opnemen")),
      schakel("automatisch_opnemen", "Meetings vanzelf opnemen", s.herkent ? "Start zodra Zoom, Teams, Meet of een andere meeting-app je microfoon gebruikt." : "Werkt vanaf macOS 14 (Sonoma).", !s.herkent),
      schakel("browsers_meenemen", "Ook meetings in de browser", "Google Meet, Teams of Zoom in Chrome, Safari, Edge, Arc en andere browsers."),
      getal("start_na_seconden", "Starten na", "Zo lang moet een app je microfoon gebruiken voordat de opname start.", "sec"),
      getal("stop_na_seconden", "Stoppen na", "Zo lang nadat de meeting-app je microfoon loslaat.", "sec"),
      getal("stilte_stop_minuten", "Stoppen bij stilte", "Vangnet: is het zo lang helemaal stil, dan stopt de opname ook.", "min"),
      getal("maximale_duur_minuten", "Maximale duur", "Langer dan dit neemt Notulist nooit op.", "min")),

    el("div", { class: "sectie", id: "claude" },
      el("div", { class: "sectie-kop" }, el("h2", {}, "Notulen met Claude"),
        el("p", {}, "Samenvatting, besluiten en actiepunten. Hiervoor gaat het transcript naar Anthropic; je opnames blijven op je Mac.")),
      sleutelRij,
      schakel("samenvatten_automatisch", "Na elke meeting vanzelf notulen maken", "Anders maak je ze per meeting met één klik.")),

    el("div", { class: "sectie" },
      el("div", { class: "sectie-kop" }, el("h2", {}, "Uitschrijven"), el("p", {}, "Spraakherkenning met Whisper, helemaal op je eigen Mac.")),
      keuze("model", "Model", "Een ander model wordt bij de volgende meeting gedownload.", modellen),
      keuze("taal", "Taal van je meetings", null, talen),
      tekstveld("naam_ik", "Jouw naam in het transcript", "Wat via je microfoon binnenkomt."),
      tekstveld("naam_anderen", "Naam voor de anderen", "Wat via je speakers of koptelefoon binnenkomt."),
      schakel("audio_bewaren", "Opnames bewaren", "Uit: na het uitschrijven blijven alleen het transcript en de notulen over.")),

    el("div", { class: "sectie" },
      el("div", { class: "sectie-kop" }, el("h2", {}, "Opslag en hulp")),
      el("div", { class: "rij" }, el("div", { class: "rij-tekst" }, el("strong", {}, "Map met meetings"), el("span", { class: "pad" }, i.instellingen.map)),
        el("button", { class: "knop", onclick: () => api("/api/map", { method: "POST" }) }, icoon("map"), "Open")),
      el("div", { class: "rij" }, el("div", { class: "rij-tekst" }, el("strong", {}, "Wat Notulist nu ziet"),
        el("span", {}, s.herkent ? (s.gezien && s.gezien.length ? "Microfoon in gebruik door: " + s.gezien.join(", ") : "Geen app gebruikt nu je microfoon.") : "Herkennen werkt vanaf macOS 14.")),
        el("button", { class: "knop", onclick: async () => {
          staat.toestemmingen = "Bezig met controleren…"; tekenInhoud();
          const r = await probeer(() => api("/api/toestemmingen", { method: "POST" }));
          staat.toestemmingen = r ? r.tekst : null; tekenInhoud();
        } }, "Controleer toestemmingen"),
        el("button", { class: "knop", onclick: () => api("/api/logboek", { method: "POST" }) }, "Logboek")),
      hulpUitslag));
}

// ---------------------------------------------------------------- start

function start() {
  document.querySelector(".zoek-icoon").innerHTML = ICONEN.zoek;
  document.getElementById("knopInstellingen").innerHTML = ICONEN.tandwiel;
  document.getElementById("knopInstellingen").onclick = () => {
    if (staat.weergave === "instellingen") { staat.weergave = staat.gekozen ? "meeting" : "start"; tekenInhoud(); if (staat.gekozen) laadDetail(); }
    else openInstellingen();
  };
  let zoekTimer = null;
  const zoek = document.getElementById("zoek");
  zoek.addEventListener("input", () => {
    clearTimeout(zoekTimer);
    zoekTimer = setTimeout(async () => {
      staat.zoek = zoek.value;
      await laadMeetings();
      if (staat.weergave === "meeting" && staat.detail && document.getElementById("tabInhoud")) {
        if (staat.zoek.trim() && staat.tab === "notulen" && staat.detail.segmenten) staat.tab = "transcript";
        tekenInhoudBehoudSpeler();
      }
    }, 200);
  });
  document.addEventListener("click", () => document.querySelectorAll(".menu").forEach((m) => m.classList.add("verborgen")));
  document.addEventListener("keydown", (e) => {
    const inVeld = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName);
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "f") { e.preventDefault(); zoek.focus(); zoek.select(); }
    else if (e.key === "Escape" && document.activeElement === zoek) { zoek.value = ""; zoek.dispatchEvent(new Event("input")); zoek.blur(); }
    else if (e.key === " " && !inVeld && speler) { e.preventDefault(); if (speler.paused) speler.play(); else speler.pause(); }
    else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !inVeld && staat.meetings.length) {
      e.preventDefault();
      const i = staat.meetings.findIndex((m) => m.id === staat.gekozen);
      const j = Math.max(0, Math.min(staat.meetings.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)));
      kies(staat.meetings[j].id);
    }
  });
  laadInstellingen();
  laadStatus().then(tekenInhoud);
  setInterval(laadStatus, 1000);
}

start();
