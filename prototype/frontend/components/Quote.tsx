"use client";

import { useEffect, useMemo, useState } from "react";
import { post, rupees, type Item, type Quote as QuoteData, type Recommendation } from "@/lib/api";
import { translator, type StringKey } from "@/lib/i18n";

export type Selection = {
  picks: Record<string, number>;
  contract: number | null;
};

// Units an owner can reasonably adjust. Site-based services follow the number of sites.
const ADJUSTABLE = new Set(["per user", "per camera", "per line", "per device", "per counter", "per vehicle", "per channel"]);

function toLines(picks: Record<string, number>) {
  return Object.entries(picks).map(([product_id, quantity]) => ({ product_id, quantity }));
}

export default function Quote({
  sessionId,
  language,
  recommendation,
  initial,
  onBack,
  onContinue,
}: {
  sessionId: string;
  language: string;
  recommendation: Recommendation;
  initial: Selection | null;
  onBack: () => void;
  onContinue: (selection: Selection, quote: QuoteData) => void;
}) {
  const t = translator(language);
  const [picks, setPicks] = useState<Record<string, number>>(
    () => initial?.picks ?? Object.fromEntries(recommendation.bundle.map((item) => [item.product_id, item.quantity])),
  );
  const [contract, setContract] = useState<number | null>(initial?.contract ?? null);
  const [quote, setQuote] = useState<QuoteData>(recommendation.quote);
  const [error, setError] = useState<string | null>(null);

  const allItems = useMemo(() => [...recommendation.bundle, ...recommendation.addons], [recommendation]);
  const addonIds = useMemo(() => new Set(recommendation.addons.map((item) => item.product_id)), [recommendation]);
  const blockedAsked = recommendation.unavailable.filter((u) => u.asked);
  const blockedOther = recommendation.unavailable.filter((u) => !u.asked);

  useEffect(() => {
    let current = true;
    post<QuoteData>(`/advisor/sessions/${sessionId}/quote`, { lines: toLines(picks), contract_months: contract })
      .then((next) => {
        if (current) {
          setQuote(next);
          setError(null);
        }
      })
      .catch((reason) => current && setError(reason.message));
    return () => {
      current = false;
    };
  }, [picks, contract, sessionId]);

  function toggle(item: Item) {
    setPicks((current) => {
      const next = { ...current };
      if (item.product_id in next) delete next[item.product_id];
      else next[item.product_id] = item.quantity;
      return next;
    });
  }

  function adjust(item: Item, change: number) {
    setPicks((current) => ({ ...current, [item.product_id]: Math.max(1, (current[item.product_id] ?? item.quantity) + change) }));
  }

  const lineFor = (id: string) => quote.lines.find((line) => line.product_id === id);
  const difference = recommendation.monthly_difference_vs_current;
  const currentSpend = difference === null ? null : recommendation.quote.monthly_subtotal - difference;
  const change = currentSpend === null ? null : quote.monthly_subtotal - currentSpend;

  function renderRow(item: Item) {
    const on = item.product_id in picks;
    const line = lineFor(item.product_id);
    const violation = quote.violations.find((v) => v.product_id === item.product_id);
    return (
      <li key={item.product_id} className="py-3">
        <div className="flex items-start gap-3">
          <button
            role="switch"
            aria-checked={on}
            aria-label={item.name}
            onClick={() => toggle(item)}
            className={`mt-0.5 h-6 w-10 shrink-0 rounded-full p-0.5 transition-colors ${on ? "bg-accent" : "bg-line"}`}
          >
            <span className={`block h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? "translate-x-4" : ""}`} />
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <p className="text-[15px] font-medium leading-snug">
                {item.name}
                {!ADJUSTABLE.has(item.unit) && (picks[item.product_id] ?? item.quantity) > 1 && <span className="font-normal text-muted"> × {picks[item.product_id] ?? item.quantity}</span>}
              </p>
              <p className="shrink-0 text-sm font-medium tabular-nums">
                {on && line ? rupees(line.monthly) : `+${rupees(item.monthly)}`}
              </p>
            </div>
            <p className="mt-0.5 text-sm leading-snug text-muted">{item.reason}</p>
            {!on && item.setup > 0 && <p className="mt-0.5 text-xs text-muted">{t("one_time")}: {rupees(item.setup)}</p>}
            {!on && item.contract_months_if_added && <p className="mt-0.5 text-xs text-warn">{t("needs_contract", { months: item.contract_months_if_added })}</p>}
            {violation && <p className="mt-1 text-sm text-bad">{violation.message}</p>}
            {on && ADJUSTABLE.has(item.unit) && (
              <div className="mt-2 flex items-center gap-2">
                <button aria-label={`Fewer: ${item.name}`} onClick={() => adjust(item, -1)} className="h-7 w-7 rounded-lg border border-line text-sm">−</button>
                <span className="w-6 text-center text-sm tabular-nums">{picks[item.product_id]}</span>
                <button aria-label={`More: ${item.name}`} onClick={() => adjust(item, 1)} className="h-7 w-7 rounded-lg border border-line text-sm">+</button>
                <span className="text-xs text-muted">{t(`unit_${item.unit.replace(" ", "_")}` as StringKey)}</span>
              </div>
            )}
          </div>
        </div>
      </li>
    );
  }

  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <button onClick={onBack} className="text-sm text-muted underline-offset-2 hover:underline">← {t("step_advisor")}</button>

        {blockedAsked.length > 0 && (
          <section className="mt-3 rounded-2xl bg-warn-soft p-4">
            <h2 className="text-sm font-semibold text-warn">{t("not_available")}</h2>
            <ul className="mt-1 space-y-1.5 text-sm leading-snug">
              {blockedAsked.map((blocked) => (
                <li key={blocked.product_id}>
                  {blocked.reason}
                  {blocked.alternative_name && <span className="font-medium"> {t("instead")}: {blocked.alternative_name}.</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="mt-3 rounded-2xl border border-line bg-surface px-4 pt-3">
          <h2 className="text-sm font-semibold text-muted">{t("included")}</h2>
          <ul className="divide-y divide-line">{recommendation.bundle.map(renderRow)}</ul>
        </section>

        {recommendation.addons.length > 0 && (
          <section className="mt-3 rounded-2xl border border-line bg-surface px-4 pt-3">
            <h2 className="text-sm font-semibold text-muted">{t("extras")}</h2>
            <ul className="divide-y divide-line">{allItems.filter((item) => addonIds.has(item.product_id)).map(renderRow)}</ul>
          </section>
        )}

        <section className="mt-3 rounded-2xl border border-line bg-surface p-4">
          <h2 className="text-sm font-semibold text-muted">{t("contract")}</h2>
          <div className="mt-2 grid grid-flow-col auto-cols-fr gap-2">
            {quote.contract_options.map((option) => {
              const selected = quote.contract_months === option.months;
              return (
                <button
                  key={option.months}
                  aria-pressed={selected}
                  onClick={() => setContract(option.months)}
                  className={`rounded-xl border px-2 py-2 text-center transition-colors ${selected ? "border-accent bg-accent-soft" : "border-line"}`}
                >
                  <span className="block text-sm font-medium">{option.months === 1 ? t("month_to_month") : t("months", { months: option.months })}</span>
                  <span className="block text-xs tabular-nums text-muted">{rupees(option.monthly_subtotal)}</span>
                </button>
              );
            })}
          </div>
        </section>

        {blockedOther.length > 0 && (
          <details className="mt-3 rounded-2xl border border-line bg-surface p-4 text-sm">
            <summary className="cursor-pointer font-semibold text-muted">{t("not_available")} ({blockedOther.length})</summary>
            <ul className="mt-2 space-y-1.5 leading-snug text-muted">
              {blockedOther.map((blocked) => <li key={blocked.product_id}>{blocked.reason}</li>)}
            </ul>
          </details>
        )}

        {recommendation.notes.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm leading-snug text-muted">
            {recommendation.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        )}

        <dl className="mt-3 space-y-1.5 px-1 pb-2 text-sm">
          {quote.monthly_saving > 0 && (
            <div className="flex justify-between text-good">
              <dt>{t("you_save")}</dt>
              <dd className="tabular-nums">{rupees(quote.monthly_saving)} {t("a_month")}</dd>
            </div>
          )}
          {quote.one_time_setup > 0 && (
            <div className="flex justify-between">
              <dt className="text-muted">{t("one_time")}</dt>
              <dd className="tabular-nums">{rupees(quote.one_time_setup)} {t("plus_gst")}</dd>
            </div>
          )}
          {change !== null && (
            <div className="flex justify-between">
              <dt className="text-muted">{t("vs_today")}</dt>
              <dd className="tabular-nums">{change >= 0 ? t("more_a_month", { amount: rupees(change) }) : t("less_a_month", { amount: rupees(-change) })}</dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt className="text-muted">{t("live_in", { days: quote.expected_activation_days })}</dt>
          </div>
        </dl>
      </div>

      <div className="shrink-0 border-t border-line bg-surface px-5 py-3">
        {error && <p className="mb-2 text-sm text-bad">{error}</p>}
        <div className="flex items-end justify-between">
          <div>
            <p className="text-2xl font-semibold leading-none tracking-tight tabular-nums">{rupees(quote.monthly_subtotal)}</p>
            <p className="mt-1 text-xs text-muted">{t("a_month")} {t("plus_gst")}</p>
          </div>
          <div className="text-right">
            <p className="text-sm font-medium tabular-nums">{rupees(quote.monthly_total)}</p>
            <p className="text-xs text-muted">{t("total_monthly")}, {t("with_gst")}</p>
          </div>
        </div>
        <button
          disabled={!quote.valid}
          onClick={() => onContinue({ picks, contract }, quote)}
          className="mt-3 w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition-opacity disabled:opacity-40"
        >
          {quote.valid ? t("continue_docs") : t("fix_first")}
        </button>
      </div>
    </>
  );
}
