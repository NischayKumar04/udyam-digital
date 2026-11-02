"use client";

import { useEffect, useRef, useState } from "react";
import { post, rupees, type AdvisorReply, type Recommendation } from "@/lib/api";
import { LANGUAGES, translator } from "@/lib/i18n";

type Bubble = { from: "owner" | "advisor"; text: string };

type SpeechResultEvent = { results: { 0: { transcript: string } }[] };
type SpeechRecognizer = {
  lang: string;
  interimResults: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
};

function speechRecognizer(): (new () => SpeechRecognizer) | null {
  if (typeof window === "undefined") return null;
  const speechWindow = window as unknown as { SpeechRecognition?: new () => SpeechRecognizer; webkitSpeechRecognition?: new () => SpeechRecognizer };
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

export default function Advisor({
  language,
  onSession,
  onRecommendation,
  recommendation,
  onContinue,
}: {
  language: string;
  onSession: (id: string) => void;
  onRecommendation: (recommendation: Recommendation) => void;
  recommendation: Recommendation | null;
  onContinue: () => void;
}) {
  const t = translator(language);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(true);
  const [listening, setListening] = useState(false);
  const [canListen, setCanListen] = useState(false);
  const [last, setLast] = useState<AdvisorReply | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const bottom = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  useEffect(() => {
    setCanListen(speechRecognizer() !== null);
    if (started.current) return;
    started.current = true;
    post<AdvisorReply>("/advisor/sessions", { language }).then((reply) => {
      setSessionId(reply.session_id);
      onSession(reply.session_id);
      setBubbles([{ from: "advisor", text: reply.reply }]);
      setBusy(false);
    });
  }, [language, onSession]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles, busy, recommendation]);

  async function send(value: string, shown: string = value) {
    if (!sessionId || !value.trim() || busy) return;
    setBubbles((current) => [...current, { from: "owner", text: shown }]);
    setInput("");
    setChosen([]);
    setLast(null);
    setBusy(true);
    try {
      const reply = await post<AdvisorReply>(`/advisor/sessions/${sessionId}/messages`, { text: value });
      setBubbles((current) => [...current, { from: "advisor", text: reply.reply }]);
      setLast(reply);
      if (reply.recommendation) onRecommendation(reply.recommendation);
    } catch (error) {
      setBubbles((current) => [...current, { from: "advisor", text: error instanceof Error ? error.message : "Please try again." }]);
    } finally {
      setBusy(false);
    }
  }

  function listen() {
    const Recognizer = speechRecognizer();
    if (!Recognizer) return;
    const recognizer = new Recognizer();
    recognizer.lang = LANGUAGES.find((l) => l.name === language)?.speech ?? "en-IN";
    recognizer.interimResults = false;
    recognizer.onresult = (event) => setInput(event.results[0][0].transcript);
    recognizer.onend = () => setListening(false);
    recognizer.onerror = () => setListening(false);
    setListening(true);
    recognizer.start();
  }

  const guided = last?.mode === "guided";
  const options = last?.quick_replies ?? [];

  return (
    <>
      <div className="flex shrink-0 items-center justify-between px-5 pt-3">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${guided ? "bg-warn-soft text-warn" : "bg-good-soft text-good"}`}>
          {guided ? t("mode_guided") : t("mode_ai")}
        </span>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-3" aria-live="polite">
        {bubbles.map((bubble, index) => (
          <div key={index} className={bubble.from === "owner" ? "flex justify-end" : "flex justify-start"}>
            <p className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed ${
              bubble.from === "owner" ? "rounded-br-md bg-accent text-white" : "rounded-bl-md border border-line bg-surface"
            }`}>
              {bubble.text}
            </p>
          </div>
        ))}

        {busy && (
          <div className="flex justify-start" aria-label="Typing">
            <p className="flex gap-1 rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3.5">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-muted" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-muted" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-muted" />
            </p>
          </div>
        )}

        {bubbles.length === 1 && !busy && (
          <div className="space-y-2 pt-1">
            {(["starter_1", "starter_2"] as const).map((key) => (
              <button key={key} onClick={() => send(t(key))} className="block w-full rounded-xl border border-line bg-surface px-4 py-2.5 text-left text-sm text-muted transition-colors hover:border-muted">
                {t(key)}
              </button>
            ))}
          </div>
        )}

        {recommendation && !busy && (
          <div className="rounded-2xl border border-accent/30 bg-surface p-4">
            <p className="text-sm font-medium text-muted">{t("your_plan")}</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight">
              {rupees(recommendation.quote.monthly_subtotal)}
              <span className="ml-1 text-sm font-normal text-muted">{t("a_month")} {t("plus_gst")}</span>
            </p>
            <p className="mt-1 text-sm text-muted">
              {recommendation.bundle.map((item) => item.name).join(" · ")}
            </p>
            <button onClick={onContinue} className="mt-3 w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90">
              {t("see_price")}
            </button>
          </div>
        )}
        <div ref={bottom} />
      </div>

      {options.length > 0 && !busy && (
        <div className="shrink-0 px-5 pb-2">
          <div className="flex flex-wrap gap-2">
            {options.map((option) => {
              const isDone = option.value === "done";
              if (last?.multi_select) {
                if (isDone) {
                  return (
                    <button
                      key={option.value}
                      onClick={() => send([...chosen, "done"].join(","), chosen.length ? options.filter((o) => chosen.includes(o.value)).map((o) => o.label).join(", ") : option.label)}
                      className="rounded-full bg-accent px-3.5 py-1.5 text-sm font-medium text-white"
                    >
                      {option.label}
                    </button>
                  );
                }
                const selected = chosen.includes(option.value);
                return (
                  <button
                    key={option.value}
                    aria-pressed={selected}
                    onClick={() => setChosen((current) => (selected ? current.filter((v) => v !== option.value) : [...current, option.value]))}
                    className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors ${selected ? "border-accent bg-accent-soft text-accent" : "border-line bg-surface"}`}
                  >
                    {option.label}
                  </button>
                );
              }
              return (
                <button key={option.value} onClick={() => send(option.value, option.label)} className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm transition-colors hover:border-muted">
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <form
        className="flex shrink-0 gap-2 border-t border-line bg-surface px-4 py-3"
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
      >
        {canListen && (
          <button
            type="button"
            onClick={listen}
            aria-label={t("listen")}
            title={t("listen")}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border ${listening ? "border-accent bg-accent-soft text-accent" : "border-line text-muted"}`}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="9" y="2" width="6" height="12" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v4" />
            </svg>
          </button>
        )}
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t("type_here")}
          aria-label={t("type_here")}
          maxLength={1000}
          className="h-11 min-w-0 flex-1 rounded-xl border border-line bg-background px-3 text-[15px] outline-none focus:border-muted"
        />
        <button type="submit" disabled={busy || !input.trim()} className="h-11 shrink-0 rounded-xl bg-accent px-4 text-sm font-semibold text-white transition-opacity disabled:opacity-40">
          {t("send")}
        </button>
      </form>
    </>
  );
}
