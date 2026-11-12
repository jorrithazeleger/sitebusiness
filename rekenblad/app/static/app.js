'use strict';
/* Rekenblad: de editor in de browser. Praat met de lokale server via /api/. */

const ROWH = 24, HEADH = 24, RHW = 52, CHUNK = 100, BUF = 30;
const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform);

const FILLS = ['FFF2CC', 'E2EFDA', 'DDEBF7', 'FCE4D6', 'EDEDED', 'D9D2E9',
  'FFD966', 'A9D08E', '9BC2E6', 'F4B084', 'BFBFBF', 'B4A7D6',
  'FFC000', '70AD47', '4472C4', 'ED7D31', '7F7F7F', '7030A0'];
const COLORS = ['000000', '595959', 'C00000', 'FF0000', 'ED7D31', 'BF8F00',
  '00B050', '548235', '0070C0', '1F4E79', '7030A0', 'FFFFFF'];

const S = {
  st: null,
  sheet: null,
  meta: null,
  colx: [0],
  cache: new Map(),
  old: new Map(),
  gen: 0,
  sel: { ar: 1, ac: 1, fr: 1, fc: 1 },
  editing: null,
  rendered: { first: 0, last: -1 },
  extra: {},
  search: { matches: [], idx: -1 },
  drag: null,
};

/* Elk tabblad heeft een eigen document: zo kun je meerdere bestanden tegelijk open hebben. */
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

const gridWrap = $('#gridWrap'), grid = $('#grid'), editor = $('#cellEditor'), fInput = $('#fInput');
const clip = $('#clip');

/* ---------------------------------------------------------------- server */

async function api(path, body) {
  const opts = { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Rekenblad': '1', 'X-Doc': DOC } };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch('/api/' + path, opts);
  } catch (e) {
    throw new Error('Geen verbinding met Rekenblad. Draait het Terminal-venster nog?');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Er ging iets mis.');
  if (data.state) applyState(data.state);
  return data;
}

async function run(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); }
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
  const wasLoaded = S.st && S.st.loaded;
  const prevFile = S.st && S.st.filename;
  S.st = st;
  $('#welcome').hidden = st.loaded;
  for (const id of ['#toolbar', '#fbar', '#gridWrap', '#bottombar', '#fileBox']) $(id).hidden = !st.loaded;
  $('#btnSave').disabled = $('#btnSaveAs').disabled = $('#btnExport').disabled = !st.loaded;
  for (const id of ['#btnSave', '#btnSaveAs', '#btnExport']) $(id).hidden = !st.loaded;
  if (!st.loaded) { renderRecent(st.recent || []); document.title = 'Rekenblad'; return; }

  $('#fileName').textContent = st.filename;
  $('#fileName').title = st.path || 'Nog niet opgeslagen op deze Mac';
  $('#dirty').hidden = !st.dirty;
  document.title = (st.dirty ? '• ' : '') + st.filename + ' – Rekenblad';
  $('#tUndo').disabled = !st.undo;
  $('#tRedo').disabled = !st.redo;
  $('#btnSaveAs').hidden = !st.can_native;

  const fresh = !wasLoaded || prevFile !== st.filename;
  if (!S.sheet || !st.sheets.some((s) => s.name === S.sheet)) {
    S.sheet = (st.sheets[st.active] || st.sheets[0]).name;
    resetView();
  }
  setMeta();
  renderTabs();
  if (fresh) showWarnings(st.warnings || []);
}

function setMeta() {
  const m = S.st.sheets.find((s) => s.name === S.sheet);
  const ex = S.extra[S.sheet] || { rows: 0, cols: 0 };
  const ncols = Math.max(m.ncols, ex.cols);
  const colw = m.colw.slice();
  while (colw.length < ncols) colw.push(75);
  S.meta = { nrows: Math.max(m.nrows, ex.rows), ncols, colw };
  S.colx = [0];
  for (let c = 1; c <= ncols; c++) S.colx[c] = S.colx[c - 1] + colw[c - 1];
}

function grow(r, c) {
  const ex = S.extra[S.sheet] || (S.extra[S.sheet] = { rows: 0, cols: 0 });
  let changed = false;
  if (r > S.meta.nrows - 5) { ex.rows = Math.min(1048576, r + 60); changed = true; }
  if (c > S.meta.ncols - 1) { ex.cols = Math.min(16384, c + 5); changed = true; }
  if (changed) { setMeta(); render(true); }
}

function resetView() {
  S.cache = new Map();
  S.old = new Map();
  S.gen++;
  S.sel = { ar: 1, ac: 1, fr: 1, fc: 1 };
  S.rendered = { first: 0, last: -1 };
  gridWrap.scrollTop = 0;
  gridWrap.scrollLeft = 0;
}

function invalidate() {
  S.old = new Map([...S.old, ...S.cache]);
  S.cache = new Map();
  S.gen++;
}

function afterMutation() {
  invalidate();
  render(true);
  updateFormulaBar();
}

function showWarnings(list) {
  if (!list.length) { $('#banner').hidden = true; return; }
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
    b.onclick = () => run(async () => { await api('open_recent', { path: list[+b.dataset.i] }); afterOpen(); });
  });
}

/* ---------------------------------------------------------------- data */

function colName(c) {
  let s = '';
  while (c > 0) { const m = (c - 1) % 26; s = String.fromCharCode(65 + m) + s; c = Math.floor((c - 1) / 26); }
  return s;
}

function chunkOf(r) {
  const i = Math.floor((r - 1) / CHUNK);
  return S.cache.get(i) || S.old.get(i) || null;
}

