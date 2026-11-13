'use strict';
/* Schrijfblad: de editor in de browser. Praat met de lokale server via /api/.

   De pagina is een gewoon bewerkbaar HTML-blok (contenteditable). Elke alinea en tabel heeft een
   data-id die bij de server bekend is. Een MutationObserver houdt bij welke alinea's veranderd zijn;
   kort na het typen gaan alleen die naar de server (sync), die ze terugschrijft in het Word-bestand. */

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform);
const SYNC_DELAY = 350;

const COLORS = ['000000', '595959', 'C00000', 'FF0000', 'ED7D31', 'BF8F00',
  '00B050', '548235', '0070C0', '1F4E79', '7030A0', 'FFFFFF'];
const MARKS = ['FFFF00', '00FF00', '00FFFF', 'FF00FF', '0000FF', 'FF0000',
  '000080', '008080', '008000', '800080', 'C0C0C0', '808080'];

const S = {
  st: null,
  r: null,            // laatste weergave van de server (stijlen, nummering, pagina)
  gen: 0,
  dirty: new Set(),   // gewijzigde alinea's en tabellen
  touched: new Set(), // delen (body/hdr/ftr) met wijzigingen
  tmp: 0,
  timer: 0,
  chain: Promise.resolve(),
  localDirty: false,
  search: { matches: [], idx: -1 },
  styleById: {},
};

const DOC = (() => {
  const url = new URL(location.href);
  let id = url.searchParams.get('doc');
  if (!id || !/^[A-Za-z0-9_-]{4,40}$/.test(id)) {
    id = Array.from(crypto.getRandomValues(new Uint8Array(9)), (b) => 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'[b % 64]).join('');
    url.searchParams.set('doc', id);
    history.replaceState(null, '', url);
  }
  return id;
})();

const docEl = $('#doc');
const scroller = $('#scroller');

/* ---------------------------------------------------------------- server */

async function api(path, body, raw) {
  const opts = { method: body === undefined && !raw ? 'GET' : 'POST', headers: { 'X-Schrijfblad': '1', 'X-Doc': DOC } };
  if (raw) {
    opts.body = raw.body;
    Object.assign(opts.headers, raw.headers || {});
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch('/api/' + path, opts);
  } catch (e) {
    throw new Error('Geen verbinding met Schrijfblad. Draait het programma nog?');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || 'Er ging iets mis.');
    err.resync = !!data.resync;
    throw err;
  }
  if (data.state) applyState(data.state);
  return data;
}

/* Alles wat het document verandert gaat één voor één, zodat de server altijd gelijk loopt. */
function queue(fn) {
  const p = S.chain.then(fn, fn);
  S.chain = p.catch(() => {});
  return p;
}

async function run(fn) {
  try { return await fn(); } catch (e) {
    if (e.resync) { toast('Het document is opnieuw geladen.', true); await reload(true); return; }
    toast(e.message, true);
  }
}

function toast(msg, isErr) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (isErr ? ' err' : '');
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, isErr ? 6000 : 3000);
}

/* ---------------------------------------------------------------- status */

function applyState(st) {
  S.st = st;
  $('#welcome').hidden = st.loaded;
  for (const id of ['#toolbar', '#scroller', '#bottombar', '#fileBox', '#btnSave', '#btnExport']) $(id).hidden = !st.loaded;
  $('#btnSaveAs').hidden = !(st.loaded && st.can_native);
  if (!st.loaded) {
    renderRecent(st.recent || []);
    document.title = 'Schrijfblad';
    $('#trackedBar').hidden = true;
    nativeTitle();
    return;
  }
  $('#fileName').textContent = st.filename;
  $('#fileName').title = st.path || 'Nog niet opgeslagen op deze Mac';
  updateDirty();
  $('#tUndo').disabled = !st.undo && !S.localDirty;
  $('#tRedo').disabled = !st.redo;
}

function isDirty() { return !!(S.st && S.st.loaded && (S.st.dirty || S.localDirty)); }

function updateDirty() {
  if (!S.st || !S.st.loaded) return;
  const d = isDirty();
  $('#dirty').hidden = !d;
  document.title = (d ? '• ' : '') + S.st.filename + ' – Schrijfblad';
  nativeTitle();
}

function showWarnings(list) {
  if (!list || !list.length) { $('#banner').hidden = true; return; }
  $('#bannerText').textContent = list.join(' ');
  $('#banner').hidden = false;
}

function renderRecent(list) {
  $('#recentBox').hidden = !list.length;
  $('#recentList').innerHTML = list.map((p, i) => {
    const name = p.split('/').pop();
    return `<li><button data-i="${i}">${esc(name)}<span class="p">${esc(p)}</span></button></li>`;
  }).join('');
  $('#recentList').querySelectorAll('button').forEach((b) => {
    b.onclick = () => run(async () => {
      const d = await api('open_recent', { path: list[+b.dataset.i], elsewhere: elsewhere() });
      if (!d.elsewhere) await afterOpen();
    });
  });
}

function nativeApi() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}
function nativeTitle() {
  const a = nativeApi();
  if (!a || !S.st) return;
  try { a.set_title(S.st.loaded ? S.st.filename : 'Schrijfblad', isDirty()); } catch (e) { /* venster nog niet klaar */ }
}
window.addEventListener('pywebviewready', nativeTitle);

/* ---------------------------------------------------------------- weergave */

const px = (twips) => Math.round(twips / 15);

function containers() { return Array.from(docEl.querySelectorAll('.ce')); }
function ceOf(key) { return docEl.querySelector(`.ce[data-c="${key}"]`); }

function renderDoc(r, caret) {
  S.r = r;
  S.gen = r.gen;
  S.styleById = {};
  for (const s of r.styles) S.styleById[s.id] = s;
  $('#docCss').textContent = r.css;
  buildNumCss();
  const pg = r.page;
  const part = (key, cls, label) => {
    const c = r.containers.find((x) => x.key === key);
    if (c) return `<span class="tag">${label}</span><div class="ce ${cls}" data-c="${key}" contenteditable="true" spellcheck="true">${c.html}</div>`;
    return `<button class="addpart" data-kind="${key}">+ ${label} toevoegen</button>`;
  };
  docEl.innerHTML = `
    <div class="page" style="width:${px(pg.w)}px;padding:0 ${px(pg.right)}px 0 ${px(pg.left)}px;min-height:${px(pg.h)}px">
      <div class="zone hdrzone" style="min-height:${px(pg.top)}px;padding-top:${px(pg.header)}px;padding-bottom:12px">${part('hdr', 'hdr', 'Koptekst')}</div>
      ${part('body', 'body-ce', 'Hoofdtekst').replace('<span class="tag">Hoofdtekst</span>', '')}
      <div class="zone ftrzone" style="min-height:${px(pg.bottom)}px;padding-bottom:${px(pg.footer)}px;padding-top:12px;display:flex;flex-direction:column;justify-content:flex-end">${part('ftr', 'ftr', 'Voettekst')}</div>
    </div>`;
  docEl.querySelectorAll('.addpart').forEach((b) => { b.onclick = () => addPart(b.dataset.kind); });
  for (const ce of containers()) observer.observe(ce, OBS);
  observer.takeRecords();
  S.dirty.clear();
  S.touched.clear();
  S.localDirty = false;
  fillStyleSelect();
  renumber();
  updateStatus();
  updateDirty();
  $('#trackedBar').hidden = !r.tracked;
  if (caret) restoreCaret(caret);
  if (!$('#searchBar').hidden) doSearch(true);
}

function fillStyleSelect() {
  const sel = $('#tStyle');
  sel.innerHTML = S.r.styles.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
}

async function reload(keepCaret) {
  const caret = keepCaret ? saveCaret() : null;
  const d = await api('render');
  renderDoc(d.render, caret);
}

async function afterOpen() {
  const d = await api('render');
  renderDoc(d.render);
  showWarnings(S.st.warnings);
  scroller.scrollTop = 0;
  const body = ceOf('body');
  if (body) {
    body.focus({ preventScroll: true });
    const p = body.querySelector('p');
    if (p) placeCaret(p, 0);
  }
}

/* ---------------------------------------------------------------- nummering */

