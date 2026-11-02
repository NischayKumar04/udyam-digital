"""Orders and the tracker the owner checks instead of calling support.

Stages are stored as keys so the app can show them in the owner's language. Prices are
always recalculated here, so nothing the browser sends can change what's charged.
"""
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import TODAY
from .pricing import LineItem, Quote, build_quote
from .rules import BusinessFacts

STAGES_WITH_VISIT = ["placed", "documents", "site_check", "scheduled", "installed", "live"]
STAGES_WITHOUT_VISIT = ["placed", "documents", "delivered", "live"]

# Verdicts that block an order until the owner fixes something.
BLOCKING_VERDICTS = {"REJECT", "REUPLOAD"}
VERIFIED_VERDICTS = {"PASS", "PASS_WITH_WARNING", "AUTO_RESOLVE"}


class OrderBlocked(Exception):
    pass


@dataclass
class Order:
    id: str
    created_on: date
    quote: Quote
    kyc_verdict: str
    language: str
    stages: list[str]
    stage_index: int = 0
    stage_dates: dict[str, date] = field(default_factory=dict)
    updates: list[dict] = field(default_factory=list)


_orders: dict[str, Order] = {}


def _planned_dates(stages: list[str], days_to_live: int, documents_days: int) -> dict[str, date]:
    start, live = TODAY, TODAY + timedelta(days=max(days_to_live, documents_days))
    planned = {
        "placed": start,
        "documents": start + timedelta(days=documents_days),
        "site_check": min(start + timedelta(days=documents_days + 1), live),
        "scheduled": min(start + timedelta(days=documents_days + 1), live),
        "installed": live,
        "delivered": live,
        "live": live,
    }
    return {stage: planned[stage] for stage in stages}


def _update(order: Order, stage: str) -> None:
    order.updates.append({"stage": stage, "on": order.stage_dates[stage].isoformat()})


def create_order(lines: list[LineItem], facts: BusinessFacts, segment: str, contract_months: int | None, kyc_verdict: str, language: str) -> Order:
    quote = build_quote(lines, facts, segment, contract_months)
    if kyc_verdict == "REJECT" and not facts.has_active_gstin and quote.valid:
        # The rules engine already kept GST-only products out of this plan, so it can go ahead once reviewed.
        kyc_verdict = "MANUAL_REVIEW"
    if kyc_verdict in BLOCKING_VERDICTS:
        raise OrderBlocked("Please fix the KYC items first.")
    if not quote.valid:
        raise OrderBlocked(quote.violations[0].message)

    has_visit = any(line.install_days > 1 for line in quote.lines)
    stages = STAGES_WITH_VISIT if has_visit else STAGES_WITHOUT_VISIT
    documents_days = 0 if kyc_verdict in VERIFIED_VERDICTS else 1
    order = Order(
        id=f"UD-{random.randint(10_000_000, 99_999_999)}",
        created_on=TODAY,
        quote=quote,
        kyc_verdict=kyc_verdict,
        language=language,
        stages=stages,
        stage_dates=_planned_dates(stages, quote.expected_activation_days, documents_days),
    )
    _update(order, "placed")
    if kyc_verdict in VERIFIED_VERDICTS:
        order.stage_index = 1
        _update(order, "documents")
    _orders[order.id] = order
    return order


def get_order(order_id: str) -> Order | None:
    return _orders.get(order_id)


def advance(order: Order) -> Order:
    """Moves the order on one stage. Stands in for field and operations systems in the demo."""
    if order.stage_index < len(order.stages) - 1:
        order.stage_index += 1
        _update(order, order.stages[order.stage_index])
    return order


def order_view(order: Order) -> dict:
    """What the owner sees: where it is, what's next, and when each service goes live."""
    current = order.stages[order.stage_index]
    under_review = current == "placed" and order.kyc_verdict == "MANUAL_REVIEW"
    next_stage = order.stages[order.stage_index + 1] if order.stage_index + 1 < len(order.stages) else None
    return {
        "id": order.id,
        "language": order.language,
        "current_stage": current,
        "under_review": under_review,
        "is_live": current == "live",
        "next_stage": next_stage,
        "next_stage_on": order.stage_dates[next_stage].isoformat() if next_stage else None,
        "live_on": order.stage_dates["live"].isoformat(),
        "stages": [
            {
                "key": stage,
                "state": "done" if i < order.stage_index or current == "live" else "current" if i == order.stage_index else "pending",
                "on": order.stage_dates[stage].isoformat(),
            }
            for i, stage in enumerate(order.stages)
        ],
        "services": [
            {
                "name": line.name,
                "quantity": line.quantity,
                "live_on": (order.created_on + timedelta(days=line.install_days)).isoformat(),
                "is_live": current == "live",
            }
            for line in sorted(order.quote.lines, key=lambda line: line.install_days)
        ],
        "updates": list(reversed(order.updates)),
        "monthly_total": order.quote.monthly_total,
        "pay_now": order.quote.pay_now,
        "contract_months": order.quote.contract_months,
    }
