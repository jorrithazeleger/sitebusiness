// De magische introductie en de onboarding met Grote Gijs.
import { h, $, wait, frame, geheugen, escapeHtml, reducedMotion, datumTekst } from './util.js';
import { geluid } from './geluid.js';
import { maakGijs } from './gijs.js';
import { sleutelSvg, brievenbusSvg } from './svg.js';

let gestopt = false;

function wachtOpKlik(el, { ookToets = true } = {}) {
  return new Promise((resolve) => {
    const klaar = () => { el.removeEventListener('click', klaar); document.removeEventListener('keydown', toets); resolve(); };
    const toets = (e) => { if (ookToets && (e.key === 'Enter' || e.key === ' ')) klaar(); };
    el.addEventListener('click', klaar);
    if (ookToets) document.addEventListener('keydown', toets);
  });
}

function wachtOfKlik(ms, el) {
  return Promise.race([wait(ms), wachtOpKlik(el)]);
}

async function fase(laag, el) {
  laag.append(el);
  await frame();
  el.classList.add('zichtbaar');
  return el;
}

async function weg(el, ms = 700) {
  el.classList.remove('zichtbaar');
  el.classList.add('vertrek');
  await wait(reducedMotion() ? 50 : ms);
  el.remove();
}

// ---------- 1. De poort: geluid kiezen ----------

async function poort(laag) {
  let keuze;
  const gekozen = new Promise((r) => { keuze = r; });
  const el = h('div', { class: 'fase fase-poort' },
    h('div', { class: 'kaars', 'aria-hidden': 'true' },
      h('span', { class: 'kaars-gloed' }), h('span', { class: 'kaars-vlam' }), h('span', { class: 'kaars-lont' }), h('span', { class: 'kaars-was' }), h('span', { class: 'kaars-schotel' })),
    h('p', { class: 'poort-tekst' }, 'Dit verhaal klinkt het mooist met het geluid aan.'),
    h('div', { class: 'poort-knoppen' },
      h('button', { class: 'knop knop-goud', type: 'button', onclick: () => keuze(true) }, 'Met geluid'),
      h('button', { class: 'knop knop-zacht', type: 'button', onclick: () => keuze(false) }, 'Zonder geluid')),
    h('p', { class: 'poort-klein' }, 'Je kunt het later altijd nog veranderen.'));
  await fase(laag, el);
  $('.knop-goud', el).focus({ preventScroll: true });
  const aan = await gekozen;
  geluid.zet(aan);
  geluid.bel(1046.5);
  await weg(el, 900);
}

// ---------- 2. De proloog ----------

const PROLOOG = [
  'Er was eens een stad waar de schoorstenen nooit sliepen.',
  'De fabrieken stampten dag en nacht, en het roet viel als zwarte sneeuw op de daken.',
  'Maar ergens in die stad, achter een deur die bijna niemand meer zag,',
  'lagen vierentwintig brieven te wachten.',
];

async function proloog(laag) {
  document.body.classList.remove('stad-verborgen');
  const regel = h('p', { class: 'proloog-regel' });
  const el = h('div', { class: 'fase fase-proloog', role: 'button', tabindex: '0', 'aria-label': 'Tik om verder te gaan' },
    regel, h('p', { class: 'proloog-hint' }, 'tik om verder te gaan'));
  await fase(laag, el);
  el.focus({ preventScroll: true });
  for (const zin of PROLOOG) {
    if (gestopt) return;
    regel.classList.remove('in');
    await wait(350);
    regel.textContent = zin;
    regel.classList.add('in');
    await wachtOfKlik(reducedMotion() ? 2500 : 3600 + zin.length * 20, el);
  }
  await weg(el, 800);
}

// ---------- 3. De deur ----------

