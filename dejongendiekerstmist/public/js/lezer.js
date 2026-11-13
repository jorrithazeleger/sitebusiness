// De lezer: envelop openen, brief op perkament lezen, bladeren.
import { h, $, api, wait, roman, datumTekst, nachtenTot, nachtenWoord, geheugen, escapeHtml, reducedMotion } from './util.js';
import { maakEnvelop } from './envelop.js';
import { geluid } from './geluid.js';
import { gijsSvg } from './gijs.js';

const GROOTTES = ['1.02rem', '1.12rem', '1.24rem', '1.38rem', '1.54rem'];

export function maakLezer({ staat, naam, onSluit, onKopen, onNaar }) {
  let overlay = null;
  let huidig = null;
  let sluitResolve = null;
  let vorigeFocus = null;

  function gelezen() { return geheugen.get('gelezen', []); }
  function markeer(n) {
    const g = new Set(gelezen());
    g.add(n);
    geheugen.set('gelezen', [...g]);
  }

  function vul(s) {
    const nm = naam() || 'reiziger';
    return String(s || '').replaceAll('{naam}', nm);
  }

  function bouwOverlay(label) {
    vorigeFocus = document.activeElement;
    overlay = h('div', { class: 'lezer', role: 'dialog', 'aria-modal': 'true', 'aria-label': label },
      h('div', { class: 'lezer-achtergrond' }),
      h('div', { class: 'lezer-podium' }),
      h('div', { class: 'lezer-scroll', tabindex: '-1' }),
    );
    document.body.append(overlay);
    document.body.classList.add('lezer-open');
    overlay.addEventListener('keydown', toetsen);
    requestAnimationFrame(() => overlay.classList.add('zichtbaar'));
  }

  function toetsen(e) {
    if (e.key === 'Escape') { e.preventDefault(); sluit(); }
    if (!huidig || huidig === 0) return;
    if (e.target.closest('input, textarea')) return;
    const s = staat();
    if (e.key === 'ArrowRight' && huidig < s.totaal && s.brieven[huidig].status === 'open') onNaar(huidig + 1);
    if (e.key === 'ArrowLeft' && huidig > 1) onNaar(huidig - 1);
  }

  function balk(titel) {
    const grootte = () => geheugen.get('lettergrootte', 1);
    const zetGrootte = (d) => {
      const g = Math.max(0, Math.min(GROOTTES.length - 1, grootte() + d));
      geheugen.set('lettergrootte', g);
      overlay.style.setProperty('--vel-grootte', GROOTTES[g]);
    };
    overlay.style.setProperty('--vel-grootte', GROOTTES[grootte()]);
    return h('header', { class: 'lezer-balk' },
      h('button', { class: 'ikoon-knop', type: 'button', 'aria-label': 'Brief sluiten', onclick: () => sluit(), html: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>' }),
      h('span', { class: 'lezer-titel' }, titel),
      h('span', { class: 'lezer-grootte' },
        h('button', { class: 'ikoon-knop klein', type: 'button', 'aria-label': 'Kleinere letters', onclick: () => zetGrootte(-1) }, 'A−'),
        h('button', { class: 'ikoon-knop', type: 'button', 'aria-label': 'Grotere letters', onclick: () => zetGrootte(1) }, 'A+'),
      ),
    );
  }

  function vel(brief, nummerTekst) {
    const tekst = h('div', { class: 'vel-tekst', html: String(brief.html || '').replaceAll('{naam}', escapeHtml(naam() || 'reiziger')) });
    return h('article', { class: 'vel' },
      h('div', { class: 'vel-kop' },
        h('span', { class: 'vel-nummer' }, nummerTekst),
        h('span', { class: 'vel-plaats' }, [vul(brief.plaats), vul(brief.datum)].filter(Boolean).join(', ')),
      ),
      brief.aanhef ? h('p', { class: 'vel-aanhef' }, vul(brief.aanhef)) : null,
      tekst,
      h('div', { class: 'vel-slot' },
        brief.groet ? h('p', { class: 'vel-groet' }, vul(brief.groet)) : null,
        brief.ondertekening ? h('p', { class: 'vel-handtekening' }, vul(brief.ondertekening)) : null,
      ),
      brief.naschrift ? h('p', { class: 'vel-ps' }, h('span', {}, 'P.S. '), vul(brief.naschrift)) : null,
      h('div', { class: 'vel-fleuron', 'aria-hidden': 'true' }, '❦'),
    );
  }

  function navigatie(n) {
    const s = staat();
    const nav = h('nav', { class: 'lezer-nav', 'aria-label': 'Andere brieven' });
    if (n > 1) {
      nav.append(h('button', { class: 'knop knop-zacht', type: 'button', onclick: () => onNaar(n - 1) }, `‹ Brief ${roman(n - 1)}`));
    } else nav.append(h('span'));
    if (n < s.totaal) {
      const volgende = s.brieven[n];
      if (volgende.status === 'open') {
        nav.append(h('button', { class: 'knop knop-goud', type: 'button', onclick: () => onNaar(n + 1) }, `Brief ${roman(n + 1)} ›`));
      } else if (volgende.status === 'kopen') {
        nav.append(h('button', { class: 'knop knop-goud', type: 'button', onclick: () => { sluit(true); onKopen(); } }, `Brief ${roman(n + 1)} ligt in de kluis`));
      } else {
        const nachten = nachtenTot(s.vandaag, volgende.opent);
        const wanneer = nachten === 1 ? 'komt vannacht om twaalf uur' : `komt over ${nachten} nachten`;
        nav.append(h('p', { class: 'lezer-wacht' }, `Brief ${roman(n + 1)} ${wanneer}`));
      }
    } else {
      nav.append(h('p', { class: 'lezer-wacht' }, 'Dit was de laatste brief. Zalig kerstfeest!'));
    }
    return nav;
  }

  function klifKaart(n) {
    const s = staat();
    if (s.gekocht || s.voorvertoning || n !== s.gratis) return null;
    return h('aside', { class: 'klif' },
      h('div', { class: 'klif-gijs', html: gijsSvg() }),
      h('div', {},
        h('h3', {}, 'Hier houden de gratis brieven op.'),
        h('p', {}, `Maar het verhaal niet. Nog ${s.totaal - s.gratis} brieven liggen achter slot en grendel in de kluis van het postkantoor. Ik heb de sleutel, en ik geef hem graag aan jou.`),
        h('button', { class: 'knop knop-goud', type: 'button', onclick: () => { sluit(true); onKopen(); } }, `Lees verder voor ${s.prijs}`),
      ),
    );
  }

  async function toonBrief({ n, haal, adres, teken, stempel, nummerTekst, titel, metNavigatie }) {
    const label = titel;
    if (!overlay) bouwOverlay(label); else overlay.setAttribute('aria-label', label);
    const podium = $('.lezer-podium', overlay);
    const scroll = $('.lezer-scroll', overlay);
    scroll.classList.remove('zichtbaar');
    scroll.innerHTML = '';
    podium.innerHTML = '';
    huidig = n;

    const verzoek = haal();
    // de welkomstbrief opent altijd met de envelop: daar leer je het zegel breken
    const nieuw = n === 0 ? true : !gelezen().includes(n);

    if (nieuw && !reducedMotion()) {
      const env = maakEnvelop({ adres, teken, stempel });
      podium.append(env.el);
      podium.classList.add('zichtbaar');
      await env.open();
      podium.classList.remove('zichtbaar');
    } else {
      geluid.papier(0.3);
    }
    if (huidig !== n || !overlay) return;

    let brief;
    try {
      brief = await verzoek;
    } catch (e) {
      podium.innerHTML = '';
      scroll.append(h('div', { class: 'lezer-fout' },
        h('p', {}, e.status === 403 ? 'Deze brief is nog niet voor jou bezorgd.' : 'Deze brief kon niet worden opgehaald. Probeer het zo nog eens.'),
        h('button', { class: 'knop knop-goud', type: 'button', onclick: () => sluit() }, 'Terug naar het postkantoor')));
      scroll.classList.add('zichtbaar');
      return;
    }
    if (huidig !== n || !overlay) return;

    podium.innerHTML = '';
    scroll.append(balk(titel), vel(brief, nummerTekst));
    if (metNavigatie) {
      const klif = klifKaart(n);
      if (klif) scroll.append(klif);
      scroll.append(navigatie(n));
    } else {
      scroll.append(h('nav', { class: 'lezer-nav enkel' },
        h('button', { class: 'knop knop-goud', type: 'button', onclick: () => sluit() }, 'Verder')));
    }
    scroll.scrollTop = 0;
    await wait(20);
    scroll.classList.add('zichtbaar');
    scroll.focus({ preventScroll: true });
    if (n === 0) geheugen.set('welkomGelezen', true); else markeer(n);
  }

  function sluit(stil = false) {
    if (!overlay) return;
    const o = overlay;
    overlay = null;
    huidig = null;
    o.classList.remove('zichtbaar');
    o.classList.add('sluiten');
    document.body.classList.remove('lezer-open');
    setTimeout(() => o.remove(), 450);
    if (vorigeFocus && vorigeFocus.focus) vorigeFocus.focus({ preventScroll: true });
    const r = sluitResolve; sluitResolve = null;
    if (r) r();
    if (!stil) onSluit();
  }

  return {
    get open() { return Boolean(overlay); },
    get nummer() { return huidig; },

    openBrief(n) {
      const s = staat();
      return toonBrief({
        n,
        haal: () => api(`/api/brief/${n}`),
        adres: `Aan ${naam() || 'de lezer'}`,
        teken: roman(n),
        stempel: datumTekst(s.brieven[n - 1].opent).replace(/ (\w{3})\w*$/, ' $1').toUpperCase(),
        nummerTekst: `Brief ${roman(n)}`,
        titel: `Brief ${roman(n)}, ${datumTekst(s.brieven[n - 1].opent)}`,
        metNavigatie: true,
      });
    },

    openWelkom() {
      return new Promise((resolve) => {
        sluitResolve = resolve;
        toonBrief({
          n: 0,
          haal: () => api('/api/welkom'),
          adres: `Aan ${naam() || 'de nieuwe lezer'}`,
          teken: 'G',
          stempel: '',
          nummerTekst: 'Welkom',
          titel: 'Een brief van Grote Gijs',
          metNavigatie: false,
        });
      });
    },

    sluit,
  };
}
