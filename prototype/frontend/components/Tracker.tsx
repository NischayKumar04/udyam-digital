"use client";

import { useEffect, useState } from "react";
import { get, post, rupees, type OrderView } from "@/lib/api";
import { formatDate, translator, type StringKey } from "@/lib/i18n";

const stageKey = (stage: string) => `stage_${stage}` as StringKey;

export default function Tracker({ orderId, language }: { orderId: string; language?: string }) {
  const [order, setOrder] = useState<OrderView | null>(null);
  const [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<OrderView>(`/orders/${orderId}`).then(setOrder).catch(() => setMissing(true));
  }, [orderId]);

  const shownLanguage = language ?? order?.language ?? "English";
  const t = translator(shownLanguage);

  if (missing) return <p className="p-5 text-[15px]">{t("not_found")}</p>;
  if (!order) return null;

  async function next() {
    setBusy(true);
    try {
      setOrder(await post<OrderView>(`/orders/${orderId}/advance`));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
      <p className="text-sm text-muted">{t("order_title", { id: order.id })}</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        {order.is_live ? t("is_live") : t("live_by", { date: formatDate(order.live_on, shownLanguage) })}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">{order.under_review ? t("under_review") : t("no_calls")}</p>

      <ol className="mt-4 rounded-2xl border border-line bg-surface p-4">
        {order.stages.map((stage, index) => {
          const last = index === order.stages.length - 1;
          return (
            <li key={stage.key} className="flex gap-3" aria-current={stage.state === "current" ? "step" : undefined}>
              <div className="flex flex-col items-center">
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] text-white ${
                  stage.state === "done" ? "bg-good" : stage.state === "current" ? "bg-accent" : "bg-line"
                }`}>
                  {stage.state === "done" ? "✓" : ""}
                </span>
                {!last && <span className={`w-0.5 flex-1 ${stage.state === "done" ? "bg-good" : "bg-line"}`} />}
              </div>
              <div className={`flex flex-1 justify-between gap-3 ${last ? "" : "pb-4"}`}>
                <p className={`text-[15px] leading-5 ${stage.state === "pending" ? "text-muted" : stage.state === "current" ? "font-semibold" : ""}`}>{t(stageKey(stage.key))}</p>
                <p className="shrink-0 text-sm leading-5 tabular-nums text-muted">{formatDate(stage.on, shownLanguage)}</p>
              </div>
            </li>
          );
        })}
      </ol>

      {order.next_stage && order.next_stage_on && (
        <p className="mt-3 rounded-2xl bg-accent-soft px-4 py-3 text-sm">
          <span className="font-semibold">{t("whats_next")}: </span>
          {t(stageKey(order.next_stage))}, {formatDate(order.next_stage_on, shownLanguage)}
        </p>
      )}

      <section className="mt-3 rounded-2xl border border-line bg-surface p-4">
        <h2 className="text-sm font-semibold text-muted">{t("your_services")}</h2>
        <ul className="mt-2 space-y-1.5">
          {order.services.map((service) => (
            <li key={service.name} className="flex justify-between gap-3 text-sm">
              <span>{service.name}{service.quantity > 1 ? ` × ${service.quantity}` : ""}</span>
              <span className={`shrink-0 tabular-nums ${service.is_live ? "text-good" : "text-muted"}`}>
                {service.is_live ? "✓" : formatDate(service.live_on, shownLanguage)}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex justify-between border-t border-line pt-2 text-sm">
          <span className="text-muted">{t("total_monthly")}, {t("with_gst")}</span>
          <span className="font-medium tabular-nums">{rupees(order.monthly_total)}</span>
        </div>
      </section>

      <section className="mt-3 rounded-2xl border border-line bg-surface p-4">
        <h2 className="text-sm font-semibold text-muted">{t("updates")}</h2>
        <ul className="mt-2 space-y-1 text-sm">
          {order.updates.map((update) => (
            <li key={update.stage} className="flex justify-between gap-3">
              <span>{t(stageKey(update.stage))}</span>
              <span className="tabular-nums text-muted">{formatDate(update.on, shownLanguage)}</span>
            </li>
          ))}
        </ul>
      </section>

      {!order.is_live && (
        <button disabled={busy} onClick={next} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line px-4 py-3 text-sm font-medium text-muted transition-colors hover:border-muted">
          <span className="rounded bg-background px-1.5 py-0.5 text-xs">{t("demo_tag")}</span>
          {t("simulate")}
        </button>
      )}
    </div>
  );
}
