"use client";

import { useCallback, useEffect, useState } from "react";
import { erase, get, post, rupees, upload, type DocumentView, type KycResult, type OrderView, type Quote, type Requirement } from "@/lib/api";
import { translator, type StringKey } from "@/lib/i18n";
import type { Selection } from "./Quote";

const SLOTS = ["gst", "udyam", "signatory_id", "address_proof"] as const;
const SLOT_LABELS: Record<string, StringKey> = {
  gst: "doc_gst",
  udyam: "doc_udyam",
  signatory_id: "doc_signatory_id",
  address_proof: "doc_address_proof",
};
const CONSENT_ROWS: [StringKey, StringKey][] = [
  ["consent_purpose", "consent_purpose_text"],
  ["consent_data", "consent_data_text"],
  ["consent_processing", "consent_processing_text"],
  ["consent_retention", "consent_retention_text"],
  ["consent_rights", "consent_rights_text"],
];
// Enough to confirm we read the right document, and no more than that on screen.
const PREVIEW_FIELDS: Record<string, string[]> = {
  gst: ["gstin", "trade_name", "constitution"],
  udyam: ["udyam_number", "enterprise_name", "city"],
  signatory_id: ["name", "designation", "id_no"],
  address_proof: ["consumer_no", "billed_to", "bill_date"],
};
const VERDICT_STYLE: Record<string, string> = {
  PASS: "bg-good-soft text-good",
  PASS_WITH_WARNING: "bg-good-soft text-good",
  AUTO_RESOLVE: "bg-good-soft text-good",
  REUPLOAD: "bg-warn-soft text-warn",
  MANUAL_REVIEW: "bg-warn-soft text-warn",
  REJECT: "bg-bad-soft text-bad",
};
const OUTCOME_STYLE: Record<string, string> = {
  REJECT: "bg-bad",
  MANUAL_REVIEW: "bg-warn",
  REUPLOAD: "bg-warn",
  AUTO_RESOLVE: "bg-good",
  PASS_WITH_WARNING: "bg-muted",
  PASS: "bg-good",
};