function roman(n) {
  const t = [[1000, 'm'], [900, 'cm'], [500, 'd'], [400, 'cd'], [100, 'c'], [90, 'xc'], [50, 'l'], [40, 'xl'], [10, 'x'], [9, 'ix'], [5, 'v'], [4, 'iv'], [1, 'i']];
  let out = '';
  for (const [v, s] of t) while (n >= v) { out += s; n -= v; }
  return out;
}
function letters(n) {
  let s = '';
  while (n > 0) { n--; s = String.fromCharCode(97 + (n % 26)) + s; n = Math.floor(n / 26); }
  return s || 'a';
}
function fmtNum(n, fmt) {
  switch (fmt) {
    case 'lowerLetter': return letters(n);
    case 'upperLetter': return letters(n).toUpperCase();
    case 'lowerRoman': return roman(n);
    case 'upperRoman': return roman(n).toUpperCase();
    case 'decimalZero': return (n < 10 ? '0' : '') + n;
    case 'none': return '';
    default: return String(n);
  }
}
function bulletChar(lv, lvl) {
  const t = lv.text || '';
  const code = t.charCodeAt(0);
  if (!t) return '•';
  if (code >= 0xF000) {
    return { 0xF0B7: '•', 0xF0A7: '▪', 0xF0D8: '➢', 0xF0FC: '✓', 0xF076: '❖', 0xF0A8: '◆', 0xF06E: '■', 0xF071: '❑' }[code] || ['•', '◦', '▪'][lvl % 3];
  }
  if (t === 'o' && /courier/i.test(lv.font || '')) return '◦';
  if (/wingdings/i.test(lv.font || '')) return ['▪', '◆', '✓'][lvl % 3];
  return t;
}

function effNum(p) {
  if (p.dataset.num !== undefined) {
    if (p.dataset.num === '0') return null;
    return [p.dataset.num, +(p.dataset.lvl || 0)];
  }
  if (p.dataset.snum) return [p.dataset.snum, +(p.dataset.slvl || 0)];
  return null;
}

function listKind(p) {
  const n = effNum(p);
  if (!n) return null;
  const def = S.r.numbering[n[0]];
  const lv = def && def.levels[String(n[1])];
  if (!lv) return null;
  return lv.fmt === 'bullet' ? 'bullet' : 'number';
}

function renumber() {
  if (!S.r) return;
  const nums = S.r.numbering || {};
  for (const ce of containers()) {
    const counters = {};
    const lastNum = {};
    for (const p of ce.querySelectorAll('p')) {
      const n = effNum(p);
      const def = n && nums[n[0]];
      const lv = def && def.levels[String(n[1])];
      if (!lv) {
        if (p.dataset.marker !== undefined) { delete p.dataset.marker; delete p.dataset.mk; }
        continue;
      }
      const key = def.abs;
      const c = counters[key] || (counters[key] = []);
      if (lastNum[key] !== n[0]) {
        for (const il of def.restart || []) c[+il] = undefined;
        lastNum[key] = n[0];
      }
      const lvl = n[1];
      c[lvl] = (c[lvl] === undefined ? (lv.start || 1) - 1 : c[lvl]) + 1;
      for (let i = lvl + 1; i < 9; i++) c[i] = undefined;
      let marker;
      if (lv.fmt === 'bullet') marker = bulletChar(lv, lvl);
      else {
        marker = (lv.text || '').replace(/%(\d)/g, (m, d) => {
          const il = +d - 1;
          const l2 = def.levels[String(il)] || lv;
          const v = c[il] === undefined ? (l2.start || 1) : c[il];
          return fmtNum(v, l2.fmt);
        });
      }
      const mk = `${n[0]}-${lvl}`;
      if (p.dataset.marker !== marker + ' ') p.dataset.marker = marker + ' ';
      if (p.dataset.mk !== mk) p.dataset.mk = mk;
    }
  }
}

function buildNumCss() {
  const out = [];
  for (const [nid, def] of Object.entries(S.r.numbering || {})) {
    for (const [il, lv] of Object.entries(def.levels)) {
      const left = lv.left != null ? lv.left : 36 * (+il + 1);
      const hang = lv.hang != null ? lv.hang : 18;
      out.push(`.ce p[data-mk="${nid}-${il}"] { margin-left: ${left}pt; text-indent: -${hang}pt; }`);
      out.push(`.ce p[data-mk="${nid}-${il}"]::before { min-width: ${hang}pt; }`);
    }
  }
  $('#numCss').textContent = out.join('\n');
}

/* ---------------------------------------------------------------- wijzigingen bijhouden */

const OBS = { subtree: true, childList: true, characterData: true, attributes: true,
  attributeFilter: ['data-style', 'data-align', 'data-num', 'data-lvl', 'style', 'href', 'color', 'class'] };
const observer = new MutationObserver(onMutations);

function onMutations(records) {
  let any = false;
  for (const m of records) {
    if (m.type === 'attributes' && m.attributeName === 'class' && m.target.tagName === 'P') continue;
    let n = m.target;
    if (n.nodeType !== 1) n = n.parentNode;
    if (!n || !n.closest) continue;
    const ce = n.closest('.ce');
    if (!ce) continue;
    markFrom(n, ce);
    if (m.type === 'childList') {
      for (const a of m.addedNodes) {
        if (a.nodeType === 1 && (a.tagName === 'P' || a.tagName === 'TABLE')) S.dirty.add(a);
      }
    }
    S.touched.add(ce.dataset.c);
    any = true;
  }
  if (any) {
    if (!S.localDirty) { S.localDirty = true; updateDirty(); $('#tUndo').disabled = false; }
    scheduleSync();
  }
}

function markFrom(n, ce) {
  const p = n.closest('p');
  if (p && ce.contains(p)) { S.dirty.add(p); n = p.parentNode; }
  let t = n && n.closest ? n.closest('table') : null;
  while (t && ce.contains(t)) {
    S.dirty.add(t);
    t = t.parentNode && t.parentNode.closest ? t.parentNode.closest('table') : null;
  }
}

function scheduleSync() {
  clearTimeout(S.timer);
  S.timer = setTimeout(() => run(flush), SYNC_DELAY);
}

function flush() {
  clearTimeout(S.timer);
  return queue(doSync);
}

async function doSync() {
  onMutations(observer.takeRecords());
  if (!S.touched.size || !S.st || !S.st.loaded) return;
  const payload = {};
  for (const key of S.touched) {
    const ce = ceOf(key);
    if (!ce) continue;
    normalize(ce);
    onMutations(observer.takeRecords());
    dedupe(ce);
    payload[key] = blocksOf(ce);
  }
  clearTimeout(S.timer);
  S.dirty.clear();
  S.touched.clear();
  $('#saving').textContent = 'Bezig…';
  try {
    const d = await api('sync', { gen: S.gen, containers: payload });
    const ids = d.ids || {};
    if (Object.keys(ids).length) {
      for (const el of docEl.querySelectorAll('[data-id^="n"], [data-from^="n"]')) {
        if (ids[el.dataset.id]) el.dataset.id = ids[el.dataset.id];
        if (el.dataset.from && ids[el.dataset.from]) el.dataset.from = ids[el.dataset.from];
      }
    }
    if (!S.touched.size) S.localDirty = false;
    updateDirty();
  } finally {
    $('#saving').textContent = '';
  }
}

/* De browser maakt soms losse tekst of <div>'s; die worden alinea's. */
function normalize(ce) {
  const holders = [ce, ...ce.querySelectorAll('td')];
  for (const h of holders) {
    let run = null;
    for (const node of Array.from(h.childNodes)) {
      const isBlock = node.nodeType === 1 && /^(P|TABLE|DIV|H[1-6]|UL|OL|LI|BLOCKQUOTE|PRE|TBODY|TR|COLGROUP)$/.test(node.tagName);
      if (isBlock) {
        run = null;
        if (node.tagName !== 'P' && node.tagName !== 'TABLE' && !(node.classList && node.classList.contains('xblock'))
            && h.tagName !== 'TABLE') {
          const p = document.createElement('p');
          p.className = defaultClass();
          while (node.firstChild) p.appendChild(node.firstChild);
          node.replaceWith(p);
        }
        continue;
      }
      if (node.nodeType === 3 && !node.data.trim() && !run) { if (h === ce || h.tagName === 'TD') node.remove(); continue; }
      if (!run) {
        run = document.createElement('p');
        run.className = defaultClass();
        h.insertBefore(run, node);
      }
      run.appendChild(node);
    }
    if (h.tagName === 'TD' && !h.querySelector(':scope > p, :scope > table')) {
      const p = document.createElement('p');
      p.className = defaultClass();
      p.innerHTML = '<br>';
      h.appendChild(p);
    }
  }
  if (!ce.querySelector(':scope > p, :scope > table, :scope > .xblock')) {
    const p = document.createElement('p');
    p.className = defaultClass();
    p.innerHTML = '<br>';
    ce.appendChild(p);
  }
  const last = ce.lastElementChild;
  if (last && last.tagName === 'TABLE') {
    const p = document.createElement('p');
    p.className = defaultClass();
    p.innerHTML = '<br>';
    ce.appendChild(p);
  }
  for (const p of ce.querySelectorAll('p')) {
    if (!p.firstChild) p.innerHTML = '<br>';
  }
}

function defaultClass() {
  return S.r && S.r.default_style ? 'ps-' + S.r.default_style.replace(/[^A-Za-z0-9_-]/g, '_') : '';
}

