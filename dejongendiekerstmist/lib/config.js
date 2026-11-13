import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const envFile = path.join(ROOT, '.env');
if (existsSync(envFile) && typeof process.loadEnvFile === 'function') {
  process.loadEnvFile(envFile);
}

const env = process.env;

function num(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export const config = {
  port: num(env.PORT, 3000),
  baseUrl: (env.BASE_URL || 'http://localhost:3000').replace(/\/$/, ''),
  production: env.NODE_ENV === 'production',
  timezone: 'Europe/Amsterdam',
  startDate: env.START_DATUM || '2026-12-01',
  totalLetters: 24,
  freeLetters: num(env.GRATIS_BRIEVEN, 3),
  price: num(env.PRIJS, 9.95),
  mollieKey: env.MOLLIE_API_KEY || '',
  previewKey: env.PREVIEW_KEY || '',
  resendKey: env.RESEND_API_KEY || '',
  mailFrom: env.MAIL_VAN || 'De Jongen die Kerst Mist <post@dejongendiekerstmist.nl>',
  fakeToday: env.FAKE_VANDAAG || '',
  dataDir: env.DATA_DIR || path.join(ROOT, 'data'),
  contentDir: env.CONTENT_DIR || path.join(ROOT, 'content'),
  publicDir: path.join(ROOT, 'public'),
};

export function paymentMode() {
  if (config.mollieKey) return 'mollie';
  return config.production ? 'uit' : 'test';
}
