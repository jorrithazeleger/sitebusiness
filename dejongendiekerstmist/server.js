import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { config, paymentMode } from './lib/config.js';
import { dateIn, unlockDate, midnightUtc, addDays } from './lib/dates.js';
import { Store } from './lib/store.js';
import { newKey, newId, normalizeKey } from './lib/codes.js';
import { loadLetter, loadWelcome, loadStory } from './lib/content.js';
import * as mollie from './lib/mollie.js';
import { sendKeyMail } from './lib/mail.js';

export function createApp(opts = {}) {
  const cfg = { ...config, ...opts };
  const store = new Store(cfg.dataDir);
  const mode = opts.paymentMode || paymentMode();
  const story = loadStory(cfg.contentDir);

  // ---------- hulpjes ----------

  const MIME = {
    '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
    '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon',
    '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8', '.xml': 'application/xml',
  };

  const SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Frame-Options': 'DENY',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
  };

  function send(res, status, body, headers = {}) {
    res.writeHead(status, { ...SECURITY_HEADERS, ...headers });
    res.end(body);
  }

  function json(res, status, data, headers = {}) {
    send(res, status, JSON.stringify(data), {
      'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...headers,
    });
  }

  function cookies(req) {
    const out = {};
    for (const part of (req.headers.cookie || '').split(';')) {
      const i = part.indexOf('=');
      if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
    }
    return out;
  }

  function cookie(name, value, maxAge) {
    const secure = cfg.baseUrl.startsWith('https://') ? '; Secure' : '';
    return `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAge}; HttpOnly; SameSite=Lax${secure}`;
  }
  const YEAR = 60 * 60 * 24 * 400;

  async function readBody(req, limit = 16 * 1024) {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > limit) throw Object.assign(new Error('te groot'), { status: 413 });
      chunks.push(chunk);
    }
    const text = Buffer.concat(chunks).toString('utf8');
    const type = req.headers['content-type'] || '';
    if (type.includes('application/json')) return text ? JSON.parse(text) : {};
    if (type.includes('application/x-www-form-urlencoded')) return Object.fromEntries(new URLSearchParams(text));
    return {};
  }

  // Simpele beperking per IP tegen misbruik.
  const hits = new Map();
  function limited(req, bucket, max, windowMs) {
    const ip = (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.socket.remoteAddress;
    const k = bucket + ':' + ip;
    const now = Date.now();
    const list = (hits.get(k) || []).filter((t) => now - t < windowMs);
    list.push(now);
    hits.set(k, list);
    if (hits.size > 5000) hits.clear();
    return list.length > max;
  }

  // ---------- toegang ----------

  function today() {
    return cfg.fakeToday || dateIn(cfg.timezone, opts.now ? opts.now() : new Date());
  }

  function access(req) {
    const c = cookies(req);
    const key = normalizeKey(c.jdkm_sleutel);
    return {
      owned: Boolean(key && store.getKey(key)),
      preview: Boolean(cfg.previewKey && c.jdkm_voorvertoning === cfg.previewKey),
    };
  }

  function status(n, day, acc) {
    if (acc.preview) return 'open';
    if (day < unlockDate(n, cfg.startDate)) return 'wacht';
    if (n <= cfg.freeLetters || acc.owned) return 'open';
    return 'kopen';
  }

  function priceLabel() {
    return '€ ' + cfg.price.toFixed(2).replace('.', ',');
  }

  // De klok van de server (bij FAKE_VANDAAG: die datum, met de echte tijd van de dag).
  function serverNow() {
    const real = opts.now ? opts.now() : new Date();
    if (!cfg.fakeToday) return real;
    const sinceMidnight = real - midnightUtc(dateIn(cfg.timezone, real), cfg.timezone);
    return new Date(midnightUtc(cfg.fakeToday, cfg.timezone).getTime() + sinceMidnight);
  }

  function state(req) {
    const acc = access(req);
    const day = today();
    const letters = [];
    for (let n = 1; n <= cfg.totalLetters; n++) {
      const s = status(n, day, acc);
      const entry = { n, status: s, opent: unlockDate(n, cfg.startDate) };
      if (s === 'open') entry.titel = loadLetter(cfg.contentDir, n)?.titel || '';
      letters.push(entry);
    }
    return {
      titel: story.titel,
      ondertitel: story.ondertitel,
      auteur: story.auteur,
      totaal: cfg.totalLetters,
      gratis: cfg.freeLetters,
      prijs: priceLabel(),
      startDatum: cfg.startDate,
      eindDatum: unlockDate(cfg.totalLetters, cfg.startDate),
      vandaag: day,
      nu: serverNow().toISOString(),
      volgendeMiddernacht: midnightUtc(addDays(day, 1), cfg.timezone).toISOString(),
      gekocht: acc.owned,
      voorvertoning: acc.preview,
      betalen: mode,
      mail: Boolean(cfg.resendKey),
      contact: story.contact || '',
      overVerhaal: story.overVerhaal || '',
      overAuteur: story.overAuteur || '',
      brieven: letters,
    };
  }

  // ---------- bestellingen ----------

  async function fulfill(order) {
    if (order.status !== 'paid' || order.key) return order;
    const key = newKey();
    order.key = key;
    order.paidAt = new Date().toISOString();
    store.putKey(key, { orderId: order.id, email: order.email || '' });
    store.putOrder(order);
    sendKeyMail({
      apiKey: cfg.resendKey, from: cfg.mailFrom, to: order.email, key,
      baseUrl: cfg.baseUrl, title: story.titel,
    }).catch((e) => console.error('mail mislukt:', e.message));
    return order;
  }

  async function refreshFromMollie(order) {
    if (mode !== 'mollie' || !order.paymentId || order.status === 'paid') return order;
    const payment = await mollie.getPayment(cfg.mollieKey, order.paymentId);
    order.status = payment.status;
    store.putOrder(order);
    return fulfill(order);
  }

  async function checkout(req, res) {
    if (limited(req, 'checkout', 20, 60 * 60 * 1000)) return json(res, 429, { fout: 'Even geduld, probeer het later opnieuw.' });
    if (mode === 'uit') return json(res, 503, { fout: 'Betalen is nog niet ingesteld.' });
    const body = await readBody(req);
    const email = String(body.email || '').trim().slice(0, 200);
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json(res, 400, { fout: 'Dat e-mailadres klopt niet helemaal.' });

    const order = { id: newId(), status: 'open', email, amount: cfg.price, createdAt: new Date().toISOString() };
    if (mode === 'test') {
      store.putOrder(order);
      return json(res, 200, { url: `/test-betaling?bestelling=${order.id}` });
    }
    const isPublic = !/localhost|127\.0\.0\.1/.test(cfg.baseUrl);
    const payment = await mollie.createPayment(cfg.mollieKey, {
      amount: { currency: 'EUR', value: cfg.price.toFixed(2) },
      description: `${story.titel}: alle ${cfg.totalLetters} brieven`,
      redirectUrl: `${cfg.baseUrl}/bedankt?bestelling=${order.id}`,
      ...(isPublic ? { webhookUrl: `${cfg.baseUrl}/api/mollie/webhook` } : {}),
      metadata: { orderId: order.id },
      locale: 'nl_NL',
    });
    order.paymentId = payment.id;
    store.putOrder(order);
    return json(res, 200, { url: payment._links.checkout.href });
  }

  async function webhook(req, res) {
    const body = await readBody(req);
    if (mode === 'mollie' && body.id) {
      try {
        const payment = await mollie.getPayment(cfg.mollieKey, body.id);
        const order = store.getOrder(payment.metadata?.orderId) || store.findOrderByPayment(payment.id);
        if (order && order.paymentId === payment.id) {
          order.status = payment.status;
          store.putOrder(order);
          await fulfill(order);
        }
      } catch (e) {
        console.error('webhook:', e.message);
      }
    }
    send(res, 200, 'ok');
  }

  async function orderStatus(req, res, id) {
    let order = store.getOrder(id);
    if (!order) return json(res, 404, { fout: 'Bestelling niet gevonden.' });
    try { order = await refreshFromMollie(order); } catch (e) { console.error(e.message); }
    if (order.status === 'paid' && order.key) {
      return json(res, 200, { status: 'paid', sleutel: order.key, email: order.email || '' }, {
        'Set-Cookie': cookie('jdkm_sleutel', order.key, YEAR),
      });
    }
    return json(res, 200, { status: order.status });
  }

  async function redeem(req, res) {
    if (limited(req, 'sleutel', 30, 10 * 60 * 1000)) return json(res, 429, { fout: 'Te veel pogingen. Probeer het over een paar minuten opnieuw.' });
    const body = await readBody(req);
    const key = normalizeKey(body.code);
    if (!key || !store.getKey(key)) return json(res, 404, { fout: 'Deze sleutel past op geen enkel slot.' });
    return json(res, 200, { ok: true, sleutel: key }, { 'Set-Cookie': cookie('jdkm_sleutel', key, YEAR) });
  }

  function testPaymentPage(res, id) {
    const order = store.getOrder(id);
    if (!order || mode !== 'test') return send(res, 404, 'Niet gevonden');
    const page = `<!doctype html><html lang="nl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Testbetaling</title><link rel="stylesheet" href="/css/test.css">
<main><h1>Testbetaling</h1><p>Mollie is nog niet ingesteld, dus dit is een nepbetaling om de flow te proberen.</p>
<p><strong>${priceLabel()}</strong> voor alle ${cfg.totalLetters} brieven</p>
<form method="post" action="/test-betaling"><input type="hidden" name="bestelling" value="${id}">
<button name="uitkomst" value="paid">Betaling gelukt</button> <button name="uitkomst" value="canceled" class="nee">Annuleren</button></form></main></html>`;
    send(res, 200, page, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
  }

  async function testPaymentSubmit(req, res) {
    const body = await readBody(req);
    const order = store.getOrder(body.bestelling);
    if (!order || mode !== 'test') return send(res, 404, 'Niet gevonden');
    order.status = body.uitkomst === 'paid' ? 'paid' : 'canceled';
    store.putOrder(order);
    await fulfill(order);
    send(res, 303, '', { Location: `/bedankt?bestelling=${order.id}` });
  }

  // ---------- statische bestanden ----------

  const SPA_ROUTES = /^\/(postkantoor|brief\/\d{1,2}|kopen|bedankt|sleutel|over)?\/?$/;

  async function serveFile(res, file, cache) {
    try {
      const info = await stat(file);
      if (!info.isFile()) throw new Error('geen bestand');
      const data = await readFile(file);
      const type = MIME[path.extname(file)] || 'application/octet-stream';
      send(res, 200, data, { 'Content-Type': type, 'Cache-Control': cache });
      return true;
    } catch {
      return false;
    }
  }

  async function serveStatic(req, res, pathname) {
    if (SPA_ROUTES.test(pathname)) {
      return serveFile(res, path.join(cfg.publicDir, 'index.html'), 'no-cache');
    }
    const decoded = decodeURIComponent(pathname);
    const file = path.normalize(path.join(cfg.publicDir, decoded));
    if (!file.startsWith(cfg.publicDir + path.sep)) return false;
    const cache = decoded.startsWith('/fonts/') ? 'public, max-age=31536000, immutable' : 'public, max-age=300';
    return serveFile(res, file, cache);
  }

  // ---------- router ----------

  async function handle(req, res) {
    const url = new URL(req.url, 'http://x');
    const p = url.pathname;
    const m = req.method;

    if (p === '/api/staat' && m === 'GET') return json(res, 200, state(req));

    if (p === '/api/welkom' && m === 'GET') {
      return json(res, 200, { n: 0, ...loadWelcome(cfg.contentDir) });
    }

    const letterMatch = p.match(/^\/api\/brief\/(\d{1,2})$/);
    if (letterMatch && m === 'GET') {
      const n = Number(letterMatch[1]);
      if (n < 1 || n > cfg.totalLetters) return json(res, 404, { fout: 'Deze brief bestaat niet.' });
      const s = status(n, today(), access(req));
      if (s !== 'open') return json(res, 403, { reden: s, opent: unlockDate(n, cfg.startDate) });
      const letter = loadLetter(cfg.contentDir, n);
      if (!letter) return json(res, 404, { fout: 'Deze brief is nog niet geschreven.' });
      return json(res, 200, { n, ...letter });
    }

    if (p === '/api/afrekenen' && m === 'POST') return checkout(req, res);
    if (p === '/api/mollie/webhook' && m === 'POST') return webhook(req, res);
    const orderMatch = p.match(/^\/api\/bestelling\/([\w-]{10,40})$/);
    if (orderMatch && m === 'GET') return orderStatus(req, res, orderMatch[1]);
    if (p === '/api/sleutel' && m === 'POST') return redeem(req, res);
    if (p === '/api/sleutel' && m === 'DELETE') {
      return json(res, 200, { ok: true }, { 'Set-Cookie': cookie('jdkm_sleutel', '', 0) });
    }

    if (p === '/test-betaling' && m === 'GET') return testPaymentPage(res, url.searchParams.get('bestelling'));
    if (p === '/test-betaling' && m === 'POST') return testPaymentSubmit(req, res);

    if (p === '/voorvertoning' && m === 'GET') {
      const ok = cfg.previewKey && url.searchParams.get('sleutel') === cfg.previewKey;
      return send(res, 302, '', {
        Location: '/postkantoor',
        ...(ok ? { 'Set-Cookie': cookie('jdkm_voorvertoning', cfg.previewKey, 60 * 60 * 24 * 60) } : {}),
      });
    }
    if (p === '/voorvertoning/uit') {
      return send(res, 302, '', { Location: '/postkantoor', 'Set-Cookie': cookie('jdkm_voorvertoning', '', 0) });
    }

    if (p.startsWith('/api/')) return json(res, 404, { fout: 'Onbekend adres.' });

    if (m === 'GET' || m === 'HEAD') {
      if (await serveStatic(req, res, p)) return;
    }
    const notFound = await readFile(path.join(cfg.publicDir, 'index.html'));
    send(res, 404, notFound, { 'Content-Type': 'text/html; charset=utf-8' });
  }

  return {
    store,
    handler: (req, res) => {
      handle(req, res).catch((e) => {
        console.error(e);
        if (!res.headersSent) json(res, e.status || 500, { fout: 'Er ging iets mis in het postkantoor.' });
      });
    },
  };
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname);
if (isMain) {
  const app = createApp();
  http.createServer(app.handler).listen(config.port, () => {
    console.log(`Het postkantoor is open op http://localhost:${config.port}  (betalen: ${paymentMode()})`);
  });
}
