// Het hart van de app: staat ophalen, routes, en alles aan elkaar knopen.
import { $, h, api, wait, geheugen, roman, escapeHtml } from './util.js';
import { geluid } from './geluid.js';
import { startSneeuw } from './sneeuw.js';
import { maakStad, zetKlok } from './stad.js';
import { maakGijs } from './gijs.js';
import { maakLezer } from './lezer.js';
import { maakPostkantoor } from './postkantoor.js';
import { maakWinkel } from './winkel.js';
import { speelIntro } from './intro.js';

const app = $('#app');
let staat = null;
let inIntro = false;
let welkomGezegd = false;

const naam = () => geheugen.get('naam', '');

// ---------- decor ----------

const stad = $('#stad');
stad.innerHTML = maakStad();
zetKlok(stad);
setInterval(() => zetKlok(stad), 30000);
const sneeuw = startSneeuw($('#sneeuw'));

document.addEventListener('pointerdown', () => geluid.wekOp(), { once: true });

const geluidKnop = $('#geluid-knop');
function toonGeluid(aan) {
  geluidKnop.setAttribute('aria-pressed', String(aan));
  geluidKnop.setAttribute('aria-label', aan ? 'Geluid uitzetten' : 'Geluid aanzetten');
  geluidKnop.classList.toggle('aan', aan);
}
toonGeluid(geluid.aan);
geluidKnop.addEventListener('click', () => geluid.wissel());
geluid.bijWissel(toonGeluid);

// ---------- onderdelen ----------

const gijs = maakGijs(document.body, { plaats: 'hoek', onKlik: () => tip() });

const lezer = maakLezer({
  staat: () => staat,
  naam,
  onSluit: () => { navigeer('/postkantoor'); postkantoor.render(); },
  onKopen: () => navigeer('/kopen'),
  onNaar: (n) => navigeer(`/brief/${n}`),
});

const winkel = maakWinkel({ staat: () => staat, gijs, naGekocht });

const postkantoor = maakPostkantoor({
  root: app,
  staat: () => staat,
  naam,
  gijs,
  onOpen: (n) => navigeer(`/brief/${n}`),
  onKopen: () => navigeer('/kopen'),
  onSleutel: (modus) => winkel.sleutel(modus),
  onOver: () => winkel.over(),
  onIntro: () => { geheugen.del('ingewerkt'); navigeer('/'); },
  onNieuweDag,
});

async function laadStaat() {
  zetStaat(await api('/api/staat'));
}

// Het verschil tussen de klok van de server en die van dit apparaat, zodat het aftellen klopt.
function zetStaat(s) {
  s.klokVerschil = Date.parse(s.nu) - Date.now();
  staat = s;
}

async function naGekocht() {
  const hadDeSleutel = staat.gekocht;
  const nieuweStaat = await api('/api/staat');
  if (nieuweStaat.gekocht && !hadDeSleutel) {
    // eerst de oude sloten laten springen, dan de kast opnieuw vullen
    window.scrollTo({ top: 0, behavior: 'smooth' });
    await wait(400);
    await postkantoor.ontgrendel();
  }
  zetStaat(nieuweStaat);
  postkantoor.render();
  if (staat.gekocht && !hadDeSleutel) {
    gijs.zwaai();
    const nieuw = staat.brieven.filter((b) => b.status === 'open' && b.n > staat.gratis).length;
    gijs.zeg(nieuw
      ? `Hoera! De kluis is open. ${nieuw === 1 ? 'Er ligt al een brief' : `Er liggen al ${nieuw} brieven`} voor je klaar.`
      : 'Hoera! De kluis is open. Vanaf nu bezorg ik elke nacht een nieuwe brief, tot en met kerstavond.', { vanzelfWeg: 8000 });
  }
}

