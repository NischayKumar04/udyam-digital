"use client";

import Link from "next/link";
import { useState } from "react";
import type { Quote as QuoteData, Recommendation } from "@/lib/api";
import { LANGUAGES, translator, type StringKey } from "@/lib/i18n";
import Advisor from "./Advisor";
import Kyc from "./Kyc";
import Quote, { type Selection } from "./Quote";
import TalkToPerson from "./TalkToPerson";
import Tracker from "./Tracker";

type Step = "advisor" | "quote" | "kyc" | "track";

const STEPS: { key: Step; label: StringKey }[] = [
  { key: "advisor", label: "step_advisor" },
  { key: "quote", label: "step_quote" },
  { key: "kyc", label: "step_kyc" },
  { key: "track", label: "step_track" },
];

export function Wordmark() {
  return (
    <Link href="/" className="font-semibold tracking-tight text-foreground">
      <span className="text-accent">Accel</span> Business
    </Link>
  );
}

export default function Journey() {
  const [language, setLanguage] = useState("English");
  const [started, setStarted] = useState(false);
  const [step, setStep] = useState<Step>("advisor");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [recommendationVersion, setRecommendationVersion] = useState(0);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [orderId, setOrderId] = useState<string | null>(null);
  const [personOpen, setPersonOpen] = useState(false);
  const [callRequested, setCallRequested] = useState<string | null>(null);
  const t = translator(language);

  if (!started) {
    return (
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col px-5 py-8">
        <Wordmark />
        <h1 className="mt-12 text-3xl font-semibold leading-tight tracking-tight">{t("tagline")}</h1>
        <p className="mt-4 text-base leading-relaxed text-muted">{t("sub")}</p>

        <p className="mt-10 text-sm font-medium">{t("choose_language")}</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {LANGUAGES.map((option) => (
            <button
              key={option.name}
              onClick={() => setLanguage(option.name)}
              aria-pressed={language === option.name}
              className={`rounded-xl border px-4 py-3 text-left text-base transition-colors ${
                language === option.name ? "border-accent bg-accent-soft font-medium text-accent" : "border-line bg-surface hover:border-muted"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <button onClick={() => setStarted(true)} className="mt-8 rounded-xl bg-accent px-5 py-4 text-base font-semibold text-white transition-opacity hover:opacity-90">
          {t("start")}
        </button>
        <div className="mt-6 flex justify-between text-sm text-muted">
          <Link href="/track" className="underline-offset-2 hover:underline">{t("track_link")}</Link>
          <Link href="/backoffice" className="underline-offset-2 hover:underline">{t("backoffice_link")}</Link>
        </div>
      </main>
    );
  }

  const reached = STEPS.findIndex((s) => s.key === step);

  return (
    <div className="mx-auto flex h-dvh w-full max-w-md flex-col bg-background">
      <header className="shrink-0 border-b border-line bg-surface px-5 pb-3 pt-4">
        <div className="flex items-center justify-between gap-3">
          <Wordmark />
          {sessionId && step !== "track" && (
            <button onClick={() => setPersonOpen(true)} className="min-w-0 truncate text-sm font-medium text-accent underline-offset-2 hover:underline">
              {callRequested ? t("person_requested") : t("person_button")}
            </button>
          )}
        </div>
        <ol className="mt-3 flex gap-1.5" aria-label="Progress">
          {STEPS.map((s, index) => (
            <li key={s.key} className="flex-1" aria-current={s.key === step ? "step" : undefined}>
              <div className={`h-1 rounded-full ${index <= reached ? "bg-accent" : "bg-line"}`} />
              <p className={`mt-1 truncate text-xs ${index === reached ? "font-medium text-foreground" : "text-muted"}`}>{t(s.label)}</p>
            </li>
          ))}
        </ol>
      </header>

      <div className={step === "advisor" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
        <Advisor
          language={language}
          onSession={setSessionId}
          onRecommendation={(next) => {
            setRecommendation(next);
            setRecommendationVersion((version) => version + 1);
          }}
          recommendation={recommendation}
          onContinue={() => setStep("quote")}
          onTalkToPerson={() => setPersonOpen(true)}
        />
      </div>

      {step === "quote" && sessionId && recommendation && (
        <Quote
          key={recommendationVersion}
          sessionId={sessionId}
          language={language}
          recommendation={recommendation}
          initial={selection}
          onBack={() => setStep("advisor")}
          onContinue={(nextSelection, nextQuote) => {
            setSelection(nextSelection);
            setQuote(nextQuote);
            setStep("kyc");
          }}
        />
      )}

      {step === "kyc" && sessionId && selection && quote && recommendation && (
        <Kyc
          sessionId={sessionId}
          language={language}
          selection={selection}
          quote={quote}
          hasActiveGstin={recommendation.has_active_gstin}
          onBack={() => setStep("quote")}
          onOrder={(id) => {
            setOrderId(id);
            setCallRequested(null);
            setStep("track");
          }}
          onTalkToPerson={() => setPersonOpen(true)}
        />
      )}

      {step === "track" && orderId && <Tracker orderId={orderId} language={language} />}

      {personOpen && sessionId && (
        <TalkToPerson
          sessionId={sessionId}
          language={language}
          requested={callRequested}
          onRequested={setCallRequested}
          onClose={() => setPersonOpen(false)}
        />
      )}
    </div>
  );
}
