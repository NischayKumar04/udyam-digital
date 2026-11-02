"""The advisor's safeguards, tested with a fake model so no quota is used."""
import pytest

from app import advisor
from app.advisor import explain_without_ai, is_grounded, redact, send_message, start_session
from app.llm import LlmReply, LlmUnavailable, ToolCall
from app.profile import BusinessProfile
from app.recommender import RecommendRequest, recommend

KIRANA_CALL = ToolCall("record_facts", {
    "reply": "", "business_type": "kirana store", "city": "Nagpur", "employee_count": 2, "num_sites": 1,
    "has_gstin": False, "needs": ["cctv", "billing_machine"],
})


class FakeModel:
    """Replays scripted replies and records exactly what was sent to the provider."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def __call__(self, messages, tools=None, max_tokens=500, force_tool=False):
        self.sent.append(messages)
        if not self.replies:
            raise LlmUnavailable
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def all_text(self) -> str:
        return " ".join(m["content"] for batch in self.sent for m in batch)


@pytest.fixture
def model(monkeypatch):
    def install(*replies):
        fake = FakeModel(*replies)
        monkeypatch.setattr(advisor, "chat", fake)
        return fake
    return install


# --- Privacy --------------------------------------------------------------------------


def session():
    return advisor._Session("English", None)


@pytest.mark.parametrize("message, token", [
    ("My GSTIN is 27XUIXG0767D1ZP", "[GSTIN]"),
    ("gst 27xuixg0767d1zp ok", "[GSTIN]"),
    ("Udyam UDYAM-MH-00-9516696", "[UDYAM]"),
    ("aadhaar 1234 5678 9012", "[ID NUMBER]"),
    ("PAN ABCDE1234F", "[PAN]"),
    ("call me on 9876543210", "[PHONE]"),
    ("or +91 98765 43210".replace(" 98765 ", " 98765"), "[PHONE]"),
    ("mail owner@shop.in", "[EMAIL]"),
])
def test_identifiers_are_stripped_before_a_model_can_see_them(message, token):
    assert token in redact(message, session())


def test_gstin_and_udyam_are_kept_for_our_own_lookups():
    s = session()
    redact("27xuixg0767d1zp and UDYAM-MH-00-9516696", s)
    assert s.gstin == "27XUIXG0767D1ZP"
    assert s.udyam == "UDYAM-MH-00-9516696"


def test_ordinary_numbers_survive_redaction():
    assert redact("We have 12 staff and spend 3050 a month", session()) == "We have 12 staff and spend 3050 a month"


def test_no_identifier_reaches_the_provider_and_the_gstin_is_still_checked(model):
    fake = model(
        LlmReply("", [ToolCall("record_facts", {"reply": "How many staff, and how many offices?", "business_type": "travel agency", "city": "Visakhapatnam", "has_gstin": True})]),
        LlmReply("", [ToolCall("record_facts", {"reply": "", "employee_count": 5, "num_sites": 1, "needs": ["whatsapp"]})]),
        LlmReply("Your GST registration is cancelled, so WhatsApp isn't available."),
    )
    session_id = start_session("English").session_id
    first = send_message(session_id, "I run a travel agency in Vizag, GSTIN 37IHKXV5167L1ZS, phone 9876543210")
    assert first.recommendation is None
    result = send_message(session_id, "5 staff, one office, I want WhatsApp")
    assert "37IHKXV5167L1ZS" not in fake.all_text
    assert "9876543210" not in fake.all_text
    # The owner has a GSTIN, but our lookup found it cancelled.
    assert result.recommendation.gstin_status == "Cancelled"
    assert "P15" not in {item.product_id for item in result.recommendation.bundle}


def test_proprietor_name_from_the_registry_never_goes_to_the_model(model):
    fake = model(
        LlmReply("", [ToolCall("record_facts", {"reply": "", "business_type": "travel agency", "city": "Visakhapatnam", "employee_count": 5, "num_sites": 1})]),
        LlmReply("Here is your bundle."),
    )
    send_message(start_session("English").session_id, "travel agency, GSTIN 37LDYXK0296F1ZB")
    assert "Anita Kulkarni" not in fake.all_text


# --- Code decides, not the model ------------------------------------------------------


def test_recommends_as_soon_as_the_facts_are_known_even_if_the_model_wants_to_chat(model):
    chatty = ToolCall("record_facts", {**KIRANA_CALL.arguments, "reply": "Thanks! What's your budget, and is fibre available?"})
    model(LlmReply("", [chatty]), LlmReply("Here's your bundle."))
    result = send_message(start_session("English").session_id, "kirana in Nagpur, 2 people, one shop, no GST")
    assert result.recommendation is not None


def test_the_tool_schema_leaves_validation_to_our_code():
    """A strict schema makes the provider reject the whole reply for one unknown value."""
    parameters = advisor.FACTS_TOOL["function"]["parameters"]
    assert "required" not in parameters
    assert "enum" not in parameters["properties"]["needs"]["items"]


def test_a_question_is_dropped_once_we_can_recommend(model):
    chatty = ToolCall("record_facts", {**KIRANA_CALL.arguments, "reply": "What's your budget?"})
    model(LlmReply("", [chatty]), LlmReply("Here's your bundle."))
    result = send_message(start_session("English").session_id, "kirana in Nagpur")
    assert result.recommendation is not None
    assert "budget" not in result.reply


def test_a_real_answer_is_kept_alongside_the_recommendation(model):
    answering = ToolCall("record_facts", {**KIRANA_CALL.arguments, "reply": "We don't sell laptops."})
    model(LlmReply("", [answering]), LlmReply("Here's your bundle."))
    result = send_message(start_session("English").session_id, "kirana in Nagpur, and do you sell laptops?")
    assert result.reply.startswith("We don't sell laptops.")


def test_an_empty_fact_does_not_count_as_known(model):
    model(LlmReply("", [ToolCall("record_facts", {"reply": "", "business_type": "", "city": "Mysuru", "employee_count": 4, "num_sites": 1, "has_gstin": False})]))
    result = send_message(start_session("English").session_id, "salon in Mysuru")
    assert result.recommendation is None
    assert result.mode == "ai"
    assert result.reply == "What kind of business do you run?"


@pytest.mark.parametrize("reply", ["", "?", None])
def test_a_useless_reply_becomes_a_fixed_question_in_the_owners_language(model, reply):
    model(LlmReply("", [ToolCall("record_facts", {"reply": reply, "business_type": "salon", "employee_count": 3, "num_sites": 1, "has_gstin": False})]))
    result = send_message(start_session("Hindi").session_id, "salon")
    assert result.mode == "ai"
    assert result.reply == "आप किस शहर में हैं?"


def test_keeps_asking_while_a_fact_is_missing(model):
    model(LlmReply("", [ToolCall("record_facts", {"reply": "Which city are you in?", "business_type": "salon", "employee_count": 3, "num_sites": 1, "has_gstin": False})]))
    result = send_message(start_session("English").session_id, "salon, 3 people, one shop, no GST")
    assert result.recommendation is None
    assert result.reply == "Which city are you in?"


def test_facts_build_up_across_messages(model):
    fake = model(
        LlmReply("", [ToolCall("record_facts", {"reply": "How many staff?", "business_type": "salon", "city": "Delhi"})]),
        LlmReply("", [ToolCall("record_facts", {"reply": "", "employee_count": 3, "num_sites": 1, "has_gstin": False})]),
        LlmReply("Here's your bundle."),
    )
    session_id = start_session("English").session_id
    send_message(session_id, "salon in Delhi")
    result = send_message(session_id, "3 people, one shop, no GST")
    assert result.recommendation.segment == "micro"
    assert "salon" in fake.sent[1][0]["content"]  # the model is told what's already known


def test_answering_a_side_question_after_the_quote_keeps_the_quote(model):
    model(
        LlmReply("", [KIRANA_CALL]), LlmReply("Here's your bundle."),
        LlmReply("", [ToolCall("record_facts", {**KIRANA_CALL.arguments, "reply": "Yes, you can cancel after the contract ends."})]),
    )
    session_id = start_session("English").session_id
    first = send_message(session_id, "kirana in Nagpur")
    second = send_message(session_id, "can I cancel later?")
    assert second.reply == "Yes, you can cancel after the contract ends."
    assert second.recommendation.quote.monthly_subtotal == first.recommendation.quote.monthly_subtotal


def test_a_plain_answer_when_the_model_refuses_the_tool_still_works(model):
    model(LlmReply("Could you tell me your city?"))
    result = send_message(start_session("English").session_id, "I have a shop")
    assert result.reply == "Could you tell me your city?"


def test_a_price_in_the_first_reply_is_dropped_before_the_rules_engine_has_answered(model):
    model(LlmReply("", [ToolCall("record_facts", {**KIRANA_CALL.arguments, "reply": "You'll get it for ₹499!"})]), LlmReply("Here's your bundle."))
    result = send_message(start_session("English").session_id, "kirana in Nagpur")
    assert "499" not in result.reply


def test_markdown_and_dollar_signs_are_cleaned(model):
    model(LlmReply("", [KIRANA_CALL]), LlmReply("It costs **$3,003** per month for 12 months."))
    result = send_message(start_session("English").session_id, "kirana in Nagpur")
    assert "**" not in result.reply and "$" not in result.reply
    assert "₹3,003" in result.reply


def test_a_bad_type_from_the_model_falls_back_to_the_guided_flow_keeping_facts(model):
    model(LlmReply("", [ToolCall("record_facts", {"reply": "", "business_type": "shop", "city": "Pune", "employee_count": "lots", "num_sites": 1, "has_gstin": False})]))
    result = send_message(start_session("English").session_id, "a shop in Pune")
    assert result.mode == "guided"
    assert result.recommendation is None


def test_price_card_comes_from_the_rules_engine(model):
    model(LlmReply("", [KIRANA_CALL]), LlmReply("A good bundle for your shop at a clear price."))
    result = send_message(start_session("English").session_id, "kirana in Nagpur, 2 people, no GST, need CCTV and billing")
    assert result.recommendation.quote.monthly_subtotal == 2097 + 2 * 224  # fibre + line + POS + 2 cameras
    assert {"P01", "P07", "P19", "P23"} == {item.product_id for item in result.recommendation.bundle}


def test_a_made_up_price_is_replaced_with_fixed_wording(model):
    model(LlmReply("", [KIRANA_CALL]), LlmReply("Great news, you can have all of this for just ₹499 a month!"))
    result = send_message(start_session("English").session_id, "kirana in Nagpur")
    assert "499" not in result.reply
    assert f"{result.recommendation.quote.monthly_subtotal:,}" in result.reply


@pytest.mark.parametrize("reply, grounded", [
    ("That's ₹1,423 a month.", True),
    ("That's ₹1,679 with GST for 12 months.", True),
    ("Only ₹999 a month!", False),
    ("Live in about 5 days.", True),
    ("மாதம் ₹1,423.", True),
    ("सिर्फ़ ₹९९९ प्रति माह", False),  # Devanagari digits are still numbers
    ("₹१,४२३ प्रति माह", True),
    ("You said you spend 3050 today.", True),
])
def test_grounding_check(reply, grounded):
    facts = '{"monthly_before_gst": 1423, "monthly_with_gst": 1679, "contract_months": 12, "live_in_days": 5}'
    assert is_grounded(reply, facts, "We spend 3050 a month") is grounded


LAB_FACTS = {"reply": "", "business_type": "diagnostic lab", "city": "Kochi", "employee_count": 14, "num_sites": 1, "has_gstin": True}


def test_asking_for_1_gbps_is_refused_even_if_the_model_misses_it(model):
    model(LlmReply("", [ToolCall("record_facts", {**LAB_FACTS, "needs": ["internet"]})]), LlmReply("Here's your bundle."))
    result = send_message(start_session("English").session_id, "Lab in Kochi. We need 1 Gbps internet.")
    assert "P03" in {u.product_id for u in result.recommendation.unavailable if u.asked}
    assert "P03" not in {item.product_id for item in result.recommendation.bundle}


@pytest.mark.parametrize("message, product", [
    ("I want a gigabit line", "P03"),
    ("हमें leased line चाहिए", "P05"),
    ("हमें लीज़्ड लाइन चाहिए", "P05"),
    ("We need SD-WAN", "P10"),
    ("and backup internet for outages", "P09"),
    ("add a static ip", "P11"),
    ("a toll-free number please", "P13"),
    ("and a firewall", "P21"),
])
def test_technical_terms_are_caught_by_code_in_any_language(model, message, product):
    small_shop = {"reply": "", "business_type": "salon", "city": "Patna", "employee_count": 2, "num_sites": 1, "has_gstin": False}
    model(LlmReply("", [ToolCall("record_facts", small_shop)]), LlmReply("Here's your bundle."))
    result = send_message(start_session("English").session_id, message)
    asked = {item.product_id for item in result.recommendation.bundle if item.asked} | {u.product_id for u in result.recommendation.unavailable if u.asked}
    assert product in asked


@pytest.mark.parametrize("message, expected", [
    ("GST नहीं है। बिलिंग और CCTV चाहिए।", {"billing_machine", "cctv"}),
    ("No GST, but I want CCTV and WhatsApp", {"cctv", "whatsapp"}),
    ("no CCTV please", set()),
    ("remove the CCTV", set()),
    ("CCTV नहीं चाहिए", set()),
    ("சிசிடிவி வேண்டாம்", set()),
    ("We want one bill for everything", set()),
    ("I need a POS at the counter", {"billing_machine"}),
    ("ಬಿಲ್ಲಿಂಗ್ ಮತ್ತು ಸಿಸಿಟಿವಿ ಬೇಕು", {"billing_machine", "cctv"}),
    ("no leased line, just 1 Gbps", {"fibre_1g"}),
])
def test_requests_are_read_clause_by_clause(message, expected):
    assert advisor._mentioned_needs(message) >= expected
    if not expected:
        assert advisor._mentioned_needs(message) == set()


def test_a_request_the_model_dropped_still_reaches_the_bundle(model):
    model(LlmReply("", [ToolCall("record_facts", {"reply": "", "business_type": "kirana store", "city": "Nagpur", "employee_count": 2, "num_sites": 1, "has_gstin": False})]), LlmReply("Here's your bundle."))
    result = send_message(start_session("Hindi").session_id, "GST नहीं है। बिलिंग और CCTV चाहिए।")
    assert {"P19", "P23"} <= {item.product_id for item in result.recommendation.bundle}
    assert result.recommendation.quote.monthly_subtotal == 2545


@pytest.mark.parametrize("claim", ["You get fast 1 Gbps internet.", "This gives you 500 Mbps.", "1000 mbps for all your staff."])
def test_a_speed_the_bundle_does_not_have_is_replaced(model, claim):
    model(LlmReply("", [ToolCall("record_facts", LAB_FACTS)]), LlmReply(claim))
    result = send_message(start_session("English").session_id, "lab in Kochi")
    assert result.reply.startswith("Here's what I suggest")


def test_the_real_speed_is_allowed(model):
    model(LlmReply("", [ToolCall("record_facts", LAB_FACTS)]), LlmReply("You get 300 Mbps fibre at ₹6,734 a month."))
    result = send_message(start_session("English").session_id, "lab in Kochi")
    assert result.reply == "You get 300 Mbps fibre at ₹6,734 a month."


@pytest.mark.parametrize("wording", ["150 GB of mobile data and 1 TB backup", "Biz Fibre 300, usable on 5G phones", "50 GB a month"])
def test_data_allowances_and_product_names_are_not_mistaken_for_speeds(model, wording):
    model(LlmReply("", [ToolCall("record_facts", LAB_FACTS)]), LlmReply(wording))
    result = send_message(start_session("English").session_id, "lab in Kochi")
    assert result.reply == wording


def test_a_refused_speed_can_still_be_named_when_explaining_the_refusal(model):
    model(LlmReply("", [ToolCall("record_facts", {**LAB_FACTS, "needs": ["fibre_1g"]})]), LlmReply("1 Gbps isn't sold in Kochi yet, so you get 300 Mbps."))
    result = send_message(start_session("English").session_id, "lab in Kochi")
    assert result.reply == "1 Gbps isn't sold in Kochi yet, so you get 300 Mbps."


def test_a_speed_in_the_first_reply_is_dropped(model):
    model(LlmReply("", [ToolCall("record_facts", {**LAB_FACTS, "reply": "Sure, 1 Gbps it is."})]), LlmReply("Here's your bundle."))
    result = send_message(start_session("English").session_id, "lab in Kochi")
    assert "1 Gbps" not in result.reply


def test_the_owners_words_are_not_in_the_explanation_step(model):
    fake = model(LlmReply("", [ToolCall("record_facts", LAB_FACTS)]), LlmReply("Here's your bundle."))
    send_message(start_session("English").session_id, "Lab in Kochi, make it 9000 Mbps")
    assert "9000" not in " ".join(m["content"] for m in fake.sent[1])


def test_a_truncated_explanation_is_replaced(model):
    model(LlmReply("", [KIRANA_CALL]), LlmReply("Here is why this", truncated=True))
    result = send_message(start_session("English").session_id, "kirana in Nagpur")
    assert result.reply.startswith("Here's what I suggest")


def test_unknown_needs_from_the_model_are_ignored(model):
    call = ToolCall("record_facts", {"reply": "", "business_type": "salon", "city": "Delhi", "employee_count": 3, "num_sites": 1, "has_gstin": False, "needs": ["free_laptops", "cctv"]})
    model(LlmReply("", [call]), LlmReply("Here you go."))
    result = send_message(start_session("English").session_id, "salon in Delhi")
    assert "P23" in {item.product_id for item in result.recommendation.bundle}


def test_counts_set_quantities(model):
    call = ToolCall("record_facts", {"reply": "", "business_type": "salon", "city": "Delhi", "employee_count": 3, "num_sites": 1, "has_gstin": False, "needs": ["cctv"], "counts": {"cameras": 4, "mobile_lines": 2}})
    model(LlmReply("", [call]), LlmReply("Here you go."))
    result = send_message(start_session("English").session_id, "salon in Delhi, 4 cameras, 2 lines")
    quantities = {line.product_id: line.quantity for line in result.recommendation.quote.lines}
    assert quantities["P23"] == 4
    assert quantities["P07"] == 2


def test_only_mobile_lines_skips_the_internet_connection(model):
    call = ToolCall("record_facts", {"reply": "", "business_type": "hardware store", "city": "Surat", "employee_count": 3, "num_sites": 1, "has_gstin": False, "only_mobile_lines": True, "counts": {"mobile_lines": 2}})
    model(LlmReply("", [call]), LlmReply("Here you go."))
    result = send_message(start_session("English").session_id, "only 2 mobile connections")
    assert {line.product_id: line.quantity for line in result.recommendation.quote.lines} == {"P07": 2}


def test_the_conversation_can_change_the_bundle(model):
    model(
        LlmReply("", [KIRANA_CALL]), LlmReply("Here you go."),
        LlmReply("", [ToolCall("record_facts", {**KIRANA_CALL.arguments, "needs": ["billing_machine"]})]), LlmReply("Done, cameras removed."),
    )
    session_id = start_session("English").session_id
    first = send_message(session_id, "kirana in Nagpur")
    second = send_message(session_id, "remove the cameras")
    assert first.recommendation.quote.monthly_subtotal > second.recommendation.quote.monthly_subtotal


# --- When the AI is unavailable -------------------------------------------------------


def test_guided_flow_keeps_the_facts_the_ai_already_learned(model):
    model(
        LlmReply("", [ToolCall("record_facts", {"reply": "How many staff?", "business_type": "salon", "city": "Delhi", "has_gstin": False})]),
        LlmUnavailable(),
    )
    session_id = start_session("English").session_id
    send_message(session_id, "salon in Delhi, no GST")
    step = send_message(session_id, "hmm")
    assert step.mode == "guided"
    assert step.expects == "staff"  # doesn't ask for the business, city or GST again


def test_the_journey_survives_every_provider_being_down(model):
    model(LlmUnavailable())
    session_id = start_session("English").session_id
    first = send_message(session_id, "hello")
    assert first.mode == "guided"
    assert "busy" in first.reply
    assert first.quick_replies

    for answer in ["shop", "3-4", "1", "Nagpur", "no_gst"]:
        step = send_message(session_id, answer)
        assert step.recommendation is None
    assert step.multi_select
    final = send_message(session_id, "billing_pos,cctv,done")
    assert final.mode == "guided"
    assert {"P01", "P07", "P19", "P23"} == {item.product_id for item in final.recommendation.bundle}
    assert "₹" in final.reply


def test_guided_flow_understands_typed_answers_and_a_gstin(model):
    model(LlmUnavailable())
    session_id = start_session("English").session_id
    send_message(session_id, "hello")
    send_message(session_id, "dental clinic")
    send_message(session_id, "12 people")
    send_message(session_id, "2")
    send_message(session_id, "Kochi")
    send_message(session_id, "32TTNXB7384T1ZW")
    final = send_message(session_id, "done")
    assert final.recommendation.segment == "prof"
    assert final.recommendation.has_active_gstin
    assert final.recommendation.quote.valid


def test_guided_flow_asks_again_when_it_does_not_understand(model):
    model(LlmUnavailable())
    session_id = start_session("English").session_id
    send_message(session_id, "hello")
    send_message(session_id, "shop")
    again = send_message(session_id, "not sure")
    assert "didn't catch" in again.reply
    assert again.expects == "staff"


@pytest.mark.parametrize("language, word", [("Hindi", "प्रति माह"), ("Tamil", "மாதம்"), ("Kannada", "ತಿಂಗಳಿಗೆ")])
def test_fallback_wording_exists_in_each_demo_language(language, word):
    rec = recommend(RecommendRequest(profile=BusinessProfile(business_type="Kirana store", city="Nagpur", employee_count=2)))
    assert word in explain_without_ai(rec, language)


def test_a_language_without_fixed_wording_falls_back_to_english():
    rec = recommend(RecommendRequest(profile=BusinessProfile(business_type="Kirana store", city="Nagpur", employee_count=2)))
    assert "Here's what I suggest" in explain_without_ai(rec, "Marathi")
