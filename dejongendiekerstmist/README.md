# De Jongen die Kerst Mist

Webapp voor het adventsverhaal van Nadia op **www.dejongendiekerstmist.nl**. Vierentwintig brieven, elke nacht in december om 00:00 (Nederlandse tijd) gaat er één open. De eerste drie zijn gratis, voor de rest koop je eenmalig een sleutel.

Wat erin zit:

- **Magische intro**: kaarslicht, een proloog over de fabrieksstad, een deur met kerstkrans die je met een gouden sleutel opent.
- **Onboarding met Grote Gijs**: de postmuis kruipt uit een brievenbus, vraagt je naam, legt uit hoe het werkt en laat je zijn welkomstbrief openen door het lakzegel te breken.
- **Het postkantoor**: een postvakkenkast als adventskalender, een zakhorloge dat aftelt naar de volgende brief, en Gijs in de hoek met tips, weetjes en grapjes.
- **De lezer**: envelop met lakzegel (ingedrukt houden om te breken), brief op perkament, lettergrootte instelbaar, bladeren naar vorige en volgende brief.
- **Kopen**: betalen via Mollie (iDEAL, creditcard, Apple Pay), daarna een sleutelceremonie. De koper krijgt een persoonlijke sleutel (bijv. `J4JD-EEDJ-M9RE`) waarmee de brieven ook op andere apparaten opengaan.
- **Geluid** (optioneel): wind, haardvuur, krakend zegel, klokjes en een muziekdoos met *Stille nacht*. Alles wordt live in de browser gemaakt, er zijn geen audiobestanden.
- Werkt op telefoon, tablet en computer. Geen trackers, alleen een functioneel cookie voor de sleutel.

## Lokaal starten

Nodig: Node.js 20.12 of nieuwer. Er zijn geen andere pakketten nodig.

```bash
cd dejongendiekerstmist
npm start
```

Open http://localhost:3000. Zonder Mollie-sleutel draait de site in **testmodus**: bij kopen krijg je een nepbetaalpagina.

Doen alsof het een andere dag is:

```bash
FAKE_VANDAAG=2026-12-05 npm start
```

Tests draaien:

```bash
npm test
```

## De brieven

De brieven staan in `content/brieven/01.md` tot en met `24.md`. Nu staan er plaatshouders in. Zo ziet een brief eruit:

```
---
titel: De eerste sneeuw
plaats: Manchester
datum: 1 december 1843
aanhef: Lieve Thomas,
groet: Je liefhebbende moeder,
ondertekening: Margaret
naschrift: Vergeet je wanten niet.
---

Hier begint de brief. Een lege regel betekent een nieuwe alinea.

Gebruik *sterretjes* voor cursief en **dubbele** voor vet.

***

Drie sterretjes op een eigen regel geven een sierlijk scheidingsteken.
```

- Alle velden bovenaan zijn optioneel. Laat een veld weg of leeg als het niet nodig is.
- `{naam}` wordt vervangen door de naam die de lezer aan Gijs gaf. Bijvoorbeeld `aanhef: Lieve {naam},`.
- De titel verschijnt alleen voor brieven die al open zijn, dus er wordt niets verklapt.
- Wijzigingen zijn meteen zichtbaar, de server hoeft niet opnieuw te starten.

Verder:

- `content/welkom.md`: de welkomstbrief van Gijs uit de onboarding.
- `content/verhaal.json`: titel, auteur, contactadres en de teksten bij *Over het verhaal* (nu plaatshouders).
- Gijs' weetjes en grapjes staan in `public/js/main.js` (zoek naar `WEETJES`).

## Instellingen

Kopieer `.env.example` naar `.env` en vul in:

| Instelling | Uitleg |
|---|---|
| `BASE_URL` | `https://www.dejongendiekerstmist.nl` |
| `START_DATUM` | Datum van brief 1, standaard `2026-12-01` |
| `GRATIS_BRIEVEN` | Standaard `3` |
| `PRIJS` | In euro, standaard `9.95` |
| `MOLLIE_API_KEY` | Begin met een `test_` sleutel, daarna `live_` |
| `PREVIEW_KEY` | Geheim woord voor de voorvertoning (zie hieronder) |
| `RESEND_API_KEY`, `MAIL_VAN` | Optioneel: sleutel ook per e-mail naar de koper |

## Voorvertoning voor Nadia

Zet een `PREVIEW_KEY` in `.env` en open:

```
https://www.dejongendiekerstmist.nl/voorvertoning?sleutel=<PREVIEW_KEY>
```

Dan zijn alle brieven open, ongeacht de datum, op dat apparaat. Stoppen kan via de knop in het postkantoor.

## Sleutels handmatig maken

Voor cadeaus, de pers of vrienden:

```bash
npm run sleutel -- "Voor oma"
```

Je krijgt een sleutel en een directe link (`/sleutel?code=...`) die hem meteen verzilvert.

## Betalen met Mollie

1. Maak een account op mollie.com en activeer iDEAL (en eventueel creditcard en Apple Pay).
2. Zet de test-API-sleutel in `MOLLIE_API_KEY` en probeer een betaling.
3. Werkt het, vervang hem door de live-sleutel.

Mollie meldt betalingen via `https://www.dejongendiekerstmist.nl/api/mollie/webhook`. Dat gaat vanzelf, mits `BASE_URL` klopt.

## Hosten

De app is één Node-proces. Bestellingen en sleutels worden opgeslagen in `data/winkel.json`. **Die map moet blijvende opslag hebben**, anders raken kopers hun sleutel kwijt bij een herstart. Maak er af en toe een back-up van.

Twee eenvoudige routes:

- **Eigen VPS** (bijv. bij een Nederlandse hoster): Node installeren, `npm start` laten draaien met systemd of pm2, en Caddy ervoor voor automatische HTTPS.
- **Render, Railway of Fly.io** met de meegeleverde `Dockerfile`, plus een *persistent disk/volume* gekoppeld aan `/app/data`.

Daarna bij je domeinregistrar de DNS van `www.dejongendiekerstmist.nl` naar de server laten wijzen, en `dejongendiekerstmist.nl` doorsturen naar `www`.

## Nog te doen

- [ ] De 24 brieven van Nadia in `content/brieven/`
- [ ] Teksten *Over het verhaal* en *Over Nadia* in `content/verhaal.json`
- [ ] Contactadres controleren in `content/verhaal.json`
- [ ] Prijs bepalen
- [ ] Mollie-account en API-sleutel
- [ ] Hosting kiezen en domein koppelen
- [ ] Optioneel: Resend voor e-mail met de sleutel
