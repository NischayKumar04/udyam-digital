"""HTTP API for the Udyam Digital prototype.

Lookups are POST, not GET, so identifiers stay out of URLs and access logs.
"""
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .catalogue import load_catalogue
from .identifiers import check_gstin, is_valid_udyam_format
from .journey_routes import router as journey_router
from .kyc_routes import router as kyc_router
from .pricing import LineItem, Quote, build_quote
from .profile import BusinessProfile, resolve_profile
from .recommender import Recommendation, RecommendRequest, recommend
from .registry import lookup_gstin, lookup_udyam

app = FastAPI(title="Udyam Digital API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(kyc_router)
app.include_router(journey_router)


class GstinLookup(BaseModel):
    gstin: str


class UdyamLookup(BaseModel):
    udyam_number: str


class QuoteRequest(BaseModel):
    profile: BusinessProfile
    lines: list[LineItem]
    contract_months: int | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/catalogue")
def catalogue() -> list[dict]:
    return [
        {**asdict(p), "city_tiers": sorted(p.city_tiers), "requires_one_of": sorted(p.requires_one_of), "target_segments": sorted(p.target_segments)}
        for p in load_catalogue().values()
    ]


@app.post("/api/lookup/gstin")
def gstin_lookup(body: GstinLookup) -> dict:
    check = check_gstin(body.gstin)
    if not check.valid:
        return {"valid": False, "errors": check.errors, "found": False, "active": False}
    record = lookup_gstin(check.gstin)
    if record is None:
        return {"valid": True, "errors": [], "found": False, "active": False}
    return {"valid": True, "errors": [], "found": True, "active": record["status"] == "Active", **record}


@app.post("/api/lookup/udyam")
def udyam_lookup(body: UdyamLookup) -> dict:
    number = body.udyam_number.strip().upper()
    if not is_valid_udyam_format(number):
        return {"valid": False, "found": False}
    record = lookup_udyam(number)
    return {"valid": True, "found": record is not None, **(record or {})}


@app.post("/api/recommend")
def recommend_bundle(body: RecommendRequest) -> Recommendation:
    return recommend(body)


@app.post("/api/quote")
def quote(body: QuoteRequest) -> Quote:
    resolved = resolve_profile(body.profile)
    try:
        return build_quote(body.lines, resolved.facts, resolved.segment, body.contract_months)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