function getCell(r, c) {
  const ch = chunkOf(r);
  const row = ch && ch.rows[r];
  return row ? row[c] || null : null;
}

function styleOf(cell, r) {
  if (!cell || cell.s == null) return null;
  const ch = chunkOf(r);
  return ch ? ch.styles[cell.s] : null;
}

function ensureChunks(first, last) {
  const a = Math.floor((first - 1) / CHUNK), b = Math.floor((last - 1) / CHUNK);
  for (let i = a; i <= b; i++) {
    if (S.cache.has(i)) continue;
    S.cache.set(i, null);
    const gen = S.gen, sheet = S.sheet;
    api(`rows?sheet=${encodeURIComponent(sheet)}&start=${i * CHUNK + 1}&count=${CHUNK}`)
      .then((d) => {
        if (gen !== S.gen || sheet !== S.sheet) return;
        S.cache.set(i, d);
        S.old.delete(i);
        render(true);
        updateFormulaBar();
        updateStatus();
      })
      .catch((e) => { if (gen === S.gen) { S.cache.delete(i); toast(e.message, true); } });
  }
}

/* ---------------------------------------------------------------- tekenen */

const mctx = document.createElement('canvas').getContext('2d');
function measure(text, st) {
  mctx.font = `${st && st.fi ? 'italic ' : ''}${st && st.fw ? '700 ' : ''}${(st && st.px) || 13}px ${FONT}`;
  return mctx.measureText(text).width;
}

function selBounds() {
  const s = S.sel;
  return { r1: Math.min(s.ar, s.fr), r2: Math.max(s.ar, s.fr), c1: Math.min(s.ac, s.fc), c2: Math.max(s.ac, s.fc) };
}

function defaultAlign(k) {
  if (k === 'n' || k === 'd') return 'right';
  if (k === 'b' || k === 'e') return 'center';
  return 'left';
}

function render(force) {
  if (!S.meta || gridWrap.hidden) return;
  const top = gridWrap.scrollTop, h = gridWrap.clientHeight || 600;
  const vFirst = Math.max(1, Math.floor(top / ROWH) + 1);
  const vLast = Math.min(S.meta.nrows, Math.ceil((top + h) / ROWH) + 1);
  if (!force && vFirst >= S.rendered.first && vLast <= S.rendered.last) return;
  const first = Math.max(1, vFirst - BUF), last = Math.min(S.meta.nrows, vLast + BUF);
  S.rendered = { first, last };
  ensureChunks(first, last);

  const { ncols, colw } = S.meta;
  const b = selBounds();
  const parts = [];
  parts.push(`<colgroup><col style="width:${RHW}px">`);
  for (let c = 1; c <= ncols; c++) parts.push(`<col style="width:${colw[c - 1]}px">`);
  parts.push('</colgroup><thead><tr><th class="corner" title="Alles selecteren"></th>');
  for (let c = 1; c <= ncols; c++) {
    parts.push(`<th class="ch${c >= b.c1 && c <= b.c2 ? ' hs' : ''}" data-c="${c}">${colName(c)}<div class="rsz" data-c="${c}"></div></th>`);
  }
  parts.push('</tr></thead><tbody>');
  if (first > 1) parts.push(`<tr class="spc" style="height:${(first - 1) * ROWH}px"><td colspan="${ncols + 1}"></td></tr>`);
  for (let r = first; r <= last; r++) parts.push(rowHtml(r, b));
  if (last < S.meta.nrows) parts.push(`<tr class="spc" style="height:${(S.meta.nrows - last) * ROWH}px"><td colspan="${ncols + 1}"></td></tr>`);
  parts.push('</tbody>');
  grid.style.width = (RHW + S.colx[ncols]) + 'px';
  grid.innerHTML = parts.join('');
}

function rowHtml(r, b) {
  const { ncols, colw } = S.meta;
  const ch = chunkOf(r);
  const row = ch && ch.rows[r];
  const out = [`<tr data-r="${r}"><th class="rh${r >= b.r1 && r <= b.r2 ? ' hs' : ''}">${r}</th>`];
  let noLeft = 0;
  for (let c = 1; c <= ncols; c++) {
    const cell = row ? row[c] : null;
    if (cell && cell.h) continue;
    const cls = [];
    let attrs = ` data-c="${c}"`, style = '', inner = '';
    if (r >= b.r1 && r <= b.r2 && c >= b.c1 && c <= b.c2) cls.push('in');
    if (r === S.sel.ar && c === S.sel.ac) cls.push('act');
    if (noLeft >= c) cls.push('nl');
    if (cell) {
      const st = cell.s != null && ch ? ch.styles[cell.s] : null;
      if (cell.cs) attrs += ` colspan="${cell.cs}"`;
      if (cell.m) cls.push('mc');
      if (st && st.css) style = st.css;
      const align = (st && st.a) || (cell.cs ? 'left' : defaultAlign(cell.k));
      if (align !== 'left') cls.push('a-' + align);
      if (cell.st) cls.push('stale');
      if (cell.k === 'e') cls.push('err');
      if (st && st.w) cls.push('wrap');
      const text = cell.d || '';
      inner = esc(text);
      if (text && align === 'left' && !(st && st.w) && !cell.cs) {
        const need = measure(text, st) + 10;
        let w = colw[c - 1], k = c + 1;
        while (need > w && k <= ncols) {
          const nb = row[k];
          if (nb && (nb.d || nb.h || nb.cs)) break;
          w += colw[k - 1];
          noLeft = k;
          k++;
        }
        if (w > colw[c - 1]) { cls.push('spl'); inner = `<div class="sp" style="width:${w - 10}px">${inner}</div>`; }
      }
      if (cell.st) attrs += ' title="Wordt opnieuw berekend zodra je het bestand opent in Excel of Numbers"';
    }
    out.push(`<td${attrs}${cls.length ? ` class="${cls.join(' ')}"` : ''}${style ? ` style="${style}"` : ''}>${inner}</td>`);
  }
  out.push('</tr>');
  return out.join('');
}

