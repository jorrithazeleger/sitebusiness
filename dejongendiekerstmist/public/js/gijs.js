// Grote Gijs: de postmuis die je door het verhaal gidst.
import { h, wait, reducedMotion } from './util.js';
import { geluid } from './geluid.js';

export const GIJS_SVG = `
<svg class="gijs-svg" viewBox="0 0 200 240" aria-hidden="true" focusable="false">
  <defs>
    <radialGradient id="gVacht" cx=".45" cy=".35" r=".8"><stop offset="0" stop-color="#a4978a"/><stop offset="1" stop-color="#7e7166"/></radialGradient>
    <radialGradient id="gBuik" cx=".5" cy=".4"><stop offset="0" stop-color="#f1e6d6"/><stop offset="1" stop-color="#d9c9b5"/></radialGradient>
    <radialGradient id="gOor" cx=".5" cy=".55"><stop offset="0" stop-color="#f3b9b4"/><stop offset="1" stop-color="#d88f8c"/></radialGradient>
    <linearGradient id="gPet" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b3a66"/><stop offset="1" stop-color="#18213f"/></linearGradient>
  </defs>
  <path class="g-staart" d="M138 214 C186 228 199 186 178 165 C166 153 151 161 159 174" fill="none" stroke="#c99a92" stroke-width="5" stroke-linecap="round"/>
  <ellipse cx="100" cy="182" rx="50" ry="47" fill="url(#gVacht)" stroke="#4d4239" stroke-width="2"/>
  <ellipse cx="100" cy="192" rx="32" ry="32" fill="url(#gBuik)"/>
  <ellipse cx="76" cy="228" rx="15" ry="7" fill="#e7aea3" stroke="#4d4239" stroke-width="1.5"/>
  <ellipse cx="124" cy="228" rx="15" ry="7" fill="#e7aea3" stroke="#4d4239" stroke-width="1.5"/>
  <g class="g-brief">
    <rect x="63" y="166" width="74" height="47" rx="3" fill="#f3e7cb" stroke="#a88a5a" stroke-width="1.6"/>
    <path d="M63 167 L100 192 L137 167" fill="none" stroke="#a88a5a" stroke-width="1.4"/>
    <circle cx="100" cy="191" r="7" fill="#9b1f1f"/><circle cx="98" cy="189" r="2.2" fill="#d4504a" opacity=".7"/>
  </g>
  <path d="M74 146 Q58 160 64 180" fill="none" stroke="#86796d" stroke-width="12" stroke-linecap="round"/>
  <ellipse cx="65" cy="182" rx="7" ry="6" fill="#e7aea3" stroke="#4d4239" stroke-width="1.3"/>
  <g class="g-arm-r">
    <path d="M126 146 Q142 160 136 180" fill="none" stroke="#86796d" stroke-width="12" stroke-linecap="round"/>
    <ellipse cx="135" cy="182" rx="7" ry="6" fill="#e7aea3" stroke="#4d4239" stroke-width="1.3"/>
  </g>
  <path d="M56 131 Q100 151 144 131 Q148 140 144 148 Q100 168 56 148 Q52 140 56 131Z" fill="#a3262a" stroke="#5e1316" stroke-width="1.5"/>
  <path d="M66 137 Q100 154 134 137 M66 143 Q100 160 134 143" fill="none" stroke="#c9463f" stroke-width="1.4" opacity=".7"/>
  <path class="g-sjaal" d="M114 150 L133 147 L134 196 L115 197Z" fill="#a3262a" stroke="#5e1316" stroke-width="1.5"/>
  <path class="g-sjaal" d="M117 197 L117 205 M121 197 L121 206 M125 197 L125 205 M129 197 L129 206 M132 196 L132 204" stroke="#a3262a" stroke-width="2" stroke-linecap="round"/>
  <g class="g-hoofd">
    <g class="g-oor-l"><circle cx="50" cy="60" r="30" fill="url(#gVacht)" stroke="#4d4239" stroke-width="2"/><circle cx="52" cy="62" r="19" fill="url(#gOor)"/></g>
    <g class="g-oor-r"><circle cx="150" cy="60" r="30" fill="url(#gVacht)" stroke="#4d4239" stroke-width="2"/><circle cx="148" cy="62" r="19" fill="url(#gOor)"/></g>
    <ellipse cx="100" cy="100" rx="50" ry="42" fill="url(#gVacht)" stroke="#4d4239" stroke-width="2"/>
    <ellipse cx="72" cy="114" rx="9" ry="6" fill="#e59a98" opacity=".35"/>
    <ellipse cx="128" cy="114" rx="9" ry="6" fill="#e59a98" opacity=".35"/>
    <ellipse cx="100" cy="121" rx="22" ry="15" fill="#dccdba"/>
    <g class="g-snor" stroke="#4f433a" stroke-width="1.3" stroke-linecap="round">
      <path d="M84 121 L50 113 M84 124 L48 124 M85 127 L52 135"/>
      <path d="M116 121 L150 113 M116 124 L152 124 M115 127 L148 135"/>
    </g>
    <ellipse cx="100" cy="112" rx="8" ry="6" fill="#d9707b"/>
    <ellipse cx="97.5" cy="110" rx="2.6" ry="1.6" fill="#fff" opacity=".7"/>
    <path class="g-mond" d="M93 126 Q100 132 107 126" fill="none" stroke="#4a3b33" stroke-width="2" stroke-linecap="round"/>
    <ellipse class="g-mond-open" cx="100" cy="128" rx="5" ry="4.5" fill="#5b2626"/>
    <circle cx="80" cy="97" r="8" fill="#1b1410"/><circle cx="83" cy="94" r="2.7" fill="#fff"/>
    <circle cx="120" cy="97" r="8" fill="#1b1410"/><circle cx="123" cy="94" r="2.7" fill="#fff"/>
    <ellipse class="g-ooglid" cx="80" cy="97" rx="10" ry="10" fill="#958879"/>
    <ellipse class="g-ooglid" cx="120" cy="97" rx="10" ry="10" fill="#958879"/>
    <g fill="none" stroke="#d4a64a" stroke-width="2.2">
      <circle cx="80" cy="97" r="13" fill="rgba(255,255,255,.12)"/>
      <circle cx="120" cy="97" r="13" fill="rgba(255,255,255,.12)"/>
      <path d="M93 95 Q100 90 107 95"/><path d="M67 95 L54 88 M133 95 L146 88"/>
    </g>
    <g class="g-pet" transform="rotate(-9 100 62) translate(0 -8)">
      <path d="M64 66 C64 36 136 36 136 66 L132 78 C112 72 88 72 68 78Z" fill="url(#gPet)" stroke="#0c1124" stroke-width="1.5"/>
      <path d="M68 73 C88 67 112 67 132 73 L131 80 C112 74 88 74 69 80Z" fill="#d4a64a"/>
      <path d="M65 79 C88 73 112 73 135 79 C128 90 72 90 65 79Z" fill="#0f1630"/>
      <circle cx="100" cy="57" r="6" fill="#d4a64a"/><path d="M97 57 L100 53 L103 57 L100 61Z" fill="#8a6420"/>
    </g>
  </g>
</svg>`;

