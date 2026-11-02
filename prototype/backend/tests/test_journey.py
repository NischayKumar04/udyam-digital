"""The whole owner journey over HTTP, plus orders and the back-office queue. Uses a fake model."""
import pytest
from fastapi.testclient import TestClient

from app import advisor
from app.backoffice import _model, queue, score_lead, suggested_owner
from app.kyc_routes import CONSENT_NOTICE_VERSION
from app.llm import LlmReply, LlmUnavailable, ToolCall
from app.main import app
from conftest import all_leads

client = TestClient(app)


def fake_model(monkeypatch, *replies):
    remaining = list(replies)

    def chat(messages, tools=None, max_tokens=500, force_tool=False):
        if not remaining:
            raise LlmUnavailable
        return remaining.pop(0)

    monkeypatch.setattr(advisor, "chat", chat)


def start_with_bundle(monkeypatch, arguments, gstin_message="my business"):
    fake_model(monkeypatch, LlmReply("", [ToolCall("record_facts", {"reply": "", **arguments})]), LlmReply("Here's your bundle."))
    session_id = client.post("/api/advisor/sessions", json={"language": "Hindi"}).json()["session_id"]
    body = client.post(f"/api/advisor/sessions/{session_id}/messages", json={"text": gstin_message}).json()
    return session_id, body


CLINIC = {"business_type": "dental clinic", "city": "Nagpur", "employee_count": 12, "num_sites": 1, "has_gstin": True}


def kyc_application(session_id: str, sample: str) -> str:
    application_id = client.post("/api/kyc/applications", json={
        "consent_accepted": True, "notice_version": CONSENT_NOTICE_VERSION, "advisor_session_id": session_id,
    }).json()["application_id"]
    client.post(f"/api/kyc/applications/{application_id}/load-sample", json={"sample_id": sample})
    return application_id


def lines_from(recommendation) -> list[dict]:
    return [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in recommendation["bundle"]]


def test_languages_are_listed():
    assert {"Hindi", "Tamil", "Kannada", "English"} <= set(client.get("/api/advisor/languages").json())


def test_greeting_is_in_the_chosen_language():
    assert "नमस्ते" in client.post("/api/advisor/sessions", json={"language": "Hindi"}).json()["reply"]


def test_empty_and_oversized_messages_are_refused(monkeypatch):
    fake_model(monkeypatch)
    session_id = client.post("/api/advisor/sessions", json={}).json()["session_id"]
    assert client.post(f"/api/advisor/sessions/{session_id}/messages", json={"text": ""}).status_code == 422
    assert client.post(f"/api/advisor/sessions/{session_id}/messages", json={"text": "x" * 1001}).status_code == 422


def test_unknown_session_is_a_404():
    assert client.post("/api/advisor/sessions/nope/messages", json={"text": "hi"}).status_code == 404


def test_erasing_a_conversation_works(monkeypatch):
    fake_model(monkeypatch)
    session_id = client.post("/api/advisor/sessions", json={}).json()["session_id"]
    assert client.delete(f"/api/advisor/sessions/{session_id}").status_code == 204
    assert client.post(f"/api/advisor/sessions/{session_id}/messages", json={"text": "hi"}).status_code == 404


def test_recommendation_reaches_the_browser_without_the_gstin(monkeypatch):
    session_id, body = start_with_bundle(monkeypatch, CLINIC, "dental clinic, GSTIN 27XUIXG0767D1ZP")
    assert body["recommendation"]["has_active_gstin"]
    assert "27XUIXG0767D1ZP" not in str(body)
    assert session_id


def test_toggling_an_add_on_reprices_on_the_server(monkeypatch):
    session_id, body = start_with_bundle(monkeypatch, CLINIC, "clinic, GSTIN 27XUIXG0767D1ZP")
    recommendation = body["recommendation"]
    addon = next(a for a in recommendation["addons"] if a["product_id"] == "P09")
    quote = client.post(f"/api/advisor/sessions/{session_id}/quote", json={
        "lines": lines_from(recommendation) + [{"product_id": "P09", "quantity": addon["quantity"]}],
    }).json()
    assert quote["valid"]
    assert quote["monthly_subtotal"] > recommendation["quote"]["monthly_subtotal"]
    assert quote["one_time_setup"] == recommendation["quote"]["one_time_setup"] + 1500


def test_quote_before_any_recommendation_is_refused(monkeypatch):
    fake_model(monkeypatch)
    session_id = client.post("/api/advisor/sessions", json={}).json()["session_id"]
    response = client.post(f"/api/advisor/sessions/{session_id}/quote", json={"lines": []})
    assert response.status_code == 409