/* ---------------------------------------------------------------- selectie */

function select(r, c, extend) {
  r = Math.max(1, Math.min(1048576, r));
  c = Math.max(1, Math.min(16384, c));
  if (extend) { S.sel.fr = r; S.sel.fc = c; } else S.sel = { ar: r, ac: c, fr: r, fc: c };
  grow(extend ? S.sel.fr : r, extend ? S.sel.fc : c);
  ensureVisible(extend ? S.sel.fr : r, extend ? S.sel.fc : c);
  render(true);
  updateFormulaBar();
  updateStatus();
}

function ensureVisible(r, c) {
  const w = gridWrap;
  const y = (r - 1) * ROWH;
  const viewH = w.clientHeight - HEADH;
  if (y < w.scrollTop) w.scrollTop = y;
  else if (y + ROWH > w.scrollTop + viewH) w.scrollTop = y + ROWH - viewH;
  const x = S.colx[c - 1], cw = S.meta.colw[c - 1] || 75;
  if (x < w.scrollLeft) w.scrollLeft = x;
  else if (RHW + x + cw > w.scrollLeft + w.clientWidth) w.scrollLeft = RHW + x + cw - w.clientWidth;
}

function updateFormulaBar() {
  if (!S.meta) return;
  const b = selBounds();
  const ref = colName(S.sel.ac) + S.sel.ar;
  $('#cellRef').textContent = (b.r1 === b.r2 && b.c1 === b.c2) ? ref : `${colName(b.c1)}${b.r1}:${colName(b.c2)}${b.r2}`;
  if (!S.editing) {
    const cell = getCell(S.sel.ar, S.sel.ac);
    fInput.value = cell ? (cell.e != null ? cell.e : cell.d || '') : '';
  }
  const cell = getCell(S.sel.ar, S.sel.ac);
  const st = styleOf(cell, S.sel.ar);
  $('#tBold').classList.toggle('on', !!(st && st.fw));
  $('#tItalic').classList.toggle('on', !!(st && st.fi));
  const nf = (cell && cell.nf) || 'General';
  const opt = [...$('#tNumfmt').options].find((o) => o.value === nf);
  $('#tNumfmt').value = opt ? nf : '';
}

function nlNumber(v, digits) {
  return v.toLocaleString('nl-NL', { maximumFractionDigits: digits == null ? 10 : digits });
}

function updateStatus() {
  const b = selBounds();
  const n = (b.r2 - b.r1 + 1) * (b.c2 - b.c1 + 1);
  if (n < 2 || n > 50000) { $('#status').textContent = ''; return; }
  let sum = 0, count = 0, filled = 0;
  for (let r = b.r1; r <= b.r2; r++) {
    const ch = chunkOf(r);
    const row = ch && ch.rows[r];
    if (!row) continue;
    for (let c = b.c1; c <= b.c2; c++) {
      const cell = row[c];
      if (!cell || cell.h) continue;
      if (cell.d) filled++;
      if (typeof cell.v === 'number') { sum += cell.v; count++; }
    }
  }
  $('#status').textContent = count
    ? `Som: ${nlNumber(sum)}   Gemiddelde: ${nlNumber(sum / count, 4)}   Aantal: ${filled}`
    : (filled ? `Aantal: ${filled}` : '');
}

/* ---------------------------------------------------------------- bewerken */

function startEdit(initial, mode) {
  if (!S.meta) return;
  const { ar: r, ac: c } = S.sel;
  const cell = getCell(r, c);
  if (cell && cell.h) return;
  const orig = cell ? (cell.e != null ? cell.e : cell.d || '') : '';
  S.editing = { r, c, orig, mode: mode || (initial != null ? 'enter' : 'edit') };
  ensureVisible(r, c);
  const left = RHW + S.colx[c - 1], top = HEADH + (r - 1) * ROWH;
  editor.style.left = left + 'px';
  editor.style.top = top + 'px';
  editor.style.minWidth = (S.meta.colw[c - 1] + 1) + 'px';
  editor.value = initial != null ? initial : orig;
  editor.hidden = false;
  sizeEditor();
  editor.focus();
  const n = editor.value.length;
  editor.setSelectionRange(n, n);
  fInput.value = editor.value;
}

function sizeEditor() {
  editor.style.width = Math.max(S.meta.colw[S.editing.c - 1] + 1, measure(editor.value, null) + 24) + 'px';
}

async function commitEdit(move) {
  const ed = S.editing;
  if (!ed) return;
  const value = ed.mode === 'bar' ? fInput.value : editor.value;
  S.editing = null;
  editor.hidden = true;
  if (document.activeElement === editor || document.activeElement === fInput) clip.focus({ preventScroll: true });
  if (value !== ed.orig) {
    // direct tonen, daarna de echte waarde van de server
    const ch = chunkOf(ed.r);
    if (ch) {
      const row = ch.rows[ed.r] || (ch.rows[ed.r] = {});
      const prev = row[ed.c] || {};
      row[ed.c] = Object.assign({}, prev, { d: value, e: value, k: 's', st: 0 });
    }
    render(true);
    run(async () => {
      const res = await api('set', { sheet: S.sheet, cells: [{ r: ed.r, c: ed.c, v: value }] });
      if (res.errors && res.errors.length) toast(res.errors[0], true);
      afterMutation();
    });
  }
  if (move) moveSel(move[0], move[1]);
  else { render(true); updateFormulaBar(); }
}