/* Dubbele id's (na Enter kopieert de browser de alinea) en nieuwe blokken krijgen een tijdelijk id. */
function dedupe(ce) {
  const seen = new Set();
  for (const el of ce.querySelectorAll('p, table, tr, td')) {
    const id = el.dataset.id;
    if (id && !seen.has(id)) { seen.add(id); continue; }
    if (id) el.dataset.from = id;
    el.dataset.id = 'n' + (++S.tmp);
    if (el.tagName === 'P' || el.tagName === 'TABLE') S.dirty.add(el);
    if (el.tagName === 'TR' || el.tagName === 'TD') markFrom(el, ce);
  }
}

function blocksOf(holder) {
  const out = [];
  for (const el of holder.children) {
    if (el.tagName === 'P') {
      out.push(S.dirty.has(el) && el.contentEditable !== 'false' ? parModel(el) : { id: el.dataset.id });
    } else if (el.tagName === 'TABLE') {
      out.push(S.dirty.has(el) ? tableModel(el) : { id: el.dataset.id });
    } else if (el.dataset && el.dataset.id) {
      out.push({ id: el.dataset.id });
    }
  }
  return out;
}

function tableModel(t) {
  const rows = [];
  for (const tr of t.rows) {
    rows.push({
      id: tr.dataset.id, from: tr.dataset.from,
      cells: Array.from(tr.cells).map((td) => ({ id: td.dataset.id, from: td.dataset.from, blocks: blocksOf(td) })),
    });
  }
  return { t: 'tbl', id: t.dataset.id, from: t.dataset.from, rows };
}

function parModel(p) {
  return {
    t: 'p', id: p.dataset.id, from: p.dataset.from,
    style: p.dataset.style || null,
    align: p.dataset.align || null,
    num: p.dataset.num !== undefined ? [p.dataset.num, +(p.dataset.lvl || 0)] : null,
    items: parItems(p),
  };
}

function hexColor(v) {
  if (!v) return null;
  v = v.trim();
  if (v === 'transparent' || v === 'inherit' || v === 'initial') return null;
  let m = v.match(/^#([0-9a-f]{6})$/i);
  if (m) return m[1].toUpperCase();
  m = v.match(/^#([0-9a-f]{3})$/i);
  if (m) return m[1].split('').map((c) => c + c).join('').toUpperCase();
  m = v.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)$/);
  if (m) {
    if (m[4] !== undefined && +m[4] === 0) return null;
    return [m[1], m[2], m[3]].map((x) => (+x).toString(16).padStart(2, '0')).join('').toUpperCase();
  }
  const named = { black: '000000', white: 'FFFFFF', red: 'FF0000', yellow: 'FFFF00', blue: '0000FF', green: '008000' };
  return named[v.toLowerCase()] || null;
}

function toPt(v) {
  const m = String(v).match(/^([\d.]+)(pt|px)$/);
  if (!m) return null;
  const n = parseFloat(m[1]);
  return Math.round((m[2] === 'px' ? n * 0.75 : n) * 2) / 2;
}

/* Opmaak van een stukje tekst, zoals de browser hem toont (moet passen bij props_css in styles.py). */
function derive(ctx, el) {
  const c = { r: ctx.r, h: ctx.h, href: ctx.href, p: Object.assign({}, ctx.p) };
  const t = el.tagName;
  if (el.dataset && el.dataset.r) c.r = el.dataset.r;
  if (t === 'A') { c.h = el.dataset.h || null; c.href = el.getAttribute('href'); }
  if (t === 'B' || t === 'STRONG') c.p.b = true;
  if (t === 'I' || t === 'EM') c.p.i = true;
  if (t === 'U') c.p.u = true;
  if (t === 'S' || t === 'STRIKE') c.p.s = true;
  if (t === 'SUP') c.p.va = 'sup';
  if (t === 'SUB') c.p.va = 'sub';
  if (t === 'FONT' && el.getAttribute('color')) c.p.color = hexColor(el.getAttribute('color'));
  if (t === 'MARK') c.p.bg = 'FFFF00';
  const s = el.style;
  if (s && s.length) {
    const fw = s.fontWeight;
    if (fw) c.p.b = fw === 'bold' || fw === 'bolder' || +fw >= 600;
    if (s.fontStyle) c.p.i = s.fontStyle === 'italic' || s.fontStyle === 'oblique';
    const d = s.textDecorationLine || s.textDecoration;
    if (d) {
      if (/none/.test(d)) { c.p.u = false; c.p.s = false; } else {
        if (/underline/.test(d)) c.p.u = true;
        if (/line-through/.test(d)) c.p.s = true;
      }
    }
    if (s.verticalAlign) {
      const va = { super: 'sup', sub: 'sub', baseline: 'base' }[s.verticalAlign];
      if (va) c.p.va = va;
    }
    if (s.color) c.p.color = hexColor(s.color);
    if (s.backgroundColor) c.p.bg = hexColor(s.backgroundColor);
    if (s.fontSize) { const pt = toPt(s.fontSize); if (pt) c.p.sz = pt; }
  }
  return c;
}

function parItems(p) {
  const items = [];
  const nodes = [];
  (function collect(node) {
    for (const ch of node.childNodes) {
      nodes.push(ch);
      if (ch.nodeType === 1 && !(ch.dataset && (ch.dataset.a || ch.dataset.n))) collect(ch);
    }
  })(p);
  const lastBr = (() => {
    // een <br> aan het eind van een alinea is alleen een plaatshouder van de browser
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (n.nodeType === 3 && n.data.replace(/[​﻿]/g, '') !== '') return null;
      if (n.nodeType === 1 && n.tagName === 'BR') return n;
      if (n.nodeType === 1 && n.dataset && (n.dataset.a || n.dataset.n)) return null;
    }
    return null;
  })();
  const push = (it) => {
    const last = items[items.length - 1];
    if (it.x !== undefined && last && last.x !== undefined && last.r === it.r && last.h === it.h
        && last.href === it.href && JSON.stringify(last.p) === JSON.stringify(it.p)) {
      last.x += it.x;
    } else items.push(it);
  };
  (function walk(node, ctx) {
    for (const ch of node.childNodes) {
      if (ch.nodeType === 3) {
        const x = ch.data.replace(/[​﻿]/g, '').replace(/\r/g, '');
        if (x) push({ x, r: ctx.r || null, h: ctx.h || null, href: ctx.href || null, p: ctx.p });
      } else if (ch.nodeType === 1) {
        if (ch.dataset.a) { items.push({ a: ch.dataset.a, h: ctx.h || null, href: ctx.href || null }); continue; }
        if (ch.dataset.n) { items.push({ n: ch.dataset.n }); continue; }
        if (ch.tagName === 'BR') {
          if (ch !== lastBr) push({ x: '\n', r: ctx.r || null, h: ctx.h || null, href: ctx.href || null, p: ctx.p });
          continue;
        }
        if (ch.tagName === 'IMG' || ch.tagName === 'STYLE' || ch.tagName === 'SCRIPT') continue;
        walk(ch, derive(ctx, ch));
      }
    }
  })(p, { r: null, h: null, href: null, p: {} });
  return items;
}

/* ---------------------------------------------------------------- selectie */

function currentCe() {
  const sel = getSelection();
  if (!sel.rangeCount) return null;
  let n = sel.anchorNode;
  if (n && n.nodeType !== 1) n = n.parentNode;
  return n && n.closest ? n.closest('.ce') : null;
}

function currentPar() {
  const sel = getSelection();
  if (!sel.rangeCount) return null;
  let n = sel.anchorNode;
  if (n && n.nodeType !== 1) n = n.parentNode;
  const p = n && n.closest ? n.closest('p') : null;
  return p && p.closest('.ce') ? p : null;
}

function selectedPars() {
  const sel = getSelection();
  if (!sel.rangeCount) return [];
  const range = sel.getRangeAt(0);
  const ce = currentCe();
  if (!ce) return [];
  const out = Array.from(ce.querySelectorAll('p')).filter((p) => range.intersectsNode(p) && p.contentEditable !== 'false');
  if (!out.length) { const p = currentPar(); if (p) out.push(p); }
  return out;
}

function placeCaret(node, offset) {
  const sel = getSelection();
  const r = document.createRange();
  try { r.setStart(node, offset); } catch (e) { r.selectNodeContents(node); r.collapse(true); }
  r.collapse(true);
  sel.removeAllRanges();
  sel.addRange(r);
}

function saveCaret() {
  const sel = getSelection();
  const ce = currentCe();
  if (!ce || !sel.rangeCount) return { key: 'body', off: 0, top: scroller.scrollTop };
  const r = document.createRange();
  r.selectNodeContents(ce);
  r.setEnd(sel.anchorNode, sel.anchorOffset);
  return { key: ce.dataset.c, off: r.toString().length, top: scroller.scrollTop };
}

function restoreCaret(c) {
  const ce = ceOf(c.key) || ceOf('body');
  if (!ce) return;
  ce.focus({ preventScroll: true });
  const walker = document.createTreeWalker(ce, NodeFilter.SHOW_TEXT);
  let left = c.off, node, last = null;
  while ((node = walker.nextNode())) {
    last = node;
    if (left <= node.data.length) { placeCaret(node, left); scroller.scrollTop = c.top; return; }
    left -= node.data.length;
  }
  if (last) placeCaret(last, last.data.length);
  scroller.scrollTop = c.top;
}

