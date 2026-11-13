// Maak handmatig een sleutel aan, bijvoorbeeld als cadeau, voor de pers of voor vrienden.
// Gebruik: npm run sleutel -- "Voor oma"
import { config } from '../lib/config.js';
import { Store } from '../lib/store.js';
import { newKey } from '../lib/codes.js';

const notitie = process.argv.slice(2).join(' ') || 'handmatig';
const store = new Store(config.dataDir);
const key = newKey();
store.putKey(key, { orderId: null, email: '', notitie });
console.log(`Nieuwe sleutel: ${key}`);
console.log(`Directe link:   ${config.baseUrl}/sleutel?code=${key}`);
