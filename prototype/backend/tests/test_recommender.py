"""Scenario tests for the advisor's decisions, plus a replay of all 5,000 leads."""
import pytest

from app.catalogue import load_catalogue
from app.profile import BusinessProfile, classify_segment, lookup_city
from app.recommender import Need, RecommendRequest, recommend
from app.rules import BusinessFacts, bundle_violations
from conftest import all_leads

CATALOGUE = load_catalogue()


def ask(needs=(), requested=(), budget=None, quantities=None, contract=None, spend=None, **profile):
    profile.setdefault("employee_count", 3)
    return recommend(RecommendRequest(
        profile=BusinessProfile(**profile),
        needs=list(needs),
        requested_products=list(requested),
        budget_monthly=budget,
        quantities=quantities or {},
        contract_months=contract,
        current_monthly_spend=spend,
    ))


def bundle_ids(rec):
    return {item.product_id for item in rec.bundle}


def addon_ids(rec):
    return {item.product_id for item in rec.addons}


def unavailable(rec, product_id):
    return next((u for u in rec.unavailable if u.product_id == product_id), None)


# --- Segment and location -------------------------------------------------------------


@pytest.mark.parametrize("business_type, sites, segment", [
    ("Kirana store", 1, "micro"),
    ("Dental clinic", 1, "prof"),
    ("Dental clinic", 3, "multi"),
    ("Restaurant chain", 5, "multi"),
    ("Textile unit", 1, "mfg"),
    ("Textile unit", 4, "mfg"),
    ("Chartered accountant office", 1, "prof"),
    ("Doctor's clinic", 1, "prof"),
    ("Garment factory", 1, "mfg"),
    ("Paan shop", 1, "micro"),
    ("Coffee chain", 1, "multi"),
])
def test_business_types_map_to_segments(business_type, sites, segment):
    assert classify_segment(business_type, sites) == segment


@pytest.mark.parametrize("city, tier", [("Mumbai", 1), ("bangalore", 1), ("Vizag", 2), ("Kochi", 2)])
def test_city_names_and_aliases_resolve_to_tiers(city, tier):
    assert lookup_city(city)[1] == tier


# --- Micro retail ---------------------------------------------------------------------


def test_kirana_gets_the_entry_bundle_with_toggles():
    rec = ask(business_type="Kirana store", city="Nagpur", employee_count=2)
    assert rec.segment == "micro"
    assert bundle_ids(rec) == {"P01", "P07"}
    assert rec.quote.monthly_subtotal == 1423
    assert {"P19", "P22", "P23", "P18"} <= addon_ids(rec)


def test_no_gstin_means_no_whatsapp_api_but_an_honest_alternative():
    rec = ask([Need.WHATSAPP], business_type="Kirana store", city="Patna", employee_count=2)
    assert "P15" not in bundle_ids(rec)
    blocked = unavailable(rec, "P15")
    assert blocked.asked
    assert "GSTIN" in blocked.reason
    assert blocked.alternative_id == "P18"
    assert "P18" in addon_ids(rec)


def test_gstin_holder_gets_whatsapp():
    rec = ask([Need.WHATSAPP], business_type="Pharmacy", city="Pune", gstin="27PZSXS1936O1ZH")
    assert "P15" in bundle_ids(rec)


def test_cancelled_gstin_counts_as_no_gstin():
    rec = ask([Need.WHATSAPP], business_type="Travel agency", city="Visakhapatnam", gstin="37IHKXV5167L1ZS", employee_count=5)
    assert not rec.has_active_gstin
    assert rec.gstin_status == "Cancelled"
    assert "P15" not in bundle_ids(rec)
    assert any("Cancelled" in note for note in rec.notes)


def test_altered_gstin_is_rejected_even_if_the_owner_says_they_have_gst():
    rec = ask([Need.WHATSAPP], gstin="08YKZXS8189L1ZO", has_active_gstin=True, city="Jaipur", business_type="Salon")
    assert rec.gstin_status == "Invalid"
    assert "P15" not in bundle_ids(rec)


