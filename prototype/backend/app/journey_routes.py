"""API for the advisor conversation, the owner's quote, orders and the back-office queue.

The browser holds only a session id. GSTINs and profiles stay on the server, so
identifiers don't pass back and forth, and prices are always worked out here.
"""
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .advisor import SUPPORTED_LANGUAGES, AdvisorReply, UnknownSession, erase_session, get_session, send_message, start_session
from .backoffice import queue
from .kyc_routes import application_verdict
from .orders import OrderBlocked, advance, create_order, get_order, order_view
from .pricing import LineItem, Quote, build_quote
from .profile import resolve_profile

router = APIRouter(prefix="/api", tags=["journey"])


class StartSession(BaseModel):
    language: str = "English"


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class SessionQuote(BaseModel):
    lines: list[LineItem]
    contract_months: int | None = None


class CreateOrder(BaseModel):
    advisor_session_id: str
    kyc_application_id: str
    lines: list[LineItem]
    contract_months: int | None = None


def _session_or_404(session_id: str):
    try:
        return get_session(session_id)
    except UnknownSession:
        raise HTTPException(status_code=404, detail="This conversation has expired. Please start again.") from None


def _reply_out(reply: AdvisorReply) -> dict:
    return {
        "session_id": reply.session_id,
        "reply": reply.reply,
        "mode": reply.mode,
        "quick_replies": reply.quick_replies,
        "multi_select": reply.multi_select,
        "expects": reply.expects,
        "recommendation": reply.recommendation.model_dump() if reply.recommendation else None,
    }


@router.get("/advisor/languages")
def languages() -> list[str]:
    return list(SUPPORTED_LANGUAGES)


@router.post("/advisor/sessions", status_code=201)
def start(body: StartSession) -> dict:
    return _reply_out(start_session(body.language))


@router.post("/advisor/sessions/{session_id}/messages")
def message(session_id: str, body: Message) -> dict:
    _session_or_404(session_id)
    return _reply_out(send_message(session_id, body.text))


@router.delete("/advisor/sessions/{session_id}", status_code=204)
def end(session_id: str) -> None:
    _session_or_404(session_id)
    erase_session(session_id)


@router.post("/advisor/sessions/{session_id}/quote")
def session_quote(session_id: str, body: SessionQuote) -> Quote:
    session = _session_or_404(session_id)
    if session.request is None:
        raise HTTPException(status_code=409, detail="There's no recommendation yet.")
    resolved = resolve_profile(session.request.profile)
    try:
        return build_quote(body.lines, resolved.facts, resolved.segment, body.contract_months, session.language)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/orders", status_code=201)
def place_order(body: CreateOrder) -> dict:
    session = _session_or_404(body.advisor_session_id)
    if session.request is None:
        raise HTTPException(status_code=409, detail="There's no recommendation yet.")
    verdict = application_verdict(body.kyc_application_id)
    resolved = resolve_profile(session.request.profile)
    try:
        order = create_order(body.lines, resolved.facts, resolved.segment, body.contract_months, verdict, session.language)
    except OrderBlocked as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return order_view(order)


@router.get("/orders/{order_id}")
def track(order_id: str) -> dict:
    order = get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="We can't find that order.")
    return order_view(order)


@router.post("/orders/{order_id}/advance")
def simulate_next_step(order_id: str) -> dict:
    order = get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="We can't find that order.")
    return order_view(advance(order))


@router.get("/backoffice/queue")
def backoffice_queue(owner: str | None = None, limit: int = 50) -> dict:
    return queue(owner, min(limit, 200))
