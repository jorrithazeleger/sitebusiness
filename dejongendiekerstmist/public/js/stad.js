// De nachtelijke fabrieksstad als SVG: sterren, maan, schoorstenen met rook,
// rijtjeshuizen met warme ramen en een klokkentoren.
import { rng } from './util.js';

const W = 1600;
const H = 900;

function rookPluim(x, y, r, seed, kleur = 'url(#rook)') {
  let s = '';
  for (let i = 0; i < 4; i++) {
    s += `<circle class="rook" cx="${x}" cy="${y}" r="${r}" fill="${kleur}" style="animation-delay:${(-i * 2.2 - seed).toFixed(2)}s"/>`;
  }
  return `<g class="pluim">${s}</g>`;
}

function huizenrij(rand, { y, hoogte, kleur, raamKans, schaal, sneeuw }) {
  let x = -40;
  let out = '';
  let ramen = '';
  let rook = '';
  while (x < W + 40) {
    const b = (70 + rand() * 90) * schaal;
    const hh = (hoogte * (0.7 + rand() * 0.5));
    const top = y - hh;
    const dak = rand();
    let pad;
    if (dak < 0.45) {
      const piek = top - (25 + rand() * 35) * schaal;
      pad = `M${x} ${y} L${x} ${top} L${x + b / 2} ${piek} L${x + b} ${top} L${x + b} ${y}Z`;
      if (sneeuw) out += `<path d="M${x - 2} ${top + 2} L${x + b / 2} ${piek - 2} L${x + b + 2} ${top + 2} L${x + b - 6} ${top + 4} L${x + b / 2} ${piek + 5} L${x + 6} ${top + 4}Z" fill="#dfe6f2" opacity=".55"/>`;
    } else if (dak < 0.75) {
      const t2 = top - 18 * schaal;
      pad = `M${x} ${y} L${x} ${top} L${x + 8} ${t2} L${x + b - 8} ${t2} L${x + b} ${top} L${x + b} ${y}Z`;
      if (sneeuw) out += `<rect x="${x + 6}" y="${t2 - 3}" width="${b - 12}" height="5" rx="2" fill="#dfe6f2" opacity=".55"/>`;
    } else {
      pad = `M${x} ${y} L${x} ${top} L${x + b} ${top} L${x + b} ${y}Z`;
      if (sneeuw) out += `<rect x="${x - 2}" y="${top - 3}" width="${b + 4}" height="5" rx="2" fill="#dfe6f2" opacity=".5"/>`;
    }
    // schoorsteen
    if (rand() < 0.75) {
      const sx = x + b * (0.15 + rand() * 0.6);
      const sh = (20 + rand() * 25) * schaal;
      const sw = 12 * schaal;
      const sTop = top - sh - (dak < 0.45 ? 10 * schaal : 0);
      out += `<rect x="${sx}" y="${sTop}" width="${sw}" height="${sh + 30}" fill="${kleur}"/>`;
      out += `<rect x="${sx - 2}" y="${sTop}" width="${sw + 4}" height="${4 * schaal}" fill="${kleur}"/>`;
      if (rand() < 0.5) rook += rookPluim(sx + sw / 2, sTop - 4, 7 * schaal, rand() * 5, 'url(#rookLicht)');
    }
    out = `<path d="${pad}" fill="${kleur}"/>` + out;
    // ramen
    const kol = Math.max(1, Math.floor(b / (26 * schaal)));
    const rij = Math.max(1, Math.floor((hh - 20) / (34 * schaal)));
    const rw = 9 * schaal, rh = 14 * schaal;
    for (let c = 0; c < kol; c++) {
      for (let r = 0; r < rij; r++) {
        if (rand() > raamKans) continue;
        const rx = x + (b / kol) * (c + 0.5) - rw / 2;
        const ry = top + 14 * schaal + r * 34 * schaal;
        if (ry + rh > y - 4) continue;
        const flikker = rand() < 0.18 ? ' flikker' : '';
        const warm = rand() < 0.8 ? '#ffc96b' : '#ffe2a8';
        ramen += `<rect class="raam${flikker}" x="${rx.toFixed(1)}" y="${ry.toFixed(1)}" width="${rw}" height="${rh}" fill="${warm}" opacity="${(0.55 + rand() * 0.45).toFixed(2)}" style="animation-delay:${(-rand() * 9).toFixed(2)}s"/>`;
      }
    }
    x += b + rand() * 6;
  }
  return { gebouwen: out, ramen, rook };
}

