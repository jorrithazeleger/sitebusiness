// Kopen, de sleutelceremonie, een sleutel invoeren en 'over het verhaal'.
import { h, $, api, wait, geheugen, reducedMotion } from './util.js';
import { geluid } from './geluid.js';
import { sleutelSvg } from './svg.js';
import { gijsSvg } from './gijs.js';

export function modal({ klasse = '', label, inhoud, onSluit }) {
  const vorigeFocus = document.activeElement;
  const sluitKnop = h('button', { class: 'ikoon-knop modal-sluit', type: 'button', 'aria-label': 'Sluiten', html: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>' });
  const paneel = h('div', { class: `modal-paneel ${klasse}` }, sluitKnop, ...inhoud);
  const el = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': label }, h('div', { class: 'modal-achter' }), paneel);
  let resolveGesloten;
  const gesloten = new Promise((r) => { resolveGesloten = r; });
  let dicht = false;
  const sluit = (waarde) => {
    if (dicht) return;
    dicht = true;
    el.classList.remove('zichtbaar');
    document.removeEventListener('keydown', esc);
    setTimeout(() => el.remove(), 400);
    if (vorigeFocus && vorigeFocus.focus) vorigeFocus.focus({ preventScroll: true });
    if (onSluit) onSluit(waarde);
    resolveGesloten(waarde);
  };
  const esc = (e) => { if (e.key === 'Escape') sluit(); };
  sluitKnop.addEventListener('click', () => sluit());
  $('.modal-achter', el).addEventListener('click', () => sluit());
  document.addEventListener('keydown', esc);
  document.body.append(el);
  requestAnimationFrame(() => el.classList.add('zichtbaar'));
  setTimeout(() => (paneel.querySelector('input, .knop-goud') || sluitKnop).focus({ preventScroll: true }), 80);
  return { el, paneel, sluit, gesloten };
}

const HANGSLOT = `<svg class="hangslot" viewBox="0 0 120 150" aria-hidden="true">
  <defs><linearGradient id="hsG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fbe7a6"/><stop offset=".5" stop-color="#c8963f"/><stop offset="1" stop-color="#7a5418"/></linearGradient></defs>
  <path class="hangslot-beugel" d="M30 70 L30 42 C30 8 90 8 90 42 L90 70" fill="none" stroke="#9aa3b5" stroke-width="12" stroke-linecap="round"/>
  <rect x="14" y="62" width="92" height="78" rx="14" fill="url(#hsG)" stroke="#6b4a1a" stroke-width="2"/>
  <circle cx="60" cy="96" r="9" fill="#2b1d12"/><path d="M56 100 L64 100 L62 120 L58 120Z" fill="#2b1d12"/>
  <path d="M22 72 L98 72" stroke="#fff6d0" stroke-width="2" opacity=".5"/>
</svg>`;

function kopieer(tekst, knop) {
  const ok = () => { const oud = knop.textContent; knop.textContent = 'Gekopieerd!'; setTimeout(() => { knop.textContent = oud; }, 1800); };
  if (navigator.clipboard) navigator.clipboard.writeText(tekst).then(ok, () => {});
}

function sleutelKaart(code) {
  const knop = h('button', { class: 'knop knop-zacht', type: 'button' }, 'Kopieer');
  knop.addEventListener('click', () => kopieer(code, knop));
  return h('div', { class: 'sleutel-kaart' },
    h('span', { class: 'sleutel-kaart-label' }, 'Jouw persoonlijke sleutel'),
    h('span', { class: 'sleutel-kaart-code' }, code),
    knop);
}

export function maakWinkel({ staat, gijs, naGekocht }) {
  function kopen() {
    const s = staat();
    const email = s.mail ? h('input', { class: 'tekst-invoer', type: 'email', name: 'email', autocomplete: 'email', placeholder: 'je@email.nl (niet verplicht)', 'aria-label': 'E-mailadres, niet verplicht' }) : null;
    const knop = h('button', { class: 'knop knop-goud knop-groot', type: 'submit' }, `Koop de sleutel · ${s.prijs}`);
    const fout = h('p', { class: 'fout', role: 'alert' });
    const form = h('form', { class: 'winkel-form', onsubmit: async (e) => {
      e.preventDefault();
      fout.textContent = '';
      knop.disabled = true;
      knop.textContent = 'Even geduld...';
      geluid.klik();
      try {
        const { url } = await api('/api/afrekenen', { method: 'POST', body: { email: email ? email.value.trim() : '' } });
        window.location.href = url;
      } catch (err) {
        fout.textContent = err.message || 'Er ging iets mis. Probeer het nog eens.';
        knop.disabled = false;
        knop.textContent = `Koop de sleutel · ${s.prijs}`;
      }
    } },
    email ? h('label', { class: 'veld' }, h('span', {}, 'Stuur de sleutel ook naar mijn e-mail'), email) : null,
    knop, fout);

    modal({
      klasse: 'winkel', label: 'De sleutel van de kluis',
      inhoud: [
        h('div', { class: 'winkel-sleutel', 'aria-hidden': 'true' }, h('span', { class: 'kussen' }), h('span', { class: 'winkel-sleutel-svg', html: sleutelSvg() }), h('span', { class: 'glans' })),
        h('h2', {}, 'De sleutel van de kluis'),
        h('p', { class: 'winkel-intro' }, `Met deze sleutel lees je het hele verhaal van ${s.titel}. Elke nacht een nieuwe brief, tot en met kerstavond.`),
        h('ul', { class: 'winkel-lijst' },
          h('li', {}, `Alle ${s.totaal} brieven, ook de brieven die al bezorgd zijn`),
          h('li', {}, 'Lees op je telefoon, tablet en computer'),
          h('li', {}, 'Heerlijk om samen voor te lezen, met het hele gezin'),
          h('li', {}, 'Eenmalig betalen, geen abonnement')),
        h('p', { class: 'winkel-prijs' }, s.prijs),
        form,
        h('p', { class: 'winkel-klein' }, 'Veilig betalen met iDEAL, creditcard of Apple Pay via Mollie.'),
        s.betalen === 'test' ? h('p', { class: 'winkel-test' }, 'Testmodus: er wordt niet echt betaald.') : null,
        s.betalen === 'uit' ? h('p', { class: 'winkel-test' }, 'Betalen is nog niet geopend. Kom binnenkort terug!') : null,
      ],
    });
  }

  async function bedankt(id) {
    const status = h('p', { class: 'ceremonie-status' }, 'Gijs telt de munten na...');
    const podium = h('div', { class: 'ceremonie-podium' },
      h('div', { class: 'ceremonie-gijs', html: gijsSvg() }),
      h('div', { class: 'munten', 'aria-hidden': 'true' }, h('span'), h('span'), h('span')));
    const inhoud = h('div', { class: 'ceremonie-inhoud' });
    const m = modal({ klasse: 'ceremonie', label: 'Je bestelling', inhoud: [podium, status, inhoud] });

    let resultaat = null;
    for (let i = 0; i < 40 && !resultaat; i++) {
      try {
        const r = await api(`/api/bestelling/${encodeURIComponent(id)}`);
        if (r.status === 'paid') resultaat = r;
        else if (['canceled', 'expired', 'failed'].includes(r.status)) resultaat = r;
      } catch (e) {
        if (e.status === 404) { resultaat = { status: 'onbekend' }; break; }
      }
      if (!resultaat) await wait(1500);
    }
    history.replaceState(null, '', '/postkantoor');

    if (!resultaat || resultaat.status !== 'paid') {
      podium.classList.add('stil');
      const mislukt = resultaat && resultaat.status !== 'onbekend';
      status.textContent = !resultaat
        ? 'De betaling is nog niet bevestigd. Ververs de pagina over een minuutje.'
        : mislukt ? 'De betaling is niet gelukt. Geen zorgen, er is niets afgeschreven.' : 'Deze bestelling ken ik niet.';
      inhoud.append(h('div', { class: 'knoppen-rij' },
        mislukt ? h('button', { class: 'knop knop-goud', type: 'button', onclick: () => { m.sluit(); kopen(); } }, 'Opnieuw proberen') : null,
        h('button', { class: 'knop knop-zacht', type: 'button', onclick: () => m.sluit() }, 'Terug naar het postkantoor')));
      return;
    }

    geheugen.set('sleutel', resultaat.sleutel);
    podium.innerHTML = '';
    const slot = h('div', { class: 'ceremonie-slot', html: HANGSLOT });
    const sleutel = h('div', { class: 'ceremonie-sleutel', html: sleutelSvg() });
    podium.append(h('div', { class: 'ceremonie-gloed' }), slot, sleutel);
    status.textContent = '';
    await wait(reducedMotion() ? 50 : 900);
    podium.classList.add('steek');
    geluid.klik();
    await wait(reducedMotion() ? 50 : 900);
    podium.classList.add('open');
    geluid.klik(); geluid.bel(1046.5);
    setTimeout(() => geluid.muziekdoos('kort'), 400);
    await wait(reducedMotion() ? 50 : 900);
    status.textContent = 'Het hele verhaal is van jou!';
    status.classList.add('feest');
    inhoud.append(
      sleutelKaart(resultaat.sleutel),
      h('p', { class: 'klein' }, resultaat.email
        ? `Bewaar deze sleutel goed. We hebben hem ook naar ${resultaat.email} gestuurd.`
        : 'Bewaar deze sleutel goed, bijvoorbeeld met een foto. Hiermee open je de brieven ook op je andere apparaten.'),
      h('button', { class: 'knop knop-goud', type: 'button', onclick: () => m.sluit('klaar') }, 'Naar het postkantoor'));
    await m.gesloten;
    naGekocht();
  }

  function formatteer(v) {
    const raw = v.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12);
    return raw.match(/.{1,4}/g)?.join('-') || '';
  }

  function sleutel(modus = 'invoeren', code = '') {
    const s = staat();
    if (modus === 'tonen') {
      const mijn = geheugen.get('sleutel', '');
      const link = `${location.origin}/sleutel?code=${encodeURIComponent(mijn)}`;
      const linkKnop = h('button', { class: 'knop knop-zacht', type: 'button' }, 'Kopieer link voor een ander apparaat');
      linkKnop.addEventListener('click', () => kopieer(link, linkKnop));
      const m = modal({
        klasse: 'sleutel-modal', label: 'Jouw sleutel',
        inhoud: [
          h('div', { class: 'modal-sleutel', html: sleutelSvg(), 'aria-hidden': 'true' }),
          h('h2', {}, 'Jouw sleutel'),
          sleutelKaart(mijn),
          h('p', { class: 'klein' }, 'Open je de brieven op een ander apparaat? Vul daar deze sleutel in, of open de link.'),
          linkKnop,
          h('button', { class: 'link', type: 'button', onclick: async () => {
            await api('/api/sleutel', { method: 'DELETE' }).catch(() => {});
            geheugen.del('sleutel');
            m.sluit();
            naGekocht();
          } }, 'Sleutel van dit apparaat verwijderen'),
        ],
      });
      return;
    }

    const input = h('input', {
      class: 'sleutel-invoer', type: 'text', name: 'sleutel', autocomplete: 'off', autocapitalize: 'characters',
      spellcheck: 'false', placeholder: 'ABCD-EFGH-JKMN', maxlength: '14', 'aria-label': 'Je sleutel', value: formatteer(code),
    });
    input.addEventListener('input', () => { input.value = formatteer(input.value); });
    const fout = h('p', { class: 'fout', role: 'alert' });
    const knop = h('button', { class: 'knop knop-goud', type: 'submit' }, 'Open de kluis');
    const form = h('form', { class: 'sleutel-form' }, input, knop, fout);
    const m = modal({
      klasse: 'sleutel-modal', label: 'Voer je sleutel in',
      inhoud: [
        h('div', { class: 'modal-sleutel', html: sleutelSvg(), 'aria-hidden': 'true' }),
        h('h2', {}, 'Voer je sleutel in'),
        h('p', {}, 'Heb je het verhaal al gekocht op een ander apparaat, of kreeg je een sleutel cadeau? Vul hem hier in.'),
        form,
        s.contact ? h('p', { class: 'klein' }, 'Sleutel kwijt? Mail naar ', h('a', { href: `mailto:${s.contact}` }, s.contact), ' met de datum van je aankoop.') : null,
      ],
    });
    const probeer = async () => {
      fout.textContent = '';
      knop.disabled = true;
      try {
        const r = await api('/api/sleutel', { method: 'POST', body: { code: input.value } });
        geheugen.set('sleutel', r.sleutel);
        geluid.klik(); geluid.bel(1046.5);
        m.sluit('ok');
        naGekocht();
      } catch (err) {
        fout.textContent = err.message;
        input.classList.remove('wiebel'); void input.offsetWidth; input.classList.add('wiebel');
        knop.disabled = false;
      }
    };
    form.addEventListener('submit', (e) => { e.preventDefault(); probeer(); });
    if (code) probeer();
  }

  function over() {
    const s = staat();
    modal({
      klasse: 'over', label: 'Over het verhaal',
      inhoud: [
        h('h2', {}, s.titel),
        h('p', { class: 'over-sub' }, `${s.ondertitel}, door ${s.auteur}`),
        h('h3', {}, 'Over het verhaal'), h('p', {}, s.overVerhaal),
        h('h3', {}, `Over ${s.auteur}`), h('p', {}, s.overAuteur),
        h('h3', {}, 'Privacy'),
        h('p', {}, 'Deze site gebruikt geen trackers en geen advertenties. Er wordt alleen een functioneel cookie geplaatst om je sleutel te onthouden. Je naam en welke brieven je las, blijven op je eigen apparaat.'),
        s.contact ? h('p', {}, 'Vragen? Mail naar ', h('a', { href: `mailto:${s.contact}` }, s.contact), '.') : null,
      ],
    });
  }

  return { kopen, bedankt, sleutel, over };
}
