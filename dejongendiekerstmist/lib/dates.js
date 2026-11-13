// Datumlogica: brief n gaat open op START_DATUM + (n - 1) dagen, om middernacht in Nederland.

const formatters = new Map();
function formatter(timeZone) {
  if (!formatters.has(timeZone)) {
    formatters.set(timeZone, new Intl.DateTimeFormat('en-CA', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    }));
  }
  return formatters.get(timeZone);
}

function parts(date, timeZone) {
  const out = {};
  for (const p of formatter(timeZone).formatToParts(date)) out[p.type] = p.value;
  return out;
}

/** Datum als 'JJJJ-MM-DD' in de gegeven tijdzone. */
export function dateIn(timeZone, now = new Date()) {
  const p = parts(now, timeZone);
  return `${p.year}-${p.month}-${p.day}`;
}

export function addDays(dateStr, days) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + days));
  return t.toISOString().slice(0, 10);
}

/** Verschil in minuten tussen de tijdzone en UTC op dat moment. */
function offsetMinutes(date, timeZone) {
  const p = parts(date, timeZone);
  const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  return Math.round((asUtc - Math.floor(date.getTime() / 1000) * 1000) / 60000);
}

/** Het UTC-moment van middernacht aan het begin van dateStr in de tijdzone. */
export function midnightUtc(dateStr, timeZone) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const guess = Date.UTC(y, m - 1, d);
  let t = guess - offsetMinutes(new Date(guess), timeZone) * 60000;
  t = guess - offsetMinutes(new Date(t), timeZone) * 60000;
  return new Date(t);
}

export function unlockDate(n, startDate) {
  return addDays(startDate, n - 1);
}

export function daysBetween(a, b) {
  return Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000);
}
