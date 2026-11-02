import re

import pytest

from app.catalogue import load_catalogue
from app.rules import BusinessFacts, RuleCode, bundle_violations
from conftest import activated_leads

BIG = BusinessFacts(city_tier=1, employee_count=500, num_sites=50, has_active_gstin=True)


def codes(bundle, facts=BIG):
    return {(v.product_id, v.code) for v in bundle_violations(set(bundle), facts)}


def test_catalogue_has_all_25_products():
    assert len(load_catalogue()) == 25


def test_a_big_business_with_a_connection_can_buy_everything():
    assert bundle_violations(set(load_catalogue()), BIG) == []


@pytest.mark.parametrize("product, tier, ok", [("P03", 1, True), ("P03", 2, False), ("P02", 2, True)])
def test_city_tier(product, tier, ok):
    facts = BusinessFacts(tier, 500, 50, True)
    assert ((product, RuleCode.CITY_TIER) not in codes([product], facts)) is ok


@pytest.mark.parametrize("product, minimum", [
    ("P03", 5), ("P05", 10), ("P06", 25), ("P10", 10), ("P12", 3), ("P21", 10), ("P24", 10),
])
def test_min_employees_boundary(product, minimum):
    at_minimum = BusinessFacts(1, minimum, 50, True)
    below = BusinessFacts(1, minimum - 1, 50, True)
    assert (product, RuleCode.MIN_EMPLOYEES) not in codes([product], at_minimum)
    assert (product, RuleCode.MIN_EMPLOYEES) in codes([product], below)


def test_sd_wan_needs_three_sites():
    assert ("P10", RuleCode.MIN_SITES) not in codes(["P10"], BusinessFacts(1, 50, 3, True))
    assert ("P10", RuleCode.MIN_SITES) in codes(["P10"], BusinessFacts(1, 50, 2, True))


@pytest.mark.parametrize("product", ["P03", "P05", "P06", "P10", "P12", "P13", "P14", "P15", "P21", "P24"])
def test_products_that_need_an_active_gstin(product):
    assert (product, RuleCode.GSTIN_REQUIRED) in codes([product], BusinessFacts(1, 500, 50, False))


@pytest.mark.parametrize("product", ["P01", "P02", "P04", "P07", "P08", "P09", "P11", "P16", "P17", "P18", "P19", "P20", "P22", "P23", "P25"])
def test_products_that_do_not_need_gstin(product):
    assert (product, RuleCode.GSTIN_REQUIRED) not in codes([product], BusinessFacts(1, 500, 50, False))


@pytest.mark.parametrize("product, works_with, fails_with", [
    ("P09", ["P01", "P02", "P03", "P05", "P06"], ["P04", "P07"]),  # AirFiber doesn't count
    ("P10", ["P01", "P02", "P03", "P05", "P06"], ["P04"]),
    ("P11", ["P01", "P02", "P03"], ["P04", "P05", "P06"]),
    ("P12", ["P01", "P02", "P03", "P04", "P05", "P06"], ["P07"]),
    ("P21", ["P01", "P02", "P03", "P05", "P06"], ["P04"]),
    ("P22", ["P01", "P02", "P03", "P04"], ["P05", "P06"]),
    ("P23", ["P01", "P02", "P03", "P04", "P05", "P06"], ["P07"]),
])
def test_dependencies(product, works_with, fails_with):
    for base in works_with:
        assert (product, RuleCode.MISSING_BASE_PRODUCT) not in codes([product, base])
    for base in fails_with:
        assert (product, RuleCode.MISSING_BASE_PRODUCT) in codes([product, base])


def test_replaying_sold_bundles_finds_the_same_48_rule_breakers_as_the_analysis():
    breakers = []
    for lead in activated_leads():
        facts = BusinessFacts(
            int(lead["city_tier"]), int(lead["employee_count"]), int(lead["num_sites"]), lead["has_gstin"] == "Y",
        )
        if bundle_violations(set(re.findall(r"(P\d\d)x", lead["bundle_products"])), facts):
            breakers.append(lead["lead_id"])
    assert len(breakers) == 48