function fabriek(x, y, schaal, kleur, rand) {
  const b = 260 * schaal;
  const hh = 110 * schaal;
  let s = '';
  // zaagtanddak
  let d = `M${x} ${y} L${x} ${y - hh}`;
  const tanden = 5;
  for (let i = 0; i < tanden; i++) {
    const tx = x + (b / tanden) * i;
    d += ` L${tx + (b / tanden) * 0.75} ${y - hh - 34 * schaal} L${tx + b / tanden} ${y - hh}`;
  }
  d += ` L${x + b} ${y}Z`;
  s += `<path d="${d}" fill="${kleur}"/>`;
  // hoge schoorstenen
  let rook = '';
  [[0.18, 330], [0.5, 380], [0.82, 300]].forEach(([p, hgt]) => {
    const cx = x + b * p;
    const top = y - hgt * schaal;
    const bw = 22 * schaal, tw = 15 * schaal;
    s += `<path d="M${cx - bw / 2} ${y - hh} L${cx - tw / 2} ${top} L${cx + tw / 2} ${top} L${cx + bw / 2} ${y - hh}Z" fill="${kleur}"/>`;
    s += `<rect x="${cx - tw / 2 - 3}" y="${top}" width="${tw + 6}" height="${6 * schaal}" fill="${kleur}"/>`;
    s += `<rect x="${cx - tw / 2}" y="${top + 16 * schaal}" width="${tw}" height="${3 * schaal}" fill="#3a2a22" opacity=".6"/>`;
    rook += rookPluim(cx, top - 6, 16 * schaal, rand() * 6);
  });
  // gloeiende ramen
  let ramen = '';
  for (let i = 0; i < 9; i++) {
    ramen += `<rect class="raam fabriekraam" x="${x + 14 * schaal + i * 27 * schaal}" y="${y - hh + 30 * schaal}" width="${14 * schaal}" height="${36 * schaal}" rx="${7 * schaal}" fill="#ff9b4a" opacity=".75" style="animation-delay:${(-i * 0.7).toFixed(1)}s"/>`;
  }
  return { s, rook, ramen };
}

function klokkentoren(x, y, schaal, kleur) {
  const b = 70 * schaal;
  const hh = 420 * schaal;
  const top = y - hh;
  let s = `<rect x="${x}" y="${top}" width="${b}" height="${hh}" fill="${kleur}"/>`;
  s += `<rect x="${x - 6 * schaal}" y="${top - 10 * schaal}" width="${b + 12 * schaal}" height="${110 * schaal}" fill="${kleur}"/>`;
  s += `<path d="M${x - 6 * schaal} ${top - 10 * schaal} L${x + b / 2} ${top - 120 * schaal} L${x + b + 6 * schaal} ${top - 10 * schaal}Z" fill="${kleur}"/>`;
  s += `<rect x="${x + b / 2 - 1.5}" y="${top - 150 * schaal}" width="3" height="${32 * schaal}" fill="${kleur}"/>`;
  const cx = x + b / 2, cy = top + 45 * schaal, r = 27 * schaal;
  s += `<circle cx="${cx}" cy="${cy}" r="${r + 10}" fill="url(#klokGloed)"/>`;
  s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#f6dc9c" opacity=".92"/>`;
  s += `<circle cx="${cx}" cy="${cy}" r="${r - 3}" fill="none" stroke="#6b4a1f" stroke-width="1.2" opacity=".6"/>`;
  s += `<line class="wijzer-uur" style="transform-box:view-box;transform-origin:${cx}px ${cy}px" x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - r * 0.5}" stroke="#2b1d12" stroke-width="2.4" stroke-linecap="round"/>`;
  s += `<line class="wijzer-min" style="transform-box:view-box;transform-origin:${cx}px ${cy}px" x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - r * 0.8}" stroke="#2b1d12" stroke-width="1.6" stroke-linecap="round"/>`;
  for (let i = 0; i < 3; i++) {
    s += `<rect class="raam" x="${x + b / 2 - 6 * schaal}" y="${top + (130 + i * 80) * schaal}" width="${12 * schaal}" height="${30 * schaal}" rx="${6 * schaal}" fill="#ffc96b" opacity="${0.4 + i * 0.15}"/>`;
  }
  return s;
}