export default function Kyc({
  sessionId,
  language,
  selection,
  quote,
  hasActiveGstin,
  onBack,
  onOrder,
  onTalkToPerson,
}: {
  sessionId: string;
  language: string;
  selection: Selection;
  quote: Quote;
  hasActiveGstin: boolean;
  onBack: () => void;
  onOrder: (orderId: string) => void;
  onTalkToPerson: () => void;
}) {
  const t = translator(language);
  const [agreed, setAgreed] = useState(false);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Record<string, DocumentView>>({});
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [reading, setReading] = useState<Record<string, boolean>>({});
  const [samples, setSamples] = useState<{ id: string; business: string }[]>([]);
  const [sameAddress, setSameAddress] = useState(false);
  const [result, setResult] = useState<KycResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [signing, setSigning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [erased, setErased] = useState(false);

  const refreshRequirements = useCallback((id: string) => {
    get<Requirement[]>(`/kyc/applications/${id}/requirements`).then(setRequirements);
  }, []);

  useEffect(() => {
    get<{ id: string; business: string }[]>("/kyc/samples").then(setSamples);
  }, []);

  async function giveConsent() {
    setBusy(true);
    try {
      const notice = await get<{ version: string }>("/kyc/consent-notice");
      const created = await post<{ application_id: string }>("/kyc/applications", {
        consent_accepted: true,
        notice_version: notice.version,
        advisor_session_id: sessionId,
        language,
      });
      setApplicationId(created.application_id);
      refreshRequirements(created.application_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function uploadDocument(slot: string, file: File) {
    if (!applicationId) return;
    setReading((current) => ({ ...current, [slot]: true }));
    setResult(null);
    try {
      const document = await upload<DocumentView>(`/kyc/applications/${applicationId}/documents`, slot, file);
      setDocuments((current) => ({ ...current, [slot]: document }));
      refreshRequirements(applicationId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Please try again.");
    } finally {
      setReading((current) => ({ ...current, [slot]: false }));
    }
  }

  async function loadSample(sampleId: string) {
    if (!applicationId || !sampleId) return;
    setReading(Object.fromEntries(SLOTS.map((slot) => [slot, true])));
    setResult(null);
    setDocuments({});
    try {
      const loaded = await post<DocumentView[]>(`/kyc/applications/${applicationId}/load-sample`, { sample_id: sampleId });
      setDocuments(Object.fromEntries(loaded.map((document) => [document.slot, document])));
      refreshRequirements(applicationId);
    } finally {
      setReading({});
    }
  }

  async function chooseSameAddress(same: boolean) {
    if (!applicationId) return;
    setSameAddress(same);
    await post(`/kyc/applications/${applicationId}/install-address`, { same });
    refreshRequirements(applicationId);
  }

  async function check() {
    if (!applicationId) return;
    setBusy(true);
    try {
      setResult(await post<KycResult>(`/kyc/applications/${applicationId}/submit`));
    } finally {
      setBusy(false);
    }
  }

  async function placeOrder() {
    if (!applicationId) return;
    setBusy(true);
    setMessage(null);
    try {
      const order = await post<OrderView>("/orders", {
        advisor_session_id: sessionId,
        kyc_application_id: applicationId,
        lines: Object.entries(selection.picks).map(([product_id, quantity]) => ({ product_id, quantity })),
        contract_months: selection.contract,
      });
      onOrder(order.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Please try again.");
      setBusy(false);
    }
  }

  async function eraseApplication() {
    if (applicationId) await erase(`/kyc/applications/${applicationId}`);
    setApplicationId(null);
    setDocuments({});
    setResult(null);
    setAgreed(false);
    setErased(true);
  }

  if (!applicationId) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <button onClick={onBack} className="text-sm text-muted underline-offset-2 hover:underline">← {t("step_quote")}</button>
        {erased && <p className="mt-3 rounded-xl bg-good-soft p-3 text-sm text-good">{t("erased")}</p>}
        <h1 className="mt-3 text-xl font-semibold tracking-tight">{t("consent_title")}</h1>
        <dl className="mt-4 space-y-3 rounded-2xl border border-line bg-surface p-4">
          {CONSENT_ROWS.map(([title, body]) => (
            <div key={title}>
              <dt className="text-sm font-semibold">{t(title)}</dt>
              <dd className="mt-0.5 text-sm leading-relaxed text-muted">{t(body)}</dd>
            </div>
          ))}
        </dl>
        <label className="mt-4 flex items-start gap-3 text-[15px] leading-snug">
          <input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--accent)]" />
          {t("consent_agree")}
        </label>
        {message && <p className="mt-3 text-sm text-bad">{message}</p>}
        <button disabled={!agreed || busy} onClick={giveConsent} className="mt-4 w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition-opacity disabled:opacity-40">
          {t("consent_continue")}
        </button>
      </div>
    );
  }

  const requirementFor = (slot: string) => requirements.find((r) => r.slot === slot);
  const anyReading = Object.values(reading).some(Boolean);
  const canOrder = result && !["REUPLOAD"].includes(result.verdict) && (result.verdict !== "REJECT" || !hasActiveGstin);

  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <button onClick={onBack} className="text-sm text-muted underline-offset-2 hover:underline">← {t("step_quote")}</button>
        <h1 className="mt-3 text-xl font-semibold tracking-tight">{t("docs_title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("docs_sub")}</p>

        <label className="mt-3 block rounded-2xl border border-dashed border-line bg-surface p-3 text-sm">
          <span className="flex items-center gap-2 font-medium">
            <span className="rounded bg-background px-1.5 py-0.5 text-xs text-muted">{t("demo_tag")}</span>
            {t("sample_title")}
          </span>
          <select
            defaultValue=""
            onChange={(event) => loadSample(event.target.value)}
            className="mt-2 h-10 w-full rounded-lg border border-line bg-background px-2 text-sm"
          >
            <option value="" disabled>{t("sample_placeholder")}</option>
            {samples.map((sample) => <option key={sample.id} value={sample.id}>{sample.id}: {sample.business}</option>)}
          </select>
        </label>

        <ul className="mt-3 space-y-2">
          {SLOTS.map((slot) => {
            const document = documents[slot];
            const requirement = requirementFor(slot);
            const isReading = reading[slot];
            return (
              <li key={slot} className="rounded-2xl border border-line bg-surface p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[15px] font-medium leading-snug">{t(SLOT_LABELS[slot])}</p>
                    {!document && !isReading && requirement?.state === "resolved" && <p className="mt-0.5 text-sm leading-snug text-good">{requirement.message ?? t("not_needed")}</p>}
                    {!document && !isReading && requirement?.state === "optional" && <p className="mt-0.5 text-sm text-muted">{t("optional")}</p>}
                    {isReading && <p className="mt-0.5 text-sm text-muted">{t("reading")}</p>}
                    {document && !isReading && (
                      <p className={`mt-0.5 text-sm ${document.readable ? "text-good" : "text-bad"}`}>{document.readable ? t("doc_read") : t("doc_unreadable")}</p>
                    )}
                  </div>
                  {requirement?.state !== "resolved" && (
                    <label className="shrink-0 cursor-pointer rounded-lg border border-line px-3 py-1.5 text-sm font-medium transition-colors hover:border-muted">
                      {document ? t("replace") : t("upload")}
                      <input
                        type="file"
                        accept="image/png,image/jpeg"
                        className="sr-only"
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) uploadDocument(slot, file);
                          event.target.value = "";
                        }}
                      />
                    </label>
                  )}
                </div>
                {document?.readable && (
                  <dl className="mt-2 space-y-0.5 border-t border-line pt-2 text-xs text-muted">
                    {PREVIEW_FIELDS[slot].filter((name) => document.fields[name]).map((name) => (
                      <div key={name} className="flex justify-between gap-3">
                        <dt className="shrink-0">{t(`field_${name}` as StringKey)}</dt>
                        <dd className="truncate text-right text-foreground">{document.fields[name]}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {slot === "address_proof" && !document && hasActiveGstin && (
                  <label className="mt-2 flex items-center gap-2 text-sm text-muted">
                    <input type="checkbox" checked={sameAddress} onChange={(event) => chooseSameAddress(event.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
                    {t("same_address")}
                  </label>
                )}
              </li>
            );
          })}
        </ul>

        {result && (
          <section className="mt-3" aria-live="polite">
            <p className={`rounded-2xl px-4 py-3 text-[15px] font-semibold ${VERDICT_STYLE[result.verdict]}`}>
              {t(`verdict_${result.verdict}` as StringKey)}
            </p>
            {result.verdict === "MANUAL_REVIEW" && <p className="mt-2 text-sm text-muted">{t("review_note")}</p>}
            {result.verdict === "REJECT" && <p className="mt-2 text-sm text-muted">{t("reject_note")}</p>}
            {["REUPLOAD", "MANUAL_REVIEW", "REJECT"].includes(result.verdict) && (
              <button onClick={onTalkToPerson} className="mt-2 text-sm font-medium text-accent underline underline-offset-2">{t("person_button")}</button>
            )}
            {result.checks.length > 0 && (
              <ul className="mt-2 space-y-2 rounded-2xl border border-line bg-surface p-4">
                {result.checks.map((check) => (
                  <li key={`${check.code}-${check.document}`} className="flex gap-2.5 text-sm leading-snug">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${OUTCOME_STYLE[check.outcome]}`} />
                    <span>{check.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {signing && (
          <section className="mt-3 rounded-2xl border border-line bg-surface p-4">
            <h2 className="flex items-center gap-2 text-[15px] font-semibold">
              {t("esign_title")}
              <span className="rounded bg-background px-1.5 py-0.5 text-xs font-normal text-muted">{t("demo_tag")}</span>
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-muted">{t("esign_text")}</p>
            <dl className="mt-3 space-y-1 text-sm">
              <div className="flex justify-between"><dt className="text-muted">{t("pay_now")}</dt><dd className="font-medium tabular-nums">{rupees(quote.pay_now)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">{t("autopay")}</dt><dd className="font-medium tabular-nums">{rupees(quote.monthly_total)}</dd></div>
            </dl>
            <button disabled={busy} onClick={placeOrder} className="mt-3 w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition-opacity disabled:opacity-40">
              {t("place_order")}
            </button>
          </section>
        )}

        {message && <p className="mt-3 text-sm text-bad">{message}</p>}
        <button onClick={eraseApplication} className="mt-4 text-sm text-muted underline underline-offset-2">{t("erase")}</button>
      </div>

      {!signing && (
        <div className="shrink-0 border-t border-line bg-surface px-5 py-3">
          {canOrder ? (
            <button onClick={() => setSigning(true)} className="w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white">
              {t("esign_pay")}
            </button>
          ) : result?.verdict === "REJECT" ? (
            <button onClick={onBack} className="w-full rounded-xl border border-line px-4 py-3 text-sm font-semibold">
              {t("back_to_plan")}
            </button>
          ) : (
            <button disabled={busy || anyReading} onClick={check} className="w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition-opacity disabled:opacity-40">
              {busy ? t("checking") : t("check_docs")}
            </button>
          )}
        </div>
      )}
    </>
  );
}
