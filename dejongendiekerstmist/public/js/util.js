// Kleine hulpjes die overal gebruikt worden.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Maak een element: h('div', { class: 'x', onclick: fn }, 'tekst', kind) */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const wait = (ms) => new Promise((r) => setTimeout(r, ms));
export const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Wacht tot een animatie of transitie klaar is (met een vangnet). */
export function settled(el, fallback = 1200) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    el.addEventListener('animationend', finish, { once: true });
    el.addEventListener('transitionend', finish, { once: true });
    setTimeout(finish, fallback);
  });
}

export function roman(n) {
  const map = [[10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']];
  let out = '';
  for (const [v, s] of map) while (n >= v) { out += s; n -= v; }
  return out;
}

const MAANDEN = ['januari', 'februari', 'maart', 'april', 'mei', 'juni', 'juli', 'augustus', 'september', 'oktober', 'november', 'december'];
export function datumTekst(iso) {
  const [, m, d] = iso.split('-').map(Number);
  return `${d} ${MAANDEN[m - 1]}`;
}

export function nachtenTot(vandaag, datum) {
  return Math.round((Date.parse(datum + 'T00:00:00Z') - Date.parse(vandaag + 'T00:00:00Z')) / 86400000);
}

export function nachtenWoord(n) {
  return n === 1 ? 'nog één nacht' : `nog ${n} nachten`;
}

export function begroeting(date = new Date()) {
  const u = date.getHours();
  if (u < 6) return 'Goedenacht';
  if (u < 12) return 'Goedemorgen';
  if (u < 18) return 'Goedemiddag';
  return 'Goedenavond';
}

// localStorage kan weigeren (privévenster); dan werkt alles gewoon zonder geheugen.
export const geheugen = {
  get(k, fallback = null) {
    try { const v = localStorage.getItem('jdkm:' + k); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(k, v) { try { localStorage.setItem('jdkm:' + k, JSON.stringify(v)); } catch { /* geen geheugen */ } },
  del(k) { try { localStorage.removeItem('jdkm:' + k); } catch { /* geen geheugen */ } },
};

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.fout || 'Fout'), { status: res.status, data });
  return data;
}

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** Seeded random, zodat de stad er elke keer hetzelfde uitziet. */
export function rng(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
