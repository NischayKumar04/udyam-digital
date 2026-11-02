"""The queue for sales and partners: which leads to call, why, and who should call them.

This is how the digital journey adds to the field force and partners rather than
competing with them. They get warmer leads, each with a reason and a next step.
"""
import csv
import json
import math
from functools import lru_cache
from pathlib import Path

from .config import LEADS_CSV
from .identifiers import mask_name
from .profile import SEGMENT_CODES

_MODEL_PATH = Path(__file__).with_name("propensity_model.json")

NEXT_ACTIONS = {
    "Owner had no time for a visit": "Send the advisor link: no visit needed",
    "Visit not scheduled by sales": "Send the advisor link and apologise for the missed visit",
    "Quote too complex to understand": "Send a one-price quote in their language",
    "Quote took too long to arrive": "Send an instant quote today",
    "Price too high": "Offer the entry bundle and show what's optional",
    "Competitor offered cheaper plan": "Compare the whole bundle, not just the internet line",
    "Decided to wait": "Check back with a reminder",
    "Missing GST or Udyam document": "Send the lookup-based KYC link, or offer the no-GST path",
    "Found paperwork too long": "Send the lookup-based KYC link",
    "Authorised signatory not available": "Send a remote e-sign link",
    "Document details did not match": "Review the mismatch and call with the fix",
    "Installation delayed beyond 21 days": "Escalate the install and give a firm date",
    "Customer cancelled before install": "Ask why, and offer a quicker install",
    "Site not feasible for fibre": "Offer AirFiber, live in about 2 days",
    "First payment failed": "Retry with UPI autopay",
    "Locked in with current provider": "Ask for the contract end date and set a reminder",
    "Only wanted a mobile plan": "Offer mobile lines only, month to month",
    "Not interested on first call": "Leave alone for now, nudge on WhatsApp next quarter",
    "Unreachable after 3 attempts": "Try WhatsApp instead of calling",
}

# Wrong numbers can't be recovered, and activated customers aren't leads any more.
_NOT_WORKABLE = {"Wrong or invalid number"}
# These can't be acted on today, so however well they score, they wait behind everyone else.
_NOT_NOW = {"Not interested on first call", "Locked in with current provider", "Decided to wait"}
_LOW_CONVERTING_LANGUAGES = {"Tamil", "Kannada", "Punjabi"}

_REASON_LABELS = {
    "has_gstin=Y": "Has GST registration",
    "lead_source=Referral": "Came through a referral",
    "lead_source=Inbound call": "Called us first",
    "segment=Professional offices": "Professional office",
    "segment=Small multi-site businesses": "Multi-site business",
    "segment=Small manufacturers": "Manufacturer",
    "current_internet=Leased line": "Already on a leased line",
    "current_internet=Mixed per site": "Mixed providers across sites",
    "annual_turnover_band=5 - 25 cr": "Turnover ₹5-25 crore",
    "current_provider=Accel (mobile only)": "Already an Accel mobile customer",
    "current_provider=Accel": "Already an Accel customer",
}


@lru_cache(maxsize=1)
def _model() -> dict:
    return json.loads(_MODEL_PATH.read_text(encoding="utf-8"))


def _features(lead: dict) -> dict[str, float]:
    features = {
        "city_tier": float(lead["city_tier"]),
        "log_employees": math.log1p(float(lead["employee_count"])),
        "num_sites": float(lead["num_sites"]),
        "log_spend": math.log1p(float(lead["monthly_telecom_spend_inr"])),
        "interest_count": float(lead["products_of_interest"].count(";") + 1 if lead["products_of_interest"] else 1),
    }
    for column in ("lead_source", "segment", "preferred_language", "annual_turnover_band", "has_gstin", "has_udyam", "current_internet", "current_provider", "contact_role"):
        features[f"{column}={lead[column]}"] = 1.0
    return features


def score_lead(lead: dict) -> tuple[float, list[str]]:
    """Chance of activating, and the plain-language reasons pushing it up the most."""
    model = _model()
    coefficients = model["coefficients"]
    contributions = {name: coefficients.get(name, 0.0) * value for name, value in _features(lead).items()}
    probability = 1 / (1 + math.exp(-(model["intercept"] + sum(contributions.values()))))
    ranked = sorted(contributions, key=contributions.get, reverse=True)
    reasons = [_REASON_LABELS[name] for name in ranked if name in _REASON_LABELS and contributions[name] > 0][:3]
    return probability, reasons


def suggested_owner(lead: dict) -> str:
    segment = SEGMENT_CODES[lead["segment"]]
    if segment in {"multi", "mfg"}:
        return "Field sales"
    if lead["has_gstin"] == "N" or lead["preferred_language"] in _LOW_CONVERTING_LANGUAGES:
        return "Local partner"
    return "Digital follow-up"


@lru_cache(maxsize=1)
def _queue() -> list[dict]:
    with LEADS_CSV.open(encoding="utf-8", newline="") as f:
        leads = [lead for lead in csv.DictReader(f) if lead["outcome"] == "Dropped" and lead["drop_reason"] not in _NOT_WORKABLE]
    rows = []
    for lead in leads:
        probability, reasons = score_lead(lead)
        rows.append({
            "lead_id": lead["lead_id"],
            "business": lead["business_name"],
            "contact": mask_name(lead["contact_name"]),
            "segment": SEGMENT_CODES[lead["segment"]],
            "city": lead["city"],
            "language": lead["preferred_language"],
            "source": lead["lead_source"],
            "stage": lead["stage_reached"],
            "drop_reason": lead["drop_reason"],
            "score": round(probability * 100),
            "reasons": reasons,
            "owner": suggested_owner(lead),
            "next_action": NEXT_ACTIONS.get(lead["drop_reason"], "Review"),
        })
    return sorted(rows, key=lambda row: (row["drop_reason"] in _NOT_NOW, -row["score"]))


def queue(owner: str | None = None, limit: int = 50) -> dict:
    rows = _queue()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["owner"]] = counts.get(row["owner"], 0) + 1
    if owner:
        rows = [row for row in rows if row["owner"] == owner]
    return {
        "total": len(_queue()),
        "by_owner": counts,
        "model": _model()["holdout_metrics"],
        "leads": rows[:limit],
    }