def test_no_fibre_means_airfiber_and_quick_install():
    rec = ask(business_type="Salon", city="Lucknow", fibre_feasible=False)
    assert "P04" in bundle_ids(rec)
    assert not bundle_ids(rec) & {"P01", "P02", "P03"}
    assert rec.quote.contract_months == 6
    assert rec.quote.expected_activation_days == 2


def test_airfiber_cannot_have_failover_but_can_have_wifi_and_cctv():
    rec = ask([Need.FAILOVER, Need.GUEST_WIFI, Need.CCTV], business_type="Salon", city="Lucknow", fibre_feasible=False)
    assert {"P04", "P22", "P23"} <= bundle_ids(rec)
    assert "P09" not in bundle_ids(rec)
    assert unavailable(rec, "P09").asked


def test_only_wants_a_mobile_plan_is_not_forced_into_a_bundle():
    rec = ask([Need.MOBILE_ONLY], business_type="Hardware store", city="Surat", quantities={"P07": 2})
    assert bundle_ids(rec) == {"P07"}
    assert rec.quote.contract_months == 1
    assert rec.quote.lines[0].quantity == 2
    assert rec.quote.expected_activation_days == 1


# --- Budget ---------------------------------------------------------------------------


def test_budget_keeps_the_bundle_under_the_limit():
    rec = ask([Need.BILLING_POS, Need.CCTV], business_type="Bakery", city="Indore", budget=2200)
    assert rec.within_budget
    assert rec.quote.monthly_subtotal <= 2200


def test_impossible_budget_gets_the_cheapest_real_plan_and_says_so():
    rec = ask(business_type="Boutique", city="Bhopal", budget=500)
    assert rec.within_budget is False
    assert len(rec.quote.lines) == 1
    assert any("lowest workable plan" in note for note in rec.notes)


def test_budget_drops_unasked_items_before_asked_ones():
    rec = ask([Need.CCTV], business_type="CA firm", city="Mumbai", employee_count=12, budget=3500)
    assert "P23" in bundle_ids(rec)
    assert rec.within_budget


def test_things_dropped_for_budget_stay_available_as_toggles():
    rec = ask(business_type="Law office", city="Delhi", employee_count=15, budget=2500)
    assert rec.within_budget
    assert {"P16", "P17", "P20"} & addon_ids(rec)
    assert any("left out" in note for note in rec.notes)


# --- Professional offices -------------------------------------------------------------


def test_clinic_gets_the_office_bundle():
    rec = ask(business_type="Dental clinic", city="Kochi", employee_count=14, gstin="32TTNXB7384T1ZW")
    assert rec.segment == "prof"
    assert bundle_ids(rec) == {"P02", "P08", "P16", "P17", "P20"}
    assert 4000 <= rec.quote.monthly_subtotal <= 8000


def test_tier_2_clinic_cannot_get_1g_and_is_told_what_it_gets_instead():
    rec = ask([Need.HIGH_SPEED], business_type="Diagnostic lab", city="Kochi", employee_count=14, gstin="32TTNXB7384T1ZW")
    blocked = unavailable(rec, "P03")
    assert blocked.asked
    assert "isn't sold in your city" in blocked.reason
    assert blocked.alternative_id == "P02"
    assert "P02" in bundle_ids(rec)


def test_tier_1_clinic_with_gstin_can_get_1g():
    rec = ask([Need.HIGH_SPEED], business_type="Diagnostic lab", city="Pune", employee_count=14, gstin="27PZSXS1936O1ZH")
    assert "P03" in bundle_ids(rec)


def test_small_office_asking_for_a_leased_line_gets_an_explanation_and_a_real_option():
    rec = ask(requested=["P05"], business_type="Architecture studio", city="Bengaluru", employee_count=5, has_active_gstin=True)
    blocked = unavailable(rec, "P05")
    assert "at least 10 employees" in blocked.reason
    assert blocked.alternative_id == "P03"
    assert "P03" in bundle_ids(rec)
    assert "P05" not in bundle_ids(rec)


def test_static_ip_comes_with_fibre_not_leased_line():
    rec = ask([Need.STATIC_IP], business_type="CA firm", city="Mumbai", employee_count=12)
    assert {"P02", "P11"} <= bundle_ids(rec)


