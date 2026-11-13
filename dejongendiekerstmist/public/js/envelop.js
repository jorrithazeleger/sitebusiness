// De envelop met lakzegel: ingedrukt houden om het zegel te breken.
import { h, wait, reducedMotion, escapeHtml } from './util.js';
import { geluid } from './geluid.js';

function zegelPad() {
  let d = '';
  const n = 15;
  for (let i = 0; i <= n * 4; i++) {
    const a = (i / (n * 4)) * Math.PI * 2;
    const r = 45 + Math.sin(a * n) * 2.2 + Math.sin(a * 5 + 1) * 1.3;
    const x = 50 + Math.cos(a) * r, y = 50 + Math.sin(a) * r;
    d += (i ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2);
  }
  return d + 'Z';
}
const PAD = zegelPad();
let zegelId = 0;

export function zegelSvg(teken) {
  const id = 'zg' + (++zegelId);
  return `<svg viewBox="0 0 100 100" aria-hidden="true">
    <defs><radialGradient id="${id}" cx=".38" cy=".32" r=".75"><stop offset="0" stop-color="#d0443a"/><stop offset=".55" stop-color="#9a1c1c"/><stop offset="1" stop-color="#5c0d10"/></radialGradient></defs>
    <path d="${PAD}" fill="url(#${id})"/>
    <circle cx="50" cy="50" r="31" fill="none" stroke="#5c0d10" stroke-width="3" opacity=".55"/>
    <circle cx="50" cy="50" r="31" fill="none" stroke="#e46a5c" stroke-width="1" opacity=".35" transform="translate(-1 -1)"/>
    <text x="50" y="51" text-anchor="middle" dominant-baseline="central" class="zegel-teken zegel-licht">${escapeHtml(teken)}</text>
    <text x="50" y="50" text-anchor="middle" dominant-baseline="central" class="zegel-teken">${escapeHtml(teken)}</text>
    <ellipse cx="36" cy="30" rx="10" ry="5" fill="#fff" opacity=".18" transform="rotate(-30 36 30)"/>
  </svg>`;
}

/**
 * Maak een envelop. Geeft { el, open() } terug; open() wacht tot het zegel gebroken is
 * en speelt dan de openingsanimatie af.
 */
export function maakEnvelop({ adres = '', teken = 'G', stempel = '', hint = 'Houd het zegel ingedrukt' }) {
  const ring = `<svg class="zegel-ring" viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="48" pathLength="100"/></svg>`;
  const zegel = h('button', { class: 'lakzegel', type: 'button', 'aria-label': 'Breek het zegel (houd ingedrukt, of druk op Enter)', html: zegelSvg(teken) + ring });
  const hintEl = h('p', { class: 'env-hint' }, hint);
  const el = h('div', { class: 'envelop-wrap' },
    h('div', { class: 'envelop' },
      h('div', { class: 'env-achter' }),
      h('div', { class: 'env-vel' }, h('span'), h('span'), h('span')),
      h('div', { class: 'env-voor' },
        h('span', { class: 'env-adres' }, adres),
        h('span', { class: 'env-postzegel', html: '<span>1d</span>' }),
        stempel ? h('span', { class: 'env-stempel' }, stempel) : null,
      ),
      h('div', { class: 'env-flap' }),
      zegel,
    ),
    hintEl,
  );

  function wachtOpBreken() {
    return new Promise((resolve) => {
      const DUUR = reducedMotion() ? 250 : 800;
      let start = 0;
      let raf = 0;
      let p = 0;
      let klaar = false;
      const zet = (v) => { p = v; zegel.style.setProperty('--p', v.toFixed(3)); };
      const loop = (now) => {
        if (!start) start = now - p * DUUR;
        zet(Math.min(1, (now - start) / DUUR));
        if (p >= 1) return gedaan();
        raf = requestAnimationFrame(loop);
      };
      const begin = (e) => {
        if (klaar) return;
        e.preventDefault();
        geluid.wekOp();
        zegel.classList.add('houden');
        start = 0;
        raf = requestAnimationFrame(loop);
      };
      const stop = () => {
        if (klaar) return;
        cancelAnimationFrame(raf);
        zegel.classList.remove('houden');
        if (p > 0 && p < 1) {
          hintEl.classList.remove('wiebel'); void hintEl.offsetWidth; hintEl.classList.add('wiebel');
          const terug = () => { zet(Math.max(0, p - 0.08)); if (p > 0 && !zegel.classList.contains('houden')) requestAnimationFrame(terug); };
          requestAnimationFrame(terug);
        }
      };
      const gedaan = () => {
        klaar = true;
        cleanup();
        resolve();
      };
      const toets = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); zet(1); gedaan(); } };
      zegel.addEventListener('pointerdown', begin);
      zegel.addEventListener('pointerup', stop);
      zegel.addEventListener('pointerleave', stop);
      zegel.addEventListener('pointercancel', stop);
      zegel.addEventListener('keydown', toets);
      zegel.addEventListener('contextmenu', (e) => e.preventDefault());
      function cleanup() {
        zegel.removeEventListener('pointerdown', begin);
        zegel.removeEventListener('pointerup', stop);
        zegel.removeEventListener('pointerleave', stop);
        zegel.removeEventListener('pointercancel', stop);
        zegel.removeEventListener('keydown', toets);
      }
    });
  }

  async function breek() {
    geluid.krak();
    const env = el.querySelector('.envelop');
    const helften = ['links', 'rechts'].map((kant) => {
      const half = h('div', { class: `zegel-half zegel-${kant}`, html: zegelSvg(teken) });
      env.append(half);
      return half;
    });
    zegel.classList.add('gebroken');
    hintEl.classList.add('weg');
    await wait(60);
    helften.forEach((x) => x.classList.add('val'));
    await wait(280);
    env.classList.add('open');
    geluid.papier(0.5);
    await wait(reducedMotion() ? 100 : 700);
    env.classList.add('uit');
    geluid.papier(0.35);
    await wait(reducedMotion() ? 100 : 750);
  }

  return {
    el,
    async open() {
      zegel.focus({ preventScroll: true });
      await wachtOpBreken();
      await breek();
    },
  };
}
