"""Deterministic bundle recommendation: what to sell, and why, in plain language.

The LLM's job is to turn a conversation into a RecommendRequest and explain the result.
Everything here is rule-based, so a recommendation can't break a catalogue rule or
quote a price outside the catalogue, whatever the conversation says.
"""
import math
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

from .catalogue import CONNECTION_PRODUCTS, load_catalogue
from .pricing import LineItem, Quote, build_quote
from .product_text import describe, note, reason
from .profile import BusinessProfile, ResolvedProfile, resolve_profile
from .rules import bundle_violations, dependency_violation, eligibility_violations


class Need(str, Enum):
    FIBRE_100 = "fibre_100"
    FIBRE_300 = "fibre_300"
    HIGH_SPEED = "fibre_1g"
    WIRELESS_INTERNET = "airfiber_wireless"
    DEDICATED_INTERNET = "leased_line"
    LEASED_LINE_100 = "leased_line_100"
    PREMIUM_MOBILE = "premium_mobile"
    FAILOVER = "backup_internet"
    CENTRAL_MANAGEMENT = "central_management"
    MOBILE_LINES = "mobile_lines"
    MOBILE_ONLY = "mobile_only"
    STATIC_IP = "static_ip"
    PHONE_SYSTEM = "phone_system"
    TOLL_FREE = "toll_free"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    BACKUP = "data_backup"
    WEBSITE = "website"
    BILLING_POS = "billing_machine"
    ANTIVIRUS = "antivirus"
    FIREWALL = "firewall"
    GUEST_WIFI = "customer_wifi"
    CCTV = "cctv"
    MACHINE_MONITORING = "machine_monitoring"
    FLEET_TRACKING = "fleet_tracking"


NEED_PRODUCTS = {
    Need.FIBRE_100: "P01", Need.FIBRE_300: "P02", Need.WIRELESS_INTERNET: "P04",
    Need.LEASED_LINE_100: "P06", Need.PREMIUM_MOBILE: "P08",
    Need.HIGH_SPEED: "P03", Need.DEDICATED_INTERNET: "P05", Need.FAILOVER: "P09",
    Need.CENTRAL_MANAGEMENT: "P10", Need.STATIC_IP: "P11", Need.PHONE_SYSTEM: "P12",
    Need.TOLL_FREE: "P13", Need.SMS: "P14", Need.WHATSAPP: "P15", Need.EMAIL: "P16",
    Need.BACKUP: "P17", Need.WEBSITE: "P18", Need.BILLING_POS: "P19", Need.ANTIVIRUS: "P20",
    Need.FIREWALL: "P21", Need.GUEST_WIFI: "P22", Need.CCTV: "P23",
    Need.MACHINE_MONITORING: "P24", Need.FLEET_TRACKING: "P25",
}

CORE_BY_SEGMENT = {
    "micro": [],
    "prof": ["P16", "P20", "P17"],
    "multi": ["P09", "P23"],
    "mfg": ["P16"],
}

ADDONS_BY_SEGMENT = {
    "micro": ["P19", "P22", "P23", "P18", "P15", "P14"],
    "prof": ["P09", "P11", "P12", "P15", "P14", "P13", "P18", "P21"],
    "multi": ["P10", "P19", "P22", "P16", "P20", "P21", "P15", "P13", "P12", "P25"],
    "mfg": ["P24", "P21", "P09", "P11", "P20", "P23", "P25"],
}

# What to offer when the owner asks for something they can't have.
ALTERNATIVES = {
    "P03": ["P02", "P01"],
    "P05": ["P03", "P02", "P01"],
    "P06": ["P05", "P03", "P02"],
    "P09": ["P02", "P01"],
    "P10": ["P09"],
    "P11": ["P02", "P01"],
    "P12": ["P08", "P07"],
    "P13": ["P08", "P07"],
    "P14": ["P18"],
    "P15": ["P18"],
    "P21": ["P20"],
    "P22": ["P02", "P01"],
}

# First out when the bundle is over budget; products the owner asked for go last.
_BUDGET_CUT_ORDER = ["P25", "P24", "P13", "P14", "P12", "P21", "P10", "P11", "P18", "P17", "P20", "P22", "P23", "P19", "P09", "P15", "P16"]
_CONNECTION_DOWNGRADES = {"P06": "P05", "P05": "P03", "P03": "P02", "P02": "P01", "P01": "P04"}


class RecommendRequest(BaseModel):
    profile: BusinessProfile
    needs: list[Need] = Field(default_factory=list)
    requested_products: list[str] = Field(default_factory=list)
    quantities: dict[str, int] = Field(default_factory=dict)
    budget_monthly: int | None = Field(default=None, ge=1)
    contract_months: int | None = None
    current_monthly_spend: int | None = Field(default=None, ge=0)
    language: str = "English"


