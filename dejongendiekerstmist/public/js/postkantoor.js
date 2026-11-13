// Het postkantoor: de postvakkenkast als adventskalender.
import { h, $, $$, roman, datumTekst, nachtenTot, nachtenWoord, begroeting, geheugen, escapeHtml, wait } from './util.js';
import { horlogeSvg, sleutelSvg } from './svg.js';
import { geluid } from './geluid.js';

export function maakPostkantoor({ root, staat, naam, gijs, onOpen, onKopen, onSleutel, onOver, onIntro, onNieuweDag }) {
  let timer = null;
  let el = null;

  const gelezen = () => new Set(geheugen.get('gelezen', []));

  function volgendeWacht(s) {
    return s.brieven.find((b) => b.status === 'wacht' && b.opent > s.vandaag) || null;
  }

  function groetTekst(s) {
    const nm = naam() ? `, ${escapeHtml(naam())}` : '';
    const g = gelezen();
    const begin = `${begroeting()}${nm}.`;
    if (s.vandaag < s.startDatum && !s.voorvertoning) {
      const n = nachtenTot(s.vandaag, s.startDatum);
      return `${begin} Nog ${n === 1 ? 'één nacht' : `${n} nachten`}, dan bezorg ik de eerste brief.`;
    }
    const open = s.brieven.filter((b) => b.status === 'open');
    const ongelezen = open.filter((b) => !g.has(b.n));
    const vandaag = s.brieven.find((b) => b.opent === s.vandaag);
    if (vandaag && vandaag.status === 'open' && !g.has(vandaag.n)) return `${begin} De brief van vandaag ligt voor je klaar.`;
    if (ongelezen.length === 1) return `${begin} Er ligt nog één ongeopende brief in je vakje.`;
    if (ongelezen.length > 1) return `${begin} Er liggen ${ongelezen.length} ongeopende brieven op je te wachten.`;
    const kluis = s.brieven.filter((b) => b.status === 'kopen');
    if (kluis.length) return `${begin} Brief ${roman(kluis[0].n)} ligt al klaar, maar dan wel in de kluis.`;
    if (open.length === s.totaal) return `${begin} Het verhaal is compleet. Zalig kerstfeest!`;
    return `${begin} Je bent helemaal bij. De volgende brief komt vannacht.`;
  }

  function vak(b, s, g) {
    const isVandaag = b.opent === s.vandaag && !s.voorvertoning;
    let klasse = 'vak';
    let inhoud;
    let label;
    if (b.status === 'open') {
      const al = g.has(b.n);
      klasse += al ? ' vak-gelezen' : ' vak-open';
      inhoud = h('span', { class: 'mini-env' + (al ? ' geopend' : '') }, h('span', { class: 'mini-zegel' }));
      label = `Brief ${b.n}${b.titel && b.titel !== `Brief ${b.n}` ? `: ${b.titel}` : ''}, ${al ? 'gelezen' : 'nieuw'}. Openen.`;
    } else if (b.status === 'kopen') {
      klasse += ' vak-kopen';
      inhoud = [h('span', { class: 'mini-env op-slot' }), h('span', { class: 'mini-slot', 'aria-hidden': 'true' })];
      label = `Brief ${b.n} ligt in de kluis. Koop de sleutel om hem te lezen.`;
    } else {
      klasse += ' vak-wacht';
      const n = nachtenTot(s.vandaag, b.opent);
      inhoud = h('span', { class: 'vak-leeg' }, h('span', { class: 'vak-nachten' }, n === 1 ? 'morgen' : `${n} nachten`));
      label = `Brief ${b.n} komt op ${datumTekst(b.opent)}.`;
    }
    if (isVandaag) klasse += ' vak-vandaag';
    const betaald = b.n > s.gratis && !s.gekocht && !s.voorvertoning;
    return h('button', {
      class: klasse, type: 'button', 'data-n': b.n, 'aria-label': label,
      onclick: (e) => klik(b, e.currentTarget),
    },
    h('span', { class: 'vak-binnen' }, inhoud),
    h('span', { class: 'vak-plaatje' }, roman(b.n), betaald ? h('span', { class: 'plaatje-slot', 'aria-hidden': 'true' }) : null),
    isVandaag ? h('span', { class: 'vak-label' }, 'vandaag') : null);
  }

  async function klik(b, knop) {
    geluid.wekOp();
    const s = staat();
    if (b.status === 'open') { geluid.klik(); onOpen(b.n); return; }
    knop.classList.remove('schud'); void knop.offsetWidth; knop.classList.add('schud');
    if (b.status === 'kopen') {
      const k = await gijs.zeg(`Brief ${roman(b.n)} ligt in de kluis. Met de sleutel kun je hem meteen lezen, en alle brieven die nog komen.`, {
        knoppen: [{ label: 'Bekijk de sleutel', waarde: 'ja', hoofd: true }, { label: 'Straks', waarde: 'nee' }],
      });
      gijs.stil();
      if (k === 'ja') onKopen();
      return;
    }
    const n = nachtenTot(s.vandaag, b.opent);
    const wanneer = n === 1 ? 'komt vannacht om klokslag twaalf' : `komt over ${n} nachten, op ${datumTekst(b.opent)}`;
    const kluis = b.n > s.gratis && !s.gekocht && !s.voorvertoning ? ' En die bewaar ik in de kluis, dus daar heb je de sleutel voor nodig.' : '';
    const geduld = ['Geduld', 'Rustig aan', 'Nog even'][b.n % 3];
    gijs.zeg(`${geduld}${naam() ? ', ' + escapeHtml(naam()) : ''}! Brief ${roman(b.n)} ${wanneer}.${kluis}`, { vanzelfWeg: 6000 });
  }

  function horloge() {
    return h('div', { class: 'horloge', role: 'timer', 'aria-live': 'off' },
      h('span', { class: 'horloge-wijzerplaat', html: horlogeSvg() }),
      h('span', { class: 'horloge-tekst' }, h('span', { class: 'horloge-tijd' }, ''), h('span', { class: 'horloge-label' }, '')));
  }

  function tik() {
    if (!el) return;
    const s = staat();
    const nu = new Date();
    const sec = nu.getSeconds(), min = nu.getMinutes(), uur = nu.getHours() % 12;
    const set = (sel, deg) => { const x = $(sel, el); if (x) x.style.transform = `rotate(${deg}deg)`; };
    set('.h-sec', sec * 6); set('.h-min', min * 6 + sec * 0.1); set('.h-uur', uur * 30 + min * 0.5);

    const tijd = $('.horloge-tijd', el);
    const label = $('.horloge-label', el);
    const volgende = volgendeWacht(s);
    if (!volgende || s.voorvertoning) {
      tijd.textContent = s.voorvertoning ? 'Alles open' : 'Alles bezorgd';
      label.textContent = s.voorvertoning ? 'voorvertoning' : 'Zalig kerstfeest';
      return;
    }
    const nachten = nachtenTot(s.vandaag, volgende.opent);
    const doel = Date.parse(s.volgendeMiddernacht) + (nachten - 1) * 86400000;
    const rest = Math.max(0, doel - (Date.now() + (s.klokVerschil || 0)));
    const wie = volgende.n === 1 ? 'tot de eerste brief' : `tot brief ${roman(volgende.n)}`;
    if (nachten > 1) {
      tijd.textContent = nachtenWoord(nachten);
      label.textContent = wie;
    } else {
      const t = Math.floor(rest / 1000);
      const pad = (x) => String(x).padStart(2, '0');
      tijd.textContent = `${pad(Math.floor(t / 3600))}:${pad(Math.floor((t % 3600) / 60))}:${pad(t % 60)}`;
      label.textContent = wie;
    }
    if (rest <= 0) {
      clearInterval(timer);
      timer = null;
      setTimeout(onNieuweDag, 1500);
    }
  }

  function kluisBanner(s) {
    if (s.voorvertoning) {
      return h('div', { class: 'banner banner-voorvertoning' },
        h('p', {}, h('strong', {}, 'Voorvertoning. '), 'Alle brieven zijn open, ongeacht de datum. Alleen jij ziet dit.'),
        h('a', { class: 'knop knop-zacht', href: '/voorvertoning/uit' }, 'Stoppen'));
    }
    if (s.gekocht) {
      const sleutel = geheugen.get('sleutel', '');
      return h('div', { class: 'banner banner-gekocht' },
        h('span', { class: 'banner-sleutel', html: sleutelSvg() }),
        h('p', {}, h('strong', {}, 'Jij hebt de sleutel van de kluis. '), 'Elke nacht wordt er een nieuwe brief voor je bezorgd, tot en met kerstavond.'),
        sleutel ? h('button', { class: 'knop knop-zacht', type: 'button', onclick: () => onSleutel('tonen') }, 'Toon mijn sleutel') : null);
    }
    return h('div', { class: 'banner banner-kluis' },
      h('span', { class: 'banner-sleutel zweef', html: sleutelSvg() }),
      h('div', {},
        h('h2', {}, 'Het hele verhaal'),
        h('p', {}, `De eerste ${s.gratis} brieven zijn een cadeautje. Brief ${roman(s.gratis + 1)} tot en met ${roman(s.totaal)} liggen veilig in de kluis. Met de sleutel worden ze elke nacht voor je bezorgd, tot en met kerstavond.`)),
      h('button', { class: 'knop knop-goud', type: 'button', onclick: () => onKopen() }, `Bekijk de sleutel · ${s.prijs}`));
  }

  function render() {
    const s = staat();
    const g = gelezen();
    const aantalGelezen = s.brieven.filter((b) => g.has(b.n)).length;
    el = h('section', { class: 'postkantoor', 'aria-labelledby': 'pk-titel' },
      h('header', { class: 'pk-kop' },
        h('div', { class: 'uithangbord' },
          h('span', { class: 'bord-klein' }, 'Het postkantoor van Grote Gijs'),
          h('h1', { class: 'bord-titel', id: 'pk-titel' }, s.titel),
          h('span', { class: 'bord-onder' }, `${s.ondertitel}, door ${s.auteur}`))),
      h('div', { class: 'pk-status' },
        horloge(),
        h('div', { class: 'pk-groet-blok' },
          h('p', { class: 'pk-groet', html: groetTekst(s) }),
          h('p', { class: 'pk-teller' }, `${aantalGelezen} van de ${s.totaal} brieven gelezen`))),
      h('div', { class: 'kast' },
        h('div', { class: 'kast-kroon' }, h('span', {}, 'Posterijen')),
        h('div', { class: 'vakken' }, s.brieven.map((b) => vak(b, s, g))),
        h('div', { class: 'kast-voet' })),
      kluisBanner(s),
      h('footer', { class: 'pk-voet' },
        !s.gekocht && !s.voorvertoning ? h('button', { type: 'button', class: 'link', onclick: () => onSleutel('invoeren') }, 'Heb je al een sleutel?') : null,
        h('button', { type: 'button', class: 'link', onclick: () => onOver() }, 'Over het verhaal'),
        h('button', { type: 'button', class: 'link geluid-link', onclick: () => geluid.wissel() }, geluid.aan ? 'Geluid uit' : 'Geluid aan'),
        h('button', { type: 'button', class: 'link', onclick: () => onIntro() }, 'Intro opnieuw')),
    );
    root.innerHTML = '';
    root.append(el);
    clearInterval(timer);
    tik();
    timer = setInterval(tik, 1000);
  }

  geluid.bijWissel((aan) => { const l = el && $('.geluid-link', el); if (l) l.textContent = aan ? 'Geluid uit' : 'Geluid aan'; });

  return {
    render,
    get el() { return el; },
    kast: () => el && $('.kast', el),
    horloge: () => el && $('.horloge', el),
    vak: (n) => el && $(`.vak[data-n="${n}"]`, el),

    /** Laat de sloten van de kast springen na het kopen. */
    async ontgrendel() {
      if (!el) return;
      const sloten = $$('.vak-kopen, .plaatje-slot', el);
      sloten.forEach((v, i) => setTimeout(() => {
        v.classList.add('slot-valt');
        if (i % 3 === 0) geluid.klik();
      }, i * 70));
      await wait(sloten.length * 70 + 700);
    },

    stop() { clearInterval(timer); },
  };
}