async function deur(laag, sneeuw) {
  const sleutel = h('button', { class: 'zwevende-sleutel', type: 'button', 'aria-label': 'Pak de sleutel en open de deur', html: sleutelSvg() });
  const deurEl = h('div', { class: 'deur' },
    h('span', { class: 'deur-plank' }), h('span', { class: 'deur-plank' }), h('span', { class: 'deur-plank' }), h('span', { class: 'deur-plank' }),
    h('span', { class: 'scharnier boven' }), h('span', { class: 'scharnier onder' }),
    h('span', { class: 'deur-krans', 'aria-hidden': 'true' }),
    h('span', { class: 'sleutelgat' }), h('span', { class: 'deurknop' }));
  const poortEl = h('div', { class: 'poort-deur' },
    h('div', { class: 'deur-licht' }), deurEl, h('div', { class: 'deur-boog' }), h('div', { class: 'deur-drempel' }));
  const el = h('div', { class: 'fase fase-deur' },
    h('div', { class: 'titel-blok' },
      h('p', { class: 'titel-klein' }, 'Een adventsverhaal in vierentwintig brieven'),
      h('h1', { class: 'titel-groot' }, h('span', { class: 'titel-regel' }, 'De Jongen'), h('span', { class: 'titel-regel' }, h('span', { class: 'titel-die' }, 'die'), ' Kerst Mist')),
      h('p', { class: 'titel-auteur' }, 'door Nadia')),
    poortEl,
    h('div', { class: 'sleutel-plek' }, sleutel, h('p', { class: 'deur-hint' }, 'Tik op de sleutel om de deur te openen')));
  await fase(laag, el);
  await wait(400);
  sleutel.focus({ preventScroll: true });
  await wachtOpKlik(sleutel, { ookToets: false });
  if (gestopt) return;
  el.classList.add('sleutel-gepakt');
  geluid.klik();

  // sleutel naar het sleutelgat
  // de punt van de sleutel moet precies in het sleutelgat belanden
  const gat = $('.sleutelgat', el).getBoundingClientRect();
  const s = sleutel.getBoundingClientRect();
  const svgRect = $('svg', sleutel).getBoundingClientRect();
  const schaal = 0.42;
  const cx = s.left + s.width / 2, cy = s.top + s.height / 2;
  const tipX = svgRect.left + svgRect.width * (190 / 220);
  const tipY = svgRect.top + svgRect.height * (40 / 90);
  const dx = gat.left + gat.width / 2 - cx - (tipX - cx) * schaal;
  const dy = gat.top + gat.height * 0.32 - cy - (tipY - cy) * schaal;
  if (!reducedMotion()) {
    await sleutel.animate([
      { transform: 'translate(0,0) scale(1)' },
      { transform: `translate(${dx}px, ${dy}px) scale(${schaal})` },
    ], { duration: 1000, easing: 'cubic-bezier(.5,0,.2,1)', fill: 'forwards' }).finished;
    geluid.klik();
    await sleutel.animate([
      { transform: `translate(${dx}px, ${dy}px) scale(${schaal}) scaleY(1)` },
      { transform: `translate(${dx}px, ${dy}px) scale(${schaal}) scaleY(-1)` },
    ], { duration: 450, easing: 'ease-in-out', fill: 'forwards' }).finished;
    geluid.klik();
  }
  sleutel.style.opacity = '0';
  el.classList.add('deur-open');
  geluid.deur();
  sneeuw.vlaag(9);
  setTimeout(() => geluid.muziekdoos('kort'), 500);
  await wait(reducedMotion() ? 200 : 1700);
  el.classList.add('erdoor');
  await wait(reducedMotion() ? 200 : 1300);
  el.remove();
}

// ---------- 4. De straat: kennismaken met Grote Gijs ----------

function naamFormulier() {
  let klaar;
  const resultaat = new Promise((r) => { klaar = r; });
  const input = h('input', {
    class: 'naam-invoer', type: 'text', name: 'naam', maxlength: '24', autocomplete: 'given-name',
    placeholder: 'je naam', 'aria-label': 'Je naam', enterkeyhint: 'done',
  });
  const form = h('form', { class: 'naam-form', onsubmit: (e) => {
    e.preventDefault();
    const v = input.value.trim().replace(/\s+/g, ' ').slice(0, 24);
    if (!v) { input.focus(); input.classList.add('wiebel'); setTimeout(() => input.classList.remove('wiebel'), 500); return; }
    geluid.klik();
    klaar(v);
  } },
  h('label', { class: 'naam-label' }, 'Mijn naam is', input),
  h('div', { class: 'naam-knoppen' },
    h('button', { class: 'knop knop-goud', type: 'submit' }, 'Dat ben ik'),
    h('button', { class: 'link', type: 'button', onclick: () => klaar('') }, 'Ik blijf liever geheim')));
  setTimeout(() => input.focus({ preventScroll: true }), 60);
  return { form, resultaat };
}