def test_static_ip_is_blocked_on_a_leased_line():
    rec = ask([Need.STATIC_IP], business_type="Textile unit", city="Surat", employee_count=60, gstin="24XORXG9365M1Z3")
    assert "P05" in bundle_ids(rec)
    assert "P11" not in bundle_ids(rec)
    assert unavailable(rec, "P11").asked


def test_cloud_telephony_needs_three_staff():
    rec = ask([Need.PHONE_SYSTEM], business_type="Travel agency", city="Delhi", employee_count=2, has_active_gstin=True)
    assert "P12" not in bundle_ids(rec)
    assert "at least 3 employees" in unavailable(rec, "P12").reason


# --- Multi-site -----------------------------------------------------------------------


def test_restaurant_chain_gets_every_site_covered_on_one_bill():
    rec = ask(business_type="Restaurant chain", city="Mumbai", employee_count=60, num_sites=8, has_active_gstin=True)
    assert rec.segment == "multi"
    quantities = {line.product_id: line.quantity for line in rec.quote.lines}
    assert quantities["P09"] == 8
    assert quantities["P23"] == 16
    connection_sites = sum(q for p, q in quantities.items() if p in {"P01", "P02"})
    assert connection_sites == 8
    assert "P10" in addon_ids(rec)


def test_sd_wan_is_refused_below_three_sites():
    rec = ask([Need.CENTRAL_MANAGEMENT], business_type="Dental clinic", city="Pune", employee_count=20, num_sites=2, has_active_gstin=True)
    blocked = unavailable(rec, "P10")
    assert "at least 3 sites" in blocked.reason
    assert blocked.alternative_id == "P09"


def test_asking_for_sd_wan_moves_the_contract_to_24_months():
    rec = ask([Need.CENTRAL_MANAGEMENT], business_type="Pharmacy chain", city="Delhi", employee_count=40, num_sites=5, has_active_gstin=True)
    assert "P10" in bundle_ids(rec)
    assert rec.quote.contract_months == 24


# --- Manufacturers --------------------------------------------------------------------


def test_factory_gets_a_leased_line_and_machine_monitoring_when_asked():
    rec = ask([Need.MACHINE_MONITORING], business_type="Auto-parts unit", city="Pune", employee_count=85, gstin="27XUIXG0767D1ZP")
    assert rec.segment == "mfg"
    assert {"P05", "P08", "P16", "P24"} <= bundle_ids(rec)
    assert rec.quote.contract_months == 24
    assert rec.quote.expected_activation_days == 21


def test_factory_without_gstin_falls_back_to_fibre_and_loses_machine_monitoring():
    rec = ask([Need.MACHINE_MONITORING], business_type="Furniture workshop", city="Nagpur", employee_count=30)
    assert "P02" in bundle_ids(rec)
    assert "P05" not in bundle_ids(rec)
    assert "GSTIN" in unavailable(rec, "P24").reason


def test_two_site_factory_gets_a_leased_line_at_the_main_site_and_fibre_at_the_other():
    rec = ask(business_type="Packaging unit", city="Pune", employee_count=90, num_sites=2, has_active_gstin=True)
    quantities = {line.product_id: line.quantity for line in rec.quote.lines}
    assert quantities["P05"] == 1
    assert quantities["P02"] == 1


# --- Honesty --------------------------------------------------------------------------


def test_products_not_in_the_catalogue_are_ignored_and_reported():
    rec = ask(requested=["P99"], business_type="Salon", city="Delhi")
    assert all(item.product_id in CATALOGUE for item in rec.bundle)
    assert any("P99" in note for note in rec.notes)


def test_unknown_city_gets_an_indicative_bundle_and_a_clear_flag():
    rec = ask(business_type="Kirana store", city="Rohtak")
    assert rec.coverage_confirmed is False
    assert rec.city_tier == 2
    assert any("confirmed coverage" in note for note in rec.notes)


def test_comparison_with_what_they_pay_today():
    rec = ask(business_type="Kirana store", city="Nagpur", spend=900)
    assert rec.monthly_difference_vs_current == rec.quote.monthly_subtotal - 900