/**
 * Maak een Gijs met tekstballon.
 * plaats: 'hoek' (vast rechtsonder) of 'podium' (groot, in een scène)
 */
let teller = 0;
export function gijsSvg() {
  const uid = ++teller;
  return GIJS_SVG.replace(/(id="|url\(#)g/g, `$1g${uid}`);
}

export function maakGijs(container, { plaats = 'hoek', onKlik } = {}) {
  const figuur = h('button', {
    class: 'gijs-figuur', type: 'button', 'aria-label': 'Grote Gijs, je gids. Tik voor een tip.', html: gijsSvg(),
  });
  const tekst = h('div', { class: 'bubbel-tekst', 'aria-live': 'polite' });
  const extra = h('div', { class: 'bubbel-extra' });
  const knoppen = h('div', { class: 'bubbel-knoppen' });
  const sluit = h('button', { class: 'bubbel-sluit', type: 'button', 'aria-label': 'Sluiten', html: '&times;' });
  const bubbel = h('div', { class: 'bubbel', role: 'dialog', 'aria-label': 'Grote Gijs zegt' }, sluit, tekst, extra, knoppen);
  const root = h('div', { class: `gijs gijs-${plaats}` }, bubbel, figuur);
  container.append(root);

  let token = 0;
  let typing = null;
  let hideTimer = null;

  // af en toe met de oren of staart wiebelen
  const idle = setInterval(() => {
    if (reducedMotion() || document.hidden) return;
    const keus = ['oor', 'staart', 'snuffel'][Math.floor(Math.random() * 3)];
    root.classList.add('idle-' + keus);
    setTimeout(() => root.classList.remove('idle-' + keus), 1200);
  }, 4200);

  figuur.addEventListener('click', () => {
    geluid.wekOp();
    if (onKlik) onKlik();
  });

  sluit.addEventListener('click', () => api.stil());
  tekst.addEventListener('click', () => { if (typing) typing.skip(); });

  function typ(str, myToken) {
    return new Promise((resolve) => {
      tekst.innerHTML = '';
      const html = str;
      // tekst met eenvoudige <em>/<strong> opmaak: zet tekst op volgorde neer
      const tmp = document.createElement('div');
      tmp.innerHTML = html;
      const doel = tekst;
      const delen = [];
      (function walk(node, parent) {
        for (const c of node.childNodes) {
          if (c.nodeType === 3) delen.push({ parent, text: c.textContent });
          else {
            const clone = c.cloneNode(false);
            delen.push({ parent, el: clone });
            walk(c, clone);
          }
        }
      })(tmp, doel);
      let skip = false;
      typing = { skip: () => { skip = true; } };
      root.classList.add('praat');
      const snel = reducedMotion();
      (async () => {
        for (const d of delen) {
          if (d.el) { d.parent.append(d.el); continue; }
          const node = document.createTextNode('');
          d.parent.append(node);
          for (const ch of d.text) {
            if (myToken !== token) return resolve(false);
            node.textContent += ch;
            if (!skip && !snel) await wait(/[.,!?:]/.test(ch) ? 120 : 18);
          }
        }
        root.classList.remove('praat');
        typing = null;
        resolve(true);
      })();
    });
  }

  const api = {
    root,
    figuur,
    bubbel,

    /**
     * Laat Gijs iets zeggen. Opties:
     *  knoppen: [{ label, waarde, hoofd }]  -> resolve met waarde
     *  extra: Node die onder de tekst komt (bijv. invoerveld)
     *  vanzelfWeg: ms waarna de ballon verdwijnt (zonder knoppen)
     */
    async zeg(html, { knoppen: keuzes = [], extra: extraNode = null, vanzelfWeg = 0, piep = true } = {}) {
      const myToken = ++token;
      clearTimeout(hideTimer);
      knoppen.innerHTML = '';
      extra.innerHTML = '';
      extra.hidden = true;
      bubbel.classList.add('open');
      root.classList.remove('hop'); void root.offsetWidth; root.classList.add('hop');
      if (piep) geluid.piep();
      const klaar = await typ(html, myToken);
      if (!klaar || myToken !== token) return null;
      if (extraNode) { extra.append(extraNode); extra.hidden = false; }
      if (!keuzes.length) {
        if (vanzelfWeg) hideTimer = setTimeout(() => { if (myToken === token) api.stil(); }, vanzelfWeg);
        return true;
      }
      return new Promise((resolve) => {
        keuzes.forEach((k, i) => {
          const b = h('button', {
            type: 'button', class: 'knop ' + (k.hoofd ? 'knop-goud' : 'knop-zacht'),
            style: { animationDelay: `${i * 80}ms` },
            onclick: () => { geluid.klik(); resolve(k.waarde); },
          }, k.label);
          knoppen.append(b);
        });
        const eerste = knoppen.querySelector('.knop-goud') || knoppen.querySelector('button');
        if (eerste && plaats === 'podium') setTimeout(() => eerste.focus({ preventScroll: true }), 50);
        api._annuleer = () => resolve(null);
      });
    },

    stil() {
      token++;
      clearTimeout(hideTimer);
      bubbel.classList.remove('open');
      root.classList.remove('praat');
      if (api._annuleer) { api._annuleer(); api._annuleer = null; }
    },

    zwaai() {
      root.classList.remove('zwaai'); void root.offsetWidth; root.classList.add('zwaai');
      setTimeout(() => root.classList.remove('zwaai'), 1800);
    },

    toon() { root.classList.remove('weg'); },
    verberg() { api.stil(); root.classList.add('weg'); },
    vernietig() { clearInterval(idle); root.remove(); },
  };
  return api;
}