function lantaarn(x, y, schaal) {
  const s = schaal;
  return `<g class="lantaarn">
    <circle cx="${x}" cy="${y - 150 * s}" r="${70 * s}" fill="url(#lantaarnGloed)" class="lantaarn-gloed"/>
    <rect x="${x - 3 * s}" y="${y - 140 * s}" width="${6 * s}" height="${140 * s}" fill="#07090f"/>
    <rect x="${x - 10 * s}" y="${y - 8 * s}" width="${20 * s}" height="${8 * s}" fill="#07090f"/>
    <path d="M${x - 12 * s} ${y - 140 * s} L${x - 9 * s} ${y - 166 * s} L${x + 9 * s} ${y - 166 * s} L${x + 12 * s} ${y - 140 * s}Z" fill="#ffd27a" opacity=".95"/>
    <path d="M${x - 15 * s} ${y - 166 * s} L${x} ${y - 180 * s} L${x + 15 * s} ${y - 166 * s}Z" fill="#07090f"/>
    <rect x="${x - 14 * s}" y="${y - 142 * s}" width="${28 * s}" height="${4 * s}" fill="#07090f"/>
    <path d="M${x - 15 * s} ${y - 167 * s} L${x} ${y - 181 * s} L${x + 15 * s} ${y - 167 * s} L${x + 9 * s} ${y - 168 * s} L${x} ${y - 176 * s} L${x - 9 * s} ${y - 168 * s}Z" fill="#e8eef8" opacity=".8"/>
  </g>`;
}

