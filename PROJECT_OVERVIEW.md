# Project Udyam Digital: project overview

A small business owner finds the right telecom bundle, buys it and gets it activated from a phone, in their own language, without a salesperson. Built for Airtel SYNC / YTL Hackathon 2026, Enterprise Track A. The operator, "Accel Business", is fictional and all data is synthetic.

**Status as of 2 Nov 2026:** the prototype works end to end, and the 7-slide deck is ready for review. See [What's real and what's mocked](#whats-real-and-whats-mocked) before you demo it.

## Web app or mobile app?

**It's a web app only, designed for phones.** You open it in a phone's browser, and its screens are laid out for phone size. It also works in a laptop browser.

- There's no Android or iOS app, and nothing to download from an app store.
- It can't be installed to a phone's home screen, because it has no web app manifest or service worker.
- It has only been tested in an emulated phone screen (390 × 844) on a laptop browser, not on a physical phone.

## Start the app

### If it's already set up

If it's a fresh clone, follow [On a new machine](#on-a-new-machine) first. Open two terminals (PowerShell or Git Bash) in the project folder.

**Terminal 1, the API:**

```bash
cd prototype/backend
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

**Terminal 2, the web app:**

```bash
cd prototype/frontend
npm run dev
```

Then open these. Press Ctrl+C in each terminal to stop.

| Address | What it is |
|---|---|
| http://localhost:3000 | The app. For a phone-sized view, press F12 and turn on the device toolbar. |
| http://localhost:3000/track | Look up an order by its number |
| http://localhost:3000/backoffice | Back office for sales and partners |
| http://localhost:8000/docs | Interactive API documentation |

### On a real phone

The phone needs **production mode**. With `npm run dev`, Next.js blocks other devices: the page loads, but tapping does nothing.

1. Connect the phone and the laptop to the same Wi-Fi. Campus and public Wi-Fi often block devices from reaching each other. If it won't connect, use your phone's hotspot instead.
2. Keep the API running. Stop `npm run dev`, then build and start the web app:

   ```bash
   cd prototype/frontend
   npm run build
   npm start
   ```

3. Find the laptop's address by running `ipconfig` and reading the IPv4 Address under Wi-Fi.
4. On the phone, open `http://<that address>:3000`.
5. If Windows Firewall asks, allow Node.js on private networks.

Run `npm run build` again after any change to the web app. The full KYC flow and uploads were tested this way through the laptop's Wi-Fi address.

### On a new machine

You need Python 3.10, 3.11 or 3.12, because the OCR library won't install on 3.13 or later, and Node 20.9 or later. This was tested with Python 3.10 and Node 24 on Windows. On Mac or Linux, use `.venv/bin/python`; that path is untested.

```bash
cd prototype/backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
```

Put free keys from [Groq](https://console.groq.com/keys) and [Google AI Studio](https://aistudio.google.com/apikey) into `.env`. Without keys, the app still runs using the guided flow, with no AI.

```bash
cd prototype/frontend
npm install
```

Then start both as above.

The first `npm run build` downloads a font from Google, so it needs a working connection. If it stops with `Can't resolve '@vercel/turbopack-next/internal/font/google/font'`, check your connection and run it again.

### A quick walkthrough

1. Choose a language and press Start.
2. Send: `I run a kirana store in Nagpur with 2 people, one shop. No GST. I need billing and CCTV.` You should get a plan at ₹2,545 a month plus GST.
3. Press **See my price**. Switch an extra on and off, and watch the price change.
4. Continue to documents and accept the consent screen. In the **Demo** box, choose an applicant from the table below, then press **Check my documents**.
5. If it passes, press **E-sign and pay** and place the order. On the tracker, press **Simulate next step**.
6. Open the back office.

| Applicant | What's planted | Result |
|---|---|---|
| K01 | GSTIN cancelled, Udyam number blank | Can't continue on this registration |
| K02 | GST scan rotated (handled); role "Manager" | Passes, with a note |
| K03 | Nothing | Passes |
| K04 | GST certificate blurred | Upload again |
| K05 | Udyam certificate missing; role "Owner" on an LLP | Fetched from the registry, with a note |
| K06 | One digit of the GSTIN changed | A person reviews it |
| K07 | Legal name doesn't match the registry | A person reviews it |
| K08, K09 | Role "Office admin" | Passes, with a note |
| K10 | The person on the ID isn't the applicant | A person reviews it |
| K11 | Electricity bill is 257 days old | Upload again |
| K12 | Nothing, though other businesses share its name | Passes |

These are our own reading of the planted problems. The official answer key is with the judges.

## Features

### Home
- Choose from 10 languages: English, Hindi, Marathi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati and Punjabi.
- Links to order tracking and the back office.

### AI advisor
- The owner describes the business in their own words, in their own language, by typing or by voice.
- It asks only for what's missing: business type, staff, sites, city and GST status. Once it has those, it recommends straight away.
- It explains the plan in plain language, in the owner's language, with one clear price.
- The conversation can change the plan: "remove the cameras", or a new number of staff.
- It handles the cases where a plain "yes" would be wrong:

| The owner says | What happens |
|---|---|
| Wants WhatsApp, has no GST | Says no, gives the reason and offers an alternative |
| Gives a cancelled or altered GSTIN | Checks it and treats it as no GST |
| Wants 1 Gbps in a tier-2 city | Says it isn't sold there, and offers 300 Mbps |
| Wants a leased line with 5 staff | Explains the 10-employee minimum, and offers an alternative |
| Wants SD-WAN with 2 sites | Explains the 3-site minimum |
| Fibre can't reach the site | Offers AirFiber, and explains why failover won't work with it |
| Only wants mobile lines | Sells just those, month to month |
| Gives a budget | Fits the plan to it, and says if it's impossible |
| Asks for something not sold | Says so plainly |
| Asks for a discount | Says prices are fixed by the plan |
| City isn't on the list | Gives an indicative plan, and says a partner will confirm coverage |

- **Guided mode:** if every AI model is unavailable, it carries on with simple questions and buttons, keeping what it already learned. The screen shows which mode is on.

### Quote and checkout
- One monthly price, with GST shown separately and the total with GST.
- Every item has a plain-language reason and an on/off switch. Product codes are never shown.
- Extras show their exact added price, any setup fee, and whether they need a longer contract.
- Quantity buttons for lines, users, cameras, devices, counters, vehicles and channels.
- Contract options with the price for each.
- Shows the saving against list price, the one-time setup fee, the expected go-live time, and the difference from current spend if the owner mentioned it.
- Explains why anything asked for isn't available.
- Blocks checkout if a change breaks a rule, such as removing the connection that CCTV depends on.

### Smart KYC
- **Consent first:** nothing is read until the owner agrees to a screen covering purpose, data, handling, retention and their rights.
- **Asks only for what it can't verify:** a verified GSTIN removes the GST certificate, installing at the GST address removes the bill, and a plan with no GST products doesn't ask for GST.
- **Reads uploaded documents locally:** checks for blur, removes the watermark, handles tilted scans and extracts the fields.
- **Validates them:**
  - GSTIN format, state code and checksum, plus OCR repair that can't hide a changed digit
  - Registry status and whether it's active
  - Names and addresses against the registry and across documents
  - Udyam number and details
  - Address proof no older than 90 days
  - ID expiry
  - Whether the signatory is the applicant or proprietor, and whether their role makes sense
  - A document uploaded in the wrong slot
- **Six possible results,** with reasons the owner can act on: passes, passes with a note, gap filled from the registry, upload again, a person reviews it, or can't continue.
- Identifiers are masked on screen, such as `27**********1ZP`.
- An erase button deletes the application.
- The demo box loads any of the 12 specimen applicants.

### Order tracker
- A go-live date as the headline, with the reassurance that there's no need to call.
- A timeline of stages with dates. Orders with a visit go: placed, documents verified, site check, visit scheduled, installed, live. Others go: placed, documents verified, SIM delivered, live.
- What's next, and a go-live date for each service.
- A shareable page at `/track/<order number>`, in the owner's language.

### Back office
- 4,313 leads that didn't close from last quarter's data, highest score first. Leads who said no, are locked into a contract or asked to wait come last.
- For each lead: the score, why it dropped, why it's worth calling, who should call (field sales, a local partner or digital follow-up) and the next step. The owner and next step come from fixed rules, not the score.
- Filters by owner, and contact names are masked. The screen shows the top 40 for each filter.
- The score shows how often similar leads activated when they first came in. It isn't the chance of winning a dropped lead back, because the data has no win-backs to test that.
- The score was tested on leads it hadn't seen, averaged over 200 random splits: AUC 0.71 (most splits fell between 0.68 and 0.74), and the top-scored 20% hold 40% of activations, twice the average rate.
- On unseen leads, scores under 30% match what happened: for example, leads scored 20-30% activated 22% of the time. Only 11 leads scored 30% or more, too few to judge.

### Languages

| | Languages | What works |
|---|---|---|
| **Full support** | English, Hindi, Tamil, Kannada | Every screen, reason, rule explanation and KYC message, even with no AI |
| **Chat support** | Marathi, Telugu, Malayalam, Bengali, Gujarati, Punjabi | AI chat in the language, with English screens. Falls back to English if the AI is unavailable |

## Architecture

```
  Owner's phone browser                  Laptop browser (back office)
            │                                       │
            └──────────────────┬────────────────────┘
                               ▼
                 Web app: Next.js, port 3000
          Screens only. Forwards /api/* to the API. Holds a session id.
                               │
                               ▼
                    API: FastAPI, port 8000
  ┌───────────────┬───────────────┬───────────────┬───────────────┐
  │    Advisor    │  Rules engine │   Smart KYC   │ Orders, back  │
  │               │               │               │ office, score │
  └───────┬───────┴───────┬───────┴───────┬───────┴───────┬───────┘
          │               │               │               │
          ▼               ▼               ▼               ▼
      AI models        Product       GSTIN, Udyam      Lead data,
   (no identifiers)   catalogue     mock registries    trained score
```

### The main idea: the AI talks, the rules decide

The AI model has two narrow jobs: turn what the owner says into structured facts, and word the explanation. Code decides when to recommend, and a rules engine decides what's allowed and what it costs. So the AI can't talk a price down or sell something a business isn't eligible for.

**What happens on each chat message:**

1. Identifiers (GSTIN, Udyam, PAN, Aadhaar, phone, email) are stripped before anything reaches an AI provider. GSTIN and Udyam are kept on the server for our own lookups.
2. The model extracts the facts. Code also spots common requests itself, such as CCTV, billing and leased line, and reads them clause by clause so "no CCTV" doesn't add CCTV.
3. If a required fact is missing, it asks for that. If all five are known, the rules engine builds the plan.
4. A second model call writes the explanation from the plan's facts only, leaving out the owner's words so a request can't be echoed back as a promise.
5. If that reply quotes a price or a speed the rules engine didn't return, it's thrown away for fixed wording.
6. If no AI model is available, the guided flow takes over.

### The parts

| Part | Files in `prototype/backend/app` | What it does |
|---|---|---|
| Advisor | `advisor.py`, `llm.py`, `advisor_text.py` | The conversation, its safeguards, the model fallback chain and the guided flow |
| Rules engine | `recommender.py`, `rules.py`, `pricing.py`, `profile.py`, `catalogue.py`, `product_text.py` | Eligibility, dependencies, budget fitting and pricing |
| Lookups | `registry.py`, `identifiers.py` | Exact-match registry lookups, GSTIN checksum and repair, masking |
| Smart KYC | `kyc_ocr.py`, `kyc_checks.py`, `kyc_routes.py`, `kyc_text.py` | Reading documents, validation, consent and retention, and messages by language |
| Orders | `orders.py` | Order stages and dates. Prices are always recalculated on the server. |
| Back office | `backoffice.py`, `propensity_model.json` | The ranked queue and lead score |
| API | `main.py`, `journey_routes.py` | The HTTP endpoints |

The web app is in `prototype/frontend`: `components/` holds the screens, `lib/api.ts` talks to the API, and `lib/i18n.ts` holds screen wording by language.

**AI models,** tried in this order: Groq `gpt-oss-120b`, Gemini `gemini-3.6-flash`, Groq `gpt-oss-20b`, Groq `qwen3.8-27b`, then the guided flow with no AI.

**Pricing rule:** start at the top of the catalogue's range. Step down a quarter of the range for each of: a 12-month contract (two steps for 24 months), an add-on on an Accel connection, and a micro business. It never goes below the catalogue's floor. Repricing last quarter's bundles this way lowers revenue by just 1.6%.

**Privacy choices:**
- KYC documents are read on our own server, never sent to an AI provider, and never written to disk.
- Extracted details expire after 24 hours.
- Identifiers travel in request bodies, so they stay out of URLs and logs.
- Registry lookups use exact identifiers, never names, because unrelated businesses share names.

### Technology

| Layer | Used |
|---|---|
| Web app | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| API | Python, FastAPI, Pydantic, Uvicorn |
| AI | Groq and Gemini free tiers, called directly over HTTP |
| Document reading | RapidOCR with ONNX Runtime and OpenCV, running locally |
| Lead score | Logistic regression, trained offline with scikit-learn and stored as plain numbers |
| Testing | pytest, and Playwright driving Microsoft Edge |

### API endpoints

| Area | Endpoints |
|---|---|
| Advisor | `GET /api/advisor/languages`, `POST /api/advisor/sessions`, `POST /api/advisor/sessions/{id}/messages`, `POST /api/advisor/sessions/{id}/quote`, `DELETE /api/advisor/sessions/{id}` |
| KYC | `GET /api/kyc/consent-notice`, `GET /api/kyc/samples`, and under `/api/kyc/applications`: `POST` to create, `POST {id}/documents`, `GET {id}/requirements`, `POST {id}/install-address`, `POST {id}/load-sample`, `POST {id}/submit`, `DELETE {id}` |
| Orders | `POST /api/orders`, `GET /api/orders/{id}`, `POST /api/orders/{id}/advance` |
| Back office | `GET /api/backoffice/queue` |
| Direct | `GET /api/catalogue`, `POST /api/lookup/gstin`, `POST /api/lookup/udyam`, `POST /api/recommend`, `POST /api/quote`, `GET /api/health` |

## What's real and what's mocked

Know this before a demo, because the deck describes some of these as the design rather than what's built.

| Part | State |
|---|---|
| AI advisor, rules engine, pricing | **Real** |
| Reading and validating documents | **Real** |
| Lead score | **Real**, trained on the data pack |
| GSTIN and Udyam lookups | **Mock:** backed by the pack's CSV files |
| E-sign and payment | **Mock:** a button. Nothing is signed or charged. |
| One bill | **Not built.** The app shows one monthly total, but produces no bill or invoice. The deck's "one bill" describes the design. |
| Support after activation | **Not built.** There's no help screen, support number or complaint flow. The tracker only replaces calls about order status. |
| Order progress | **Simulated** with a demo button |
| "Updates sent to you" on the tracker | **On screen only.** No SMS or WhatsApp is sent. |
| Site feasibility check | **Simulated** as a tracker stage. The advisor just asks the owner about fibre. |
| Data storage | **In memory only.** Restarting the API loses all conversations, applications and orders. |
| Login | **None.** Anyone with an order number can see that order, and the back office is open. |
| Back-office queue | Shows **last quarter's dropped leads,** not live conversations from the app |
| Partner QR credit, referrals | **Proposal in the deck,** not built |
| DigiLocker, real registries | **Not built** |
| WhatsApp front end | **Not built** (stretch goal) |
| Voice input | **Built but untested.** Browsers generally allow the microphone only on HTTPS or localhost, so expect it to fail on a phone over a plain Wi-Fi address. |

Other limits:
- Tracker dates show July 2026, because the data pack fixes "today" as 15 Jul 2026.
- The Hindi, Tamil and Kannada wording was written by Claude and hasn't been checked by a native speaker.

## Free AI limits

Groq allows about 8,000 tokens a minute and 200,000 a day per model, and a recommendation uses about 3,000. That's roughly 65 recommendations a day on the best model, recovering over 24 hours. Gemini's free limits aren't published.

**Don't run the AI test scripts in the 24 hours before a demo.** Once the best model's quota is gone, conversations move to weaker models and make more mistakes.

## How it was tested

| Check | Last result |
|---|---|
| Backend tests | 366 pass |
| Replay of all 5,000 leads through the rules engine | 0 rule breaks, against 15% of bundles sold today |
| Lead score on unseen leads, averaged over 200 random splits | AUC 0.71, and the top-scored 20% hold 40% of activations |
| The 12 specimen KYC applicants, with real OCR | 12 of 12 give the expected result |
| Browser journey in Hindi, Tamil and English | Runs with no errors |
| Journey with all AI switched off | Works, and gives the same plan |
| 16 test conversations on real AI, in 4 languages | 16 of 16 on the last full run |
| The six other languages on real AI | 6 of 6 with quota, 2 of 6 once it ran out |
| Production build, lint, type-check | Clean |
| App reached through the Wi-Fi address in production mode | Works, including uploads |

The real-AI conversations ran before the final change (model order, and code that catches billing, CCTV and WhatsApp requests). They haven't been re-run since, because the day's quota ran out.

To run the tests, from `prototype/backend`:

```bash
.venv/Scripts/python -m pytest
```

More commands are in [CLAUDE.md](CLAUDE.md) and [prototype/README.md](prototype/README.md).

## What's in this repository

| In the repo | What it is |
|---|---|
| `prototype/` | The app: `backend/` (API) and `frontend/` (web app) |
| `product_catalogue.csv`, `smb_leads.csv`, the two `mock_*_registry.csv` files, `kyc_documents/` | The synthetic data pack, which the app reads directly |
| `analysis/kyc_expected_results.json` | Our expected result for each KYC applicant, used by the tests and the demo box |
| [`README.md`](README.md) | The data pack's column guide, supplied with the case |
| [`CLAUDE.md`](CLAUDE.md) | Guidance for Claude Code sessions |

The case PDF, the submission template, the deck, the demo script, and the research and business-case work are kept out of the repo on purpose. `.gitignore` lists them.