async function onNieuweDag() {
  await laadStaat();
  postkantoor.render();
  const nieuw = staat.brieven.find((b) => b.opent === staat.vandaag);
  geluid.bel(1318.5);
  setTimeout(() => geluid.bel(1046.5), 350);
  if (!nieuw) return;
  if (nieuw.status === 'open') {
    const k = await gijs.zeg(`Ding dong! Brief ${roman(nieuw.n)} is zojuist bezorgd. Nog warm van de reis.`, {
      knoppen: [{ label: 'Openen', waarde: 'open', hoofd: true }, { label: 'Straks', waarde: 'later' }],
    });
    gijs.stil();
    if (k === 'open') navigeer(`/brief/${nieuw.n}`);
  } else {
    gijs.zeg(`Ding dong! Brief ${roman(nieuw.n)} is bezorgd. Hij ligt in de kluis.`, { vanzelfWeg: 7000 });
  }
}

// ---------- Gijs' tips en weetjes ----------

const WEETJES = [
  'Wist je dat lantaarnopstekers elke avond langs alle gaslantaarns liepen om ze met een lange stok aan te steken? Ik liep weleens een stukje mee.',
  'De eerste postzegel ter wereld, de Penny Black, verscheen in 1840. Ik heb er nog een. Ik gebruik hem als dekentje.',
  'In 1843 werd de allereerste kerstkaart verstuurd. In datzelfde jaar schreef Charles Dickens zijn beroemde kerstverhaal. Een goed jaar voor de post!',
  'In de fabrieken van toen werkten ook kinderen, soms wel twaalf uur per dag. Daar word ik stil van.',
  'Een stoommachine stampt zo hard dat ik het in mijn brievenbus voel trillen. Slapen is lastig, maar je went eraan.',
  'Kerstbomen werden pas echt populair toen de koningin en haar prins er een in hun paleis zetten, rond 1848. Iedereen wilde er toen eentje.',
  'Waarom ze me Grote Gijs noemen? Omdat Kleine Gijs al bezet was. Die woont in de bibliotheek.',
  'Ik ben dol op kaas. En op brieven. Het allerliefst een brief óver kaas.',
  'Een goede brief lees je twee keer: één keer om te weten wat erin staat, en één keer om te voelen wat erin staat.',
  'Als het sneeuwt, is de stad even stil. Zelfs de fabrieken lijken dan zachter te stampen.',
];
let weetjeIndex = Math.floor(Math.random() * WEETJES.length);
let tipTeller = 0;

async function tip() {
  if (inIntro) return;
  if (gijs.bubbel.classList.contains('open')) { gijs.stil(); return; }
  tipTeller++;
  const gelezen = new Set(geheugen.get('gelezen', []));
  const ongelezen = staat.brieven.find((b) => b.status === 'open' && !gelezen.has(b.n));
  const kluis = staat.brieven.find((b) => b.status === 'kopen');
  const nm = naam() ? `, ${escapeHtml(naam())}` : '';

  if (ongelezen && tipTeller % 2 === 1) {
    const k = await gijs.zeg(`Psst${nm}. Brief ${roman(ongelezen.n)} ligt nog ongeopend in je vakje.`, {
      knoppen: [{ label: 'Open hem', waarde: 'open', hoofd: true }, { label: 'Vertel iets anders', waarde: 'meer' }],
    });
    if (k === 'open') { gijs.stil(); navigeer(`/brief/${ongelezen.n}`); return; }
    if (k !== 'meer') return;
  } else if (!staat.gekocht && !staat.voorvertoning && tipTeller % 3 === 2) {
    const k = await gijs.zeg(kluis
      ? `Brief ${roman(kluis.n)} ligt al in de kluis te wachten. De sleutel kost minder dan een warme chocolademelk. Nou ja, twee.`
      : 'De sleutel van de kluis kost minder dan een warme chocolademelk met slagroom. Nou ja, twee. En je leest er vierentwintig avonden van.', {
      knoppen: [{ label: 'Bekijk de sleutel', waarde: 'kopen', hoofd: true }, { label: 'Vertel iets anders', waarde: 'meer' }],
    });
    if (k === 'kopen') { gijs.stil(); navigeer('/kopen'); return; }
    if (k !== 'meer') return;
  }
  weetjeIndex = (weetjeIndex + 1) % WEETJES.length;
  const k = await gijs.zeg(WEETJES[weetjeIndex], {
    knoppen: [{ label: 'Nog eentje', waarde: 'meer' }, { label: 'Dank je', waarde: 'ok', hoofd: true }],
  });
  if (k === 'meer') { gijs.stil(); setTimeout(tip, 150); } else gijs.stil();
}

