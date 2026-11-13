// Gedeelde illustraties.

let n = 0;
const uid = (p) => `${p}${++n}`;

export function sleutelSvg() {
  const g = uid('sk');
  return `<svg class="sleutel-svg" viewBox="0 0 220 90" aria-hidden="true">
  <defs>
    <linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fbe7a6"/><stop offset=".45" stop-color="#d9a94e"/><stop offset=".55" stop-color="#b9842f"/><stop offset="1" stop-color="#f0cf7c"/>
    </linearGradient>
  </defs>
  <g fill="url(#${g})" stroke="#7a5418" stroke-width="2" stroke-linejoin="round">
    <path d="M45 13 C60 13 72 25 72 40 C72 47 70 52 66 57 L66 33 L66 57 C61 64 54 67 45 67 C30 67 18 55 18 40 C18 25 30 13 45 13Z M45 27 C38 27 32 33 32 40 C32 47 38 53 45 53 C52 53 58 47 58 40 C58 33 52 27 45 27Z" fill-rule="evenodd"/>
    <circle cx="45" cy="9" r="6"/><circle cx="45" cy="71" r="6"/><circle cx="14" cy="40" r="6"/>
    <rect x="70" y="35" width="128" height="10" rx="3"/>
    <rect x="82" y="31" width="8" height="18" rx="2"/>
    <path d="M168 45 L168 72 L178 72 L178 62 L186 62 L186 72 L198 72 L198 45Z"/>
  </g>
  <path d="M74 37 L196 37" stroke="#fff6d0" stroke-width="2" opacity=".6"/>
  <circle cx="38" cy="22" r="4" fill="#fff" opacity=".5"/>
</svg>`;
}

export function horlogeSvg() {
  const g = uid('hg');
  let streepjes = '';
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    const r1 = i % 3 === 0 ? 24 : 26.5;
    streepjes += `<line x1="${50 + Math.sin(a) * r1}" y1="${68 - Math.cos(a) * r1}" x2="${50 + Math.sin(a) * 29}" y2="${68 - Math.cos(a) * 29}" stroke="#3a2a1a" stroke-width="${i % 3 === 0 ? 2 : 1}"/>`;
  }
  const o = 'transform-box:view-box;transform-origin:50px 68px';
  return `<svg class="horloge-svg" viewBox="0 0 100 112" aria-hidden="true">
  <defs><linearGradient id="${g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fbe7a6"/><stop offset=".5" stop-color="#c8963f"/><stop offset="1" stop-color="#8a6123"/></linearGradient></defs>
  <circle cx="50" cy="10" r="7" fill="none" stroke="url(#${g})" stroke-width="3.5"/>
  <rect x="43" y="16" width="14" height="10" rx="2" fill="url(#${g})" stroke="#6b4a1a"/>
  <circle cx="50" cy="68" r="40" fill="url(#${g})" stroke="#6b4a1a" stroke-width="1.5"/>
  <circle cx="50" cy="68" r="35" fill="#8a6123" opacity=".5"/>
  <circle cx="50" cy="68" r="32" fill="#f8efd8"/>
  ${streepjes}
  <line class="h-uur" style="${o}" x1="50" y1="68" x2="50" y2="52" stroke="#2b1d12" stroke-width="3" stroke-linecap="round"/>
  <line class="h-min" style="${o}" x1="50" y1="68" x2="50" y2="44" stroke="#2b1d12" stroke-width="2" stroke-linecap="round"/>
  <line class="h-sec" style="${o}" x1="50" y1="72" x2="50" y2="42" stroke="#9b1f1f" stroke-width="1"/>
  <circle cx="50" cy="68" r="2.5" fill="#2b1d12"/>
  <path d="M24 46 A32 32 0 0 1 50 36" fill="none" stroke="#fff" stroke-width="3" opacity=".5" stroke-linecap="round"/>
</svg>`;
}

export function brievenbusSvg() {
  const g = uid('bb');
  return `<svg class="brievenbus-svg" viewBox="0 0 120 230" aria-hidden="true">
  <defs>
    <linearGradient id="${g}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5e0f12"/><stop offset=".35" stop-color="#b3262a"/><stop offset=".55" stop-color="#c8383a"/><stop offset="1" stop-color="#5e0f12"/></linearGradient>
  </defs>
  <path d="M14 62 C14 24 106 24 106 62Z" fill="url(#${g})" stroke="#3a0709" stroke-width="2"/>
  <path d="M30 40 C45 28 75 28 90 40" fill="none" stroke="#e8eef8" stroke-width="7" stroke-linecap="round" opacity=".85"/>
  <rect x="8" y="58" width="104" height="10" rx="3" fill="#7a1418" stroke="#3a0709" stroke-width="2"/>
  <rect x="16" y="68" width="88" height="140" fill="url(#${g})" stroke="#3a0709" stroke-width="2"/>
  <rect x="28" y="84" width="64" height="12" rx="3" fill="#1a0506"/>
  <rect x="24" y="80" width="72" height="5" rx="2" fill="#7a1418"/>
  <rect x="38" y="112" width="44" height="28" rx="3" fill="#f3e2b0" stroke="#7a5418"/>
  <text x="60" y="131" text-anchor="middle" class="bus-tekst">POST</text>
  <circle cx="60" cy="168" r="4" fill="#d4a64a"/>
  <rect x="10" y="204" width="100" height="18" rx="3" fill="#4a0b0e" stroke="#2a0406" stroke-width="2"/>
  <ellipse cx="60" cy="226" rx="62" ry="5" fill="#000" opacity=".35"/>
</svg>`;
}
