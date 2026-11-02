"""The queue for sales and partners: which leads to call, why, and who should call them.

This is how the digital journey adds to the field force and partners rather than
competing with them. They get warmer leads, each with a reason and a next step.

Two kinds of lead share the queue. Owners who asked for a call in the app come first, live
from their chat. After them come last quarter's dropped leads from the data pack.
"""
import csv
import json
import math
from functools import lru_cache
from pathlib import Path

from .advisor import chats_without_contact, sessions_asking_for_a_call
from .config import LEADS_CSV
from .identifiers import mask_mobile, mask_name
from .kyc_routes import last_checked_verdict
from .profile import SEGMENT_CODES, classify_segment

_MODEL_PATH = Path(__file__).with_name("propensity_model.json")
_SEGMENT_NAMES = {code: name for name, code in SEGMENT_CODES.items()}

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
_KYC_FOLLOW_UPS = {
    "REJECT": ("Registration can't be used", "Explain the plan without GST, or help them fix the registration"),
    "REUPLOAD": ("Documents need fixing", "Help them fix the documents, then finish the order"),
    "MANUAL_REVIEW": ("Documents need a review", "Check the documents, then help them place the order"),
}

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


def _chat_features(session) -> dict[str, float]:
    """The chat model's inputs: only what the advisor collects, because the chat never asks for the rest."""
    plan, profile = session.recommendation, session.request.profile
    return {
        "city_tier": float(plan.city_tier),
        "log_employees": math.log1p(profile.employee_count),
        "num_sites": float(profile.num_sites),
        "interest_count": float(max(1, len(session.request.needs))),
        f"segment={_SEGMENT_NAMES[plan.segment]}": 1.0,
        f"preferred_language={session.language}": 1.0,
        f"has_gstin={'Y' if plan.has_active_gstin else 'N'}": 1.0,
    }


def _score(model: dict, features: dict[str, float]) -> tuple[float, list[str]]:
    """Chance of activating, and the plain-language reasons pushing it up the most."""
    coefficients = model["coefficients"]
    contributions = {name: coefficients.get(name, 0.0) * value for name, value in features.items()}
    probability = 1 / (1 + math.exp(-(model["intercept"] + sum(contributions.values()))))
    ranked = sorted(contributions, key=contributions.get, reverse=True)
    reasons = [_REASON_LABELS[name] for name in ranked if name in _REASON_LABELS and contributions[name] > 0][:3]
    return probability, reasons


def score_lead(lead: dict) -> tuple[float, list[str]]:
    return _score(_model(), _features(lead))


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
            "live": False,
        })
    return sorted(rows, key=lambda row: (row["drop_reason"] in _NOT_NOW, -row["score"]))


def _reached(session) -> str:
    if session.kyc_application_id:
        return "Documents"
    if session.saw_price:
        return "Price"
    return "Plan" if session.recommendation else "Chat"


def _why_and_next(session) -> tuple[str, str]:
    """Why this owner wants a person, and what to do about it, from how far they got."""
    if session.kyc_application_id:
        verdict = last_checked_verdict(session.kyc_application_id)
        if verdict in _KYC_FOLLOW_UPS:
            return _KYC_FOLLOW_UPS[verdict]
        if verdict:
            return "Documents passed, no order yet", "Help them sign and place the order"
        return "Stopped at documents", "Explain what's needed, and that lookups replace most uploads"
    plan = session.recommendation
    if plan is None:
        return "Asked before getting a plan", "Ask the remaining questions and recommend a plan"
    if plan.within_budget is False:
        return "Plan is over their budget", "Offer the entry bundle and show what's optional"
    refused = next((item for item in plan.unavailable if item.asked), None)
    if refused:
        offer = f"offer {refused.alternative_name} instead" if refused.alternative_name else "say what's possible instead"
        return f"Couldn't get {refused.name}", f"Explain why, and {offer}"
    price = f"₹{plan.quote.monthly_subtotal:,}"
    if session.saw_price:
        return "Stopped at the price", f"Walk through the {price} plan and show what's optional"
    return "Wants to talk before buying", f"Walk through the {price} plan"


def _live_owner(session) -> str:
    plan, slots = session.recommendation, session.slots
    if plan:
        segment, has_gstin = plan.segment, plan.has_active_gstin
    else:
        # No plan yet, so go by what the owner has said. Unknown GST isn't treated as no GST.
        sites = slots.get("num_sites")
        segment = classify_segment(str(slots.get("business_type") or ""), sites if isinstance(sites, int) else 1)
        has_gstin = slots.get("has_gstin") is not False
    return suggested_owner({"segment": _SEGMENT_NAMES[segment], "has_gstin": "Y" if has_gstin else "N", "preferred_language": session.language})


def _said(session, slot: str) -> str:
    """Something the owner typed, kept short for a table cell."""
    value = str(session.slots.get(slot) or "").strip()[:60]
    return value[:1].upper() + value[1:]


def _live_rows() -> list[dict]:
    rows = []
    for session in sorted(sessions_asking_for_a_call(), key=lambda s: s.callback.requested_at, reverse=True):
        plan = session.recommendation
        probability, reasons = _score(_model()["chat_model"], _chat_features(session)) if plan else (None, [])
        reason, next_action = _why_and_next(session)
        rows.append({
            # Never the session id: this page has no login, and that id opens the owner's conversation.
            "lead_id": session.callback.lead_id,
            "business": _said(session, "business_type") or "Not known yet",
            "contact": mask_mobile(session.callback.mobile),
            "segment": plan.segment if plan else None,
            "city": _said(session, "city"),
            "language": session.language,
            "source": "Advisor",
            "stage": _reached(session),
            "drop_reason": reason,
            "score": round(probability * 100) if plan else None,
            "reasons": ["Asked for a call", *reasons],
            "owner": _live_owner(session),
            "next_action": next_action,
            "live": True,
        })
    return rows


def queue(owner: str | None = None, limit: int = 50) -> dict:
    live = _live_rows()
    rows = [*live, *_queue()]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["owner"]] = counts.get(row["owner"], 0) + 1
    total = len(rows)
    if owner:
        rows = [row for row in rows if row["owner"] == owner]
    return {
        "total": total,
        "live": len(live),
        "no_contact": chats_without_contact(),
        "by_owner": counts,
        "model": _model()["holdout_metrics"],
        "chat_model": _model()["chat_model"]["holdout_metrics"],
        "leads": rows[:limit],
    }
