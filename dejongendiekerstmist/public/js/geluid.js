// Alle geluiden worden live gemaakt met de Web Audio API: geen bestanden nodig.
import { geheugen } from './util.js';

let ctx = null;
let master = null;
let ambientGain = null;
let noise = null;
let ambientStarted = false;
let enabled = geheugen.get('geluid', false);
const listeners = new Set();

function ensure() {
  if (ctx) return ctx;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  ctx = new AC();
  master = ctx.createGain();
  master.gain.value = enabled ? 0.9 : 0;
  master.connect(ctx.destination);
  const len = ctx.sampleRate * 2;
  noise = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = noise.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  document.addEventListener('visibilitychange', () => {
    if (!ctx) return;
    if (document.hidden) ctx.suspend(); else if (enabled) ctx.resume();
  });
  return ctx;
}

function noiseSource(loop = false) {
  const src = ctx.createBufferSource();
  src.buffer = noise;
  src.loop = loop;
  if (!loop) src.loopStart = 0;
  return src;
}

function envGain(t, attack, peak, decay) {
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
  return g;
}

function startAmbient() {
  if (ambientStarted || !ctx) return;
  ambientStarted = true;
  ambientGain = ctx.createGain();
  ambientGain.gain.value = 0.0001;
  ambientGain.connect(master);
  ambientGain.gain.exponentialRampToValueAtTime(1, ctx.currentTime + 4);

  // Wind: ruis door een bandfilter dat langzaam op en neer gaat.
  const wind = noiseSource(true);
  const bp = ctx.createBiquadFilter();
  bp.type = 'bandpass'; bp.frequency.value = 420; bp.Q.value = 0.9;
  const wg = ctx.createGain(); wg.gain.value = 0.05;
  const lfo = ctx.createOscillator(); lfo.frequency.value = 0.07;
  const lfoAmt = ctx.createGain(); lfoAmt.gain.value = 220;
  lfo.connect(lfoAmt).connect(bp.frequency);
  const lfo2 = ctx.createOscillator(); lfo2.frequency.value = 0.11;
  const lfo2Amt = ctx.createGain(); lfo2Amt.gain.value = 0.025;
  lfo2.connect(lfo2Amt).connect(wg.gain);
  wind.connect(bp).connect(wg).connect(ambientGain);
  wind.start(); lfo.start(); lfo2.start();

  // Haardvuur: lage gloed plus af en toe een knapje.
  const rumble = noiseSource(true);
  const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 160;
  const rg = ctx.createGain(); rg.gain.value = 0.03;
  rumble.connect(lp).connect(rg).connect(ambientGain);
  rumble.start();
  const crackle = () => {
    if (enabled && !document.hidden) {
      const t = ctx.currentTime;
      const s = noiseSource();
      const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 1800 + Math.random() * 2500;
      const g = envGain(t, 0.002, 0.03 + Math.random() * 0.05, 0.02 + Math.random() * 0.04);
      s.connect(hp).connect(g).connect(ambientGain);
      s.start(t, Math.random() * 1.5, 0.1);
    }
    setTimeout(crackle, 80 + Math.random() * 600);
  };
  crackle();
}

