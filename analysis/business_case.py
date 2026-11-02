"""Business-case numbers for slide 7: what the journey is worth, and on what assumptions.

Every input comes from smb_leads.csv or is named as an assumption below. Run from the repo root:
    python analysis/business_case.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
L = pd.read_csv(ROOT / "smb_leads.csv")
STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
L["stage_idx"] = L.stage_reached.map({s: i for i, s in enumerate(STAGES)})
A = L[L.outcome == "Activated"]

# The share of drops the journey recovers, in each scenario. The rest stay lost.
RECOVERY_SCENARIOS = {"Cautious": 0.15, "Base": 0.30, "Stretch": 0.50}
ADDRESSABLE = {
    # stage reached -> reasons the four modules directly remove
    "Contacted": ["Owner had no time for a visit", "Visit not scheduled by sales"],
    "Needs assessed": ["Quote too complex to understand", "Quote took too long to arrive"],
    "Quote accepted": ["Missing GST or Udyam document", "Found paperwork too long", "Authorised signatory not available", "Document details did not match"],
    "KYC complete": ["Installation delayed beyond 21 days", "Customer cancelled before install", "Site not feasible for fibre", "First payment failed"],
}
# Assumption: the margin left after network and service costs, before acquisition cost.
GROSS_MARGIN = 0.40
# Assumption: a digitally served lead still costs something: ads, AI, KYC checks, support.
DIGITAL_COST_PER_LEAD = 150
# Assumption: only half of field-sold micro and professional leads move to digital in the plan period.
FIELD_LEADS_MOVED = 0.5


def reach(stage: str) -> int:
    return int((L.stage_idx >= STAGES.index(stage)).sum())


def pass_rate(stage: str) -> float:
    i = STAGES.index(stage)
    return reach(STAGES[i + 1]) / reach(stage)


def extra_activations(recovery: float, group: pd.DataFrame = L) -> float:
    """A recovered lead carries on from the next stage at today's downstream pass rates."""
    extra = 0.0
    for stage, reasons in ADDRESSABLE.items():
        dropped = group[(group.stage_reached == stage) & group.drop_reason.isin(reasons)]
        survive = 1.0
        for later in STAGES[STAGES.index(stage) + 1 : -1]:
            survive *= pass_rate(later)
        extra += len(dropped) * recovery * survive
    return extra


print("=== Baseline, one quarter ===")
spend = L.acquisition_cost_inr.sum()
monthly_revenue = A.monthly_bundle_value_inr.sum()
print(f"Leads {len(L):,} | activated {len(A)} ({len(A) / len(L):.1%}) | acquisition spend ₹{spend:,.0f} | CAC ₹{spend / len(A):,.0f}")
print(f"New monthly revenue ₹{monthly_revenue:,.0f} | average bundle ₹{monthly_revenue / len(A):,.0f}")

print("\n=== Funnel bridge: addressable drops ===")
total_addressable = 0
for stage, reasons in ADDRESSABLE.items():
    count = int(L[(L.stage_reached == stage) & L.drop_reason.isin(reasons)].shape[0])
    total_addressable += count
    print(f"{stage:15s} {count:5d}  ({', '.join(reasons)})")
drops = int((L.outcome == "Dropped").sum())
print(f"Total {total_addressable:,} of {drops:,} drops ({total_addressable / drops:.0%})")

print("\n=== Scenarios, per quarter at today's lead volume ===")
field_mask = (L.lead_source == "Field sales") & L.segment.isin(["Micro retail & services", "Professional offices"])
field_cost = L[field_mask].acquisition_cost_inr.sum()
moved_leads = int(field_mask.sum() * FIELD_LEADS_MOVED)
saving = field_cost * FIELD_LEADS_MOVED - moved_leads * DIGITAL_COST_PER_LEAD
print(f"Field-sold micro and professional leads: {int(field_mask.sum()):,}, costing ₹{field_cost:,.0f}. Moving half saves ₹{saving:,.0f} a quarter.")

avg_bundle_by_segment = A.groupby("segment").monthly_bundle_value_inr.mean()
rows = []
for name, recovery in RECOVERY_SCENARIOS.items():
    extra_by_segment = {seg: extra_activations(recovery, L[L.segment == seg]) for seg in L.segment.unique()}
    extra = sum(extra_by_segment.values())
    activated = len(A) + extra
    extra_monthly = sum(extra_by_segment[seg] * avg_bundle_by_segment[seg] for seg in extra_by_segment)
    new_spend = spend - saving
    rows.append({
        "Scenario": name,
        "Recovered": f"{recovery:.0%}",
        "Activated": round(activated),
        "Conversion": f"{activated / len(L):.1%}",
        "CAC": round(new_spend / activated),
        "Extra monthly revenue (₹ lakh)": round(extra_monthly / 1e5, 1),
        "Extra annual revenue from one quarter's cohort (₹ cr)": round(extra_monthly * 12 / 1e7, 2),
        "Extra annual gross margin (₹ cr)": round(extra_monthly * 12 * GROSS_MARGIN / 1e7, 2),
    })
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== Unit economics by segment: CAC payback on gross margin ===")
for seg, group in L.groupby("segment"):
    active = group[group.outcome == "Activated"]
    cac = group.acquisition_cost_inr.sum() / len(active)
    bundle = active.monthly_bundle_value_inr.mean()
    churn = (active.churned_within_6_months == "Y").mean()
    margin = bundle * GROSS_MARGIN
    print(f"{seg:30s} CAC ₹{cac:7,.0f} | avg bundle ₹{bundle:7,.0f} | payback {cac / margin:5.1f} months at {GROSS_MARGIN:.0%} margin | 6m churn {churn:.1%}")

print("\n=== Micro retail: what digital has to achieve ===")
micro = L[L.segment == "Micro retail & services"]
micro_active = micro[micro.outcome == "Activated"]
bundle = micro_active.monthly_bundle_value_inr.mean()
print(f"Today: CAC ₹{micro.acquisition_cost_inr.sum() / len(micro_active):,.0f}, payback {micro.acquisition_cost_inr.sum() / len(micro_active) / (bundle * GROSS_MARGIN):.1f} months on a ₹{bundle:,.0f} bundle")
for target in (6, 12):
    print(f"To pay back in {target} months, CAC must be under ₹{bundle * GROSS_MARGIN * target:,.0f}")

print("\n=== Status chasing and churn ===")
one_two = A[A.customer_follow_up_calls <= 2]
four_five = A[A.customer_follow_up_calls >= 4]
print(f"1-2 calls: churn {(one_two.churned_within_6_months == 'Y').mean():.1%} (n={len(one_two)}) | 4-5 calls: churn {(four_five.churned_within_6_months == 'Y').mean():.1%} (n={len(four_five)})")
if_all_low = (one_two.churned_within_6_months == "Y").mean()
print(f"Bringing everyone to the 1-2 call rate would take 6-month churn from {(A.churned_within_6_months == 'Y').mean():.1%} to {if_all_low:.1%}")

print("\n=== Time to activate today, by step (days) ===")
dates = ["created_date", "contacted_date", "needs_assessed_date", "quote_accepted_date", "kyc_complete_date", "activated_date"]
values = A[dates].apply(pd.to_datetime)
steps = {f"{a[:-5]} -> {b[:-5]}": (values[b] - values[a]).dt.days.mean() for a, b in zip(dates, dates[1:])}
for step, days in steps.items():
    print(f"  {step:40s} {days:4.1f}")
before_install = sum(list(steps.values())[:-1])
print(f"Before installation: {before_install:.1f} days. Installation: {list(steps.values())[-1]:.1f} days.")