function cancelEdit() {
  if (!S.editing) return;
  S.editing = null;
  editor.hidden = true;
  clip.focus({ preventScroll: true });
  updateFormulaBar();
}

function moveSel(dr, dc) {
  select(S.sel.ar + dr, S.sel.ac + dc, false);
}

editor.addEventListener('input', () => { fInput.value = editor.value; sizeEditor(); });
editor.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); commitEdit(e.shiftKey ? [-1, 0] : [1, 0]); }
  else if (e.key === 'Tab') { e.preventDefault(); commitEdit(e.shiftKey ? [0, -1] : [0, 1]); }
  else if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); }
  else if (S.editing && S.editing.mode === 'enter' && e.key.startsWith('Arrow') && !editor.value.startsWith('=')) {
    e.preventDefault();
    const d = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
    commitEdit(d);
  }
});
editor.addEventListener('blur', () => { if (S.editing && S.editing.mode !== 'bar') commitEdit(null); });

fInput.addEventListener('focus', () => {
  if (S.editing && S.editing.mode !== 'bar') return;
  if (!S.meta) return;
  const cell = getCell(S.sel.ar, S.sel.ac);
  if (cell && cell.h) return;
  S.editing = { r: S.sel.ar, c: S.sel.ac, orig: fInput.value, mode: 'bar' };
});
fInput.addEventListener('keydown', (e) => {
  if (!S.editing) return;
  if (e.key === 'Enter') { e.preventDefault(); commitEdit([1, 0]); }
  else if (e.key === 'Tab') { e.preventDefault(); commitEdit([0, 1]); }
  else if (e.key === 'Escape') { e.preventDefault(); fInput.value = S.editing.orig; cancelEdit(); }
});
fInput.addEventListener('blur', () => { if (S.editing && S.editing.mode === 'bar') commitEdit(null); });

/* ---------------------------------------------------------------- muis */

function cellFromEvent(e) {
  const td = e.target.closest('td[data-c]');
  if (!td) return null;
  const tr = td.parentElement;
  return { r: +tr.dataset.r, c: +td.dataset.c };
}

gridWrap.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  const rsz = e.target.closest('.rsz');
  if (rsz) { startResize(e, +rsz.dataset.c); return; }
  if (S.editing) commitEdit(null);
  const th = e.target.closest('th');
  const nr = S.meta.nrows, nc = S.meta.ncols;
  if (th && th.classList.contains('corner')) {
    S.sel = { ar: 1, ac: 1, fr: nr, fc: nc };
    render(true); updateFormulaBar(); updateStatus();
  } else if (th && th.classList.contains('ch')) {
    const c = +th.dataset.c;
    if (e.shiftKey) { S.sel.fc = c; S.sel.ar = 1; S.sel.fr = nr; } else S.sel = { ar: 1, ac: c, fr: nr, fc: c };
    S.drag = { kind: 'col' };
    render(true); updateFormulaBar(); updateStatus();
  } else if (th && th.classList.contains('rh')) {
    const r = +th.parentElement.dataset.r;
    if (e.shiftKey) { S.sel.fr = r; S.sel.ac = 1; S.sel.fc = nc; } else S.sel = { ar: r, ac: 1, fr: r, fc: nc };
    S.drag = { kind: 'row' };
    render(true); updateFormulaBar(); updateStatus();
  } else {
    const pos = cellFromEvent(e);
    if (!pos) return;
    select(pos.r, pos.c, e.shiftKey);
    S.drag = { kind: 'cell' };
  }
  e.preventDefault();
  clip.focus({ preventScroll: true });
});

gridWrap.addEventListener('mousemove', (e) => {
  if (!S.drag || !(e.buttons & 1)) { S.drag = null; return; }
  if (S.drag.kind === 'cell') {
    const pos = cellFromEvent(e);
    if (pos && (pos.r !== S.sel.fr || pos.c !== S.sel.fc)) { S.sel.fr = pos.r; S.sel.fc = pos.c; render(true); updateFormulaBar(); updateStatus(); }
  } else if (S.drag.kind === 'col') {
    const th = e.target.closest('th.ch');
    if (th && +th.dataset.c !== S.sel.fc) { S.sel.fc = +th.dataset.c; render(true); updateFormulaBar(); updateStatus(); }
  } else if (S.drag.kind === 'row') {
    const th = e.target.closest('th.rh');
    if (th) { const r = +th.parentElement.dataset.r; if (r !== S.sel.fr) { S.sel.fr = r; render(true); updateFormulaBar(); updateStatus(); } }
  }
});
window.addEventListener('mouseup', () => { S.drag = null; });

gridWrap.addEventListener('dblclick', (e) => {
  const pos = cellFromEvent(e);
  if (!pos) return;
  select(pos.r, pos.c, false);
  startEdit(null, 'edit');
});

gridWrap.addEventListener('scroll', () => {
  if (S.raf) return;
  S.raf = requestAnimationFrame(() => { S.raf = 0; render(false); });
});
window.addEventListener('resize', () => render(true));

function startResize(e, c) {
  e.preventDefault();
  e.stopPropagation();
  const startX = e.clientX, startW = S.meta.colw[c - 1];
  const col = grid.querySelectorAll('col')[c];
  let w = startW;
  const move = (ev) => {
    w = Math.max(20, Math.round(startW + ev.clientX - startX));
    if (col) col.style.width = w + 'px';
    grid.style.width = (RHW + S.colx[S.meta.ncols] - startW + w) + 'px';
  };
  const up = () => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
    if (w !== startW) {
      S.meta.colw[c - 1] = w;
      run(async () => { await api('colwidth', { sheet: S.sheet, c, px: w }); render(true); });
    }
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
}