export const geluid = {
  get aan() { return enabled; },

  /** Moet vanuit een klik of tik worden aangeroepen (eis van browsers). */
  zet(aan) {
    enabled = aan;
    geheugen.set('geluid', aan);
    if (aan) {
      if (!ensure()) return;
      ctx.resume();
      master.gain.cancelScheduledValues(ctx.currentTime);
      master.gain.setTargetAtTime(0.9, ctx.currentTime, 0.3);
      startAmbient();
    } else if (ctx) {
      master.gain.setTargetAtTime(0, ctx.currentTime, 0.2);
    }
    listeners.forEach((fn) => fn(aan));
  },

  wissel() { this.zet(!enabled); },
  bijWissel(fn) { listeners.add(fn); },

  /** Na de eerste klik op een pagina het geluid weer opstarten als het aan stond. */
  wekOp() {
    if (enabled && ensure()) { ctx.resume(); startAmbient(); }
  },

  _ok() { return enabled && ensure() && ctx.state !== 'closed'; },

  klik() {
    if (!this._ok()) return;
    const t = ctx.currentTime;
    for (const [dt, f] of [[0, 2200], [0.07, 1500]]) {
      const o = ctx.createOscillator(); o.type = 'triangle'; o.frequency.value = f;
      const g = envGain(t + dt, 0.001, 0.25, 0.04);
      o.connect(g).connect(master); o.start(t + dt); o.stop(t + dt + 0.08);
    }
  },

  krak() {
    if (!this._ok()) return;
    const t = ctx.currentTime;
    for (const dt of [0, 0.045, 0.09]) {
      const s = noiseSource();
      const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 1200;
      const g = envGain(t + dt, 0.002, 0.5 - dt * 2, 0.06);
      s.connect(hp).connect(g).connect(master); s.start(t + dt, Math.random(), 0.12);
    }
    const o = ctx.createOscillator(); o.frequency.setValueAtTime(220, t); o.frequency.exponentialRampToValueAtTime(80, t + 0.15);
    const g = envGain(t, 0.002, 0.4, 0.15);
    o.connect(g).connect(master); o.start(t); o.stop(t + 0.2);
  },

  papier(duur = 0.45) {
    if (!this._ok()) return;
    const t = ctx.currentTime;
    const s = noiseSource();
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 2800; bp.Q.value = 0.6;
    const g = ctx.createGain(); g.gain.setValueAtTime(0.0001, t);
    for (let i = 0; i < 12; i++) g.gain.setValueAtTime(0.04 + Math.random() * 0.14, t + (i / 12) * duur);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duur + 0.05);
    s.connect(bp).connect(g).connect(master); s.start(t, Math.random(), duur + 0.1);
  },

  deur() {
    if (!this._ok()) return;
    const t = ctx.currentTime;
    const o = ctx.createOscillator(); o.type = 'sawtooth';
    o.frequency.setValueAtTime(70, t); o.frequency.linearRampToValueAtTime(130, t + 0.7); o.frequency.linearRampToValueAtTime(95, t + 1.4);
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 700; bp.Q.value = 8;
    const g = ctx.createGain(); g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.18, t + 0.2); g.gain.setValueAtTime(0.12, t + 1.0); g.gain.exponentialRampToValueAtTime(0.0001, t + 1.5);
    const trem = ctx.createOscillator(); trem.frequency.value = 23; const tg = ctx.createGain(); tg.gain.value = 0.06;
    trem.connect(tg).connect(g.gain);
    o.connect(bp).connect(g).connect(master); o.start(t); trem.start(t); o.stop(t + 1.6); trem.stop(t + 1.6);
    this.wind(1.8);
  },

  wind(duur = 1.5) {
    if (!this._ok()) return;
    const t = ctx.currentTime;
    const s = noiseSource();
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 1.2;
    bp.frequency.setValueAtTime(300, t); bp.frequency.exponentialRampToValueAtTime(1400, t + duur * 0.6); bp.frequency.exponentialRampToValueAtTime(500, t + duur);
    const g = envGain(t, duur * 0.4, 0.22, duur * 0.6);
    s.connect(bp).connect(g).connect(master); s.start(t, 0, duur + 0.1);
  },

  bel(toon = 1318.5) {
    if (!this._ok()) return;
    const t = ctx.currentTime;
    for (const [mul, vol] of [[1, 0.22], [2.01, 0.08], [3.03, 0.04], [4.2, 0.02]]) {
      const o = ctx.createOscillator(); o.frequency.value = toon * mul;
      const g = envGain(t, 0.004, vol, 1.8 / mul + 0.3);
      o.connect(g).connect(master); o.start(t); o.stop(t + 2.4);
    }
  },

  piep() {
    if (!this._ok()) return;
    const t = ctx.currentTime;
    [0, 0.09].forEach((dt, i) => {
      const o = ctx.createOscillator(); o.type = 'sine';
      o.frequency.setValueAtTime(2300 + i * 300, t + dt); o.frequency.exponentialRampToValueAtTime(3300 + i * 200, t + dt + 0.06);
      const g = envGain(t + dt, 0.005, 0.05, 0.06);
      o.connect(g).connect(master); o.start(t + dt); o.stop(t + dt + 0.1);
    });
  },

  /** Muziekdoos met 'Stille nacht' (Franz Gruber, 1818, publiek domein). */
  muziekdoos(deel = 'heel') {
    if (!this._ok()) return;
    const N = { C5: 523.25, D5: 587.33, E5: 659.25, F5: 698.46, G5: 783.99, A5: 880, B5: 987.77, C6: 1046.5, D6: 1174.66, E6: 1318.51, F6: 1396.91 };
    const r1 = [['G5', 3], ['A5', 1], ['G5', 2], ['E5', 6]];
    const melodie = [
      ...r1, ...r1, ['D6', 4], ['D6', 2], ['B5', 6], ['C6', 4], ['C6', 2], ['G5', 6],
      ['A5', 4], ['A5', 2], ['C6', 3], ['B5', 1], ['A5', 2], ...r1,
      ['A5', 4], ['A5', 2], ['C6', 3], ['B5', 1], ['A5', 2], ...r1,
      ['D6', 4], ['D6', 2], ['F6', 3], ['D6', 1], ['B5', 2], ['C6', 6], ['E6', 6],
      ['C6', 3], ['G5', 1], ['E5', 2], ['G5', 3], ['F5', 1], ['D5', 2], ['C5', 12],
    ];
    const noten = deel === 'kort' ? melodie.slice(0, 16) : melodie;
    const tel = 0.14;
    let t = ctx.currentTime + 0.1;
    const out = ctx.createGain(); out.gain.value = 0.5; out.connect(master);
    for (const [noot, duur] of noten) {
      const f = N[noot];
      for (const [mul, vol] of [[1, 0.16], [2, 0.05], [3.98, 0.025]]) {
        const o = ctx.createOscillator(); o.frequency.value = f * mul;
        const g = envGain(t, 0.003, vol, 1.1);
        o.connect(g).connect(out); o.start(t); o.stop(t + 1.3);
      }
      t += duur * tel;
    }
  },
};
