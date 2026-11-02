# Udyam Digital prototype

A digital-first journey that lets a small business owner find the right telecom bundle, buy it and get it activated on a phone, in their language. Built for Airtel SYNC / YTL Hackathon 2026, Track A. All data is synthetic.

## What's here

| Part | State |
|---|---|
| Web app: advisor, quote, KYC, tracker, back office (Next.js) | Working |
| AI advisor in 10 languages: Groq, then Gemini, then a guided flow with no AI | Working |
| Catalogue rules, pricing, bundle recommender | Working |
| Mock GSTIN and Udyam lookups | Working |
| Smart KYC: consent, local OCR, validation, erase | Working |
| Order tracker, with a demo control that moves an order on | Working |
| Back-office queue and lead score | Working |
| Voice input | Built but untested. Needs a browser with speech recognition, and HTTPS on a phone |
| E-sign, payment, real registries, WhatsApp front end | Mocked or not built |

## Run it

You need Python 3.10+, Node 20+ and free API keys from [Groq](https://console.groq.com/keys) and [Google AI Studio](https://aistudio.google.com/apikey). The app still works without keys, using the guided flow.

**API**, from `prototype/backend`:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Then put your keys in `.env`. API docs are at http://127.0.0.1:8000/docs.

**Web app**, from `prototype/frontend`, in a second terminal:

```bash
npm install
npm run dev
```

Open http://localhost:3000 on a phone-sized window. In the KYC step, the "Demo" box loads any of the 12 specimen applicants. The back office is at http://localhost:3000/backoffice.

## Test it

From `prototype/backend`:

```bash
.venv/Scripts/python -m pytest
```

This includes real OCR on all 47 specimen images, which takes about two minutes. To skip that:

```bash
.venv/Scripts/python -m pytest -m "not slow"
```

Test conversations through the real AI models, which use free-tier quota:

```bash
.venv/Scripts/python -m scripts.advisor_scenarios
```

The whole journey in a real browser, from `prototype/frontend` with both servers running. It uses Microsoft Edge and saves screenshots:

```bash
node e2e/journey.mjs
```

## Free-tier limits to plan around

- Groq allows about 200,000 tokens a day and 8,000 a minute per model. A recommendation uses about 3,000 tokens, so that's roughly 65 a day on the best model.
- Heavy testing uses this up, and it recovers over a rolling 24 hours. **Don't run the AI scenario scripts in the 24 hours before a live demo.**
- When the best model is out, the chain moves to Gemini, then Groq's smaller models, which misread more. Requests for billing, CCTV, WhatsApp, leased lines, SD-WAN and similar are caught in code, so those aren't lost.
- With everything out, the guided flow takes over. English, Hindi, Tamil and Kannada have fixed wording; the other six languages fall back to English in that case.

## Design decisions

- **The AI never decides what's allowed or what it costs.** It only turns the conversation into structured facts and words the reply. Code decides when to recommend, and a rules engine picks the products and prices, so a recommendation can't break a catalogue rule, however the conversation goes. Replaying all 5,000 leads gives no rule breaks.
- **The model doesn't see identifiers.** GSTIN, Udyam, PAN, Aadhaar, phone and email are stripped from each message before it reaches a provider. A reply quoting a number the rules engine didn't return is replaced with fixed wording.
- **KYC documents never go to an AI provider.** They're read locally with open-source OCR. This also fits the free-tier constraint: Gemini's terms let Google use free-tier content to improve its products, with human review.
- **A rate limit can't break the demo.** Free tiers are tight, so the advisor works through three Groq models (limits apply per model), then Gemini, then a guided flow that needs no AI and keeps what the conversation already learned.
- **Lookups use exact identifiers, never names.** Names repeat across unrelated businesses in the data. Identifiers travel in POST bodies, so they stay out of URLs and access logs.
- **Pricing is one rule.** Start at the top of the catalogue range, and step down a quarter of the range for each of: a 12-month contract (two steps for 24 months), an add-on bought with an Accel connection, and a micro business. It never goes below the catalogue floor. Replaying last quarter's bundles through this rule changes revenue by -1.6%.

## Numbers for the deck

From `prototype/backend`:

```bash
.venv/Scripts/python -m scripts.replay_quarter
```