function envelopMetNaam(naam) {
  return h('div', { class: 'schrijf-envelop', 'aria-hidden': 'true' },
    h('span', { class: 'schrijf-postzegel' }),
    h('span', { class: 'schrijf-tekst' }, `Aan ${naam}`),
    h('span', { class: 'schrijf-sub' }, 'per bijzondere bode'));
}

function strook({ metSlot }) {
  const s = h('div', { class: 'strook' + (metSlot ? ' met-slot' : ''), 'aria-hidden': 'true' });
  for (let i = 1; i <= 24; i++) {
    s.append(h('span', { class: 'strook-env' + (i <= 3 ? ' gratis' : ''), style: { animationDelay: `${i * 35}ms` } }));
  }
  return s;
}

async function straat(laag, ctx) {
  const bus = h('div', { class: 'brievenbus', html: brievenbusSvg() });
  const podium = h('div', { class: 'straat-podium' }, bus);
  const el = h('div', { class: 'fase fase-straat' }, podium);
  await fase(laag, el);
  const gijs = maakGijs(podium, { plaats: 'podium' });
  gijs.root.classList.add('in-bus');
  await wait(900);
  if (gestopt) return;
  bus.classList.add('rammel'); geluid.piep();
  await wait(700);
  bus.classList.remove('rammel'); void bus.offsetWidth; bus.classList.add('rammel');
  await wait(600);
  gijs.root.classList.remove('in-bus');
  gijs.root.classList.add('uit-bus');
  geluid.bel(1568);
  await wait(900);
  gijs.zwaai();

  const z = (tekst, opties) => (gestopt ? null : gijs.zeg(tekst, opties));

  await z('Ahem! Goedenavond! Schrik maar niet, ik ben maar een muis. Al zeggen ze in deze straat dat ik de <em>grootste</em> muis van het hele postkantoor ben.', {
    knoppen: [{ label: 'Hallo!', waarde: 1, hoofd: true }],
  });
  await z('Grote Gijs, aangenaam. Ik bezorg brieven. Maar niet zomaar brieven: deze brieven zijn heel bijzonder.', {
    knoppen: [{ label: 'Wat voor brieven?', waarde: 1, hoofd: true }],
  });

  const { form, resultaat } = naamFormulier();
  await z('Dat vertel ik zo. Eerst moet ik weten voor wie ik ze bezorg. Hoe heet jij?', { extra: form });
  const naam = gestopt ? '' : await resultaat;
  ctx.zetNaam(naam);

  if (naam) {
    await z(`${escapeHtml(naam)}! Wat een mooie naam om op een envelop te schrijven.`, {
      extra: envelopMetNaam(naam), knoppen: [{ label: 'Dank je, Gijs', waarde: 1, hoofd: true }],
    });
  } else {
    await z('Een geheimzinnige reiziger! Dat vind ik wel spannend. Dan schrijf ik gewoon <em>Aan de lezer</em> op de envelop.', {
      extra: envelopMetNaam('de lezer'), knoppen: [{ label: 'Prima', waarde: 1, hoofd: true }],
    });
  }

  await z('Zo werkt het. Elke nacht in december, klokslag twaalf, leg ik een nieuwe brief in jouw postvak. Vierentwintig nachten, vierentwintig brieven, tot en met kerstavond.', {
    extra: strook({ metSlot: false }), knoppen: [{ label: 'En dan?', waarde: 1, hoofd: true }],
  });
  const s = ctx.staat();
  await z(`De eerste ${s.gratis === 3 ? 'drie' : s.gratis} bezorg ik gratis. De rest bewaar ik in de kluis, en daar heb je een sleutel voor nodig. Ook een muis moet tenslotte kaas kopen.`, {
    extra: strook({ metSlot: true }), knoppen: [{ label: 'Begrepen', waarde: 1, hoofd: true }],
  });

  const voorStart = s.vandaag < s.startDatum;
  await z(voorStart
    ? `De eerste brief komt op ${datumTekst(s.startDatum)}. Maar ik heb alvast iets voor je klaargelegd: een brief van mij. Breek het zegel maar.`
    : 'Maar eerst: er ligt al iets voor je klaar. Een brief van mij. Breek het zegel maar.', {
    knoppen: [{ label: 'Laat zien!', waarde: 1, hoofd: true }],
  });
  if (gestopt) return;
  gijs.stil();
  await ctx.lezer.openWelkom();
  if (gestopt) return;

  await z('Kom, dan laat ik je het postkantoor zien. Ik loop wel even voor.', {
    knoppen: [{ label: 'Naar het postkantoor', waarde: 1, hoofd: true }],
  });
  gijs.stil();
  gijs.root.classList.add('rent-weg');
  geluid.piep();
  await wait(700);
  gijs.vernietig();
  await weg(el, 700);
}