@pytest.mark.slow
def test_full_journey_from_chat_to_live(monkeypatch):
    session_id, body = start_with_bundle(monkeypatch, CLINIC, "clinic, GSTIN 27XUIXG0767D1ZP")
    application_id = kyc_application(session_id, "K03")
    order = client.post("/api/orders", json={
        "advisor_session_id": session_id, "kyc_application_id": application_id, "lines": lines_from(body["recommendation"]),
    })
    assert order.status_code == 201
    view = order.json()
    assert view["current_stage"] == "documents"
    assert view["language"] == "Hindi"
    assert view["next_stage"] == "site_check"
    assert view["live_on"] == "2026-07-20"  # 5-day fibre install from the pack's "today"
    assert view["monthly_total"] == body["recommendation"]["quote"]["monthly_total"]

    seen = [view["current_stage"]]
    while not view["is_live"]:
        view = client.post(f"/api/orders/{view['id']}/advance").json()
        seen.append(view["current_stage"])
    assert seen == ["documents", "site_check", "scheduled", "installed", "live"]
    assert all(stage["state"] == "done" for stage in view["stages"])
    assert client.get(f"/api/orders/{view['id']}").json()["is_live"]


@pytest.mark.slow
@pytest.mark.parametrize("sample, status", [("K11", 409), ("K01", 409)])
def test_orders_are_blocked_until_kyc_problems_are_fixed(monkeypatch, sample, status):
    session_id, body = start_with_bundle(monkeypatch, CLINIC)
    application_id = kyc_application(session_id, sample)
    response = client.post("/api/orders", json={
        "advisor_session_id": session_id, "kyc_application_id": application_id, "lines": lines_from(body["recommendation"]),
    })
    assert response.status_code == status


@pytest.mark.slow
def test_a_review_case_can_order_but_shows_it_is_under_review(monkeypatch):
    session_id, body = start_with_bundle(monkeypatch, CLINIC)
    application_id = kyc_application(session_id, "K07")
    view = client.post("/api/orders", json={
        "advisor_session_id": session_id, "kyc_application_id": application_id, "lines": lines_from(body["recommendation"]),
    }).json()
    assert view["under_review"]
    assert view["current_stage"] == "placed"


def test_a_broken_bundle_cannot_be_ordered(monkeypatch):
    session_id, _ = start_with_bundle(monkeypatch, CLINIC)
    application_id = client.post("/api/kyc/applications", json={
        "consent_accepted": True, "notice_version": CONSENT_NOTICE_VERSION,
        "applicant": {"gstin_on_file": "27XUIXG0767D1ZP", "udyam_on_file": "UDYAM-MH-00-9516696", "install_address_same_as_gst": True},
    }).json()["application_id"]
    # Missing signatory ID, so KYC blocks this first.
    response = client.post("/api/orders", json={
        "advisor_session_id": session_id, "kyc_application_id": application_id, "lines": [{"product_id": "P23", "quantity": 1}],
    })
    assert response.status_code == 409


def test_unknown_order_is_a_404():
    assert client.get("/api/orders/UD-0").status_code == 404
    assert client.post("/api/orders/UD-0/advance").status_code == 404


# --- Back office ----------------------------------------------------------------------


def test_score_is_a_probability_with_reasons_an_agent_can_read():
    lead = next(l for l in all_leads() if l["lead_source"] == "Referral" and l["has_gstin"] == "Y" and l["outcome"] == "Dropped")
    probability, reasons = score_lead(lead)
    assert 0 < probability < 1
    assert "Has GST registration" in reasons
    assert not any("=" in reason for reason in reasons)


def test_referred_gst_holders_outscore_cold_no_gst_leads():
    def average(condition):
        scores = [score_lead(l)[0] for l in all_leads() if condition(l)]
        return sum(scores) / len(scores)

    warm = average(lambda l: l["lead_source"] == "Referral" and l["has_gstin"] == "Y")
    cold = average(lambda l: l["lead_source"] == "WhatsApp campaign" and l["has_gstin"] == "N")
    assert warm > 4 * cold


def test_big_accounts_go_to_field_sales_and_no_gst_shops_to_partners():
    lead = {"segment": "Small manufacturers", "has_gstin": "Y", "preferred_language": "Hindi"}
    assert suggested_owner(lead) == "Field sales"
    lead = {"segment": "Micro retail & services", "has_gstin": "N", "preferred_language": "Hindi"}
    assert suggested_owner(lead) == "Local partner"
    lead = {"segment": "Professional offices", "has_gstin": "Y", "preferred_language": "Tamil"}
    assert suggested_owner(lead) == "Local partner"
    lead = {"segment": "Professional offices", "has_gstin": "Y", "preferred_language": "Hindi"}
    assert suggested_owner(lead) == "Digital follow-up"


