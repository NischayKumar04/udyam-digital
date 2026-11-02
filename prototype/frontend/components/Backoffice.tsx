"use client";

import { useEffect, useState } from "react";
import { get, type QueueLead, type QueueView } from "@/lib/api";

const OWNERS = ["Field sales", "Local partner", "Digital follow-up"];
const SEGMENTS: Record<string, string> = { micro: "Micro retail", prof: "Professional", multi: "Multi-site", mfg: "Manufacturer" };

function GroupRow({ label }: { label: string }) {
  return (
    <tr className="border-b border-line bg-background">
      <th scope="colgroup" colSpan={6} className="px-4 py-2 text-left text-xs font-semibold">{label}</th>
    </tr>
  );
}

function LeadRow({ lead }: { lead: QueueLead }) {
  return (
    <tr className="border-b border-line align-top last:border-0">
      <td className="px-4 py-3">
        {lead.score === null ? (
          <span className="font-semibold">New</span>
        ) : (
          <>
            <span className="font-semibold tabular-nums">{lead.score}%</span>
            <div className="mt-1 h-1 w-12 rounded-full bg-line">
              <div className="h-1 rounded-full bg-accent" style={{ width: `${lead.score}%` }} />
            </div>
          </>
        )}
      </td>
      <td className="px-4 py-3">
        <p className="font-medium">{lead.business}</p>
        <p className="text-xs text-muted">{[lead.segment && SEGMENTS[lead.segment], lead.city, lead.language].filter(Boolean).join(" · ")}</p>
        <p className="text-xs text-muted">{lead.contact} · {lead.source}</p>
      </td>
      <td className="px-4 py-3">
        <p>{lead.drop_reason}</p>
        <p className="text-xs text-muted">Reached: {lead.stage}</p>
      </td>
      <td className="px-4 py-3 text-xs leading-relaxed text-muted">{lead.reasons.join(" · ")}</td>
      <td className="px-4 py-3 whitespace-nowrap">{lead.owner}</td>
      <td className="px-4 py-3">{lead.next_action}</td>
    </tr>
  );
}

export default function Backoffice() {
  const [owner, setOwner] = useState<string | null>(null);
  const [queue, setQueue] = useState<QueueView | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ limit: "40" });
    if (owner) params.set("owner", owner);
    get<QueueView>(`/backoffice/queue?${params}`).then(setQueue);
  }, [owner]);

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Leads to follow up</h1>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
        Owners who asked for a call come first, then last quarter&apos;s leads that didn&apos;t close, with who should call and what to offer.
      </p>

      {queue && (
        <>
          <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Filter by owner">
            {[null, ...OWNERS].map((name) => {
              const count = name ? queue.by_owner[name] ?? 0 : queue.total;
              const selected = owner === name;
              return (
                <button
                  key={name ?? "all"}
                  role="tab"
                  aria-selected={selected}
                  onClick={() => setOwner(name)}
                  className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors ${selected ? "border-accent bg-accent-soft font-medium text-accent" : "border-line bg-surface hover:border-muted"}`}
                >
                  {name ?? "All"} <span className="tabular-nums text-muted">{count.toLocaleString("en-IN")}</span>
                </button>
              );
            })}
          </div>

          <div className="mt-3 max-w-4xl space-y-1 text-xs leading-relaxed text-muted">
            <p>
              Score: how often similar leads activated when they first came in. Use it to choose who to call first. It isn&apos;t the chance of winning a lost lead back. Leads who said no, are locked into a contract or asked to wait come last.
            </p>
            <p>
              Tested on leads kept out of training, averaged over {queue.model.test_splits} random splits: AUC {queue.model.auc.toFixed(2)}. The top-scored 20% of leads hold {Math.round(queue.model.top_20pct_share_of_activations * 100)}% of activations, {(queue.model.top_20pct_rate / queue.model.base_rate).toFixed(1)} times the average rate. Owners from the chat are scored by a smaller model that uses only what the chat collects (AUC {queue.chat_model.auc.toFixed(2)}), so their scores run lower.
            </p>
            <p>
              Showing the top {queue.leads.length} of {(owner ? queue.by_owner[owner] ?? 0 : queue.total).toLocaleString("en-IN")}.
              {queue.no_contact > 0 && ` ${queue.no_contact} more ${queue.no_contact === 1 ? "chat" : "chats"} got a plan but left no number, so ${queue.no_contact === 1 ? "it" : "they"} can't be called.`}
            </p>
          </div>

          <div className="mt-3 overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th scope="col" className="px-4 py-2.5 font-medium">Score</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Business</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Why it dropped</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Why call</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Owner</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Next step</th>
                </tr>
              </thead>
              <tbody>
                {queue.leads.some((lead) => lead.live) && <GroupRow label="Asked for a call, live from the app" />}
                {queue.leads.filter((lead) => lead.live).map((lead) => <LeadRow key={lead.lead_id} lead={lead} />)}
                {queue.leads.some((lead) => lead.live) && <GroupRow label="Last quarter's leads" />}
                {queue.leads.filter((lead) => !lead.live).map((lead) => <LeadRow key={lead.lead_id} lead={lead} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
