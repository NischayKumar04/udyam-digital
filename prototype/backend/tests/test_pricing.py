import re

import pytest

from app.catalogue import load_catalogue
from app.pricing import LineItem, build_quote, price_position, unit_price
from app.rules import BusinessFacts
from conftest import activated_leads

FACTS = BusinessFacts(city_tier=1, employee_count=500, num_sites=50, has_active_gstin=True)
CATALOGUE = load_catalogue()


def lines(*items):
    return [LineItem(product_id=p, quantity=q) for p, q in items]


@pytest.mark.parametrize("contract", [1, 6, 12, 24])
@pytest.mark.parametrize("has_connection", [True, False])
@pytest.mark.parametrize("segment", ["micro", "prof", "multi", "mfg", None])
def test_every_product_price_stays_inside_its_catalogue_range(contract, has_connection, segment):
    for product in CATALOGUE.values():
        price = unit_price(product, price_position(product, contract, has_connection, segment))
        assert product.price_min <= price <= product.price_max


def test_micro_entry_bundle_price():
    quote = build_quote(lines(("P01", 1), ("P07", 1)), FACTS, "micro")
    assert quote.contract_months == 12
    assert [line.unit_price for line in quote.lines] == [1099, 324]
    assert quote.monthly_subtotal == 1423
    assert quote.list_monthly_subtotal == 1598
    assert quote.monthly_saving == 175


def test_gst_and_setup_are_shown_separately():
    quote = build_quote(lines(("P01", 1), ("P19", 2)), FACTS, "micro")
    assert quote.one_time_setup == 5000
    assert quote.one_time_gst == 900
    assert quote.one_time_total == 5900
    assert quote.monthly_gst == round(quote.monthly_subtotal * 0.18)
    assert quote.monthly_total == quote.monthly_subtotal + quote.monthly_gst
    assert quote.pay_now == quote.one_time_total + quote.monthly_total


def test_switching_on_an_add_on_adds_exactly_its_own_price():
    base = build_quote(lines(("P05", 1), ("P08", 3)), FACTS, "mfg")
    with_addon = build_quote(lines(("P05", 1), ("P08", 3), ("P20", 4)), FACTS, "mfg")
    added = next(line for line in with_addon.lines if line.product_id == "P20")
    assert with_addon.monthly_subtotal - base.monthly_subtotal == added.monthly


def test_longer_contract_lowers_the_price():
    quote = build_quote(lines(("P02", 1), ("P08", 2), ("P16", 10)), FACTS, "prof")
    by_months = {option.months: option.monthly_subtotal for option in quote.contract_options}
    assert sorted(by_months) == [12, 24]
    assert by_months[24] < by_months[12]
    assert quote.monthly_subtotal == by_months[12]


def test_contract_cannot_go_below_what_the_products_require():
    quote = build_quote(lines(("P02", 1), ("P21", 1)), FACTS, "prof", contract_months=12)
    assert quote.contract_months == 24
    assert [option.months for option in quote.contract_options] == [24]


def test_mobile_only_is_month_to_month():
    quote = build_quote(lines(("P07", 2)), FACTS, "micro")
    assert quote.contract_months == 1
    assert [option.months for option in quote.contract_options] == [1, 12, 24]


def test_duplicate_lines_are_merged():
    quote = build_quote(lines(("P23", 1), ("P23", 2), ("P01", 1)), FACTS, "micro")
    assert next(line for line in quote.lines if line.product_id == "P23").quantity == 3


def test_unknown_products_are_rejected():
    with pytest.raises(ValueError, match="P99"):
        build_quote(lines(("P99", 1)), FACTS)


def test_broken_bundles_are_flagged_invalid():
    facts = BusinessFacts(city_tier=2, employee_count=3, num_sites=1, has_active_gstin=False)
    quote = build_quote(lines(("P03", 1), ("P11", 1)), facts)
    assert not quote.valid
    assert {v.code for v in quote.violations} >= {"CITY_TIER", "MIN_EMPLOYEES", "GSTIN_REQUIRED"}


def test_contract_and_setup_rules_match_every_bundle_sold_last_quarter():
    for lead in activated_leads():
        items = [(p, int(q)) for p, q in re.findall(r"(P\d\d)x(\d+)", lead["bundle_products"])]
        quote = build_quote(lines(*items), FACTS, None)
        assert quote.contract_months == int(float(lead["contract_months"]))
        assert quote.one_time_setup == int(float(lead["one_time_setup_inr"]))