/* ---------------------------------------------------------------- opmaak */

function cmd(name, value) {
  const ce = currentCe();
  if (!ce) return;
  document.execCommand('styleWithCSS', false, true);
  document.execCommand(name, false, value === undefined ? null : value);
  updateToolbar();
}

function setStyle(p, sid) {
  const def = S.r.default_style;
  if (!sid || sid === def) delete p.dataset.style; else p.dataset.style = sid;
  const eff = sid || def;
  p.className = p.className.split(/\s+/).filter((c) => c && !c.startsWith('ps-')).concat(eff ? ['ps-' + eff.replace(/[^A-Za-z0-9_-]/g, '_')] : []).join(' ');
}

function applyStyle(sid) {
  const ps = selectedPars();
  for (const p of ps) {
    setStyle(p, sid);
    if (p.dataset.snum) { delete p.dataset.snum; delete p.dataset.slvl; }
  }
  renumber();
  updateToolbar();
}

function setAlign(al) {
  const ps = selectedPars();
  const allOn = ps.length && ps.every((p) => (p.dataset.align || '') === al);
  for (const p of ps) {
    if (allOn) { delete p.dataset.align; p.style.textAlign = ''; } else {
      p.dataset.align = al;
      p.style.textAlign = { left: 'left', center: 'center', right: 'right', both: 'justify' }[al];
    }
  }
  updateToolbar();
}

function setSize(pt) {
  if (!pt) return;
  cmd('fontSize', 7);
  const ce = currentCe();
  if (!ce) return;
  for (const el of ce.querySelectorAll('span[style*="xxx-large"], font[size="7"]')) {
    if (el.tagName === 'FONT') {
      const s = document.createElement('span');
      s.style.fontSize = pt + 'pt';
      while (el.firstChild) s.appendChild(el.firstChild);
      el.replaceWith(s);
    } else el.style.fontSize = pt + 'pt';
  }
}

async function toggleList(kind) {
  const ps = selectedPars();
  if (!ps.length) return;
  const on = ps.every((p) => listKind(p) === kind);
  if (on) {
    for (const p of ps) {
      if (p.dataset.snum) p.dataset.num = '0'; else { delete p.dataset.num; delete p.dataset.lvl; }
      if (p.dataset.style && p.dataset.style === S.r.list_style) setStyle(p, null);
    }
    renumber();
    return;
  }
  const prev = ps[0].previousElementSibling;
  let nid = null;
  if (prev && prev.tagName === 'P' && listKind(prev) === kind) nid = effNum(prev)[0];
  if (!nid && kind === 'bullet') {
    // een bestaande opsomming hergebruiken: dan hoeft er niet op de server gewacht te worden
    for (const [id, def] of Object.entries(S.r.numbering || {})) {
      const lv = def.levels['0'];
      if (lv && lv.fmt === 'bullet' && def.levels['1']) { nid = id; break; }
    }
  }
  if (!nid) {
    const d = await queue(() => api('list', { kind, fresh: kind === 'number' }));
    nid = d.num;
    S.r.numbering = d.numbering;
    buildNumCss();
  }
  for (const p of ps) {
    p.dataset.num = nid;
    p.dataset.lvl = p.dataset.lvl || (p.dataset.slvl || '0');
    if (!p.dataset.style && S.r.list_style) setStyle(p, S.r.list_style);
  }
  renumber();
  updateToolbar();
}

function indent(delta) {
  const ps = selectedPars();
  for (const p of ps) {
    const n = effNum(p);
    if (!n) continue;
    p.dataset.num = n[0];
    p.dataset.lvl = String(Math.max(0, Math.min(8, n[1] + delta)));
  }
  renumber();
}

function updateToolbar() {
  if (!S.r) return;
  const p = currentPar();
  const sel = $('#tStyle');
  if (p) {
    const sid = p.dataset.style || S.r.default_style;
    if (!S.styleById[sid] && sid) {
      sel.insertAdjacentHTML('beforeend', `<option value="${esc(sid)}">${esc(sid)}</option>`);
      S.styleById[sid] = { id: sid, name: sid };
    }
    sel.value = sid || '';
  }
  for (const b of document.querySelectorAll('[data-cmd]')) {
    let on = false;
    try { on = document.queryCommandState(b.dataset.cmd); } catch (e) { on = false; }
    b.classList.toggle('on', on);
  }
  for (const b of document.querySelectorAll('[data-align]')) {
    b.classList.toggle('on', !!p && (p.dataset.align || '') === b.dataset.align);
  }
  $('#tBullet').classList.toggle('on', !!p && listKind(p) === 'bullet');
  $('#tNumber').classList.toggle('on', !!p && listKind(p) === 'number');
  const inTable = !!(p && p.closest('td'));
  document.querySelectorAll('[data-top]').forEach((b) => { b.disabled = !inTable; });
}

document.addEventListener('selectionchange', () => {
  clearTimeout(updateToolbar.t);
  updateToolbar.t = setTimeout(updateToolbar, 60);
});

/* ---------------------------------------------------------------- invoegen */

function insertHtmlAtCaret(html) {
  document.execCommand('insertHTML', false, html);
}

function pageBreak() {
  const ce = currentCe();
  if (!ce || ce.dataset.c !== 'body') { toast('Zet de cursor eerst in de tekst.'); return; }
  insertHtmlAtCaret('<span class="atom pb" contenteditable="false" data-n="pagebreak">Pagina-einde</span>');
}

function pickImage() {
  if (!currentCe()) { toast('Zet de cursor eerst op de plek voor de afbeelding.'); return; }
  S.imgRange = getSelection().getRangeAt(0).cloneRange();
  $('#imageInput').click();
}

async function insertImage(file, range) {
  const ce = range ? (range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentNode).closest('.ce') : currentCe();
  if (!ce) { toast('Zet de cursor eerst op de plek voor de afbeelding.'); return; }
  await run(async () => {
    const d = await queue(() => api('image?container=' + ce.dataset.c, undefined, { body: file, headers: { 'Content-Type': 'application/octet-stream' } }));
    ce.focus({ preventScroll: true });
    if (range) { const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range); }
    insertHtmlAtCaret(d.html);
  });
}

async function editLink() {
  const ce = currentCe();
  if (!ce) return;
  const sel = getSelection();
  const range = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  let a = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentNode).closest('a');
  if (a && !ce.contains(a)) a = null;
  const cur = a ? a.getAttribute('href') : '';
  const res = await ask('Link', [{ name: 'url', label: 'Webadres (of #bladwijzer)', value: cur && cur !== '#' ? cur : 'https://', placeholder: 'https://' }],
    a ? 'Link verwijderen' : null);
  ce.focus({ preventScroll: true });
  if (range) { sel.removeAllRanges(); sel.addRange(range); }
  if (!res) return;
  if (res.extra) {
    if (a) { const r = document.createRange(); r.selectNodeContents(a); sel.removeAllRanges(); sel.addRange(r); }
    cmd('unlink');
    return;
  }
  let url = (res.url || '').trim();
  if (!url || url === 'https://') return;
  if (!/^[a-z][a-z0-9+.-]*:/i.test(url) && !url.startsWith('#')) url = 'https://' + url;
  if (a) {
    a.setAttribute('href', url);
    a.removeAttribute('data-h');
    a.title = url;
  } else if (sel.isCollapsed) {
    insertHtmlAtCaret(`<a href="${esc(url)}">${esc(url)}</a>`);
  } else {
    cmd('createLink', url);
  }
}

async function insertTable(rows, cols) {
  const p = currentPar();
  if (!p) { toast('Zet de cursor eerst op de plek voor de tabel.'); return; }
  await run(async () => {
    await flush();
    const caret = saveCaret();
    const d = await queue(() => api('insert_table', { after: p.dataset.id, rows, cols }));
    renderDoc(d.render, caret);
  });
}

async function tableOp(op) {
  const p = currentPar();
  const td = p && p.closest('td');
  if (!td) { toast('Zet de cursor eerst in een tabel.'); return; }
  await run(async () => {
    await flush();
    const caret = saveCaret();
    const id = td.dataset.id;
    const d = await queue(() => api('table', { cell: id, op }));
    renderDoc(d.render, caret);
  });
}

async function addPart(kind) {
  await run(async () => {
    await flush();
    const d = await queue(() => api('add_part', { kind }));
    renderDoc(d.render);
    const ce = ceOf(kind);
    if (ce) { ce.focus(); const p = ce.querySelector('p'); if (p) placeCaret(p, 0); }
  });
}

