"use client";

import { useEffect, useState } from "react";
import { get, type QueueView } from "@/lib/api";

const OWNERS = ["Field sales", "Local partner", "Digital follow-up"];
const SEGMENTS: Record<string, string> = { micro: "Micro retail", prof: "Professional", multi: "Multi-site", mfg: "Manufacturer" };

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
        Leads the digital journey couldn&apos;t close, ranked by how likely each one is to activate, with who should call and what to offer.
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

          <p className="mt-3 text-xs text-muted">
            Lead score tested on held-out leads: AUC {queue.model.auc.toFixed(2)}. The top-scored 20% of leads hold {Math.round(queue.model.top_20pct_share_of_activations * 100)}% of activations.
          </p>

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
                {queue.leads.map((lead) => (
                  <tr key={lead.lead_id} className="border-b border-line align-top last:border-0">
                    <td className="px-4 py-3">
                      <span className="font-semibold tabular-nums">{lead.score}%</span>
                      <div className="mt-1 h-1 w-12 rounded-full bg-line">
                        <div className="h-1 rounded-full bg-accent" style={{ width: `${Math.min(100, lead.score * 2)}%` }} />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium">{lead.business}</p>
                      <p className="text-xs text-muted">{SEGMENTS[lead.segment]} · {lead.city} · {lead.language}</p>
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
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