/* ---------------------------------------------------------------- toetsenbord */

function isTyping() {
  const a = document.activeElement;
  if (!a || a === clip || a === document.body) return false;
  return a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA';
}

document.addEventListener('keydown', (e) => {
  const mod = IS_MAC ? e.metaKey : e.ctrlKey;
  const k = e.key.toLowerCase();
  if (mod && k === 's') { e.preventDefault(); if (S.editing) commitEdit(null); save(); return; }
  if (mod && k === 'o') { e.preventDefault(); openFile(); return; }
  if (!S.meta || !S.st || !S.st.loaded) return;
  if (mod && k === 'f') { e.preventDefault(); openSearch(); return; }
  if (e.key === 'Escape' && !$('#searchBar').hidden && document.activeElement.closest('#searchBar')) { closeSearch(); return; }
  if (S.editing || isTyping()) return;
  if (!$('#ctx').hidden && e.key === 'Escape') { hideCtx(); return; }

  if (mod) {
    if (k === 'z') { e.preventDefault(); run(async () => { await api(e.shiftKey ? 'redo' : 'undo', {}); afterMutation(); }); }
    else if (k === 'y') { e.preventDefault(); run(async () => { await api('redo', {}); afterMutation(); }); }
    else if (k === 'b') { e.preventDefault(); toggleFont('bold'); }
    else if (k === 'i') { e.preventDefault(); toggleFont('italic'); }
    else if (k === 'a') { e.preventDefault(); S.sel = { ar: 1, ac: 1, fr: S.meta.nrows, fc: S.meta.ncols }; render(true); updateFormulaBar(); updateStatus(); }
    else if (k === 'c' || k === 'x') { prepareCopy(k === 'x'); }
    else if (k === 'v') { clip.value = ''; clip.focus({ preventScroll: true }); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); jump(1, 0, e.shiftKey); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); jump(-1, 0, e.shiftKey); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); jump(0, 1, e.shiftKey); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); jump(0, -1, e.shiftKey); }
    return;
  }
  const nav = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
  if (nav) {
    e.preventDefault();
    if (e.shiftKey) select(S.sel.fr + nav[0], S.sel.fc + nav[1], true);
    else moveSel(nav[0], nav[1]);
    return;
  }
  if (e.key === 'Tab') { e.preventDefault(); moveSel(0, e.shiftKey ? -1 : 1); return; }
  if (e.key === 'Enter') { e.preventDefault(); startEdit(null, 'edit'); return; }
  if (e.key === 'F2') { e.preventDefault(); startEdit(null, 'edit'); return; }
  if (e.key === 'Backspace' || e.key === 'Delete') { e.preventDefault(); clearSelection(); return; }
  if (e.key === 'PageDown' || e.key === 'PageUp') {
    e.preventDefault();
    const n = Math.max(1, Math.floor(gridWrap.clientHeight / ROWH) - 1);
    moveSel(e.key === 'PageDown' ? n : -n, 0);
    return;
  }
  if (e.key === 'Home') { e.preventDefault(); select(S.sel.ar, 1, e.shiftKey); return; }
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) { e.preventDefault(); startEdit(e.key, 'enter'); }
});

function jump(dr, dc) {
  // naar de rand van het gevulde gebied, zoals ⌘-pijl in Excel
  let r = S.sel.ar, c = S.sel.ac;
  const filled = (rr, cc) => { const x = getCell(rr, cc); return !!(x && x.d); };
  const start = filled(r, c);
  const next = () => { r += dr; c += dc; };
  next();
  if (r < 1 || c < 1) { select(Math.max(1, r), Math.max(1, c), false); return; }
  if (start && filled(r, c)) {
    while (filled(r + dr, c + dc) && r + dr >= 1 && c + dc >= 1 && r + dr <= S.meta.nrows && c + dc <= S.meta.ncols) next();
  } else {
    while (!filled(r, c) && r + dr >= 1 && c + dc >= 1 && r <= S.meta.nrows && c <= S.meta.ncols) next();
  }
  select(Math.min(Math.max(1, r), S.meta.nrows), Math.min(Math.max(1, c), S.meta.ncols), false);
}

/* ---------------------------------------------------------------- klembord */

