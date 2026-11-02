"""Catalogue eligibility and dependency rules.

Every product the advisor offers and every quote it prices goes through this module.
The LLM never decides what is allowed.
"""
from dataclasses import dataclass, field
from enum import Enum

from .catalogue import Product, load_catalogue


class RuleCode(str, Enum):
    CITY_TIER = "CITY_TIER"
    MIN_EMPLOYEES = "MIN_EMPLOYEES"
    MIN_SITES = "MIN_SITES"
    GSTIN_REQUIRED = "GSTIN_REQUIRED"
    MISSING_BASE_PRODUCT = "MISSING_BASE_PRODUCT"


@dataclass(frozen=True)
class BusinessFacts:
    city_tier: int
    employee_count: int
    num_sites: int
    has_active_gstin: bool


@dataclass(frozen=True)
class Violation:
    product_id: str
    code: RuleCode
    message: str
    params: dict = field(default_factory=dict)


def eligibility_violations(product: Product, facts: BusinessFacts) -> list[Violation]:
    """Rules that depend only on the business, not on the rest of the bundle."""
    found = []
    if facts.city_tier not in product.city_tiers:
        found.append(Violation(product.id, RuleCode.CITY_TIER, f"{product.name} isn't sold in your city yet.", {"name": product.name}))
    if facts.employee_count < product.min_employees:
        found.append(Violation(
            product.id, RuleCode.MIN_EMPLOYEES,
            f"{product.name} is for businesses with at least {product.min_employees} employees; you have {facts.employee_count}.",
            {"name": product.name, "minimum": product.min_employees, "have": facts.employee_count},
        ))
    if facts.num_sites < product.min_sites:
        found.append(Violation(
            product.id, RuleCode.MIN_SITES,
            f"{product.name} is for businesses with at least {product.min_sites} sites; you have {facts.num_sites}.",
            {"name": product.name, "minimum": product.min_sites, "have": facts.num_sites},
        ))
    if product.requires_gstin and not facts.has_active_gstin:
        found.append(Violation(product.id, RuleCode.GSTIN_REQUIRED, f"{product.name} needs a valid, active GSTIN.", {"name": product.name}))
    return found


def dependency_violation(product: Product, bundle_ids: set[str]) -> Violation | None:
    """A product with requires_one_of needs one of those products in the same bundle."""
    if not product.requires_one_of or product.requires_one_of & bundle_ids:
        return None
    catalogue = load_catalogue()
    options = ", ".join(sorted(catalogue[p].name for p in product.requires_one_of))
    return Violation(
        product.id, RuleCode.MISSING_BASE_PRODUCT,
        f"{product.name} only works with one of these in the same bundle: {options}.",
        {"name": product.name, "options": options},
    )


def bundle_violations(bundle_ids: set[str], facts: BusinessFacts) -> list[Violation]:
    catalogue = load_catalogue()
    found = []
    for product_id in sorted(bundle_ids):
        product = catalogue[product_id]
        found.extend(eligibility_violations(product, facts))
        violation = dependency_violation(product, bundle_ids)
        if violation:
            found.append(violation)
    return found
