"""Provider fallback, tested with a fake network so no quota is used."""
import httpx
import pytest

from app import llm
from app.llm import LlmUnavailable, Provider, chat

GROQ = Provider("groq", "https://groq.test", "k1", "m1", 5.0)
GEMINI = Provider("gemini", "https://gemini.test", "k2", "m2", 5.0)


def ok(text="hello", finish="stop", tool_calls=None):
    message = {"content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": finish}]})


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setattr(llm, "configured_providers", lambda: [GROQ, GEMINI])
    llm._resting_until.clear()
    responses = {}
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        result = responses[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    yield responses, calls
    llm._resting_until.clear()


def test_first_provider_answers(network):
    responses, calls = network
    responses[GROQ.url] = ok("from groq")
    reply = chat([])
    assert reply.text == "from groq"
    assert reply.provider == "groq"
    assert calls == [GROQ.url]


def test_rate_limit_falls_through_and_rests_the_provider(network):
    responses, calls = network
    responses[GROQ.url] = httpx.Response(429, headers={"retry-after": "60"})
    responses[GEMINI.url] = ok("from gemini")
    assert chat([]).provider == "gemini"
    # While resting, Groq isn't tried at all.
    assert chat([]).provider == "gemini"
    assert calls == [GROQ.url, GEMINI.url, GEMINI.url]


@pytest.mark.parametrize("failure", [
    httpx.Response(500),
    httpx.Response(400, json={"error": {"code": "tool_use_failed"}}),
    httpx.ReadTimeout("slow"),
    httpx.ConnectError("no network"),
    httpx.Response(200, json={"unexpected": True}),
    ok(""),
])
def test_any_failure_moves_to_the_next_provider(network, failure):
    responses, _ = network
    responses[GROQ.url] = failure
    responses[GEMINI.url] = ok("from gemini")
    assert chat([]).provider == "gemini"


def test_all_providers_down_raises_so_the_guided_flow_takes_over(network):
    responses, _ = network
    responses[GROQ.url] = httpx.Response(429)
    responses[GEMINI.url] = httpx.Response(503)
    with pytest.raises(LlmUnavailable):
        chat([])


def test_no_keys_configured_is_the_same_as_all_down(monkeypatch):
    monkeypatch.setattr(llm, "configured_providers", lambda: [])
    with pytest.raises(LlmUnavailable):
        chat([])


def test_tool_calls_are_parsed_and_bad_ones_skipped(network):
    responses, _ = network
    responses[GROQ.url] = ok("", tool_calls=[
        {"function": {"name": "recommend_bundle", "arguments": '{"city": "Pune"}'}},
        {"function": {"name": "broken", "arguments": "{not json"}},
    ])
    reply = chat([])
    assert [(c.name, c.arguments) for c in reply.tool_calls] == [("recommend_bundle", {"city": "Pune"})]


def test_truncated_replies_are_flagged(network):
    responses, _ = network
    responses[GROQ.url] = ok("cut off here", finish="length")
    assert chat([]).truncated


def test_groq_lists_several_models_because_its_limits_are_per_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.delenv("GROQ_MODELS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    names = [p.name for p in llm.configured_providers()]
    assert names == ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b", "groq:qwen/qwen3.8-27b"]


def test_gemini_backs_up_the_main_model_ahead_of_the_smaller_ones(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GROQ_MODELS", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    names = [p.name for p in llm.configured_providers()]
    assert names == ["groq:openai/gpt-oss-120b", "gemini:gemini-3.6-flash", "groq:openai/gpt-oss-20b", "groq:qwen/qwen3.8-27b"]


def test_errors_are_logged_without_the_body_which_can_echo_the_owner(network, caplog):
    responses, _ = network
    responses[GROQ.url] = httpx.Response(400, json={"error": {"code": "tool_use_failed", "failed_generation": "secret text from the owner"}})
    responses[GEMINI.url] = ok("from gemini")
    chat([])
    assert "tool_use_failed" in caplog.text
    assert "secret text" not in caplog.text
