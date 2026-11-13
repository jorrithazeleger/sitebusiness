// Optioneel: stuur de sleutel per e-mail via Resend (https://resend.com).
export async function sendKeyMail({ apiKey, from, to, key, baseUrl, title }) {
  if (!apiKey || !to) return false;
  const link = `${baseUrl}/sleutel?code=${encodeURIComponent(key)}`;
  const text = [
    'Beste lezer,',
    '',
    `Dank je wel voor het kopen van "${title}". Hieronder staat je persoonlijke sleutel.`,
    'Daarmee open je alle brieven, ook op je telefoon of tablet.',
    '',
    `   ${key}`,
    '',
    `Op een ander apparaat? Klik op deze link: ${link}`,
    '',
    'Elke nacht in december om twaalf uur ligt er een nieuwe brief klaar.',
    '',
    'Met een staartzwaai,',
    'Grote Gijs',
    'Hoofdbesteller van het Postkantoor',
  ].join('\n');
  const html = `<div style="font-family:Georgia,serif;max-width:520px;margin:auto;padding:32px;background:#f4e9d2;color:#2b1d12;border-radius:8px">
<p>Beste lezer,</p>
<p>Dank je wel voor het kopen van <em>${title}</em>. Hieronder staat je persoonlijke sleutel. Daarmee open je alle brieven, ook op je telefoon of tablet.</p>
<p style="font-size:26px;letter-spacing:4px;text-align:center;font-family:monospace;background:#fff8e8;border:1px dashed #a07a3b;padding:16px">${key}</p>
<p style="text-align:center"><a href="${link}" style="background:#7a1f1f;color:#fff;padding:12px 20px;border-radius:6px;text-decoration:none">Open het postkantoor</a></p>
<p>Elke nacht in december om twaalf uur ligt er een nieuwe brief klaar.</p>
<p>Met een staartzwaai,<br><em>Grote Gijs</em><br><small>Hoofdbesteller van het Postkantoor</small></p></div>`;
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from, to, subject: `Je sleutel voor ${title}`, text, html }),
  });
  return res.ok;
}
