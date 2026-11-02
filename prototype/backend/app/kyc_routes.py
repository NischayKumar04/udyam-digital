"""KYC API: consent first, documents read in memory, nothing written to disk.

Applications live in memory and expire after RETENTION. Uploaded images are never kept:
only the fields read from them, and only until the application expires or is erased.
"""
import csv
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .advisor import UnknownSession, get_session
from .config import KYC_DOCS_DIR, LEADS_CSV, REPO_ROOT
from .identifiers import mask_gstin, mask_udyam
from .kyc_checks import SLOT_NAMES, Applicant, KycResult, validate_application
from .kyc_ocr import DocumentResult, read_document
from .kyc_text import localize

router = APIRouter(prefix="/api/kyc", tags=["kyc"])

CONSENT_NOTICE_VERSION = "2026-11-v1"
RETENTION = timedelta(hours=24)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/png", "image/jpeg"}
_PRESENCE_CODES = {"GST_FROM_REGISTRY", "GST_NOT_NEEDED", "DOCUMENT_MISSING", "UDYAM_FROM_REGISTRY", "UDYAM_NOT_PROVIDED", "ADDRESS_FROM_GST"}
_SAMPLE_FILES = {"gst": "gst_certificate", "udyam": "udyam_certificate", "signatory_id": "signatory_id", "address_proof": "address_proof"}


@dataclass
class _Application:
    applicant: Applicant
    consent_at: datetime
    language: str = "English"
    documents: dict[str, DocumentResult] = field(default_factory=dict)


_applications: dict[str, _Application] = {}


class CreateApplication(BaseModel):
    consent_accepted: bool
    notice_version: str
    applicant: Applicant = Applicant()
    advisor_session_id: str | None = None
    language: str = "English"


class SampleRequest(BaseModel):
    sample_id: str


class InstallAddress(BaseModel):
    same: bool


def _purge_expired() -> None:
    cutoff = datetime.now(timezone.utc) - RETENTION
    for application_id in [a for a, app in _applications.items() if app.consent_at < cutoff]:
        del _applications[application_id]


