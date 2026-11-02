"""An owner asks for a person and becomes a live lead in the back office. Uses a fake model."""
import json
import math
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import advisor
from app.backoffice import _model, _score, queue
from app.identifiers import mask_mobile, normalize_mobile
from app.journey_routes import CALL_NOTICE_VERSION
from app.kyc_routes import CONSENT_NOTICE_VERSION
from app.llm import LlmReply, LlmUnavailable, ToolCall
from app.main import app
from conftest import all_leads

client = TestClient(app)

MOBILE = "9876543210"
MASKED = "98******10"
CLINIC = {"business_type": "dental clinic", "city": "Nagpur", "employee_count": 12, "num_sites": 1, "has_gstin": True}
KIRANA = {"business_type": "kirana store", "city": "Nagpur", "employee_count": 2, "num_sites": 1, "has_gstin": False}
FACTORY = {"business_type": "textile unit", "city": "Surat", "employee_count": 30, "num_sites": 1, "has_gstin": True}


@pytest.fixture(autouse=True)
def fresh_sessions():
    advisor._sessions.clear()
    yield
    advisor._sessions.clear()


def fake_model(monkeypatch, *replies):
    """Replays replies in order, then acts as if every provider is down. Returns every message it was sent."""
    remaining, seen = list(replies), []

    def chat(messages, tools=None, max_tokens=500, force_tool=False):
        seen.extend(messages)
        if not remaining:
            raise LlmUnavailable
        return remaining.pop(0)

    monkeypatch.setattr(advisor, "chat", chat)
    return seen


def facts(arguments=None):
    return LlmReply("", [ToolCall("record_facts", {"reply": "", **(arguments or {})})])


def new_session(language="English") -> str:
    return client.post("/api/advisor/sessions", json={"language": language}).json()["session_id"]


def say(session_id: str, message: str) -> dict:
    return client.post(f"/api/advisor/sessions/{session_id}/messages", json={"text": message}).json()


def with_plan(monkeypatch, arguments=CLINIC, language="English") -> tuple[str, dict]:
    fake_model(monkeypatch)  # Six languages translate the greeting, which would use up the first reply.
    session_id = new_session(language)
    fake_model(monkeypatch, facts(arguments), LlmReply("Here's your bundle."))
    return session_id, say(session_id, "my business")


def request_call(session_id: str, mobile: str = MOBILE, consent: bool = True, version: str = CALL_NOTICE_VERSION):
    return client.post(f"/api/advisor/sessions/{session_id}/call-request", json={
        "mobile": mobile, "consent_accepted": consent, "notice_version": version,
    })


def live_leads(**kwargs) -> list[dict]:
    return [lead for lead in queue(limit=10_000, **kwargs)["leads"] if lead["live"]]


# --- Asking for a person in the chat ----------------------------------------------------


@pytest.mark.parametrize("message", [
    "I want to talk to a person",
    "can I speak to someone?",
    "Please call me",
    "call me back please",
    "I need a callback",
    "I want a call",
    "talk to a human",
    "speak with an agent",
    "No GST, please call me",
    "मुझे किसी से बात करनी है",
    "मुझे कॉल कीजिए",
    "kisi se baat karni hai",
    "mujhe call karo",
    "யாரிடமாவது பேச வேண்டும்",
    "என்னை அழையுங்கள்",
    "ಯಾರಾದರೂ ಜೊತೆ ಮಾತನಾಡಬೇಕು",
    "ನನಗೆ ಕರೆ ಮಾಡಿ",
    "मला कॉल करा",
    "నాకు కాల్ చేయండి",
    "আমাকে কল করুন",
    "મને કોલ કરો",
    "ਮੈਨੂੰ ਕਾਲ ਕਰੋ",
])
def test_asking_for_a_person_is_noticed(message):
    assert advisor._asks_for_person(message)


@pytest.mark.parametrize("message", [
    "We need voice calling",
    "I want a call centre number",
    "We want call recording",
    "IVR for incoming calls",
    "mobile lines so staff can call customers",
    "missed call service for my shop",
    "customers call us all day",
    "speak to customers on WhatsApp",
    "don't call me",
    "no need to talk to a person",
    "call mat karo",
    "मुझे कॉल मत करो",
    "I run a kirana store in Nagpur with 2 people",
    "ग्राहकों से बात करने के लिए WhatsApp चाहिए",
])
def test_other_talk_of_calls_is_not_taken_as_asking_for_a_person(message):
    assert not advisor._asks_for_person(message)