function welkomTerug() {
  if (welkomGezegd) return;
  welkomGezegd = true;
  const gelezen = new Set(geheugen.get('gelezen', []));
  const ongelezen = staat.brieven.filter((b) => b.status === 'open' && !gelezen.has(b.n));
  const nm = naam() ? `, ${escapeHtml(naam())}` : '';
  setTimeout(() => {
    if (lezer.open || document.querySelector('.modal')) return;
    if (ongelezen.length) {
      gijs.zeg(`Welkom terug${nm}! ${ongelezen.length === 1 ? 'Er ligt een nieuwe brief' : `Er liggen ${ongelezen.length} nieuwe brieven`} in je vakje.`, { vanzelfWeg: 7000 });
    } else {
      gijs.zeg(`Welkom terug${nm}! Fijn je weer te zien.`, { vanzelfWeg: 4500 });
    }
  }, 1400);
}

// ---------- routes ----------

function navigeer(pad, { vervang = false } = {}) {
  if (location.pathname + location.search !== pad) history[vervang ? 'replaceState' : 'pushState'](null, '', pad);
  route();
}

async function startIntro() {
  inIntro = true;
  postkantoor.stop();
  app.innerHTML = '';
  await speelIntro({
    gijs, sneeuw, lezer, postkantoor, naam,
    staat: () => staat,
    zetNaam: (v) => geheugen.set('naam', v),
    naarPostkantoor: () => { history.replaceState(null, '', '/postkantoor'); postkantoor.render(); },
  });
  inIntro = false;
  welkomGezegd = true;
}

function route() {
  if (inIntro) return;
  const url = new URL(location.href);
  const p = url.pathname.replace(/\/$/, '') || '/';

  if (p === '/') {
    if (!geheugen.get('ingewerkt', false)) { startIntro(); return; }
    history.replaceState(null, '', '/postkantoor');
  }
  if (!postkantoor.el || !postkantoor.el.isConnected) postkantoor.render();
  gijs.toon();

  const brief = p.match(/^\/brief\/(\d{1,2})$/);
  if (brief) {
    const n = Number(brief[1]);
    const b = staat.brieven[n - 1];
    if (b && b.status === 'open') {
      if (lezer.nummer !== n) { gijs.stil(); lezer.openBrief(n); }
    } else {
      if (lezer.open) lezer.sluit(true);
      history.replaceState(null, '', '/postkantoor');
      if (b && b.status === 'kopen') winkel.kopen();
      else if (b) gijs.zeg(`Brief ${roman(n)} is nog niet bezorgd. Nog even geduld!`, { vanzelfWeg: 5000 });
    }
    return;
  }
  if (lezer.open) lezer.sluit(true);

  if (p === '/kopen') {
    history.replaceState(null, '', '/postkantoor');
    if (staat.gekocht || staat.voorvertoning) gijs.zeg('Jij hebt de sleutel van de kluis al! Alle brieven worden voor je bezorgd.', { vanzelfWeg: 6000 });
    else winkel.kopen();
    return;
  }
  if (p === '/bedankt') { winkel.bedankt(url.searchParams.get('bestelling') || ''); return; }
  if (p === '/sleutel') {
    const code = url.searchParams.get('code') || '';
    history.replaceState(null, '', '/postkantoor');
    winkel.sleutel('invoeren', code);
    return;
  }
  if (p === '/over') { history.replaceState(null, '', '/postkantoor'); winkel.over(); return; }
  welkomTerug();
}

window.addEventListener('popstate', route);

(async () => {
  try {
    await laadStaat();
  } catch {
    app.append(h('div', { class: 'storing' },
      h('h1', {}, 'Het postkantoor is even dicht'),
      h('p', {}, 'Er ging iets mis bij het ophalen van de brieven. Probeer het over een paar minuten opnieuw.')));
    return;
  }
  document.body.classList.add('geladen');
  route();
})();