def _get(application_id: str) -> _Application:
    _purge_expired()
    application = _applications.get(application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found. It may have expired or been erased.")
    return application


def _mask_for_display(fields: dict[str, str]) -> dict[str, str]:
    masked = dict(fields)
    if "gstin" in masked:
        masked["gstin"] = mask_gstin(masked["gstin"])
    if "udyam_number" in masked:
        masked["udyam_number"] = mask_udyam(masked["udyam_number"])
    for key in ("id_no", "consumer_no"):
        if key in masked:
            masked[key] = f"{'*' * max(0, len(masked[key]) - 4)}{masked[key][-4:]}"
    return masked


def _document_out(doc: DocumentResult) -> dict:
    return {
        "slot": doc.slot,
        "name": SLOT_NAMES.get(doc.slot, doc.slot),
        "readable": doc.readable,
        "detected_type": doc.detected_type,
        "fields": _mask_for_display(doc.fields),
    }


@router.get("/consent-notice")
def consent_notice() -> dict:
    return {
        "version": CONSENT_NOTICE_VERSION,
        "purpose": "To verify your business and the person signing, so we can activate the services you chose. We won't use this for marketing.",
        "data": ["GSTIN and Udyam number", "Business name and address", "Name, role and ID of the person signing", "A recent utility bill"],
        "processing": "Documents are read on our own systems and are not sent to any AI provider.",
        "retention": f"Your images aren't stored. The details read from them are deleted after {int(RETENTION.total_seconds() // 3600)} hours unless you complete the order.",
        "rights": "You can withdraw consent and erase your application at any time.",
    }


@router.post("/applications", status_code=201)
def create_application(body: CreateApplication) -> dict:
    if not body.consent_accepted:
        raise HTTPException(status_code=403, detail="We can't read your documents without your consent.")
    if body.notice_version != CONSENT_NOTICE_VERSION:
        raise HTTPException(status_code=409, detail="The consent notice has changed. Please read the latest version.")
    _purge_expired()
    applicant = body.applicant
    if body.advisor_session_id:
        # Identifiers the owner typed in the chat stay on the server; they don't return through the browser.
        try:
            session = get_session(body.advisor_session_id)
            applicant = applicant.model_copy(update={
                "gstin_on_file": session.gstin or applicant.gstin_on_file,
                "udyam_on_file": session.udyam or applicant.udyam_on_file,
                "no_gst_path": session.recommendation is not None and not session.recommendation.has_active_gstin,
            })
        except UnknownSession:
            pass
    application_id = uuid.uuid4().hex
    _applications[application_id] = _Application(applicant, datetime.now(timezone.utc), body.language)
    return {"application_id": application_id, "retention_hours": int(RETENTION.total_seconds() // 3600)}


@router.post("/applications/{application_id}/documents")
async def upload_document(application_id: str, slot: str = Form(...), file: UploadFile = File(...)) -> dict:
    application = _get(application_id)
    if slot not in SLOT_NAMES:
        raise HTTPException(status_code=422, detail=f"Unknown document type: {slot}")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Please upload a PNG or JPEG image.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is too large. Please upload one under 8 MB.")
    document = read_document(slot, data)
    application.documents[slot] = document
    return _document_out(document)


@router.post("/applications/{application_id}/submit")
def submit(application_id: str) -> KycResult:
    application = _get(application_id)
    return localize(validate_application(dict(application.documents), application.applicant), application.language)


@router.get("/applications/{application_id}/requirements")
def requirements(application_id: str) -> list[dict]:
    """Asks only for what can't be verified another way."""
    application = _get(application_id)
    checks = localize(validate_application(dict(application.documents), application.applicant), application.language).checks
    out = []
    for slot in SLOT_NAMES:
        if slot in application.documents:
            out.append({"slot": slot, "state": "uploaded", "message": None})
            continue
        check = next((c for c in checks if c.document == slot and c.code in _PRESENCE_CODES), None)
        state = {"AUTO_RESOLVE": "resolved", "PASS": "resolved", "PASS_WITH_WARNING": "optional"}.get(check.outcome if check else "", "needed")
        out.append({"slot": slot, "state": state, "message": check.message if check else None})
    return out


@router.post("/applications/{application_id}/install-address")
def set_install_address(application_id: str, body: InstallAddress) -> dict:
    application = _get(application_id)
    application.applicant = application.applicant.model_copy(update={"install_address_same_as_gst": body.same})
    return {"same": body.same}


def application_verdict(application_id: str) -> str:
    application = _get(application_id)
    return validate_application(dict(application.documents), application.applicant).verdict


@router.delete("/applications/{application_id}", status_code=204)
def erase(application_id: str) -> None:
    _get(application_id)
    del _applications[application_id]


# --- Demo helpers: the data pack's specimen applicants, so nobody has to upload files by hand -------------


def _sample_index() -> dict[str, dict]:
    fixture = json.loads((REPO_ROOT / "analysis" / "kyc_expected_results.json").read_text(encoding="utf-8"))
    return {a["id"]: {"id": a["id"], "lead_id": a["lead_id"], "business": a["business"]} for a in fixture["applicants"]}


@router.get("/samples")
def samples() -> list[dict]:
    return [{"id": s["id"], "business": s["business"]} for s in _sample_index().values()]


@router.post("/applications/{application_id}/load-sample")
def load_sample(application_id: str, body: SampleRequest) -> list[dict]:
    application = _get(application_id)
    sample = _sample_index().get(body.sample_id) if re.fullmatch(r"K\d\d", body.sample_id) else None
    if sample is None:
        raise HTTPException(status_code=404, detail="No such sample applicant.")
    with LEADS_CSV.open(encoding="utf-8", newline="") as f:
        lead = next(row for row in csv.DictReader(f) if row["lead_id"] == sample["lead_id"])
    application.applicant = Applicant(
        contact_name=lead["contact_name"],
        gstin_on_file=lead["gstin"] or None,
        udyam_on_file=lead["udyam_number"] or None,
    )
    application.documents = {}
    for slot, suffix in _SAMPLE_FILES.items():
        path = KYC_DOCS_DIR / f"{body.sample_id}_{suffix}.png"
        if path.exists():
            application.documents[slot] = read_document(slot, path.read_bytes())
    return [_document_out(doc) for doc in application.documents.values()]