async function resolveTracked(accept) {
  const label = accept ? 'Alle wijzigingen accepteren?' : 'Alle wijzigingen afwijzen?';
  if (!confirm(label + ' Dit kun je ongedaan maken met ⌘Z.')) return;
  await run(async () => {
    await flush();
    const d = await queue(() => api('tracked', { accept }));
    renderDoc(d.render);
    toast(accept ? 'Alle wijzigingen zijn geaccepteerd.' : 'Alle wijzigingen zijn afgewezen.');
  });
}

async function undoRedo(which) {
  await run(async () => {
    await flush();
    const caret = saveCaret();
    const d = await queue(() => api(which, {}));
    renderDoc(d.render, caret);
  });
}

/* ---------------------------------------------------------------- plakken */

function sanitizePaste(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const internal = !!doc.querySelector('[data-r], [data-id]');
  const blocks = [];
  let cur = null;
  const newPar = (style) => { cur = { style, html: '' }; blocks.push(cur); return cur; };
  const ensure = () => cur || newPar(null);
  const headingStyle = (n) => (S.r.headings || {})[String(n)] || null;

  function inline(node) {
    let out = '';
    for (const ch of node.childNodes) {
      if (ch.nodeType === 3) { out += esc(ch.data.replace(/\s*\n\s*/g, ' ')); continue; }
      if (ch.nodeType !== 1) continue;
      const t = ch.tagName;
      if (/^(SCRIPT|STYLE|META|LINK|TITLE|HEAD|O:P)$/.test(t)) continue;
      if (t === 'BR') { out += '<br>'; continue; }
      if (t === 'IMG') continue;
      const inner = inline(ch);
      if (!inner) continue;
      if (internal && ch.dataset && (ch.dataset.a || ch.dataset.n)) { out += ch.outerHTML; continue; }
      if (t === 'A' && ch.getAttribute('href')) {
        const href = ch.getAttribute('href');
        out += `<a href="${esc(href)}"${internal && ch.dataset.h ? ` data-h="${esc(ch.dataset.h)}"` : ''}>${inner}</a>`;
        continue;
      }
      const tagMap = { B: 'b', STRONG: 'b', I: 'i', EM: 'i', U: 'u', S: 's', STRIKE: 's', SUP: 'sup', SUB: 'sub' };
      let open = '', close = '';
      if (tagMap[t]) { open = `<${tagMap[t]}>`; close = `</${tagMap[t]}>`; }
      const st = ch.style;
      const css = [];
      if (st) {
        if (st.fontWeight) css.push('font-weight:' + (st.fontWeight === 'bold' || +st.fontWeight >= 600 ? '700' : '400'));
        if (st.fontStyle) css.push('font-style:' + st.fontStyle);
        const d = st.textDecorationLine || st.textDecoration;
        if (d && /underline|line-through/.test(d)) css.push('text-decoration:' + d.match(/underline|line-through/g).join(' '));
        if (st.verticalAlign === 'super' || st.verticalAlign === 'sub') css.push('vertical-align:' + st.verticalAlign);
        if (internal) {
          if (st.color) css.push('color:' + st.color);
          if (st.backgroundColor) css.push('background-color:' + st.backgroundColor);
          if (st.fontSize && /pt$/.test(st.fontSize)) css.push('font-size:' + st.fontSize);
        }
      }
      const r = internal && ch.dataset && ch.dataset.r ? ` data-r="${esc(ch.dataset.r)}"` : '';
      if (css.length || r) { open += `<span${r} style="${esc(css.join(';'))}">`; close = '</span>' + close; }
      out += open + inner + close;
    }
    return out;
  }

  function block(node) {
    for (const ch of node.childNodes) {
      if (ch.nodeType === 3) {
        if (ch.data.trim()) ensure().html += esc(ch.data.replace(/\s*\n\s*/g, ' '));
        continue;
      }
      if (ch.nodeType !== 1) continue;
      const t = ch.tagName;
      if (/^(SCRIPT|STYLE|META|LINK|TITLE|HEAD)$/.test(t)) continue;
      const hm = t.match(/^H([1-6])$/);
      if (hm) { newPar(headingStyle(+hm[1])).html = inline(ch); cur = null; continue; }
      if (t === 'P' || t === 'DIV' || t === 'BLOCKQUOTE' || t === 'PRE' || t === 'SECTION' || t === 'ARTICLE') {
        if (ch.querySelector('p, div, h1, h2, h3, h4, h5, h6, ul, ol, table, li')) { cur = null; block(ch); cur = null; continue; }
        const b = newPar(internal && ch.dataset.style ? ch.dataset.style : null);
        b.html = inline(ch);
        if (internal && ch.dataset.num !== undefined) { b.num = ch.dataset.num; b.lvl = ch.dataset.lvl || '0'; }
        cur = null;
        continue;
      }
      if (t === 'LI') {
        const b = newPar(null);
        b.list = ch.parentNode && ch.parentNode.tagName === 'OL' ? 'number' : 'bullet';
        const nested = Array.from(ch.childNodes).filter((n) => !(n.nodeType === 1 && /^(UL|OL)$/.test(n.tagName)));
        const tmp = document.createElement('div');
        nested.forEach((n) => tmp.appendChild(n.cloneNode(true)));
        b.html = inline(tmp);
        cur = null;
        for (const sub of ch.children) if (/^(UL|OL)$/.test(sub.tagName)) block(sub);
        continue;
      }
      if (t === 'TR') {
        const cells = Array.from(ch.cells).map((c) => inline(c)).join('\t');
        newPar(null).html = cells;
        cur = null;
        continue;
      }
      if (/^(UL|OL|TABLE|TBODY|THEAD|TFOOT|BODY|HTML|MAIN|SPAN|FONT|CENTER|FORM|HEADER|FOOTER|NAV|ASIDE|FIGURE)$/.test(t)) {
        if (/^(SPAN|FONT)$/.test(t) && !ch.querySelector('p, div, br, li, tr')) { ensure().html += inline({ childNodes: [ch] }); continue; }
        block(ch);
        continue;
      }
      ensure().html += inline({ childNodes: [ch] });
    }
  }
  block(doc.body);
  return blocks.filter((b) => b.html.replace(/<[^>]+>/g, '').trim() || b.html.includes('data-a'))
    .map((b) => {
      const style = b.style && S.styleById[b.style] ? b.style : null;
      const cls = 'ps-' + (style || S.r.default_style || '').replace(/[^A-Za-z0-9_-]/g, '_');
      const attrs = [`class="${cls}"`];
      if (style) attrs.push(`data-style="${esc(style)}"`);
      if (b.list) attrs.push(`data-list="${b.list}"`);
      if (b.num !== undefined) attrs.push(`data-num="${esc(b.num)}" data-lvl="${esc(b.lvl)}"`);
      return `<p ${attrs.join(' ')}>${b.html || '<br>'}</p>`;
    }).join('');
}

function textToHtml(text) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  if (lines.length === 1) return null;
  return lines.map((l) => `<p class="${defaultClass()}">${esc(l) || '<br>'}</p>`).join('');
}

async function applyPastedLists(ce) {
  const ps = Array.from(ce.querySelectorAll('p[data-list]'));
  if (!ps.length) return;
  const kinds = {};
  for (const p of ps) {
    const k = p.dataset.list;
    if (!kinds[k]) {
      const d = await queue(() => api('list', { kind: k, fresh: k === 'number' }));
      kinds[k] = d.num;
      S.r.numbering = d.numbering;
    }
    p.dataset.num = kinds[k];
    p.dataset.lvl = '0';
    delete p.dataset.list;
    if (!p.dataset.style && S.r.list_style) setStyle(p, S.r.list_style);
  }
  buildNumCss();
  renumber();
}