def test_asking_for_a_person_offers_the_button_and_keeps_the_conversation_going(monkeypatch):
    fake_model(monkeypatch, facts())
    body = say(new_session(), "I want to talk to a person")
    assert body["offer_person"]
    assert "our team will call you" in body["reply"]
    assert body["reply"].endswith("What kind of business do you run?")


def test_the_model_cannot_promise_a_call(monkeypatch):
    fake_model(monkeypatch, facts({"reply": "Sure, our manager will call you at 5 pm today."}))
    body = say(new_session(), "please call me")
    assert "manager" not in body["reply"]
    assert "our team will call you" in body["reply"]


def test_the_system_prompt_is_not_changed_by_this_feature():
    """A sentence about the button here made the smaller models stop short on Tamil, so code handles it instead."""
    assert "button" not in advisor.SYSTEM_PROMPT
    assert "call" not in advisor.SYSTEM_PROMPT.replace("Always call record_facts", "")


def test_the_offer_is_in_the_owners_language(monkeypatch):
    fake_model(monkeypatch, facts())
    body = say(new_session("Hindi"), "मुझे किसी से बात करनी है")
    assert "हमारी टीम आपको कॉल करेगी" in body["reply"]


def test_an_ordinary_message_offers_nothing(monkeypatch):
    fake_model(monkeypatch, facts())
    assert not say(new_session(), "I run a clinic")["offer_person"]


def test_the_plan_is_the_same_whether_or_not_they_ask_for_a_person(monkeypatch):
    fake_model(monkeypatch, facts(CLINIC), LlmReply("Here's your bundle."))
    plain = say(new_session(), "dental clinic in Nagpur, 12 staff, one site, GST")
    fake_model(monkeypatch, facts(CLINIC), LlmReply("Here's your bundle."))
    asked = say(new_session(), "dental clinic in Nagpur, 12 staff, one site, GST. Please call me")
    assert asked["offer_person"] and not plain["offer_person"]
    assert asked["recommendation"]["quote"] == plain["recommendation"]["quote"]
    assert "our team will call you" in asked["reply"]


def test_a_number_typed_in_the_chat_is_stripped_and_offers_the_form(monkeypatch):
    seen = fake_model(monkeypatch, facts())
    session_id = new_session()
    body = say(session_id, f"call me on {MOBILE}")
    assert body["offer_person"]
    assert MOBILE not in str(seen)
    assert MOBILE not in str(advisor._sessions[session_id])
    assert advisor._sessions[session_id].callback is None


def test_in_guided_mode_the_request_does_not_become_the_business_type(monkeypatch):
    fake_model(monkeypatch)
    session_id = new_session()
    say(session_id, "hello")
    assert advisor._sessions[session_id].guided
    body = say(session_id, "I want to talk to a person")
    assert body["offer_person"]
    assert body["mode"] == "guided"
    assert body["expects"] == "business"
    assert "our team will call you" in body["reply"]
    assert not advisor._sessions[session_id].slots.get("business_type")


def test_when_the_ai_is_down_the_first_message_still_offers_the_button(monkeypatch):
    fake_model(monkeypatch)
    body = say(new_session(), "please call me")
    assert body["offer_person"]
    assert body["mode"] == "guided"
    assert body["reply"].startswith("Of course.")


# --- The request itself -----------------------------------------------------------------


@pytest.mark.parametrize("raw", [MOBILE, "98765 43210", "98765-43210", f"+91{MOBILE}", f"+91 {MOBILE}", f"91{MOBILE}", f"0{MOBILE}"])
def test_common_ways_of_writing_a_mobile_number_are_understood(raw):
    assert normalize_mobile(raw) == MOBILE


@pytest.mark.parametrize("raw", ["", "12345", "1234567890", "5876543210", "98765432101", "abcdefghij", "+1 9876543210", "98765"])
def test_things_that_are_not_mobile_numbers_are_refused(raw, monkeypatch):
    assert normalize_mobile(raw) is None
    fake_model(monkeypatch)
    session_id = new_session()
    assert request_call(session_id, raw).status_code == 422
    assert advisor._sessions[session_id].callback is None


