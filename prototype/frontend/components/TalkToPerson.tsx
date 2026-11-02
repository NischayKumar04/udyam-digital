"use client";

import { useEffect, useState } from "react";
import { erase, get, post } from "@/lib/api";
import { translator } from "@/lib/i18n";

const MOBILE = /^(\+?91|0)?[6-9]\d{9}$/;

export default function TalkToPerson({
  sessionId,
  language,
  requested,
  onRequested,
  onClose,
}: {
  sessionId: string;
  language: string;
  requested: string | null;
  onRequested: (maskedMobile: string | null) => void;
  onClose: () => void;
}) {
  const t = translator(language);
  const [mobile, setMobile] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [cancelled, setCancelled] = useState(false);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  async function send() {
    if (!MOBILE.test(mobile.replace(/[\s-]/g, ""))) {
      setMessage(t("person_bad_number"));
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const notice = await get<{ version: string }>("/advisor/call-notice");
      const sent = await post<{ mobile: string }>(`/advisor/sessions/${sessionId}/call-request`, {
        mobile,
        consent_accepted: agreed,
        notice_version: notice.version,
      });
      setMobile("");
      setAgreed(false);
      setCancelled(false);
      onRequested(sent.mobile);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    setMessage(null);
    try {
      await erase(`/advisor/sessions/${sessionId}/call-request`);
      setCancelled(true);
      onRequested(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-20 overflow-y-auto bg-black/40 px-4 pb-6 pt-16">
      <div role="dialog" aria-modal="true" aria-labelledby="person-title" className="mx-auto w-full max-w-md rounded-2xl bg-surface p-5">
        <div className="flex items-start justify-between gap-3">
          <h2 id="person-title" className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            {t("person_button")}
            <span className="rounded bg-background px-1.5 py-0.5 text-xs font-normal text-muted">{t("demo_tag")}</span>
          </h2>
          <button onClick={onClose} className="shrink-0 text-sm text-muted underline-offset-2 hover:underline">{t("person_close")}</button>
        </div>

        {requested ? (
          <div className="mt-3">
            <p className="rounded-xl bg-good-soft p-3 text-sm leading-relaxed text-good">{t("person_sent", { mobile: requested })}</p>
            <p className="mt-2 text-sm leading-relaxed text-muted">{t("person_demo")}</p>
            {message && <p className="mt-2 text-sm text-bad">{message}</p>}
            <button disabled={busy} onClick={cancel} className="mt-3 text-sm text-muted underline underline-offset-2 disabled:opacity-40">{t("person_cancel")}</button>
          </div>
        ) : (
          <form
            className="mt-3"
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
          >
            {cancelled && <p className="mb-3 rounded-xl bg-good-soft p-3 text-sm leading-relaxed text-good">{t("person_cancelled")}</p>}
            <p className="text-sm leading-relaxed text-muted">{t("person_sub")}</p>
            <label className="mt-3 block text-sm font-medium">
              {t("person_mobile")}
              <input
                value={mobile}
                onChange={(event) => setMobile(event.target.value)}
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                maxLength={16}
                autoFocus
                className="mt-1 h-11 w-full rounded-xl border border-line bg-background px-3 text-[15px] font-normal outline-none focus:border-muted"
              />
            </label>
            <p className="mt-3 text-sm leading-relaxed text-muted">{t("person_notice")}</p>
            <label className="mt-3 flex items-start gap-3 text-[15px] leading-snug">
              <input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--accent)]" />
              {t("person_agree")}
            </label>
            {message && <p className="mt-3 text-sm text-bad">{message}</p>}
            <button type="submit" disabled={!agreed || !mobile.trim() || busy} className="mt-4 w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition-opacity disabled:opacity-40">
              {t("person_send")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