function tsvField(s) {
  return /[\t\n"]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function rangeTexts(b) {
  const missing = [];
  for (let r = b.r1; r <= b.r2; r += CHUNK) if (!S.cache.get(Math.floor((r - 1) / CHUNK))) missing.push(r);
  if (missing.length || !S.cache.get(Math.floor((b.r2 - 1) / CHUNK))) {
    // niet alles is geladen: synchroon ophalen zodat het kopiëren in dezelfde toetsaanslag kan
    const xhr = new XMLHttpRequest();
    xhr.open('GET', `/api/rows?sheet=${encodeURIComponent(S.sheet)}&start=${b.r1}&count=${Math.min(1000, b.r2 - b.r1 + 1)}`, false);
    xhr.setRequestHeader('X-Rekenblad', '1');
    xhr.setRequestHeader('X-Doc', DOC);
    xhr.send();
    const d = JSON.parse(xhr.responseText);
    return (r, c) => { const row = d.rows[r]; const x = row && row[c]; return x ? x.d || '' : ''; };
  }
  return (r, c) => { const x = getCell(r, c); return x ? x.d || '' : ''; };
}

function prepareCopy(cut) {
  const b = selBounds();
  b.r2 = Math.min(b.r2, b.r1 + 999);
  const get = rangeTexts(b);
  const lines = [];
  for (let r = b.r1; r <= b.r2; r++) {
    const cols = [];
    for (let c = b.c1; c <= b.c2; c++) cols.push(tsvField(get(r, c)));
    lines.push(cols.join('\t'));
  }
  clip.value = lines.join('\n');
  clip.focus({ preventScroll: true });
  clip.select();
  if (cut) setTimeout(clearSelection, 60);
}

function parseTsv(text) {
  const rows = [];
  let row = [], field = '', q = false;
  text = text.replace(/\r\n?/g, '\n');
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') q = false;
      else field += ch;
    } else if (ch === '"' && field === '') q = true;
    else if (ch === '\t') { row.push(field); field = ''; }
    else if (ch === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else field += ch;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  return rows;
}

clip.addEventListener('paste', (e) => {
  e.preventDefault();
  if (!S.meta) return;
  const text = (e.clipboardData || window.clipboardData).getData('text/plain');
  if (!text) return;
  const data = parseTsv(text);
  const b = selBounds();
  const cells = [];
  if (data.length === 1 && data[0].length === 1 && (b.r1 !== b.r2 || b.c1 !== b.c2)) {
    for (let r = b.r1; r <= Math.min(b.r2, b.r1 + 5000); r++) for (let c = b.c1; c <= b.c2; c++) cells.push({ r, c, v: data[0][0] });
  } else {
    data.forEach((row, i) => row.forEach((v, j) => cells.push({ r: b.r1 + i, c: b.c1 + j, v })));
  }
  if (cells.length > 200000) { toast('Dat is te veel om in één keer te plakken.', true); return; }
  const last = cells[cells.length - 1];
  S.sel = { ar: b.r1, ac: b.c1, fr: Math.max(b.r1, last.r), fc: Math.max(b.c1, last.c) };
  grow(last.r, last.c);
  run(async () => { await api('set', { sheet: S.sheet, cells }); afterMutation(); updateStatus(); });
});

function clearSelection() {
  const b = selBounds();
  run(async () => { await api('clear', Object.assign({ sheet: S.sheet }, b)); afterMutation(); });
}

/* ---------------------------------------------------------------- opmaak */

function applyFormat(props) {
  const b = selBounds();
  run(async () => { await api('format', Object.assign({ sheet: S.sheet, props }, b)); afterMutation(); });
}

function toggleFont(kind) {
  const st = styleOf(getCell(S.sel.ar, S.sel.ac), S.sel.ar);
  const on = kind === 'bold' ? !!(st && st.fw) : !!(st && st.fi);
  applyFormat({ [kind]: !on });
}

function buildPalette(el, colors, prop, noneLabel) {
  el.innerHTML = colors.map((c) => `<button data-c="${c}" style="background:#${c}" title="#${c}"></button>`).join('') +
    `<button class="none" data-c="">${noneLabel}</button>`;
  el.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    el.hidden = true;
    applyFormat({ [prop]: b.dataset.c || null });
    if (prop === 'fill' && b.dataset.c) $('#fillSwatch').style.stroke = '#' + b.dataset.c;
    if (prop === 'color' && b.dataset.c) $('#colorSwatch').style.background = '#' + b.dataset.c;
  });
}
buildPalette($('#fillMenu'), FILLS, 'fill', 'Geen vulkleur');
buildPalette($('#colorMenu'), COLORS, 'color', 'Automatisch');

function toggleMenu(menu) {
  const open = menu.hidden;
  document.querySelectorAll('.menu').forEach((m) => { m.hidden = true; });
  menu.hidden = !open;
}
$('#tFill').onclick = (e) => { e.stopPropagation(); toggleMenu($('#fillMenu')); };
$('#tColor').onclick = (e) => { e.stopPropagation(); toggleMenu($('#colorMenu')); };
$('#btnExport').onclick = (e) => { e.stopPropagation(); toggleMenu($('#exportMenu')); };
document.addEventListener('click', (e) => {
  if (!e.target.closest('.menu')) document.querySelectorAll('.menu').forEach((m) => { m.hidden = true; });
  if (!e.target.closest('#ctx')) hideCtx();
});

$('#tBold').onclick = () => toggleFont('bold');
$('#tItalic').onclick = () => toggleFont('italic');
document.querySelectorAll('[data-align]').forEach((b) => {
  b.onclick = () => {
    const st = styleOf(getCell(S.sel.ar, S.sel.ac), S.sel.ar);
    applyFormat({ align: st && st.a === b.dataset.align ? null : b.dataset.align });
  };
});
$('#tNumfmt').onchange = (e) => {
  if (!e.target.value) return;
  applyFormat({ numfmt: e.target.value });
  clip.focus({ preventScroll: true });
};
$('#tUndo').onclick = () => run(async () => { await api('undo', {}); afterMutation(); });
$('#tRedo').onclick = () => run(async () => { await api('redo', {}); afterMutation(); });

/* ---------------------------------------------------------------- rijen en kolommen */

function structural(kind, axis, where) {
  const b = selBounds();
  const count = axis === 'row' ? b.r2 - b.r1 + 1 : b.c2 - b.c1 + 1;
  if (count > 5000 && kind === 'insert') { toast('Selecteer minder rijen of kolommen.', true); return; }
  let at;
  if (kind === 'insert') at = axis === 'row' ? (where === 'after' ? b.r2 + 1 : b.r1) : (where === 'after' ? b.c2 + 1 : b.c1);
  else at = axis === 'row' ? b.r1 : b.c1;
  run(async () => {
    await api(kind, { sheet: S.sheet, axis, at, count });
    if (kind === 'delete') S.sel = { ar: S.sel.ar, ac: S.sel.ac, fr: S.sel.ar, fc: S.sel.ac };
    afterMutation();
  });
}
$('#tInsRow').onclick = () => structural('insert', 'row', 'before');
$('#tDelRow').onclick = () => structural('delete', 'row');
$('#tInsCol').onclick = () => structural('insert', 'col', 'before');
$('#tDelCol').onclick = () => structural('delete', 'col');