def test_masking_shows_only_four_digits():
    assert mask_mobile(MOBILE) == MASKED


def test_a_request_needs_consent(monkeypatch):
    fake_model(monkeypatch)
    session_id = new_session()
    assert request_call(session_id, consent=False).status_code == 403
    assert advisor._sessions[session_id].callback is None
    assert not live_leads()


def test_a_request_needs_the_current_notice(monkeypatch):
    fake_model(monkeypatch)
    session_id = new_session()
    assert request_call(session_id, version="old").status_code == 409
    assert advisor._sessions[session_id].callback is None


def test_the_notice_says_what_consent_covers():
    notice = client.get("/api/advisor/call-notice").json()
    assert notice["version"] == CALL_NOTICE_VERSION
    assert "marketing" in notice["purpose"]
    assert "AI provider" in notice["processing"]
    assert "24 hours" in notice["retention"]
    assert "cancel" in notice["rights"]


def test_consent_is_recorded_with_the_notice_version(monkeypatch):
    fake_model(monkeypatch)
    session_id = new_session()
    request_call(session_id)
    assert advisor._sessions[session_id].callback.notice_version == CALL_NOTICE_VERSION


def test_an_expired_conversation_is_a_404():
    assert request_call("nope").status_code == 404
    assert client.delete("/api/advisor/sessions/nope/call-request").status_code == 404


def test_only_the_masked_number_comes_back(monkeypatch):
    fake_model(monkeypatch)
    response = request_call(new_session())
    assert response.status_code == 201
    assert response.json() == {"mobile": MASKED}


def test_the_number_never_reaches_a_model(monkeypatch):
    seen = fake_model(monkeypatch, facts(CLINIC), LlmReply("Here's your bundle."), facts(CLINIC))
    session_id = new_session()
    request_call(session_id)
    say(session_id, "I run a dental clinic")
    say(session_id, "and what about email?")
    assert seen
    assert MOBILE not in json.dumps(seen, ensure_ascii=False)
    assert all(MOBILE not in message["content"] for message in advisor._sessions[session_id].history)


# --- The back office --------------------------------------------------------------------


def test_a_request_becomes_the_first_lead_in_the_queue(monkeypatch):
    session_id, body = with_plan(monkeypatch)
    request_call(session_id)
    result = queue(limit=5)
    lead = result["leads"][0]
    assert lead["live"] and result["live"] == 1
    assert lead["contact"] == MASKED
    assert lead["business"] == "Dental clinic"
    assert lead["city"] == "Nagpur"
    assert lead["segment"] == "prof"
    assert lead["source"] == "Advisor"
    assert lead["stage"] == "Plan"
    assert lead["drop_reason"] == "Wants to talk before buying"
    assert lead["reasons"][0] == "Asked for a call"
    assert 0 < lead["score"] < 100
    assert lead["owner"] == "Digital follow-up"
    assert f"₹{body['recommendation']['quote']['monthly_subtotal']:,}" in lead["next_action"]


def test_the_queue_never_shows_the_full_number_or_the_session_id(monkeypatch):
    session_id, _ = with_plan(monkeypatch)
    request_call(session_id)
    text = client.get("/api/backoffice/queue", params={"limit": 200}).text
    assert MASKED in text
    assert MOBILE not in text
    assert session_id not in text


def test_newest_requests_come_first_and_counts_include_them(monkeypatch):
    older, _ = with_plan(monkeypatch)
    newer, _ = with_plan(monkeypatch, FACTORY)
    request_call(older)
    request_call(newer, "9123456780")
    advisor._sessions[older].callback.requested_at -= timedelta(minutes=5)
    result = queue(limit=5)
    assert [lead["contact"] for lead in result["leads"][:2]] == ["91******80", MASKED]
    assert result["total"] == 4313 + 2
    assert sum(result["by_owner"].values()) == result["total"]


def test_the_owner_rule_is_the_same_as_for_other_leads(monkeypatch):
    session_id, _ = with_plan(monkeypatch, FACTORY)
    request_call(session_id)
    assert live_leads()[0]["owner"] == "Field sales"
    assert len(live_leads(owner="Field sales")) == 1
    assert not live_leads(owner="Local partner")
    advisor._sessions.clear()
    session_id, _ = with_plan(monkeypatch, KIRANA)
    request_call(session_id)
    assert live_leads()[0]["owner"] == "Local partner"