export function maakStad({ seed = 1843, lantaarns = true } = {}) {
  const rand = rng(seed);
  let sterren = '';
  for (let i = 0; i < 110; i++) {
    const x = rand() * W, y = rand() * H * 0.55;
    const r = rand() < 0.1 ? 1.8 : 0.5 + rand() * 1.1;
    sterren += `<circle class="ster" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(2)}" fill="#fff" style="animation-delay:${(-rand() * 6).toFixed(2)}s;animation-duration:${(3 + rand() * 5).toFixed(1)}s"/>`;
  }

  const ver = huizenrij(rand, { y: 760, hoogte: 150, kleur: '#151b30', raamKans: 0.25, schaal: 0.7, sneeuw: false });
  const fab1 = fabriek(140, 700, 1, '#121729', rand);
  const fab2 = fabriek(1150, 690, 0.85, '#121729', rand);
  const toren = klokkentoren(820, 770, 1, '#10152a');
  const midden = huizenrij(rand, { y: 830, hoogte: 190, kleur: '#0d1222', raamKans: 0.35, schaal: 1, sneeuw: true });
  const voor = huizenrij(rand, { y: 920, hoogte: 120, kleur: '#070a14', raamKans: 0.2, schaal: 1.35, sneeuw: true });

  return `<svg class="stad-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="lucht" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#03050c"/>
      <stop offset=".45" stop-color="#0b1330"/>
      <stop offset=".8" stop-color="#2a2140"/>
      <stop offset="1" stop-color="#4a2b33"/>
    </linearGradient>
    <radialGradient id="maanGloed"><stop offset="0" stop-color="#fff6dc" stop-opacity=".55"/><stop offset=".35" stop-color="#fff2cc" stop-opacity=".12"/><stop offset="1" stop-color="#fff2cc" stop-opacity="0"/></radialGradient>
    <radialGradient id="maan" cx=".4" cy=".38"><stop offset="0" stop-color="#fffaf0"/><stop offset=".7" stop-color="#f2e6c4"/><stop offset="1" stop-color="#d8c79c"/></radialGradient>
    <radialGradient id="rook"><stop offset="0" stop-color="#5a5a6e" stop-opacity=".55"/><stop offset="1" stop-color="#5a5a6e" stop-opacity="0"/></radialGradient>
    <radialGradient id="rookLicht"><stop offset="0" stop-color="#8a8ea6" stop-opacity=".35"/><stop offset="1" stop-color="#8a8ea6" stop-opacity="0"/></radialGradient>
    <radialGradient id="klokGloed"><stop offset="0" stop-color="#ffd98a" stop-opacity=".5"/><stop offset="1" stop-color="#ffd98a" stop-opacity="0"/></radialGradient>
    <radialGradient id="lantaarnGloed"><stop offset="0" stop-color="#ffd27a" stop-opacity=".55"/><stop offset=".4" stop-color="#ffb84d" stop-opacity=".15"/><stop offset="1" stop-color="#ffb84d" stop-opacity="0"/></radialGradient>
    <radialGradient id="fabriekGloed" cx=".5" cy="1"><stop offset="0" stop-color="#ff7a3a" stop-opacity=".35"/><stop offset="1" stop-color="#ff7a3a" stop-opacity="0"/></radialGradient>
    <linearGradient id="mist" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b2140" stop-opacity="0"/><stop offset="1" stop-color="#1b2140" stop-opacity=".7"/></linearGradient>
  </defs>
  <rect width="${W}" height="${H}" fill="url(#lucht)"/>
  <g class="sterren">${sterren}</g>
  <circle cx="1270" cy="170" r="190" fill="url(#maanGloed)"/>
  <circle cx="1270" cy="170" r="52" fill="url(#maan)"/>
  <circle cx="1255" cy="160" r="9" fill="#e3d4ac" opacity=".5"/><circle cx="1290" cy="185" r="6" fill="#e3d4ac" opacity=".45"/><circle cx="1278" cy="145" r="4" fill="#e3d4ac" opacity=".4"/>
  <ellipse cx="300" cy="720" rx="420" ry="160" fill="url(#fabriekGloed)"/>
  <ellipse cx="1260" cy="710" rx="380" ry="150" fill="url(#fabriekGloed)"/>
  <g class="laag-ver">${fab1.rook}${fab2.rook}${fab1.s}${fab2.s}${fab1.ramen}${fab2.ramen}${ver.gebouwen}${ver.ramen}</g>
  <g class="laag-toren">${toren}</g>
  <rect y="600" width="${W}" height="300" fill="url(#mist)"/>
  <g class="laag-midden">${midden.rook}${midden.gebouwen}${midden.ramen}</g>
  <g class="laag-voor">${voor.rook}${voor.gebouwen}${voor.ramen}</g>
  ${lantaarns ? `<g class="lantaarns">${lantaarn(120, 900, 1.1)}${lantaarn(1480, 900, 1.1)}</g>` : ''}
</svg>`;
}

/** Zet de wijzers van de klokkentoren op de echte tijd. */
export function zetKlok(root) {
  const nu = new Date();
  const uur = ((nu.getHours() % 12) + nu.getMinutes() / 60) * 30;
  const min = nu.getMinutes() * 6;
  root.querySelectorAll('.wijzer-uur').forEach((el) => { el.style.transform = `rotate(${uur}deg)`; });
  root.querySelectorAll('.wijzer-min').forEach((el) => { el.style.transform = `rotate(${min}deg)`; });
}
