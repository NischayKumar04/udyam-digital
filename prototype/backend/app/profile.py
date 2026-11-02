"""Turns what the owner tells us into verified facts: segment, city tier, GSTIN status."""
import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from pydantic import BaseModel, Field

from .config import LEADS_CSV
from .identifiers import check_gstin
from .product_text import note
from .registry import lookup_gstin
from .rules import BusinessFacts

SEGMENT_CODES = {
    "Micro retail & services": "micro",
    "Professional offices": "prof",
    "Small multi-site businesses": "multi",
    "Small manufacturers": "mfg",
}

_CITY_ALIASES = {
    "bangalore": "bengaluru", "bombay": "mumbai", "calcutta": "kolkata", "madras": "chennai",
    "vizag": "visakhapatnam", "baroda": "vadodara", "mysore": "mysuru", "cochin": "kochi",
    "ernakulam": "kochi", "new delhi": "delhi",
}

_MANUFACTURING = re.compile(r"\b(unit|factory|workshop|manufactur\w*|moulding|mill|plant|foundry|fabricat\w*|printing press|textile|garment)\b")
_PROFESSIONAL = re.compile(r"\b(clinic|doctor|dental|dentist|physio\w*|diagnostic|lab|hospital|ca|chartered|accountant|firm|law|lawyer|advocate|legal|architect\w*|studio|agency|consult\w*|coaching|tuition|institute|office|insurance|real estate|travel)\b")
_CHAIN = re.compile(r"\b(chain|branches|outlets|franchise)\b")


@lru_cache(maxsize=1)
def _lead_lookups() -> tuple[dict[str, str], dict[str, tuple[str, int, str]]]:
    """Business type -> segment, and city -> (name, tier, state), from the leads file."""
    types, cities = {}, {}
    with LEADS_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            types[row["business_type"].lower()] = SEGMENT_CODES[row["segment"]]
            cities[row["city"].lower()] = (row["city"], int(row["city_tier"]), row["state"])
    return types, cities


def lookup_city(city: str) -> tuple[str, int, str] | None:
    key = city.strip().lower()
    return _lead_lookups()[1].get(_CITY_ALIASES.get(key, key))


def classify_segment(business_type: str | None, num_sites: int) -> str:
    text = (business_type or "").strip().lower()
    known = _lead_lookups()[0].get(text)
    is_manufacturer = known == "mfg" or (known is None and bool(_MANUFACTURING.search(text)))
    if is_manufacturer:
        return "mfg"
    if num_sites >= 3 or _CHAIN.search(text):
        return "multi"
    if known:
        return known
    return "prof" if _PROFESSIONAL.search(text) else "micro"


class BusinessProfile(BaseModel):
    business_type: str | None = None
    segment: str | None = Field(default=None, pattern="^(micro|prof|multi|mfg)$")
    city: str | None = None
    city_tier: int | None = Field(default=None, ge=1, le=2)
    employee_count: int = Field(ge=1)
    num_sites: int = Field(default=1, ge=1)
    gstin: str | None = None
    has_active_gstin: bool = False
    fibre_feasible: bool = True


@dataclass(frozen=True)
class ResolvedProfile:
    facts: BusinessFacts
    segment: str
    coverage_confirmed: bool
    gstin_status: str | None
    fibre_feasible: bool
    notes: tuple[str, ...]


def resolve_profile(profile: BusinessProfile, language: str = "English") -> ResolvedProfile:
    notes = []

    # A GSTIN we can check always beats what the owner says about it.
    active, status = profile.has_active_gstin, None
    if profile.gstin:
        check = check_gstin(profile.gstin)
        record = lookup_gstin(check.gstin) if check.valid else None
        if not check.valid:
            active, status = False, "Invalid"
            notes.append(note(language, "gstin_invalid", error=check.errors[0]))
        elif record is None:
            active, status = False, "NotFound"
            notes.append(note(language, "gstin_not_found"))
        else:
            status = record["status"]
            active = status == "Active"
            if not active:
                notes.append(note(language, "gstin_inactive", status=status))

    # An unlisted city gets an indicative tier-2 bundle, the narrower of the two ranges.
    tier, confirmed = profile.city_tier, profile.city_tier is not None
    if profile.city:
        known = lookup_city(profile.city)
        tier, confirmed = (known[1], True) if known else (tier, False)
    if not confirmed:
        tier = tier or 2
        notes.append(note(language, "coverage"))

    return ResolvedProfile(
        facts=BusinessFacts(tier, profile.employee_count, profile.num_sites, active),
        segment=profile.segment or classify_segment(profile.business_type, profile.num_sites),
        coverage_confirmed=confirmed,
        gstin_status=status,
        fibre_feasible=profile.fibre_feasible,
        notes=tuple(notes),
    )