def test_a_request_before_any_plan_is_still_a_lead(monkeypatch):
    fake_model(monkeypatch)
    session_id = new_session()
    request_call(session_id)
    lead = live_leads()[0]
    assert lead["score"] is None
    assert lead["segment"] is None
    assert lead["business"] == "Not known yet"
    assert lead["stage"] == "Chat"
    assert lead["drop_reason"] == "Asked before getting a plan"
    assert lead["reasons"] == ["Asked for a call"]
    assert lead["owner"] == "Digital follow-up"


def test_a_partly_finished_chat_uses_what_the_owner_said(monkeypatch):
    fake_model(monkeypatch, facts({"business_type": "textile unit", "has_gstin": False}))
    session_id = new_session()
    say(session_id, "textile unit, no GST")
    request_call(session_id)
    lead = live_leads()[0]
    assert lead["business"] == "Textile unit"
    assert lead["owner"] == "Field sales"
    assert lead["score"] is None


def test_what_the_owner_typed_is_kept_short(monkeypatch):
    fake_model(monkeypatch)
    session_id = new_session()
    say(session_id, "hello")
    advisor._sessions[session_id].slots["business_type"] = "x" * 900
    request_call(session_id)
    assert len(live_leads()[0]["business"]) == 60


@pytest.mark.parametrize("arguments, reason, action", [
    ({**CLINIC, "budget_monthly": 100}, "Plan is over their budget", "entry bundle"),
    ({**KIRANA, "needs": ["whatsapp"]}, "Couldn't get", "Explain why"),
])
def test_the_reason_follows_what_went_wrong_in_the_plan(monkeypatch, arguments, reason, action):
    session_id, _ = with_plan(monkeypatch, arguments)
    request_call(session_id)
    lead = live_leads()[0]
    assert reason in lead["drop_reason"]
    assert action in lead["next_action"]


def test_the_reason_follows_how_far_they_got(monkeypatch):
    session_id, body = with_plan(monkeypatch)
    request_call(session_id)
    lines = [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in body["recommendation"]["bundle"]]
    client.post(f"/api/advisor/sessions/{session_id}/quote", json={"lines": lines})
    lead = live_leads()[0]
    assert lead["stage"] == "Price"
    assert lead["drop_reason"] == "Stopped at the price"

    application_id = client.post("/api/kyc/applications", json={
        "consent_accepted": True, "notice_version": CONSENT_NOTICE_VERSION, "advisor_session_id": session_id,
    }).json()["application_id"]
    lead = live_leads()[0]
    assert lead["stage"] == "Documents"
    assert lead["drop_reason"] == "Stopped at documents"

    verdict = client.post(f"/api/kyc/applications/{application_id}/submit").json()["verdict"]
    assert verdict == "REUPLOAD"
    assert live_leads()[0]["drop_reason"] == "Documents need fixing"

    assert client.delete(f"/api/kyc/applications/{application_id}").status_code == 204
    assert live_leads()[0]["drop_reason"] == "Stopped at documents"


@pytest.mark.parametrize("verdict, reason", [
    ("REJECT", "Registration can't be used"),
    ("MANUAL_REVIEW", "Documents need a review"),
    ("PASS", "Documents passed, no order yet"),
    ("AUTO_RESOLVE", "Documents passed, no order yet"),
])
def test_every_kyc_result_gets_a_reason(monkeypatch, verdict, reason):
    session_id, _ = with_plan(monkeypatch)
    request_call(session_id)
    client.post("/api/kyc/applications", json={
        "consent_accepted": True, "notice_version": CONSENT_NOTICE_VERSION, "advisor_session_id": session_id,
    })
    monkeypatch.setattr("app.backoffice.last_checked_verdict", lambda application_id: verdict)
    assert live_leads()[0]["drop_reason"] == reason


# --- When a lead goes away --------------------------------------------------------------


def test_cancelling_removes_the_lead_and_the_number(monkeypatch):
    session_id, _ = with_plan(monkeypatch)
    request_call(session_id)
    assert client.delete(f"/api/advisor/sessions/{session_id}/call-request").status_code == 204
    assert not live_leads()
    assert advisor._sessions[session_id].callback is None