docEl.addEventListener('paste', (e) => {
  const ce = e.target.closest && e.target.closest('.ce');
  if (!ce) return;
  const dt = e.clipboardData;
  if (!dt) return;
  const file = Array.from(dt.files || []).find((f) => /^image\//.test(f.type));
  const html = dt.getData('text/html');
  const text = dt.getData('text/plain');
  e.preventDefault();
  if (file && !text) { insertImage(file, getSelection().getRangeAt(0).cloneRange()); return; }
  if (html) {
    const clean = sanitizePaste(html);
    if (clean) {
      // één alinea zonder eigen profiel: alleen de inhoud plakken, niet een nieuwe alinea
      const single = clean.match(/^<p class="[^"]*">(.*)<\/p>$/s);
      insertHtmlAtCaret(single && !single[1].includes('</p>') ? single[1] : clean);
      run(() => applyPastedLists(ce));
      return;
    }
  }
  if (text) {
    const multi = textToHtml(text);
    if (multi) insertHtmlAtCaret(multi); else document.execCommand('insertText', false, text);
  }
});

/* ---------------------------------------------------------------- toetsen */

function parText(p) { return p.textContent.replace(/[​﻿]/g, ''); }

docEl.addEventListener('keydown', (e) => {
  const mod = IS_MAC ? e.metaKey : e.ctrlKey;
  const p = currentPar();
  if (e.key === 'Tab' && !mod && !e.altKey) {
    e.preventDefault();
    if (p && effNum(p) && (parText(p) === '' || caretAtStart(p) || !getSelection().isCollapsed)) { indent(e.shiftKey ? -1 : 1); return; }
    const td = p && p.closest('td');
    if (td && !effNum(p)) {
      const cells = Array.from(td.closest('table').querySelectorAll('td:not([hidden])'));
      const next = cells[cells.indexOf(td) + (e.shiftKey ? -1 : 1)];
      if (next) { const q = next.querySelector('p') || next; placeCaret(q, 0); }
      return;
    }
    if (p && effNum(p) && e.shiftKey) { indent(-1); return; }
    if (!e.shiftKey) document.execCommand('insertText', false, '\t');
    return;
  }
  if (e.key === 'Enter' && !mod && !e.shiftKey && p && effNum(p) && parText(p) === '') {
    e.preventDefault();
    const n = effNum(p);
    if (n[1] > 0) { indent(-1); return; }
    if (p.dataset.snum) p.dataset.num = '0'; else { delete p.dataset.num; delete p.dataset.lvl; }
    if (p.dataset.style === S.r.list_style) setStyle(p, null);
    renumber();
    return;
  }
  if (e.key === 'Enter' && mod) { e.preventDefault(); pageBreak(); }
});

function caretAtStart(p) {
  const sel = getSelection();
  if (!sel.rangeCount || !sel.isCollapsed) return false;
  const r = document.createRange();
  r.selectNodeContents(p);
  r.setEnd(sel.anchorNode, sel.anchorOffset);
  return r.toString().length === 0;
}

/* Enter in een kop: de nieuwe alinea krijgt het volgende profiel (meestal Standaard). */
docEl.addEventListener('input', (e) => {
  if (e.inputType === 'insertParagraph') {
    const p = currentPar();
    const prev = p && p.previousElementSibling;
    if (p && prev && prev.tagName === 'P' && parText(p) === '') {
      const sid = prev.dataset.style || S.r.default_style;
      const st = S.styleById[sid];
      if (st && st.next && st.next !== sid) setStyle(p, st.next);
      if (p.dataset.snum && p.dataset.style !== prev.dataset.style) { delete p.dataset.snum; delete p.dataset.slvl; }
    }
    renumber();
  } else if (/^(insertFromPaste|deleteContent|deleteByCut|insertText|historyUndo)/.test(e.inputType)) {
    clearTimeout(renumber.t);
    renumber.t = setTimeout(renumber, 150);
  }
  clearTimeout(updateStatus.t);
  updateStatus.t = setTimeout(updateStatus, 400);
});

docEl.addEventListener('beforeinput', (e) => {
  if (e.inputType === 'historyUndo' || e.inputType === 'historyRedo') {
    e.preventDefault();
    undoRedo(e.inputType === 'historyUndo' ? 'undo' : 'redo');
  }
});

docEl.addEventListener('click', (e) => {
  const a = e.target.closest && e.target.closest('a[href]');
  if (a && (e.metaKey || e.ctrlKey) && /^https?:/i.test(a.getAttribute('href'))) {
    e.preventDefault();
    window.open(a.getAttribute('href'), '_blank');
  }
});

docEl.addEventListener('contextmenu', (e) => {
  const td = e.target.closest && e.target.closest('.ce td');
  if (!td) return;
  e.preventDefault();
  const p = td.querySelector('p');
  if (!currentPar() || !td.contains(currentPar())) if (p) placeCaret(p, 0);
  showCtx(e.clientX, e.clientY, [
    ['Rij erboven invoegen', () => tableOp('row_above')],
    ['Rij eronder invoegen', () => tableOp('row_below')],
    ['Kolom links invoegen', () => tableOp('col_left')],
    ['Kolom rechts invoegen', () => tableOp('col_right')],
    null,
    ['Rij verwijderen', () => tableOp('row_delete'), true],
    ['Kolom verwijderen', () => tableOp('col_delete'), true],
    ['Tabel verwijderen', () => tableOp('table_delete'), true],
  ]);
});

function showCtx(x, y, items) {
  const m = $('#ctx');
  m.innerHTML = '';
  for (const it of items) {
    if (!it) { m.appendChild(document.createElement('hr')); continue; }
    const b = document.createElement('button');
    b.textContent = it[0];
    if (it[2]) b.className = 'danger';
    b.onmousedown = (ev) => ev.preventDefault();
    b.onclick = () => { m.hidden = true; it[1](); };
    m.appendChild(b);
  }
  m.hidden = false;
  m.style.left = Math.min(x, innerWidth - m.offsetWidth - 8) + 'px';
  m.style.top = Math.min(y, innerHeight - m.offsetHeight - 8) + 'px';
}

document.addEventListener('mousedown', (e) => {
  if (!e.target.closest('#ctx')) $('#ctx').hidden = true;
  if (!e.target.closest('.menu-wrap')) document.querySelectorAll('.menu').forEach((m) => { m.hidden = true; });
});

document.addEventListener('keydown', (e) => {
  const mod = IS_MAC ? e.metaKey : e.ctrlKey;
  if (!$('#dialog').hidden) { if (e.key === 'Escape') { e.preventDefault(); closeDialog(null); } return; }
  if (e.key === 'Escape') {
    $('#ctx').hidden = true;
    document.querySelectorAll('.menu').forEach((m) => { m.hidden = true; });
    if (!$('#searchBar').hidden) closeSearch();
    return;
  }
  if (!mod) return;
  const k = e.key.toLowerCase();
  const loaded = S.st && S.st.loaded;
  // eigen venster: eerst de laatste wijzigingen doorgeven, dan sluiten of stoppen
  if (nativeApi() && (k === 'w' || k === 'q')) {
    e.preventDefault();
    const go = () => { if (k === 'w') nativeApi().close(); else nativeApi().quit(); };
    flush().then(go, go);
    return;
  }
  if (k === 's') { e.preventDefault(); if (e.shiftKey) saveAs(); else save(); return; }
  if (k === 'o') { e.preventDefault(); openFile(); return; }
  if (k === 'n' && !e.shiftKey) { e.preventDefault(); newDoc(); return; }
  if (!loaded) return;
  if (k === 'f') { e.preventDefault(); openSearch(); return; }
  if (k === 'p') { e.preventDefault(); printDoc(); return; }
  if (k === 'z') { e.preventDefault(); undoRedo(e.shiftKey ? 'redo' : 'undo'); return; }
  if (k === 'y' && !IS_MAC) { e.preventDefault(); undoRedo('redo'); return; }
  const inDoc = !!currentCe() && document.activeElement && document.activeElement.closest && document.activeElement.closest('.ce');
  if (!inDoc) return;
  if (k === 'b') { e.preventDefault(); cmd('bold'); return; }
  if (k === 'i') { e.preventDefault(); cmd('italic'); return; }
  if (k === 'u') { e.preventDefault(); cmd('underline'); return; }
  if (k === 'k') { e.preventDefault(); editLink(); return; }
  if (e.altKey && /^(Digit[0-6])$/.test(e.code)) {
    e.preventDefault();
    const n = +e.code.slice(5);
    applyStyle(n === 0 ? S.r.default_style : (S.r.headings || {})[String(n)]);
  }
});

/* ---------------------------------------------------------------- werkbalk */

function buildPalette(el, colors, onPick, noneLabel) {
  el.innerHTML = '';
  for (const c of colors) {
    const b = document.createElement('button');
    b.style.background = '#' + c;
    b.title = '#' + c;
    b.onmousedown = (e) => e.preventDefault();
    b.onclick = () => { el.hidden = true; onPick(c); };
    el.appendChild(b);
  }
  const none = document.createElement('button');
  none.className = 'none';
  none.textContent = noneLabel;
  none.onmousedown = (e) => e.preventDefault();
  none.onclick = () => { el.hidden = true; onPick(null); };
  el.appendChild(none);
}

function toggleMenu(menu) {
  const open = menu.hidden;
  document.querySelectorAll('.menu').forEach((m) => { m.hidden = true; });
  menu.hidden = !open;
}

buildPalette($('#colorMenu'), COLORS, (c) => {
  $('#colorSwatch').style.background = '#' + (c || '000000');
  cmd('foreColor', '#' + (c || '000000'));
}, 'Automatisch (zwart)');
buildPalette($('#markMenu'), MARKS, (c) => {
  cmd('hiliteColor', c ? '#' + c : 'transparent');
}, 'Geen markering');

/* Klikken op de werkbalk mag de cursor in de tekst niet wegnemen. */
document.querySelectorAll('.toolbar button').forEach((b) => b.addEventListener('mousedown', (e) => e.preventDefault()));

$('#tUndo').onclick = () => undoRedo('undo');
$('#tRedo').onclick = () => undoRedo('redo');
document.querySelectorAll('[data-cmd]').forEach((b) => { b.onclick = () => cmd(b.dataset.cmd); });
$('#tColor').onclick = () => toggleMenu($('#colorMenu'));
$('#tMark').onclick = () => toggleMenu($('#markMenu'));
$('#tClear').onclick = () => cmd('removeFormat');
document.querySelectorAll('[data-align]').forEach((b) => { b.onclick = () => setAlign(b.dataset.align); });
$('#tBullet').onclick = () => run(() => toggleList('bullet'));
$('#tNumber').onclick = () => run(() => toggleList('number'));
$('#tIndent').onclick = () => indent(1);
$('#tOutdent').onclick = () => indent(-1);
$('#tLink').onclick = editLink;
$('#tImage').onclick = pickImage;
$('#tBreak').onclick = pageBreak;
$('#tTable').onclick = () => { updateToolbar(); toggleMenu($('#tableMenu')); };
document.querySelectorAll('[data-top]').forEach((b) => {
  b.addEventListener('mousedown', (e) => e.preventDefault());
  b.onclick = () => { $('#tableMenu').hidden = true; tableOp(b.dataset.top); };
});
$('#tSearch').onclick = openSearch;

/* Keuzelijsten nemen de focus; onthoud waar de cursor stond. */
let savedRange = null;
for (const id of ['#tStyle', '#tSize']) {
  $(id).addEventListener('mousedown', () => {
    const sel = getSelection();
    savedRange = sel.rangeCount && currentCe() ? sel.getRangeAt(0).cloneRange() : null;
  });
  $(id).addEventListener('focus', () => {
    const sel = getSelection();
    if (!savedRange && sel.rangeCount && currentCe()) savedRange = sel.getRangeAt(0).cloneRange();
  });
}
function restoreRange() {
  if (!savedRange) return !!currentCe();
  const n = savedRange.startContainer;
  const ce = (n.nodeType === 1 ? n : n.parentNode).closest('.ce');
  if (!ce) return false;
  ce.focus({ preventScroll: true });
  const sel = getSelection();
  sel.removeAllRanges();
  sel.addRange(savedRange);
  savedRange = null;
  return true;
}
$('#tStyle').onchange = (e) => { if (restoreRange()) applyStyle(e.target.value); };
$('#tSize').onchange = (e) => {
  const v = parseFloat(e.target.value);
  e.target.value = '';
  if (restoreRange() && v) setSize(v);
};

(function buildGridPicker() {
  const g = $('#gridPick');
  for (let r = 1; r <= 8; r++) {
    for (let c = 1; c <= 8; c++) {
      const s = document.createElement('span');
      s.dataset.r = r;
      s.dataset.c = c;
      g.appendChild(s);
    }
  }
  g.addEventListener('mousedown', (e) => e.preventDefault());
  g.addEventListener('mouseover', (e) => {
    const t = e.target.closest('span');
    if (!t) return;
    const R = +t.dataset.r, C = +t.dataset.c;
    g.querySelectorAll('span').forEach((s) => s.classList.toggle('on', +s.dataset.r <= R && +s.dataset.c <= C));
    $('#gridLabel').textContent = `Tabel invoegen: ${C} × ${R}`;
  });
  g.addEventListener('click', (e) => {
    const t = e.target.closest('span');
    if (!t) return;
    $('#tableMenu').hidden = true;
    insertTable(+t.dataset.r, +t.dataset.c);
  });
})();

$('#imageInput').onchange = (e) => {
  const f = e.target.files[0];
  e.target.value = '';
  if (f) insertImage(f, S.imgRange);
};

$('#zoom').onchange = (e) => {
  const z = e.target.value;
  const page = docEl.querySelector('.page');
  if (page) page.style.zoom = z;
  try { localStorage.setItem('schrijfblad-zoom', z); } catch (err) { /* geen opslag */ }
};

function updateStatus() {
  const body = ceOf('body');
  if (!body) { $('#status').textContent = ''; return; }
  const text = body.innerText || '';
  const words = (text.match(/[\p{L}\p{N}][\p{L}\p{N}'’\-]*/gu) || []).length;
  const chars = text.replace(/\n/g, '').length;
  $('#status').textContent = `${words.toLocaleString('nl-NL')} ${words === 1 ? 'woord' : 'woorden'} · ${chars.toLocaleString('nl-NL')} tekens`;
  const page = docEl.querySelector('.page');
  if (page) page.style.zoom = $('#zoom').value;
}

/* ---------------------------------------------------------------- dialoog */

let dialogResolve = null;
function ask(title, fields, extraLabel) {
  $('#dialogTitle').textContent = title;
  $('#dialogFields').innerHTML = fields.map((f) =>
    `<label>${esc(f.label)}<input name="${f.name}" value="${esc(f.value || '')}" placeholder="${esc(f.placeholder || '')}" autocomplete="off" spellcheck="false"></label>`).join('');
  $('#dialogExtra').hidden = !extraLabel;
  $('#dialogExtra').textContent = extraLabel || '';
  $('#dialog').hidden = false;
  const first = $('#dialogFields input');
  if (first) { first.focus(); first.select(); }
  return new Promise((res) => { dialogResolve = res; });
}
function closeDialog(val) {
  $('#dialog').hidden = true;
  if (dialogResolve) { const r = dialogResolve; dialogResolve = null; r(val); }
}
$('#dialogForm').onsubmit = (e) => {
  e.preventDefault();
  const out = {};
  $('#dialogFields').querySelectorAll('input').forEach((i) => { out[i.name] = i.value; });
  closeDialog(out);
};
$('#dialogCancel').onclick = () => closeDialog(null);
$('#dialogExtra').onclick = () => closeDialog({ extra: true });

/* ---------------------------------------------------------------- zoeken en vervangen */

function openSearch() {
  $('#searchBar').hidden = false;
  const sel = getSelection();
  const s = sel && !sel.isCollapsed ? sel.toString() : '';
  if (s && !s.includes('\n') && s.length < 100) $('#sQuery').value = s;
  $('#sQuery').focus();
  $('#sQuery').select();
  doSearch(true);
}
function closeSearch() {
  $('#searchBar').hidden = true;
  if (window.CSS && CSS.highlights) { CSS.highlights.delete('zoek'); CSS.highlights.delete('zoekhuidig'); }
  S.search = { matches: [], idx: -1 };
}

function findMatches(q, cs) {
  const out = [];
  if (!q) return out;
  const needle = cs ? q : q.toLocaleLowerCase();
  for (const ce of containers()) {
    for (const p of ce.querySelectorAll('p')) {
      if (p.closest('[contenteditable="false"]') || p.closest('td[hidden]')) continue;
      const nodes = [];
      let text = '';
      const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, {
        acceptNode: (n) => (n.parentNode.closest('[contenteditable="false"]') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
      });
      let n;
      while ((n = walker.nextNode())) {
        if (n.parentNode.closest('p') !== p) continue;
        nodes.push([n, text.length]);
        text += n.data;
      }
      const hay = cs ? text : text.toLocaleLowerCase();
      let i = hay.indexOf(needle);
      while (i >= 0) {
        const r = document.createRange();
        const at = (off, end) => {
          for (let k = nodes.length - 1; k >= 0; k--) {
            const [node, start] = nodes[k];
            if (end ? off > start : off >= start) return [node, Math.min(off - start, node.data.length)];
          }
          return [nodes[0][0], 0];
        };
        const [sn, so] = at(i, false);
        const [en, eo] = at(i + needle.length, true);
        r.setStart(sn, so);
        r.setEnd(en, eo);
        out.push(r);
        i = hay.indexOf(needle, i + Math.max(1, needle.length));
      }
    }
  }
  return out;
}

function doSearch(keepIdx) {
  const q = $('#sQuery').value;
  const matches = findMatches(q, $('#sCase').checked);
  S.search.matches = matches;
  if (!keepIdx || S.search.idx >= matches.length) S.search.idx = matches.length ? 0 : -1;
  if (S.search.idx < 0 && matches.length) S.search.idx = 0;
  paintSearch();
}

function paintSearch() {
  const { matches, idx } = S.search;
  const q = $('#sQuery').value;
  $('#sCount').textContent = !q ? '' : matches.length ? `${idx + 1} van ${matches.length}` : 'niet gevonden';
  if (window.CSS && CSS.highlights && window.Highlight) {
    CSS.highlights.set('zoek', new Highlight(...matches));
    if (idx >= 0) CSS.highlights.set('zoekhuidig', new Highlight(matches[idx])); else CSS.highlights.delete('zoekhuidig');
  }
  if (idx >= 0) {
    const rect = matches[idx].getBoundingClientRect();
    const box = scroller.getBoundingClientRect();
    if (rect.top < box.top + 40 || rect.bottom > box.bottom - 40) scroller.scrollTop += rect.top - box.top - box.height / 3;
  }
}

function gotoMatch(dir) {
  const n = S.search.matches.length;
  if (!n) { doSearch(); return; }
  S.search.idx = (S.search.idx + dir + n) % n;
  paintSearch();
}

function replaceRange(range, text) {
  const n = range.startContainer;
  const ce = (n.nodeType === 1 ? n : n.parentNode).closest('.ce');
  if (!ce) return;
  ce.focus({ preventScroll: true });
  const sel = getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  if (text) document.execCommand('insertText', false, text); else document.execCommand('delete');
}

function replaceOne() {
  const { matches, idx } = S.search;
  if (idx < 0 || !matches[idx]) { doSearch(); return; }
  replaceRange(matches[idx], $('#sRepl').value);
  doSearch(true);
  $('#sRepl').focus();
}

function replaceAll() {
  const matches = findMatches($('#sQuery').value, $('#sCase').checked);
  if (!matches.length) { toast('Niets gevonden.'); return; }
  const repl = $('#sRepl').value;
  for (let i = matches.length - 1; i >= 0; i--) replaceRange(matches[i], repl);
  toast(`${matches.length} keer vervangen.`);
  doSearch();
}

let searchTimer = 0;
$('#sQuery').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => doSearch(), 120); });
$('#sQuery').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); gotoMatch(e.shiftKey ? -1 : 1); }
});
$('#sRepl').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); replaceOne(); } });
$('#sCase').onchange = () => doSearch();
$('#sPrev').onclick = () => gotoMatch(-1);
$('#sNext').onclick = () => gotoMatch(1);
$('#sReplOne').onclick = replaceOne;
$('#sReplAll').onclick = replaceAll;
$('#sClose').onclick = closeSearch;

