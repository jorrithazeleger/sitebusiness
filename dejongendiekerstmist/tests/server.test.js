import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createApp } from '../server.js';

let server, base, dataDir;
let fakeToday = '2026-12-05';

before(async () => {
  dataDir = mkdtempSync(path.join(tmpdir(), 'jdkm-'));
  const app = createApp({ dataDir, paymentMode: 'test', previewKey: 'geheim', baseUrl: 'http://localhost', fakeToday: '' , now: () => new Date(`${fakeToday}T12:00:00Z`) });
  server = http.createServer(app.handler);
  await new Promise((r) => server.listen(0, r));
  base = `http://localhost:${server.address().port}`;
});
after(() => { server.close(); rmSync(dataDir, { recursive: true, force: true }); });

const get = (p, cookie = '') => fetch(base + p, { headers: { cookie }, redirect: 'manual' });

test('gratis brieven zijn open zodra hun datum er is', async () => {
  fakeToday = '2026-12-02';
  const staat = await (await get('/api/staat')).json();
  assert.deepEqual(staat.brieven.slice(0, 4).map((b) => b.status), ['open', 'open', 'wacht', 'wacht']);
  assert.equal((await get('/api/brief/2')).status, 200);
  assert.equal((await get('/api/brief/3')).status, 403);
});

test('na de gratis brieven moet je kopen', async () => {
  fakeToday = '2026-12-05';
  const r = await get('/api/brief/4');
  assert.equal(r.status, 403);
  assert.equal((await r.json()).reden, 'kopen');
});

test('kopen in testmodus levert een sleutel op die brieven opent', async () => {
  fakeToday = '2026-12-05';
  const { url } = await (await fetch(base + '/api/afrekenen', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' })).json();
  const id = new URL(url, base).searchParams.get('bestelling');
  const betaal = await fetch(base + '/test-betaling', {
    method: 'POST', redirect: 'manual',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: `bestelling=${id}&uitkomst=paid`,
  });
  assert.equal(betaal.status, 303);
  const status = await get(`/api/bestelling/${id}`);
  const body = await status.json();
  assert.equal(body.status, 'paid');
  const cookie = status.headers.get('set-cookie').split(';')[0];
  assert.equal((await get('/api/brief/4', cookie)).status, 200);
  assert.equal((await get('/api/brief/6', cookie)).status, 403, 'toekomstige brief blijft dicht');

  // dezelfde sleutel werkt op een ander apparaat
  const redeem = await fetch(base + '/api/sleutel', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ code: body.sleutel.toLowerCase() }) });
  assert.equal(redeem.status, 200);
});

test('een verkeerde sleutel past niet', async () => {
  const r = await fetch(base + '/api/sleutel', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{"code":"AAAA-BBBB-CCCC"}' });
  assert.equal(r.status, 404);
});

test('voorvertoning opent alles, ook toekomstige brieven', async () => {
  fakeToday = '2026-11-20';
  const r = await get('/voorvertoning?sleutel=geheim');
  const cookie = r.headers.get('set-cookie').split(';')[0];
  assert.equal((await get('/api/brief/24', cookie)).status, 200);
  assert.equal((await get('/api/brief/24')).status, 403);
  const fout = await get('/voorvertoning?sleutel=fout');
  assert.equal(fout.headers.get('set-cookie'), null);
});

test('pagina-routes en beveiliging', async () => {
  assert.equal((await get('/postkantoor')).status, 200);
  assert.equal((await get('/brief/7')).status, 200);
  assert.equal((await get('/../server.js')).status, 404);
  assert.equal((await get('/%2e%2e/server.js')).status, 404);
  assert.match((await get('/')).headers.get('content-security-policy'), /default-src 'self'/);
});