// ---------- 5. Rondleiding in het postkantoor ----------

async function rondleiding(ctx) {
  const { gijs, postkantoor } = ctx;
  const spot = h('div', { class: 'spot' });
  document.body.append(spot);
  const richt = async (el) => {
    if (!el) return;
    el.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
    await wait(450);
    const r = el.getBoundingClientRect();
    const p = 10;
    Object.assign(spot.style, { left: `${r.left - p}px`, top: `${r.top - p}px`, width: `${r.width + p * 2}px`, height: `${r.height + p * 2}px` });
    spot.classList.add('aan');
  };
  gijs.toon();
  await wait(300);
  const naam = ctx.naam();
  await richt(postkantoor.kast());
  await gijs.zeg('Dit is jouw postvakkenkast. Elke nacht verschijnt er een brief in het vakje van die dag. Een rood zegel betekent: nog niet gelezen!', {
    knoppen: [{ label: 'Mooi', waarde: 1, hoofd: true }],
  });
  await richt(postkantoor.horloge());
  await gijs.zeg('Dit zakhorloge telt af tot de volgende brief. Ik kijk er zelf ook steeds op. Ik ben nogal ongeduldig.', {
    knoppen: [{ label: 'Ha!', waarde: 1, hoofd: true }],
  });
  await richt(gijs.figuur);
  await gijs.zeg(`En hier zit ik. Tik op me als je hulp nodig hebt, of gewoon voor een praatje. Veel leesplezier${naam ? ', ' + escapeHtml(naam) : ''}!`, {
    knoppen: [{ label: 'Dank je, Gijs', waarde: 1, hoofd: true }],
  });
  gijs.stil();
  spot.classList.remove('aan');
  window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' });
  setTimeout(() => spot.remove(), 500);
}

// ---------- Alles achter elkaar ----------

export async function speelIntro(ctx) {
  gestopt = false;
  ctx.gijs.verberg();
  document.body.classList.add('in-intro', 'stad-verborgen');
  const laag = h('div', { class: 'intro' });
  const overslaan = h('button', { class: 'overslaan', type: 'button' }, 'Overslaan ›');
  laag.append(overslaan);
  document.body.append(laag);

  let klaarMetIntro;
  const einde = new Promise((r) => { klaarMetIntro = r; });

  const afronden = async (overgeslagen) => {
    if (laag.isConnected) {
      laag.classList.add('vertrek');
      setTimeout(() => laag.remove(), 800);
    }
    document.body.classList.remove('in-intro', 'stad-verborgen');
    geheugen.set('ingewerkt', true);
    ctx.naarPostkantoor();
    await wait(600);
    if (overgeslagen) {
      ctx.gijs.toon();
      ctx.gijs.zwaai();
      ctx.gijs.zeg('Haast? Dat begrijp ik. Ik ben Grote Gijs, je gids in het postkantoor. Tik op me als je iets wilt weten.', { vanzelfWeg: 7000 });
    }
    klaarMetIntro();
  };

  overslaan.addEventListener('click', () => {
    if (gestopt) return;
    gestopt = true;
    geluid.wekOp();
    if (ctx.lezer.open) ctx.lezer.sluit(true);
    afronden(true);
  });

  (async () => {
    await poort(laag);
    if (!gestopt) await proloog(laag);
    if (!gestopt) await deur(laag, ctx.sneeuw);
    if (!gestopt) await straat(laag, ctx);
    if (gestopt) return;
    overslaan.remove();
    gestopt = true;
    laag.classList.add('vertrek');
    setTimeout(() => laag.remove(), 800);
    document.body.classList.remove('in-intro');
    ctx.naarPostkantoor();
    await wait(900);
    await rondleiding(ctx);
    geheugen.set('ingewerkt', true);
    klaarMetIntro();
  })();

  return einde;
}