def test_erasing_the_conversation_removes_the_lead(monkeypatch):
    session_id, _ = with_plan(monkeypatch)
    request_call(session_id)
    assert client.delete(f"/api/advisor/sessions/{session_id}").status_code == 204
    assert not live_leads()


def test_placing_an_order_removes_the_lead_and_the_number(monkeypatch):
    session_id, body = with_plan(monkeypatch)
    request_call(session_id)
    application_id = client.post("/api/kyc/applications", json={
        "consent_accepted": True, "notice_version": CONSENT_NOTICE_VERSION, "advisor_session_id": session_id,
    }).json()["application_id"]
    monkeypatch.setattr("app.journey_routes.application_verdict", lambda application_id: "PASS")
    order = client.post("/api/orders", json={
        "advisor_session_id": session_id, "kyc_application_id": application_id,
        "lines": [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in body["recommendation"]["bundle"]],
    })
    assert order.status_code == 201
    assert not live_leads()
    assert advisor._sessions[session_id].callback is None
    assert queue()["no_contact"] == 0


def test_a_blocked_order_keeps_the_lead(monkeypatch):
    session_id, body = with_plan(monkeypatch)
    request_call(session_id)
    application_id = client.post("/api/kyc/applications", json={
        "consent_accepted": True, "notice_version": CONSENT_NOTICE_VERSION, "advisor_session_id": session_id,
    }).json()["application_id"]
    order = client.post("/api/orders", json={
        "advisor_session_id": session_id, "kyc_application_id": application_id,
        "lines": [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in body["recommendation"]["bundle"]],
    })
    assert order.status_code == 409
    assert len(live_leads()) == 1


def test_requests_expire_with_the_conversation(monkeypatch):
    session_id, _ = with_plan(monkeypatch)
    request_call(session_id)
    advisor._sessions[session_id].created_at -= advisor.SESSION_TTL + timedelta(minutes=1)
    assert not live_leads()
    assert session_id not in advisor._sessions


def test_asking_again_replaces_the_number_and_keeps_one_lead(monkeypatch):
    session_id, _ = with_plan(monkeypatch)
    request_call(session_id)
    request_call(session_id, "9123456780")
    leads = live_leads()
    assert len(leads) == 1
    assert leads[0]["contact"] == "91******80"


def test_chats_that_left_no_number_are_only_counted(monkeypatch):
    with_plan(monkeypatch)
    asked, _ = with_plan(monkeypatch)
    request_call(asked)
    fake_model(monkeypatch)
    new_session()
    result = queue(limit=10)
    assert result["no_contact"] == 1
    assert result["live"] == 1
    assert len([lead for lead in result["leads"] if lead["live"]]) == 1


# --- The chat model ---------------------------------------------------------------------


def test_the_chat_model_uses_only_what_the_chat_collects():
    allowed = ("city_tier", "log_employees", "num_sites", "interest_count", "segment=", "preferred_language=", "has_gstin=")
    assert all(name.startswith(allowed) for name in _model()["chat_model"]["coefficients"])


def test_the_chat_model_has_been_tested_properly():
    metrics = queue()["chat_model"]
    assert metrics["test_splits"] >= 100
    assert metrics["auc"] > 0.65


def test_the_chat_model_averages_out_to_the_real_activation_rate():
    def probability(lead):
        return _score(_model()["chat_model"], {
            "city_tier": float(lead["city_tier"]),
            "log_employees": math.log1p(float(lead["employee_count"])),
            "num_sites": float(lead["num_sites"]),
            "interest_count": float(lead["products_of_interest"].count(";") + 1),
            f"segment={lead['segment']}": 1.0,
            f"preferred_language={lead['preferred_language']}": 1.0,
            f"has_gstin={lead['has_gstin']}": 1.0,
        })[0]

    scores = [probability(lead) for lead in all_leads()]
    assert sum(scores) / len(scores) == pytest.approx(368 / 5000, abs=0.002)


@pytest.mark.parametrize("language", ["English", "Hindi", "Marathi", "Tamil", "Telugu", "Kannada", "Malayalam", "Bengali", "Gujarati", "Punjabi"])
def test_every_language_can_be_scored(monkeypatch, language):
    session_id, _ = with_plan(monkeypatch, language=language)
    request_call(session_id)
    assert f"preferred_language={language}" in _model()["chat_model"]["coefficients"]
    assert live_leads()[0]["score"] is not None