def test_owner_facing_reasons_never_show_product_codes():
    rec = ask(business_type="Dental clinic", city="Kochi", employee_count=14)
    for item in rec.bundle + rec.addons:
        assert "P0" not in item.reason and "P1" not in item.reason and "P2" not in item.reason


# --- Replay of the whole quarter ------------------------------------------------------


def test_replaying_all_5000_leads_never_breaks_a_rule_or_a_price_range():
    assert len(all_leads()) == 5000
    for lead in all_leads():
        rec = recommend(RecommendRequest(
            profile=BusinessProfile(
                business_type=lead["business_type"],
                city=lead["city"],
                employee_count=int(lead["employee_count"]),
                num_sites=int(lead["num_sites"]),
                gstin=lead["gstin"] or None,
            ),
            requested_products=[p for p in lead["products_of_interest"].split(";") if p],
        ))
        facts = BusinessFacts(rec.city_tier, int(lead["employee_count"]), int(lead["num_sites"]), rec.has_active_gstin)
        ids = {line.product_id for line in rec.quote.lines}
        assert ids, lead["lead_id"]
        assert bundle_violations(ids, facts) == [], lead["lead_id"]
        assert rec.quote.valid, lead["lead_id"]
        for line in rec.quote.lines:
            product = CATALOGUE[line.product_id]
            assert product.price_min <= line.unit_price <= product.price_max, lead["lead_id"]
            assert line.quantity >= 1
        # Every toggle offered must keep the bundle valid if switched on.
        for addon in rec.addons:
            assert bundle_violations(ids | {addon.product_id}, facts) == [], (lead["lead_id"], addon.product_id)


def test_replaying_all_leads_with_tight_budgets_still_never_breaks_a_rule():
    for lead in all_leads()[:1500]:
        rec = recommend(RecommendRequest(
            profile=BusinessProfile(
                business_type=lead["business_type"],
                city=lead["city"],
                employee_count=int(lead["employee_count"]),
                num_sites=int(lead["num_sites"]),
                gstin=lead["gstin"] or None,
            ),
            requested_products=[p for p in lead["products_of_interest"].split(";") if p],
            budget_monthly=max(1, int(lead["monthly_telecom_spend_inr"])),
        ))
        assert rec.quote.valid, lead["lead_id"]
        if rec.within_budget:
            assert rec.quote.monthly_subtotal <= int(lead["monthly_telecom_spend_inr"]), lead["lead_id"]


# --- In the owner's language ----------------------------------------------------------


@pytest.mark.parametrize("language, word", [("Hindi", "इंटरनेट"), ("Tamil", "இணைய"), ("Kannada", "ಇಂಟರ್ನೆಟ್")])
def test_reasons_and_refusals_come_in_the_owners_language(language, word):
    rec = recommend(RecommendRequest(
        profile=BusinessProfile(business_type="Kirana store", city="Nagpur", employee_count=2),
        needs=[Need.WHATSAPP],
        language=language,
    ))
    assert word in next(item for item in rec.bundle if item.product_id == "P01").reason
    assert "GSTIN" in unavailable(rec, "P15").reason
    assert "needs a valid" not in unavailable(rec, "P15").reason


@pytest.mark.parametrize("language", ["Hindi", "Tamil", "Kannada"])
def test_every_product_reason_is_translated(language):
    from app.product_text import REASONS
    assert set(REASONS[language]) == set(CATALOGUE)
    assert all(REASONS[language][p] != REASONS["English"][p] for p in CATALOGUE)


def test_other_languages_fall_back_to_english_wording():
    rec = recommend(RecommendRequest(profile=BusinessProfile(business_type="Kirana store", city="Nagpur", employee_count=2), language="Marathi"))
    assert "Fast, unlimited internet" in next(item for item in rec.bundle if item.product_id == "P01").reason


@pytest.mark.parametrize("language", ["English", "Hindi", "Tamil", "Kannada"])
def test_budget_and_coverage_notes_work_in_each_language(language):
    rec = recommend(RecommendRequest(
        profile=BusinessProfile(business_type="Law office", city="Rohtak", employee_count=15, gstin="08YKZXS8189L1ZO"),
        budget_monthly=500,
        language=language,
    ))
    assert len(rec.notes) >= 3  # bad GSTIN, unconfirmed city, over budget
