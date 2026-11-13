import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dateIn, addDays, midnightUtc, unlockDate } from '../lib/dates.js';
import { newKey, normalizeKey } from '../lib/codes.js';
import { parseFrontmatter, renderBody } from '../lib/content.js';

test('datum in Nederland wisselt om middernacht lokale tijd', () => {
  assert.equal(dateIn('Europe/Amsterdam', new Date('2026-12-04T22:59:59Z')), '2026-12-04');
  assert.equal(dateIn('Europe/Amsterdam', new Date('2026-12-04T23:00:00Z')), '2026-12-05');
});

test('middernacht in december is 23:00 UTC, in de zomer 22:00 UTC', () => {
  assert.equal(midnightUtc('2026-12-05', 'Europe/Amsterdam').toISOString(), '2026-12-04T23:00:00.000Z');
  assert.equal(midnightUtc('2026-07-01', 'Europe/Amsterdam').toISOString(), '2026-06-30T22:00:00.000Z');
});

test('brief n opent op startdatum + n - 1', () => {
  assert.equal(unlockDate(1, '2026-12-01'), '2026-12-01');
  assert.equal(unlockDate(24, '2026-12-01'), '2026-12-24');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
});

test('sleutels hebben het juiste formaat en worden genormaliseerd', () => {
  const k = newKey();
  assert.match(k, /^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/);
  assert.equal(normalizeKey(k.toLowerCase().replace(/-/g, ' ')), k);
  assert.equal(normalizeKey('kort'), null);
  assert.equal(normalizeKey('ABCD-EFGH-IJK0'), null);
});

test('brieftekst wordt veilig omgezet naar HTML', () => {
  const { meta, body } = parseFrontmatter('---\ntitel: Een titel\naanhef: Lieve {naam},\n---\n\nEerste *alinea* <script>x</script>\n\n***\n\nTweede\nregel');
  assert.equal(meta.titel, 'Een titel');
  assert.equal(meta.aanhef, 'Lieve {naam},');
  const html = renderBody(body);
  assert.match(html, /<em>alinea<\/em>/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /class="sep"/);
  assert.match(html, /Tweede<br>regel/);
});