def test_queue_is_ranked_masked_and_actionable():
    body = queue(limit=200)
    leads = body["leads"]
    assert body["total"] == 4632 - 319  # all drops except wrong numbers
    assert [row["score"] for row in leads] == sorted((row["score"] for row in leads), reverse=True)
    assert sum(body["by_owner"].values()) == body["total"]
    assert all("*" in row["contact"] for row in leads)
    assert body["model"]["auc"] > 0.7


def test_every_lead_in_the_queue_has_an_action():
    assert all(row["next_action"] != "Review" for row in queue(limit=10_000)["leads"])


def test_leads_we_cant_act_on_today_come_after_everyone_else():
    not_now = {"Not interested on first call", "Locked in with current provider", "Decided to wait"}
    leads = queue(limit=10_000)["leads"]
    waiting = [row["drop_reason"] in not_now for row in leads]
    assert waiting == sorted(waiting) and any(waiting) and not all(waiting)
    first_waiting = waiting.index(True)
    for group in (leads[:first_waiting], leads[first_waiting:]):
        scores = [row["score"] for row in group]
        assert scores == sorted(scores, reverse=True)


def test_the_test_figures_are_an_average_not_one_lucky_split():
    assert _model()["holdout_metrics"]["test_splits"] >= 100


def test_scores_average_out_to_the_real_activation_rate():
    scores = [score_lead(lead)[0] for lead in all_leads()]
    assert sum(scores) / len(scores) == pytest.approx(368 / 5000, abs=0.002)


def test_no_internet_and_no_provider_have_their_own_weights():
    coefficients = _model()["coefficients"]
    assert "current_internet=None" in coefficients
    assert "current_provider=None" in coefficients


def test_queue_filters_by_owner_over_http():
    body = client.get("/api/backoffice/queue", params={"owner": "Field sales", "limit": 10}).json()
    assert len(body["leads"]) == 10
    assert all(row["owner"] == "Field sales" for row in body["leads"])


# --- KYC asks only for what it must ---------------------------------------------------


def states(application_id: str) -> dict:
    return {r["slot"]: r["state"] for r in client.get(f"/api/kyc/applications/{application_id}/requirements").json()}


def new_application(session_id: str) -> str:
    return client.post("/api/kyc/applications", json={
        "consent_accepted": True, "notice_version": CONSENT_NOTICE_VERSION, "advisor_session_id": session_id,
    }).json()["application_id"]


def test_a_verified_gstin_removes_the_gst_upload(monkeypatch):
    session_id, _ = start_with_bundle(monkeypatch, CLINIC, "clinic, GSTIN 27XUIXG0767D1ZP")
    found = states(new_application(session_id))
    assert found["gst"] == "resolved"
    assert found["signatory_id"] == "needed"
    assert found["address_proof"] == "needed"


def test_installing_at_the_gst_address_removes_the_bill_upload(monkeypatch):
    session_id, _ = start_with_bundle(monkeypatch, CLINIC, "clinic, GSTIN 27XUIXG0767D1ZP")
    application_id = new_application(session_id)
    client.post(f"/api/kyc/applications/{application_id}/install-address", json={"same": True})
    assert states(application_id)["address_proof"] == "resolved"


def test_a_shop_without_gst_is_not_asked_for_it(monkeypatch):
    shop = {"business_type": "kirana store", "city": "Nagpur", "employee_count": 2, "num_sites": 1, "has_gstin": False}
    session_id, _ = start_with_bundle(monkeypatch, shop)
    found = states(new_application(session_id))
    assert found["gst"] == "resolved"
    assert found["udyam"] == "optional"


@pytest.mark.slow
def test_cancelled_gstin_on_a_plan_without_gst_products_goes_to_review_not_a_dead_end(monkeypatch):
    agency = {"business_type": "travel agency", "city": "Visakhapatnam", "employee_count": 5, "num_sites": 1, "has_gstin": True}
    session_id, body = start_with_bundle(monkeypatch, agency, "agency, GSTIN 37IHKXV5167L1ZS")
    assert not body["recommendation"]["has_active_gstin"]
    application_id = kyc_application(session_id, "K01")
    view = client.post("/api/orders", json={
        "advisor_session_id": session_id, "kyc_application_id": application_id, "lines": lines_from(body["recommendation"]),
    })
    assert view.status_code == 201
    assert view.json()["under_review"]
