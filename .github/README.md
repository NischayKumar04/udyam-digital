# Project Udyam Digital

A small business owner finds the right telecom bundle, buys it and gets it activated from a phone, in their own language, without a salesperson.

Built for Airtel SYNC / YTL Hackathon 2026, Enterprise Track A. The operator, "Accel Business", is fictional, and all businesses, people, identifiers and documents in this repo are synthetic.

It's a mobile-first web app:

- **AI advisor** in 10 languages, which falls back to a guided flow when no AI model is available
- **One clear monthly price**, with extras you can switch on and off
- **Smart KYC:** consent first, registry lookups, and documents read and validated on our own server
- **Order tracker**, so nobody has to call to chase status
- **Talk to a person**, so an owner can ask for a call at any point, with consent
- **Back office** that puts those requests first, then ranks last quarter's unclosed leads for sales staff and partners

The AI only extracts facts and words its replies. A rules engine decides what's allowed and what it costs, so a conversation can't break a catalogue rule or talk a price down.

## Run it

You need Python 3.10, 3.11 or 3.12 (the OCR library won't install on 3.13 or later) and Node 20.9 or later. Free keys from [Groq](https://console.groq.com/keys) and [Google AI Studio](https://aistudio.google.com/apikey), added to `prototype/backend/.env`, enable the AI advisor. Without them, the app runs on the guided flow.

```bash
cd prototype/backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

In a second terminal:

```bash
cd prototype/frontend
npm install
npm run dev
```

Then open http://localhost:3000 in a phone-sized window. On Mac or Linux, use `.venv/bin/python`.

## Read more

- [Project overview](../PROJECT_OVERVIEW.md): every feature, the architecture, what's real and what's mocked, and how to use it on a phone
- [Prototype setup and design decisions](../prototype/README.md)
- [Data pack guide](../README.md): what's in the CSV files
- [Competitive research](../analysis/competitive_analysis.md), with the [data analysis](../analysis/eda.py) and [business case](../analysis/business_case.py) scripts behind the deck's figures

The root `README.md` is the guide supplied with the data pack. This page is what GitHub shows first.