/* ---------------------------------------------------------------- bestanden */

function confirmDiscard() {
  return !isDirty() || confirm('Je hebt wijzigingen die nog niet zijn opgeslagen. Wil je die weggooien?');
}

function elsewhere() {
  return !!(S.st && S.st.window && S.st.loaded);
}

function openFile() {
  const away = elsewhere();
  if (!away && !confirmDiscard()) return;
  if (S.st && S.st.can_native) {
    run(async () => {
      await flush();
      const d = await api('open_dialog', { elsewhere: away });
      if (!d.cancelled && !d.elsewhere) await afterOpen();
    });
  } else {
    $('#fileInput').click();
  }
}

async function upload(file) {
  const away = elsewhere();
  if (!away && !confirmDiscard()) return;
  await run(async () => {
    toast('Bezig met openen…');
    await flush().catch(() => {});
    const d = await api('upload' + (away ? '?elsewhere=1' : ''), undefined, {
      body: file, headers: { 'X-Filename': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream' },
    });
    if (!d.elsewhere) await afterOpen();
    $('#toast').hidden = true;
  });
}

function newDoc() {
  const away = elsewhere();
  if (!away && !confirmDiscard()) return;
  run(async () => {
    const d = await api('new', { elsewhere: away });
    if (!d.elsewhere) await afterOpen();
  });
}

function save() {
  if (!S.st || !S.st.loaded) return;
  run(async () => {
    await flush();
    const d = await queue(() => api('save', {}));
    if (d.need_path) return saveAs();
    toast('Opgeslagen');
  });
}

function saveAs() {
  if (!S.st || !S.st.loaded) return;
  if (!S.st.can_native) { download('docx'); return; }
  run(async () => {
    await flush();
    const d = await queue(() => api('save_as', {}));
    if (!d.cancelled) toast('Opgeslagen als ' + d.path);
  });
}

function download(fmt) {
  run(async () => {
    await flush();
    if (S.st && S.st.can_native) {
      const d = await queue(() => api('export', { fmt }));
      if (!d.cancelled) toast('Bewaard als ' + d.path);
      return;
    }
    const a = document.createElement('a');
    a.href = `/api/download?doc=${DOC}&fmt=${fmt}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
}

function printHtml() {
  const page = docEl.querySelector('.page').cloneNode(true);
  page.querySelectorAll('.addpart, .tag').forEach((el) => el.remove());
  page.querySelectorAll('[contenteditable]').forEach((el) => el.removeAttribute('contenteditable'));
  page.style.zoom = '';
  const pg = S.r.page;
  const inch = (t) => (t / 1440).toFixed(3) + 'in';
  const title = esc((S.st && S.st.filename) || 'Document');
  return `<!doctype html><html lang="nl"><head><meta charset="utf-8"><title>${title}</title>
<base href="${location.origin}/"><link rel="stylesheet" href="${location.origin}/app.css">
<style>${$('#docCss').textContent}\n${$('#numCss').textContent}
@page { size: ${inch(pg.w)} ${inch(pg.h)}; margin: ${inch(pg.top)} ${inch(pg.right)} ${inch(pg.bottom)} ${inch(pg.left)}; }
body.print { background: #eef1f5; }
body.print .page { margin: 24px auto; }
@media print { body.print { background: #fff; } body.print .page { margin: 0; } }</style></head>
<body class="print"><div class="doc">${page.outerHTML}</div>
<script>window.addEventListener('load', function () { setTimeout(function () { window.print(); }, 300); });<\/script>
</body></html>`;
}

function printDoc() {
  if (!S.st || !S.st.loaded) return;
  const native = !!(S.st && S.st.window);
  const w = native ? null : window.open('', '_blank');
  run(async () => {
    await flush();
    const html = printHtml();
    if (native) {
      await api('print', { html, open: true });
      toast('De afdrukversie opent in je browser. Kies daar Afdrukken (⌘P) of Bewaar als PDF.');
    } else if (w) {
      w.document.open();
      w.document.write(html);
      w.document.close();
    } else {
      toast('Je browser blokkeerde het afdrukvenster. Sta pop-ups toe voor deze pagina en probeer het opnieuw.', true);
    }
  });
}

$('#btnOpen').onclick = openFile;
$('#wOpen').onclick = openFile;
$('#btnNew').onclick = newDoc;
$('#wNew').onclick = newDoc;
$('#wBrowse').onclick = (e) => { e.preventDefault(); $('#fileInput').click(); };
$('#btnSave').onclick = save;
$('#btnSaveAs').onclick = saveAs;
$('#btnExport').onclick = () => toggleMenu($('#exportMenu'));
document.querySelectorAll('[data-export]').forEach((b) => {
  b.onclick = () => { $('#exportMenu').hidden = true; download(b.dataset.export); };
});
$('#btnPrint').onclick = () => { $('#exportMenu').hidden = true; printDoc(); };
$('#fileInput').onchange = (e) => {
  const f = e.target.files[0];
  e.target.value = '';
  if (f) upload(f);
};
$('#bannerClose').onclick = () => { $('#banner').hidden = true; };
$('#trAccept').onclick = () => resolveTracked(true);
$('#trReject').onclick = () => resolveTracked(false);

let dragDepth = 0;
const isImageFile = (f) => /^image\//.test(f.type) || /\.(png|jpe?g|gif|bmp|tiff?)$/i.test(f.name);
window.addEventListener('dragenter', (e) => {
  if (![...(e.dataTransfer.types || [])].includes('Files')) return;
  dragDepth++;
  $('#dropText').textContent = S.st && S.st.loaded ? 'Laat los: document openen of afbeelding invoegen' : 'Laat los om te openen';
  $('#dropHint').hidden = false;
});
window.addEventListener('dragleave', () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $('#dropHint').hidden = true; });
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => {
  e.preventDefault();
  dragDepth = 0;
  $('#dropHint').hidden = true;
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  if (!f) return;
  if (S.st && S.st.loaded && isImageFile(f)) {
    let range = null;
    if (document.caretRangeFromPoint) range = document.caretRangeFromPoint(e.clientX, e.clientY);
    if (range && !(range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentNode).closest('.ce')) range = null;
    insertImage(f, range || (getSelection().rangeCount ? getSelection().getRangeAt(0).cloneRange() : null));
    return;
  }
  upload(f);
});

window.addEventListener('beforeunload', (e) => {
  if (S.touched.size) flush();
  if (isDirty()) { e.preventDefault(); e.returnValue = ''; }
});

/* Terug in dit venster? Kijken of het document intussen elders veranderd is
   (bijvoorbeeld omdat je hetzelfde bestand nog eens opende vanuit de Finder). */
async function refreshIfChanged() {
  if (!S.st || S.touched.size) return;
  const prevVersion = S.st.version, prevFile = S.st.filename, prevLoaded = S.st.loaded;
  await queue(() => api('state'));
  if (!S.st.loaded) return;
  if (!prevLoaded || S.st.filename !== prevFile || S.st.gen !== S.gen) await afterOpen();
  else if (S.st.version !== prevVersion && !S.touched.size) await reload(true);
}
window.addEventListener('focus', () => run(refreshIfChanged));

/* ---------------------------------------------------------------- start */

try { const z = localStorage.getItem('schrijfblad-zoom'); if (z) $('#zoom').value = z; } catch (e) { /* geen opslag */ }
document.execCommand('defaultParagraphSeparator', false, 'p');
run(async () => {
  await api('state');
  if (S.st.loaded) await afterOpen();
});
