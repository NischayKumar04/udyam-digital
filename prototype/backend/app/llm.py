"""Calls free-tier models through their OpenAI-compatible endpoints.

Tries each configured model in turn and rests one that returns a rate limit. Groq's
limits apply per model, so its models give several times the capacity of any one of them.
A busy free tier costs a slower reply rather than a failed conversation. When every model
is out, callers get LlmUnavailable and switch to the guided flow.
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger("advisor.llm")

_DEFAULT_GROQ_MODELS = "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b"
_DEFAULT_REST_SECONDS = 30.0
_REST_AFTER_ERROR_SECONDS = 10.0


class LlmUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    api_key: str
    model: str
    timeout: float


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class LlmReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    truncated: bool = False


_resting_until: dict[str, float] = {}


def configured_providers() -> list[Provider]:
    """Best extraction first: a wrong bundle costs more than a slow reply, so Gemini backs up the
    main model ahead of Groq's smaller ones, which misread requests more often."""
    groq, gemini = [], []
    if key := os.getenv("GROQ_API_KEY", "").strip():
        for model in (os.getenv("GROQ_MODELS", "").strip() or _DEFAULT_GROQ_MODELS).split(","):
            groq.append(Provider(f"groq:{model.strip()}", "https://api.groq.com/openai/v1/chat/completions", key, model.strip(), timeout=15.0))
    if key := os.getenv("GEMINI_API_KEY", "").strip():
        model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.6-flash"
        gemini.append(Provider(f"gemini:{model}", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", key, model, timeout=15.0))
    return [*groq[:1], *gemini, *groq[1:]]


def _error_code(response: httpx.Response) -> str:
    """Just the error's code: the rest of an error body can echo what the owner typed."""
    try:
        return str(response.json()["error"].get("code"))
    except (ValueError, KeyError, TypeError, AttributeError):
        return "unknown"


def _rest(provider: Provider, seconds: float) -> None:
    _resting_until[provider.name] = time.monotonic() + seconds


def _parse_tool_calls(message: dict) -> list[ToolCall]:
    calls = []
    for call in message.get("tool_calls") or []:
        try:
            calls.append(ToolCall(call["function"]["name"], json.loads(call["function"]["arguments"] or "{}")))
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
    return calls


def chat(messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 500, force_tool: bool = False) -> LlmReply:
    for provider in configured_providers():
        if time.monotonic() < _resting_until.get(provider.name, 0.0):
            continue
        # These models think before answering. Keeping that short saves tokens and time.
        body = {"model": provider.model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens, "reasoning_effort": "low"}
        if tools:
            body["tools"] = tools
            if force_tool:
                body["tool_choice"] = "required"
        try:
            response = httpx.post(provider.url, headers={"Authorization": f"Bearer {provider.api_key}"}, json=body, timeout=provider.timeout)
        except httpx.HTTPError as error:
            logger.warning("%s failed: %s", provider.name, type(error).__name__)
            _rest(provider, _REST_AFTER_ERROR_SECONDS)
            continue
        if response.status_code != 200:
            logger.warning("%s returned %s (%s)", provider.name, response.status_code, _error_code(response))
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after", "")
            _rest(provider, float(retry_after) if retry_after.replace(".", "", 1).isdigit() else _DEFAULT_REST_SECONDS)
            continue
        if response.status_code >= 500:
            _rest(provider, _REST_AFTER_ERROR_SECONDS)
            continue
        if response.status_code != 200:
            # A malformed tool call or similar: this reply is unusable, so try the next provider.
            continue
        try:
            choice = response.json()["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, ValueError):
            continue
        reply = LlmReply(
            (message.get("content") or "").strip(), _parse_tool_calls(message), provider.name, provider.model,
            truncated=choice.get("finish_reason") == "length",
        )
        if reply.text or reply.tool_calls:
            return reply
    raise LlmUnavailable
