import { readFileSync, statSync, existsSync } from 'node:fs';
import path from 'node:path';

// Brieven staan als tekstbestanden in content/brieven/01.md t/m 24.md.
// Bovenaan staat een kopje tussen --- regels met gegevens over de brief.

const cache = new Map();

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function inline(s) {
  return escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, '$1<em>$2</em>')
    .replace(/(^|\W)_(?!\s)(.+?)_(?=\W|$)/g, '$1<em>$2</em>')
    .replace(/ -- /g, ' &ndash; ');
}

export function parseFrontmatter(text) {
  const src = text.replace(/^﻿/, '').replace(/\r\n/g, '\n');
  const m = src.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!m) return { meta: {}, body: src };
  const meta = {};
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^([\w-]+)\s*:\s*(.*)$/);
    if (kv) meta[kv[1].toLowerCase()] = kv[2].trim().replace(/^["']|["']$/g, '');
  }
  return { meta, body: src.slice(m[0].length) };
}

export function renderBody(body) {
  const blocks = body.trim().split(/\n\s*\n/);
  const html = [];
  for (const raw of blocks) {
    const block = raw.trim();
    if (!block) continue;
    if (/^(\*\s*){3,}$|^-{3,}$|^~{3,}$/.test(block)) {
      html.push('<p class="sep" aria-hidden="true">&#10086;</p>');
    } else if (block.startsWith('## ')) {
      html.push(`<h3>${inline(block.slice(3))}</h3>`);
    } else if (block.split('\n').every((l) => l.startsWith('>'))) {
      const inner = block.split('\n').map((l) => l.replace(/^>\s?/, '')).join(' ');
      html.push(`<blockquote>${inline(inner)}</blockquote>`);
    } else {
      html.push(`<p>${block.split('\n').map(inline).join('<br>')}</p>`);
    }
  }
  return html.join('\n');
}

function load(file) {
  if (!existsSync(file)) return null;
  const { mtimeMs } = statSync(file);
  const hit = cache.get(file);
  if (hit && hit.mtimeMs === mtimeMs) return hit.letter;
  const { meta, body } = parseFrontmatter(readFileSync(file, 'utf8'));
  const letter = {
    titel: meta.titel || '',
    plaats: meta.plaats || '',
    datum: meta.datum || '',
    aanhef: meta.aanhef || '',
    groet: meta.groet || '',
    ondertekening: meta.ondertekening || '',
    naschrift: meta.naschrift || '',
    html: renderBody(body),
  };
  cache.set(file, { mtimeMs, letter });
  return letter;
}

export function loadLetter(contentDir, n) {
  return load(path.join(contentDir, 'brieven', String(n).padStart(2, '0') + '.md'));
}

export function loadWelcome(contentDir) {
  return load(path.join(contentDir, 'welkom.md'));
}

export function loadStory(contentDir) {
  const file = path.join(contentDir, 'verhaal.json');
  return JSON.parse(readFileSync(file, 'utf8'));
}
