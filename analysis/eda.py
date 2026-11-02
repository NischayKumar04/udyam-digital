"""Reproducible analysis of the Track A data pack (Project Udyam Digital).

Run from the repo root:  python analysis/eda.py
The deck's funnel, segment and planted-signal figures come from this script. Needs pandas.
"""
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

ROOT = Path(__file__).resolve().parent.parent
L = pd.read_csv(ROOT / "smb_leads.csv")
P = pd.read_csv(ROOT / "product_catalogue.csv").set_index("product_id")
L["act"] = (L.outcome == "Activated").astype(int)
STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
L["stage_idx"] = L.stage_reached.map({s: i for i, s in enumerate(STAGES)})
A = L[L.act == 1].copy()
A["churn"] = (A.churned_within_6_months == "Y").astype(int)


def section(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}")


def nps(scores):
    return 100 * ((scores >= 9).mean() - (scores <= 6).mean())


def pass_through(df):
    reach = [(df.stage_idx >= i).sum() for i in range(len(STAGES))]
    return " | ".join(f"{STAGES[i]} {reach[i] / reach[i - 1]:.0%}" for i in range(1, len(STAGES)))


def economics(col):
    g = L.groupby(col).agg(leads=("lead_id", "size"), activated=("act", "sum"), conv=("act", "mean"))
    g["cac_per_activation"] = L.groupby(col).acquisition_cost_inr.sum() / g.activated.replace(0, np.nan)
    g["median_bundle"] = A.groupby(col).monthly_bundle_value_inr.median()
    g["churn_6m"] = A.groupby(col).churn.mean()
    g["conv"] = (g.conv * 100).round(1)
    g["churn_6m"] = (g.churn_6m * 100).round(1)
    return g.sort_values("conv", ascending=False).round(0)


section("Funnel and headline metrics")
print(f"Leads {len(L)} -> activated {len(A)} ({L.act.mean():.1%})")
print("Pass-through:", pass_through(L))
print(f"Days lead->activation {A.days_lead_to_activation.mean():.1f} | follow-up calls {A.customer_follow_up_calls.mean():.2f}"
      f" | CAC/activation Rs {L.acquisition_cost_inr.sum() / len(A):,.0f} | median bundle Rs {A.monthly_bundle_value_inr.median():,.0f}"
      f" | 6m churn {A.churn.mean():.1%} | NPS {nps(A.nps_score):.0f}")

section("Segment economics")
print(economics("segment").to_string())

section("Lead source economics")
print(economics("lead_source").to_string())

section("GSTIN effect")
print(economics("has_gstin").to_string())
for flag, d in L.groupby("has_gstin"):
    print(f"has_gstin={flag}: {pass_through(d)}")
t = L.groupby(["segment", "has_gstin", "has_udyam"]).act.agg(["size", "mean"])
t["mean"] = (t["mean"] * 100).round(1)
print(t.rename(columns={"size": "leads", "mean": "conv_%"}).to_string())

section("Language gap (stage pass-through)")
L["lang_group"] = np.select(
    [L.preferred_language.isin(["Tamil", "Kannada", "Punjabi"]), L.preferred_language.isin(["Hindi", "English"])],
    ["Tamil/Kannada/Punjabi", "Hindi/English"], "Other regional")
for g, d in L.groupby("lang_group"):
    print(f"{g:22s} conv {d.act.mean():.1%} | {pass_through(d)}")
print((pd.crosstab(L.lead_source, L.lang_group, values=L.act, aggfunc="mean") * 100).round(1).to_string())

section("Drop reasons mapped to the module that removes them")
MODULE = {
    "Owner had no time for a visit": "Advisor", "Visit not scheduled by sales": "Advisor",
    "Quote too complex to understand": "Quote", "Quote took too long to arrive": "Quote",
    "Price too high": "Pricing/bundle fit", "Competitor offered cheaper plan": "Pricing/bundle fit",
    "Missing GST or Udyam document": "Smart KYC", "Found paperwork too long": "Smart KYC",
    "Authorised signatory not available": "Smart KYC", "Document details did not match": "Smart KYC",
    "Installation delayed beyond 21 days": "Tracker/fulfilment", "Customer cancelled before install": "Tracker/fulfilment",
    "Site not feasible for fibre": "Tracker/fulfilment", "First payment failed": "Tracker/fulfilment",
}
D = L[L.outcome == "Dropped"].copy()
D["module"] = D.drop_reason.map(MODULE).fillna("Lead engagement / other")
print(pd.crosstab([D.module, D.drop_reason], D.stage_reached, margins=True).to_string())

section("Post-activation: status chasing vs churn and NPS")
by_calls = A.groupby("customer_follow_up_calls").agg(n=("lead_id", "size"), churn=("churn", "mean"))
by_calls["nps"] = A.groupby("customer_follow_up_calls").nps_score.apply(nps)
by_calls["churn"] = (by_calls.churn * 100).round(1)
print(by_calls.round(0).to_string())
A["days_bin"] = pd.cut(A.days_lead_to_activation, [0, 14, 21, 200], labels=["<=14d", "15-21d", ">21d"])
by_days = A.groupby("days_bin", observed=True).agg(n=("lead_id", "size"), churn=("churn", "mean"))
by_days["nps"] = A.groupby("days_bin", observed=True).nps_score.apply(nps)
print(by_days.round(2).to_string())
stage_gaps = {
    "lead->contacted": ("created_date", "contacted_date"), "contacted->needs": ("contacted_date", "needs_assessed_date"),
    "needs->quote": ("needs_assessed_date", "quote_accepted_date"), "quote->kyc": ("quote_accepted_date", "kyc_complete_date"),
    "kyc->activated": ("kyc_complete_date", "activated_date"),
}
print("Mean days per step:", {k: round((pd.to_datetime(A[b]) - pd.to_datetime(A[a])).dt.days.mean(), 1) for k, (a, b) in stage_gaps.items()})

section("Bundles that break catalogue rules (mis-selling)")
SEG = {"Micro retail & services": "micro", "Professional offices": "prof",
       "Small multi-site businesses": "multi", "Small manufacturers": "mfg"}
violations, no_overlap = [], 0
for _, r in A.iterrows():
    items = [(p, int(q)) for p, q in re.findall(r"(P\d\d)x(\d+)", r.bundle_products)]
    ids = {p for p, _ in items}
    no_overlap += not (ids & set(str(r.products_of_interest).split(";")))
    for p, _ in items:
        pr = P.loc[p]
        if str(r.city_tier) not in str(pr.available_city_tiers).split(";"):
            violations.append((r.lead_id, p, "not sold in this city tier"))
        if r.employee_count < pr.min_employees:
            violations.append((r.lead_id, p, "below min employees"))
        if r.num_sites < pr.min_sites:
            violations.append((r.lead_id, p, "below min sites"))
        if pr.requires_gstin == "Y" and r.has_gstin != "Y":
            violations.append((r.lead_id, p, "needs GSTIN"))
        if isinstance(pr.requires_one_of, str) and not set(pr.requires_one_of.split("|")) & ids:
            violations.append((r.lead_id, p, "missing required base product"))
V = pd.DataFrame(violations, columns=["lead_id", "product", "rule"])
print(f"{V.lead_id.nunique()} of {len(A)} activated bundles break at least one rule;"
      f" {no_overlap} ({no_overlap / len(A):.0%}) contain none of the products the lead asked about")
print(V.groupby(["product", "rule"]).size().sort_values(ascending=False).to_string())

section("Lead score")
print("See prototype/backend/scripts/train_propensity.py, which trains it and tests it across 200 random splits.")