class RecommendedItem(BaseModel):
    product_id: str
    name: str
    unit: str
    quantity: int
    reason: str
    asked: bool
    monthly: int = 0
    setup: int = 0
    contract_months_if_added: int | None = None


class UnavailableProduct(BaseModel):
    product_id: str
    name: str
    asked: bool
    reason: str
    alternative_id: str | None = None
    alternative_name: str | None = None


class Recommendation(BaseModel):
    segment: str
    city_tier: int
    coverage_confirmed: bool
    has_active_gstin: bool
    gstin_status: str | None
    bundle: list[RecommendedItem]
    addons: list[RecommendedItem]
    unavailable: list[UnavailableProduct]
    quote: Quote
    within_budget: bool | None
    monthly_difference_vs_current: int | None
    notes: list[str]


@dataclass
class _Pick:
    quantity: int
    asked: bool


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class _Builder:
    def __init__(self, resolved: ResolvedProfile, request: RecommendRequest):
        self.catalogue = load_catalogue()
        self.facts = resolved.facts
        self.segment = resolved.segment
        self.fibre_feasible = resolved.fibre_feasible
        self.request = request
        self.language = request.language
        self.needs = set(request.needs)
        self.selected: dict[str, _Pick] = {}
        self.unavailable: dict[str, UnavailableProduct] = {}
        self.extra_addons: list[str] = []
        self.notes = list(resolved.notes)

        requested = [p for p in request.requested_products if p in self.catalogue]
        ignored = sorted(set(request.requested_products) - self.catalogue.keys())
        if ignored:
            self.notes.append(note(self.language, "ignored", names=", ".join(ignored)))
        from_needs = [NEED_PRODUCTS[n] for n in request.needs if n in NEED_PRODUCTS]
        self.asked = list(dict.fromkeys(requested + from_needs))

    def default_quantity(self, product_id: str) -> int:
        facts, segment = self.facts, self.segment
        sites, staff = facts.num_sites, facts.employee_count
        if product_id in self.request.quantities:
            return max(1, self.request.quantities[product_id])
        if product_id in {"P01", "P02", "P03", "P04", "P09", "P10", "P19", "P22"}:
            return sites
        if product_id in {"P07", "P08"}:
            lines = {"micro": 1, "prof": 2, "mfg": 3}.get(segment, _clamp(math.ceil(sites / 2) + 1, 2, 6))
            return min(lines, staff)
        if product_id == "P12":
            return _clamp(staff // 5, 1, 3)
        if product_id == "P16":
            return _clamp(math.ceil(staff * 0.6), 1, 20)
        if product_id == "P20":
            return _clamp(math.ceil(staff * 0.4), 1, 12)
        if product_id == "P23":
            return 2 * sites
        if product_id == "P24":
            return _clamp(staff // 10, 1, 12)
        if product_id == "P25":
            return 5
        return 1

    def _blockers(self, product_id: str) -> list[str]:
        product = self.catalogue[product_id]
        messages = [describe(v, self.language) for v in eligibility_violations(product, self.facts)]
        if not self.fibre_feasible and product_id in {"P01", "P02", "P03"}:
            messages.append(note(self.language, "no_fibre", name=product.name))
        dependency = dependency_violation(product, set(self.selected))
        if dependency:
            messages.append(describe(dependency, self.language))
        return messages

    def _alternative_for(self, product_id: str) -> str | None:
        options = ALTERNATIVES.get(product_id, [])
        for option in options:
            if option in self.selected:
                return option
        for option in options:
            if not self._blockers(option):
                return option
        return None

    def _mark_unavailable(self, product_id: str, asked: bool, messages: list[str], alternative: str | None = None) -> None:
        alternative = alternative or (self._alternative_for(product_id) if asked else None)
        if alternative and alternative not in self.selected and alternative not in CONNECTION_PRODUCTS:
            self.extra_addons.append(alternative)
        self.unavailable[product_id] = UnavailableProduct(
            product_id=product_id,
            name=self.catalogue[product_id].name,
            asked=asked,
            reason=" ".join(messages),
            alternative_id=alternative,
            alternative_name=self.catalogue[alternative].name if alternative else None,
        )

    def _try_add(self, product_id: str, asked: bool = False, quantity: int | None = None) -> bool:
        blockers = self._blockers(product_id)
        if blockers:
            self._mark_unavailable(product_id, asked, blockers)
            return False
        self.selected[product_id] = _Pick(quantity or self.default_quantity(product_id), asked)
        return True

    def _connection_preferences(self) -> list[str]:
        if not self.fibre_feasible:
            return ["P04"]
        if Need.DEDICATED_INTERNET in self.needs or self.segment == "mfg":
            return ["P05", "P03", "P02", "P01"]
        if Need.HIGH_SPEED in self.needs:
            return ["P03", "P02", "P01"]
        if self.segment == "micro":
            return ["P01"]
        if self.segment == "multi" and self.facts.employee_count / self.facts.num_sites < 10:
            return ["P01", "P02"]
        return ["P02", "P01"]

    def _add_connection(self) -> None:
        blocked, chosen = [], None
        for product_id in (p for p in self.asked if p in CONNECTION_PRODUCTS):
            blockers = self._blockers(product_id)
            if blockers:
                blocked.append((product_id, blockers))
            elif chosen is None:
                chosen = product_id
        was_asked = chosen is not None

        if chosen is None:
            closest = ALTERNATIVES[blocked[0][0]] if blocked else []
            chosen = next(p for p in closest + self._connection_preferences() + ["P04"] if not self._blockers(p))

        if chosen in {"P05", "P06"}:
            self.selected[chosen] = _Pick(self.request.quantities.get(chosen, 1), was_asked)
            if self.facts.num_sites > 1 and not self._blockers("P02"):
                # A leased line goes to the main site; other sites get business fibre.
                self.selected["P02"] = _Pick(self.facts.num_sites - 1, False)
        else:
            self.selected[chosen] = _Pick(self.default_quantity(chosen), was_asked)

        for product_id, blockers in blocked:
            self._mark_unavailable(product_id, True, blockers, alternative=chosen)

    def _line_product(self) -> str:
        if self.segment == "micro" or (self.segment == "prof" and self.facts.employee_count < 10):
            return "P07"
        return "P08"

    def build(self) -> None:
        asked_lines = [p for p in self.asked if p in {"P07", "P08"}]
        line_product = asked_lines[0] if asked_lines else self._line_product()
        line_asked = bool(asked_lines) or Need.MOBILE_LINES in self.needs or Need.MOBILE_ONLY in self.needs

        if Need.MOBILE_ONLY in self.needs:
            self._try_add(line_product, asked=True)
            self.notes.append(note(self.language, "mobile_only"))
            return

        self._add_connection()
        self._try_add(line_product, asked=line_asked)
        for product_id in CORE_BY_SEGMENT[self.segment]:
            if product_id not in self.asked:
                self._try_add(product_id)
        for product_id in self.asked:
            if product_id not in CONNECTION_PRODUCTS and product_id not in self.selected:
                self._try_add(product_id, asked=True)

    def _quote_for(self, picks: dict[str, _Pick]) -> Quote:
        lines = [LineItem(product_id=p, quantity=pick.quantity) for p, pick in picks.items()]
        return build_quote(lines, self.facts, self.segment, self.request.contract_months)

    def _fits_budget(self) -> bool:
        return self._quote_for(self.selected).monthly_subtotal <= self.request.budget_monthly

    def _drop(self, product_id: str, dropped: list[str]) -> None:
        del self.selected[product_id]
        dropped.append(product_id)
        for other in list(self.selected):
            if dependency_violation(self.catalogue[other], set(self.selected)):
                self._drop(other, dropped)

    def _downgrade_connection(self, dropped: list[str]) -> bool:
        main = next((p for p in _CONNECTION_DOWNGRADES if p in self.selected), None)
        cheaper = _CONNECTION_DOWNGRADES.get(main)
        while cheaper and self._blockers(cheaper):
            cheaper = _CONNECTION_DOWNGRADES.get(cheaper)
        if cheaper is None:
            return False
        del self.selected[main]
        self.selected[cheaper] = _Pick(self.default_quantity(cheaper), False)
        self.notes.append(note(self.language, "moved", old=self.catalogue[main].name, new=self.catalogue[cheaper].name))
        for other in list(self.selected):
            if other in self.selected and dependency_violation(self.catalogue[other], set(self.selected)):
                self._drop(other, dropped)
        return True

    def fit_budget(self) -> bool | None:
        budget = self.request.budget_monthly
        if budget is None:
            return None
        dropped: list[str] = []

        # 1. Remove what the owner didn't ask for, least essential first.
        for product_id in _BUDGET_CUT_ORDER:
            pick = self.selected.get(product_id)
            if pick and not pick.asked and not self._fits_budget():
                self._drop(product_id, dropped)

        # 2. Cheaper lines keep the same number of people connected, so try them before trimming.
        line = self.selected.get("P08")
        if line and not line.asked and "P07" not in self.selected and not self._fits_budget():
            self.selected["P07"] = self.selected.pop("P08")

        # 3. Trim quantities on everything except connections.
        for product_id, pick in self.selected.items():
            if product_id not in CONNECTION_PRODUCTS and pick.quantity > 1 and not self._fits_budget():
                pick.quantity = 1
                self.notes.append(note(self.language, "reduced", name=self.catalogue[product_id].name))

        # 4. Move to a cheaper connection.
        while not self._fits_budget() and self._downgrade_connection(dropped):
            pass

        # 5. Last resort: drop the rest, keeping the connection as the minimum plan.
        for product_id in [p for p in self.selected if p not in CONNECTION_PRODUCTS]:
            if product_id in self.selected and len(self.selected) > 1 and not self._fits_budget():
                self._drop(product_id, dropped)

        # 6. Put back anything that still fits, most essential first.
        for product_id in reversed(list(dict.fromkeys(dropped))):
            if product_id not in self.selected and not self._blockers(product_id):
                self.selected[product_id] = _Pick(self.default_quantity(product_id), False)
                if not self._fits_budget():
                    del self.selected[product_id]

        dropped = [p for p in dict.fromkeys(dropped) if p not in self.selected]
        self.extra_addons.extend(dropped)
        if dropped:
            names = ", ".join(self.catalogue[p].name for p in dropped)
            self.notes.append(note(self.language, "left_out", budget=f"{budget:,}", names=names))
        within = self._fits_budget()
        if not within:
            cheapest = self._quote_for(self.selected).monthly_subtotal
            self.notes.append(note(self.language, "lowest_plan", cheapest=f"{cheapest:,}", budget=f"{budget:,}"))
        return within

    def addon_items(self) -> list[RecommendedItem]:
        seen = set(self.selected)
        items = []
        candidates = list(dict.fromkeys(self.extra_addons + ADDONS_BY_SEGMENT[self.segment]))
        if Need.MOBILE_ONLY in self.needs:
            candidates = ["P04" if not self.fibre_feasible else "P01"]
        for product_id in candidates:
            if product_id in seen:
                continue
            seen.add(product_id)
            blockers = self._blockers(product_id)
            if blockers:
                if product_id not in self.unavailable:
                    self._mark_unavailable(product_id, False, blockers)
                continue
            quantity = self.default_quantity(product_id)
            base = self._quote_for(self.selected)
            added = self._quote_for({**self.selected, product_id: _Pick(quantity, False)})
            items.append(RecommendedItem(
                product_id=product_id,
                name=self.catalogue[product_id].name,
                unit=self.catalogue[product_id].unit,
                quantity=quantity,
                reason=reason(product_id, self.language),
                asked=False,
                monthly=added.monthly_subtotal - base.monthly_subtotal,
                setup=added.one_time_setup - base.one_time_setup,
                contract_months_if_added=added.contract_months if added.contract_months != base.contract_months else None,
            ))
        return items

    def bundle_items(self) -> list[RecommendedItem]:
        lines = {line.product_id: line for line in self._quote_for(self.selected).lines}
        return [
            RecommendedItem(
                product_id=product_id,
                name=self.catalogue[product_id].name,
                unit=self.catalogue[product_id].unit,
                quantity=pick.quantity,
                reason=reason(product_id, self.language),
                asked=pick.asked,
                monthly=lines[product_id].monthly,
                setup=lines[product_id].setup_total,
            )
            for product_id, pick in sorted(self.selected.items())
        ]


def recommend(request: RecommendRequest) -> Recommendation:
    resolved = resolve_profile(request.profile, request.language)
    builder = _Builder(resolved, request)
    builder.build()
    within_budget = builder.fit_budget()

    # The builder should never produce a broken bundle; if it ever does, don't sell it.
    while violations := bundle_violations(set(builder.selected), resolved.facts):
        for violation in violations:
            builder.selected.pop(violation.product_id, None)

    quote = builder._quote_for(builder.selected)
    addons = builder.addon_items()
    spend = request.current_monthly_spend
    return Recommendation(
        segment=resolved.segment,
        city_tier=resolved.facts.city_tier,
        coverage_confirmed=resolved.coverage_confirmed,
        has_active_gstin=resolved.facts.has_active_gstin,
        gstin_status=resolved.gstin_status,
        bundle=builder.bundle_items(),
        addons=addons,
        unavailable=list(builder.unavailable.values()),
        quote=quote,
        within_budget=within_budget,
        monthly_difference_vs_current=quote.monthly_subtotal - spend if spend is not None else None,
        notes=builder.notes,
    )
