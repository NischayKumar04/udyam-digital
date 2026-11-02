"""Replays Apr-Jun 2026 through our engine and prints the numbers quoted in the deck.

Run from prototype/backend:  python -m scripts.replay_quarter
"""
import csv
import re
import statistics
import sys

from app.catalogue import load_catalogue
from app.config import LEADS_CSV
from app.pricing import LineItem, build_quote
from app.profile import SEGMENT_CODES, BusinessProfile
from app.recommender import RecommendRequest, recommend
from app.registry import lookup_gstin
from app.rules import BusinessFacts, bundle_violations

sys.stdout.reconfigure(encoding="utf-8")

with LEADS_CSV.open(encoding="utf-8", newline="") as f:
    leads = list(csv.DictReader(f))
activated = [lead for lead in leads if lead["outcome"] == "Activated"]
catalogue = load_catalogue()


def status(lead: dict) -> str | None:
    record = lookup_gstin(lead["gstin"]) if lead["gstin"] else None
    return record["status"] if record else None


def products(lead: dict) -> list[tuple[str, int]]:
    return [(p, int(q)) for p, q in re.findall(r"(P\d\d)x(\d+)", lead["bundle_products"])]


def facts(lead: dict, active: bool) -> BusinessFacts:
    return BusinessFacts(int(lead["city_tier"]), int(lead["employee_count"]), int(lead["num_sites"]), active)


print("=== Rule breaks: what was sold vs what the engine recommends ===")
by_flag = sum(bool(bundle_violations({p for p, _ in products(l)}, facts(l, l["has_gstin"] == "Y"))) for l in activated)
by_registry = sum(bool(bundle_violations({p for p, _ in products(l)}, facts(l, status(l) == "Active"))) for l in activated)
print(f"Sold last quarter, trusting the lead's GSTIN flag: {by_flag} of {len(activated)} ({by_flag / len(activated):.1%})")
print(f"Sold last quarter, checking the registry too:      {by_registry} of {len(activated)} ({by_registry / len(activated):.1%})")

broken = 0
for lead in leads:
    rec = recommend(RecommendRequest(
        profile=BusinessProfile(
            business_type=lead["business_type"], city=lead["city"],
            employee_count=int(lead["employee_count"]), num_sites=int(lead["num_sites"]), gstin=lead["gstin"] or None,
        ),
        requested_products=[p for p in lead["products_of_interest"].split(";") if p],
    ))
    broken += not rec.quote.valid
print(f"Engine, replaying all {len(leads):,} leads with what each one asked for: {broken} rule breaks")

print("\n=== KYC that slipped through on an inactive GSTIN ===")
past_kyc = [l for l in leads if l["stage_reached"] in ("KYC complete", "Activated")]
inactive = [l for l in past_kyc if status(l) in ("Cancelled", "Suspended")]
gst_only = {p for p, product in catalogue.items() if product.requires_gstin}
print(f"Passed KYC on a Cancelled or Suspended GSTIN: {len(inactive)} of {len(past_kyc)} ({len(inactive) / len(past_kyc):.1%})")
active_on_inactive = [l for l in activated if status(l) in ("Cancelled", "Suspended")]
holding = [l for l in active_on_inactive if {p for p, _ in products(l)} & gst_only]
print(f"Activated on one: {len(active_on_inactive)}, of which {len(holding)} hold a product that requires an active GSTIN")

print("\n=== Pricing rule against what was actually charged, same bundles ===")
open_facts = BusinessFacts(1, 500, 50, True)
rows: dict[str, list[tuple[int, int]]] = {}
for lead in activated:
    segment = SEGMENT_CODES[lead["segment"]]
    lines = [LineItem(product_id=p, quantity=q) for p, q in products(lead)]
    rows.setdefault(segment, []).append((int(float(lead["monthly_bundle_value_inr"])), build_quote(lines, open_facts, segment).monthly_subtotal))
total_actual = total_rule = 0
for segment, pairs in rows.items():
    actual, rule = sum(a for a, _ in pairs), sum(r for _, r in pairs)
    total_actual, total_rule = total_actual + actual, total_rule + rule
    print(f"{segment:6s} n={len(pairs):3d}  actual avg ₹{actual / len(pairs):8,.0f}  rule avg ₹{rule / len(pairs):8,.0f}  {100 * (rule - actual) / actual:+.1f}%")
print(f"All    ₹{total_actual:,} a month vs ₹{total_rule:,} a month: {100 * (total_rule - total_actual) / total_actual:+.1f}%")

print("\n=== Starting recommendation vs what similar customers bought (median a month) ===")
medians: dict[str, list[tuple[int, int]]] = {}
for lead in activated:
    rec = recommend(RecommendRequest(profile=BusinessProfile(
        business_type=lead["business_type"], city=lead["city"],
        employee_count=int(lead["employee_count"]), num_sites=int(lead["num_sites"]), gstin=lead["gstin"] or None,
    )))
    medians.setdefault(SEGMENT_CODES[lead["segment"]], []).append((int(float(lead["monthly_bundle_value_inr"])), rec.quote.monthly_subtotal))
for segment, pairs in medians.items():
    print(f"{segment:6s} bought ₹{statistics.median(a for a, _ in pairs):8,.0f}   recommended ₹{statistics.median(b for _, b in pairs):8,.0f}")