/* ---------------------------------------------------------------- contextmenu */

function showCtx(x, y, items) {
  const el = $('#ctx');
  el.innerHTML = items.map((it, i) => it === '-' ? '<hr>' : `<button data-i="${i}" class="${it.danger ? 'danger' : ''}">${esc(it.label)}</button>`).join('');
  el.hidden = false;
  const w = el.offsetWidth, h = el.offsetHeight;
  el.style.left = Math.min(x, window.innerWidth - w - 8) + 'px';
  el.style.top = Math.min(y, window.innerHeight - h - 8) + 'px';
  el.querySelectorAll('button').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); hideCtx(); items[+b.dataset.i].fn(); };
  });
}
function hideCtx() { $('#ctx').hidden = true; }

gridWrap.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  if (S.editing) commitEdit(null);
  const b0 = selBounds();
  const pos = cellFromEvent(e);
  if (pos && !(pos.r >= b0.r1 && pos.r <= b0.r2 && pos.c >= b0.c1 && pos.c <= b0.c2)) select(pos.r, pos.c, false);
  const b = selBounds();
  const nr = b.r2 - b.r1 + 1, nc = b.c2 - b.c1 + 1;
  const rw = nr === 1 ? 'rij' : `${nr} rijen`, kw = nc === 1 ? 'kolom' : `${nc} kolommen`;
  showCtx(e.clientX, e.clientY, [
    { label: `${cap(rw)} boven invoegen`, fn: () => structural('insert', 'row', 'before') },
    { label: `${cap(rw)} onder invoegen`, fn: () => structural('insert', 'row', 'after') },
    { label: `${cap(kw)} links invoegen`, fn: () => structural('insert', 'col', 'before') },
    { label: `${cap(kw)} rechts invoegen`, fn: () => structural('insert', 'col', 'after') },
    '-',
    { label: `${cap(rw)} verwijderen`, fn: () => structural('delete', 'row'), danger: true },
    { label: `${cap(kw)} verwijderen`, fn: () => structural('delete', 'col'), danger: true },
    '-',
    { label: 'Inhoud wissen', fn: clearSelection },
  ]);
});
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/* ---------------------------------------------------------------- bladen */

function renderTabs() {
  const el = $('#tabs');
  el.innerHTML = S.st.sheets.map((s, i) =>
    `<button class="tab${s.name === S.sheet ? ' on' : ''}${s.hidden ? ' hid' : ''}" data-i="${i}" title="${s.hidden ? 'Verborgen blad' : 'Dubbelklik om te hernoemen'}">${esc(s.name)}</button>`).join('');
  el.querySelectorAll('.tab').forEach((t) => {
    const name = S.st.sheets[+t.dataset.i].name;
    t.onclick = () => switchSheet(name);
    t.ondblclick = () => renameSheet(name);
    t.oncontextmenu = (e) => {
      e.preventDefault();
      showCtx(e.clientX, e.clientY - 90, [
        { label: 'Hernoemen', fn: () => renameSheet(name) },
        { label: 'Nieuw blad', fn: addSheet },
        '-',
        { label: 'Blad verwijderen', fn: () => deleteSheet(name), danger: true },
      ]);
    };
  });
}

function switchSheet(name) {
  if (S.editing) commitEdit(null);
  if (name === S.sheet) return;
  S.sheet = name;
  resetView();
  setMeta();
  renderTabs();
  render(true);
  updateFormulaBar();
  updateStatus();
}

function renameSheet(name) {
  const nw = prompt('Nieuwe naam voor het blad:', name);
  if (!nw || nw === name) return;
  run(async () => {
    const res = await api('sheet_rename', { old: name, new: nw });
    S.sheet = res.name;
    S.extra[res.name] = S.extra[name];
    setMeta(); renderTabs(); afterMutation();
  });
}

function addSheet() {
  run(async () => {
    const res = await api('sheet_add', {});
    switchSheet(res.name);
  });
}
$('#addSheet').onclick = addSheet;

function deleteSheet(name) {
  if (!confirm(`Blad '${name}' verwijderen? Dit kun je ongedaan maken met ⌘Z.`)) return;
  run(async () => {
    await api('sheet_delete', { name });
    if (S.sheet === name) { S.sheet = null; applyState(S.st); }
    afterMutation();
  });
}

/* ---------------------------------------------------------------- zoeken */

function openSearch() {
  $('#searchBar').hidden = false;
  const q = $('#sQuery');
  q.focus();
  q.select();
}
function closeSearch() {
  $('#searchBar').hidden = true;
  clip.focus({ preventScroll: true });
}

