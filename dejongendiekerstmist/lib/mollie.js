const API = 'https://api.mollie.com/v2';

async function call(key, method, url, body) {
  const res = await fetch(API + url, {
    method,
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(`Mollie ${res.status}: ${json.detail || json.title || 'onbekende fout'}`);
    err.status = res.status;
    throw err;
  }
  return json;
}

export function createPayment(key, payload) {
  return call(key, 'POST', '/payments', payload);
}

export function getPayment(key, id) {
  return call(key, 'GET', `/payments/${encodeURIComponent(id)}`);
}
