import { randomBytes } from 'node:crypto';

// Zonder verwarrende tekens als 0/O en 1/I/L.
const ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';

export function newKey() {
  const bytes = randomBytes(12);
  let raw = '';
  for (const b of bytes) raw += ALPHABET[b % ALPHABET.length];
  return `${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}`;
}

export function normalizeKey(input) {
  const raw = String(input || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (raw.length !== 12) return null;
  if ([...raw].some((c) => !ALPHABET.includes(c))) return null;
  return `${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}`;
}

export function newId() {
  return randomBytes(16).toString('base64url');
}