let searchTimer = 0;
function doSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => run(async () => {
    const q = $('#sQuery').value;
    if (!q) { S.search = { matches: [], idx: -1 }; $('#sCount').textContent = ''; return; }
    const sheet = $('#sAll').checked ? '' : S.sheet;
    const d = await api(`search?q=${encodeURIComponent(q)}&sheet=${encodeURIComponent(sheet)}&case=${$('#sCase').checked ? 1 : 0}`);
    S.search = { matches: d.matches, idx: -1 };
    $('#sCount').textContent = d.matches.length ? `${d.matches.length}${d.more ? '+' : ''} gevonden` : 'niets gevonden';
  }), 200);
}
function gotoMatch(dir) {
  const m = S.search.matches;
  if (!m.length) return;
  S.search.idx = (S.search.idx + dir + m.length) % m.length;
  const hit = m[S.search.idx];
  if (hit.sheet !== S.sheet) switchSheet(hit.sheet);
  select(hit.r, hit.c, false);
  $('#sCount').textContent = `${S.search.idx + 1} van ${m.length}`;
}
$('#sQuery').addEventListener('input', doSearch);
$('#sAll').addEventListener('change', doSearch);
$('#sCase').addEventListener('change', doSearch);
$('#sQuery').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); clearTimeout(searchTimer); gotoMatch(e.shiftKey ? -1 : 1); }
  if (e.key === 'Escape') closeSearch();
});
$('#sNext').onclick = () => gotoMatch(1);
$('#sPrev').onclick = () => gotoMatch(-1);
$('#sClose').onclick = closeSearch;
$('#tSearch').onclick = openSearch;
$('#sReplAll').onclick = () => run(async () => {
  const q = $('#sQuery').value;
  if (!q) { toast('Vul eerst in waar je naar zoekt.', true); return; }
  const res = await api('replace', { q, repl: $('#sRepl').value, sheet: $('#sAll').checked ? '' : S.sheet, case: $('#sCase').checked });
  toast(res.count === 1 ? '1 cel aangepast' : `${res.count} cellen aangepast`);
  afterMutation();
  doSearch();
});

/* ---------------------------------------------------------------- bestanden */

function confirmDiscard() {
  return !(S.st && S.st.loaded && S.st.dirty) ||
    confirm('Je hebt wijzigingen die nog niet zijn opgeslagen. Wil je die weggooien?');
}

function afterOpen() {
  S.sheet = null;
  S.extra = {};
  applyState(S.st);
  resetView();
  setMeta();
  render(true);
  updateFormulaBar();
  clip.focus({ preventScroll: true });
}

function openFile() {
  if (!confirmDiscard()) return;
  if (S.st && S.st.can_native) {
    run(async () => {
      const d = await api('open_dialog', {});
      if (!d.cancelled) afterOpen();
    });
  } else {
    $('#fileInput').click();
  }
}

async function upload(file) {
  if (!confirmDiscard()) return;
  await run(async () => {
    toast('Bezig met openen…');
    const res = await fetch('/api/upload', {
      method: 'POST',
      headers: { 'X-Rekenblad': '1', 'X-Doc': DOC, 'X-Filename': encodeURIComponent(file.name) },
      body: file,
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(d.error || 'Openen mislukt.');
    applyState(d.state);
    afterOpen();
    $('#toast').hidden = true;
  });
}

function newBook() {
  if (!confirmDiscard()) return;
  run(async () => { await api('new', {}); afterOpen(); });
}

function save() {
  if (!S.st || !S.st.loaded) return;
  run(async () => {
    const d = await api('save', { sheet: S.sheet });
    if (d.need_path) return saveAs();
    toast('Opgeslagen');
  });
}

function saveAs() {
  if (!S.st.can_native) { download('xlsx'); return; }
  run(async () => {
    const d = await api('save_as', { sheet: S.sheet });
    if (!d.cancelled) toast('Opgeslagen als ' + d.path);
  });
}

function download(fmt) {
  const a = document.createElement('a');
  a.href = `/api/download?doc=${DOC}&fmt=${fmt}&sheet=${encodeURIComponent(S.sheet)}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

$('#btnOpen').onclick = openFile;
$('#wOpen').onclick = openFile;
$('#btnNew').onclick = newBook;
$('#wNew').onclick = newBook;
$('#wBrowse').onclick = (e) => { e.preventDefault(); $('#fileInput').click(); };
$('#btnSave').onclick = save;
$('#btnSaveAs').onclick = saveAs;
document.querySelectorAll('[data-export]').forEach((b) => {
  b.onclick = () => { $('#exportMenu').hidden = true; download(b.dataset.export); };
});
$('#fileInput').onchange = (e) => {
  const f = e.target.files[0];
  e.target.value = '';
  if (f) upload(f);
};
$('#bannerClose').onclick = () => { $('#banner').hidden = true; };

let dragDepth = 0;
window.addEventListener('dragenter', (e) => {
  if (![...(e.dataTransfer.types || [])].includes('Files')) return;
  dragDepth++;
  $('#dropHint').hidden = false;
});
window.addEventListener('dragleave', () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $('#dropHint').hidden = true; });
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => {
  e.preventDefault();
  dragDepth = 0;
  $('#dropHint').hidden = true;
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  if (f) upload(f);
});

window.addEventListener('beforeunload', (e) => {
  if (S.st && S.st.loaded && S.st.dirty) { e.preventDefault(); e.returnValue = ''; }
});

/* Terug in dit tabblad? Dan kijken of het document intussen veranderd is
   (bijvoorbeeld omdat je hetzelfde bestand nog eens opende vanuit de Finder). */
async function refreshIfChanged() {
  if (!S.st || S.editing) return;
  const prev = S.st.version, prevFile = S.st.filename, prevLoaded = S.st.loaded;
  await api('state');
  if (!S.st.loaded) return;
  if (!prevLoaded || S.st.filename !== prevFile) afterOpen();
  else if (S.st.version !== prev) afterMutation();
}
window.addEventListener('focus', () => run(refreshIfChanged));
document.addEventListener('visibilitychange', () => { if (!document.hidden) run(refreshIfChanged); });

/* ---------------------------------------------------------------- start */

run(async () => {
  await api('state');
  if (S.st.loaded) afterOpen();
});
