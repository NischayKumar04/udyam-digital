"""Validates a KYC application and explains the verdict in terms an owner can act on.

Registry lookups use exact identifiers only. Names repeat across unrelated businesses,
so a matching name is never treated as proof of anything.

Deliberately not checked, because they differ on every document in the data pack:
Udyam registration date, Udyam major activity, and PIN code against state.
"""
import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from pydantic import BaseModel

from .config import ADDRESS_PROOF_MAX_AGE_DAYS, TODAY
from .identifiers import check_gstin, is_valid_udyam_format
from .kyc_ocr import DocumentResult
from .registry import lookup_gstin, lookup_udyam

# Worst first. The application's verdict is the worst result among its checks.
VERDICTS = ["REJECT", "MANUAL_REVIEW", "REUPLOAD", "AUTO_RESOLVE", "PASS_WITH_WARNING", "PASS"]

SLOT_NAMES = {
    "gst": "GST certificate",
    "udyam": "Udyam certificate",
    "signatory_id": "signatory ID",
    "address_proof": "address proof",
}

# Who can normally sign for each kind of business.
SIGNING_ROLES = {
    "Proprietorship": {"owner", "proprietor"},
    "Limited Liability Partnership": {"partner", "designated partner"},
    "Partnership": {"partner"},
    "Private Limited Company": {"director", "managing director", "authorised signatory"},
}

# A name this similar is the same name read imperfectly; below it, the names differ.
NAME_MATCH = 0.92


class Applicant(BaseModel):
    contact_name: str | None = None
    gstin_on_file: str | None = None
    udyam_on_file: str | None = None
    install_address_same_as_gst: bool = False
    no_gst_path: bool = False


class Check(BaseModel):
    code: str
    outcome: str
    document: str | None = None
    message: str
    params: dict[str, str] = {}


class KycResult(BaseModel):
    verdict: str
    checks: list[Check]
    verified_fields: dict[str, str]


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _same(a: str | None, b: str | None) -> bool:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio() >= NAME_MATCH


def _parse_date(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


@dataclass
class _Run:
    checks: list[Check]

    def add(self, code: str, outcome: str, message: str, document: str | None = None, **params: str) -> None:
        self.checks.append(Check(code=code, outcome=outcome, document=document, message=message, params=params))


def _check_presence(run: _Run, docs: dict[str, DocumentResult | None], applicant: Applicant) -> None:
    for slot, name in SLOT_NAMES.items():
        doc = docs.get(slot)
        if doc is None:
            continue
        if not doc.readable:
            run.add("DOCUMENT_UNREADABLE", "REUPLOAD", f"Your {name} is too blurred to read. Please take a clearer photo.", slot)
        elif doc.detected_type and doc.detected_type != slot:
            run.add("WRONG_DOCUMENT", "REUPLOAD", f"This doesn't look like a {name}. It looks like a {SLOT_NAMES[doc.detected_type]}.", slot, detected=doc.detected_type)

    if docs.get("gst") is None:
        record = lookup_gstin(applicant.gstin_on_file) if applicant.gstin_on_file else None
        if record and record["status"] == "Active":
            run.add("GST_FROM_REGISTRY", "AUTO_RESOLVE", "No GST certificate needed. We verified your GSTIN with the registry.", "gst")
        elif applicant.no_gst_path and not applicant.gstin_on_file:
            run.add("GST_NOT_NEEDED", "PASS", "Your plan doesn't need GST registration, so we won't ask for it.", "gst")
        elif not record:
            run.add("DOCUMENT_MISSING", "REUPLOAD", "Please upload your GST certificate or type your GSTIN.", "gst")

    if docs.get("udyam") is None:
        record = lookup_udyam(applicant.udyam_on_file) if applicant.udyam_on_file else None
        if record:
            run.add("UDYAM_FROM_REGISTRY", "AUTO_RESOLVE", "Your Udyam certificate wasn't uploaded, so we fetched it from the Udyam registry using your number.", "udyam")
        else:
            run.add("UDYAM_NOT_PROVIDED", "PASS_WITH_WARNING", "No Udyam registration provided. You can still continue without one.", "udyam")

    if docs.get("signatory_id") is None:
        run.add("DOCUMENT_MISSING", "REUPLOAD", "Please upload the ID of the person signing for the business.", "signatory_id")

    if docs.get("address_proof") is None:
        if applicant.install_address_same_as_gst:
            run.add("ADDRESS_FROM_GST", "AUTO_RESOLVE", "No address proof needed. Installation is at your registered GST address.", "address_proof")
        else:
            run.add("DOCUMENT_MISSING", "REUPLOAD", f"Please upload a utility bill from the last {ADDRESS_PROOF_MAX_AGE_DAYS} days.", "address_proof")


def _readable_fields(doc: DocumentResult | None, slot: str) -> dict[str, str] | None:
    if doc is None or not doc.readable or (doc.detected_type and doc.detected_type != slot):
        return None
    return doc.fields


def _check_gst(run: _Run, fields: dict[str, str] | None, applicant: Applicant) -> dict[str, str] | None:
    """Returns the registry record the rest of the application is compared against."""
    on_file = applicant.gstin_on_file
    if fields is None:
        record = lookup_gstin(on_file) if on_file else None
        if record and record["status"] != "Active":
            run.add("GSTIN_INACTIVE", "REJECT", f"This GSTIN is {record['status']} in the registry. Products that need GST can't be sold on it.", "gst", status=record["status"])
        return record

    gstin = fields.get("gstin", "")
    check = check_gstin(gstin)
    if not check.valid:
        run.add("GSTIN_INVALID", "MANUAL_REVIEW", f"The GSTIN on this certificate isn't valid. {check.errors[0]} We'll have someone review it.", "gst")
    record = lookup_gstin(gstin) if check.valid else None
    if check.valid and record is None:
        run.add("GSTIN_NOT_FOUND", "MANUAL_REVIEW", "The GSTIN on this certificate isn't in the GST registry. We'll have someone review it.", "gst")
    if on_file and gstin != on_file:
        run.add("GSTIN_DIFFERS_FROM_APPLICATION", "MANUAL_REVIEW", "The GSTIN on this certificate differs from the one on your application.", "gst")
    if record is None:
        # Compare the other documents against the number on file, if that one is real.
        return lookup_gstin(on_file) if on_file else None

    if record["status"] != "Active":
        run.add("GSTIN_INACTIVE", "REJECT", f"This GSTIN is {record['status']} in the registry. Products that need GST can't be sold on it.", "gst", status=record["status"])
    if not _same(fields.get("legal_name"), record["legal_name"]):
        run.add("LEGAL_NAME_MISMATCH", "MANUAL_REVIEW", f"The legal name on this certificate doesn't match the registry, which says \"{record['legal_name']}\".", "gst", expected=record["legal_name"])
    if not _same(fields.get("trade_name"), record["trade_name"]):
        run.add("TRADE_NAME_MISMATCH", "MANUAL_REVIEW", f"The trade name on this certificate doesn't match the registry, which says \"{record['trade_name']}\".", "gst")
    if not _same(fields.get("address"), record["principal_place_of_business"]):
        run.add("GST_ADDRESS_MISMATCH", "MANUAL_REVIEW", "The address on this certificate doesn't match the registry.", "gst")
    return record


def _check_udyam(run: _Run, fields: dict[str, str] | None, applicant: Applicant, trade_name: str | None) -> None:
    if fields is None:
        return
    number = fields.get("udyam_number", "")
    if not number:
        run.add("UDYAM_NUMBER_BLANK", "REUPLOAD", "The registration number is blank on this Udyam certificate. Please upload a complete copy.", "udyam")
        return
    if not is_valid_udyam_format(number):
        run.add("UDYAM_INVALID", "REUPLOAD", "The Udyam number on this certificate isn't in the right format.", "udyam")
        return
    record = lookup_udyam(number)
    if record is None:
        run.add("UDYAM_NOT_FOUND", "MANUAL_REVIEW", "This Udyam number isn't in the registry. We'll have someone review it.", "udyam")
        return
    if applicant.udyam_on_file and number != applicant.udyam_on_file:
        run.add("UDYAM_DIFFERS_FROM_APPLICATION", "MANUAL_REVIEW", "The Udyam number on this certificate differs from the one on your application.", "udyam")
    if not _same(fields.get("enterprise_name"), record["enterprise_name"]):
        run.add("UDYAM_NAME_MISMATCH", "MANUAL_REVIEW", f"The name on this Udyam certificate doesn't match the registry, which says \"{record['enterprise_name']}\".", "udyam")
    if not _same(fields.get("state"), record["state"]) or not _same(fields.get("city"), record["city"]):
        run.add("UDYAM_LOCATION_MISMATCH", "MANUAL_REVIEW", "The city or state on this Udyam certificate doesn't match the registry.", "udyam")
    if trade_name and not _same(record["enterprise_name"], trade_name):
        run.add("UDYAM_GST_NAME_MISMATCH", "MANUAL_REVIEW", "The business name on your Udyam registration differs from your GST registration.", "udyam")


def _check_address_proof(run: _Run, fields: dict[str, str] | None, gst_record: dict[str, str] | None) -> None:
    if fields is None:
        return
    bill_date = _parse_date(fields.get("bill_date"))
    if bill_date is None:
        run.add("BILL_DATE_UNREADABLE", "REUPLOAD", "We couldn't read the date on this bill. Please upload a clearer copy.", "address_proof")
    else:
        age = (TODAY - bill_date).days
        if age > ADDRESS_PROOF_MAX_AGE_DAYS:
            run.add("ADDRESS_PROOF_STALE", "REUPLOAD", f"This bill is {age} days old. We need one from the last {ADDRESS_PROOF_MAX_AGE_DAYS} days.", "address_proof", age=str(age), limit=str(ADDRESS_PROOF_MAX_AGE_DAYS))
        elif age < 0:
            run.add("ADDRESS_PROOF_FUTURE_DATED", "MANUAL_REVIEW", "This bill is dated in the future. We'll have someone review it.", "address_proof")
    if gst_record:
        names = (gst_record["trade_name"], gst_record["legal_name"])
        if not any(_same(fields.get("billed_to"), name) for name in names):
            run.add("BILL_NAME_MISMATCH", "MANUAL_REVIEW", "The name on this bill doesn't match your GST registration.", "address_proof")
        if not _same(fields.get("address"), gst_record["principal_place_of_business"]):
            run.add("BILL_ADDRESS_MISMATCH", "MANUAL_REVIEW", "The address on this bill doesn't match your registered GST address.", "address_proof")


def _check_signatory(run: _Run, fields: dict[str, str] | None, gst_record: dict[str, str] | None, applicant: Applicant) -> None:
    if fields is None:
        return
    valid_till = _parse_date(fields.get("valid_till"))
    if valid_till is None:
        run.add("ID_EXPIRY_UNREADABLE", "REUPLOAD", "We couldn't read the expiry date on this ID. Please upload a clearer copy.", "signatory_id")
    elif valid_till < TODAY:
        run.add("ID_EXPIRED", "REUPLOAD", f"This ID expired on {valid_till}. Please upload a valid one.", "signatory_id", date=str(valid_till))

    name = fields.get("name")
    if applicant.contact_name and not _same(name, applicant.contact_name):
        run.add("SIGNATORY_NOT_APPLICANT", "MANUAL_REVIEW", f"The ID is in the name of {name}, but {applicant.contact_name} applied. We need to confirm who is authorised to sign.", "signatory_id", name=name or "", applicant=applicant.contact_name)
    if not gst_record:
        return
    constitution = gst_record["constitution"]
    if constitution == "Proprietorship":
        proprietor = gst_record["legal_name"].split(" (Prop.")[0]
        if not _same(name, proprietor):
            run.add("SIGNATORY_NOT_PROPRIETOR", "MANUAL_REVIEW", f"The ID is in the name of {name}, but the registered proprietor is {proprietor}.", "signatory_id")
    if not any(_same(fields.get("for_business"), n) for n in (gst_record["trade_name"], gst_record["legal_name"])):
        run.add("ID_BUSINESS_MISMATCH", "MANUAL_REVIEW", "The business named on this ID doesn't match your GST registration.", "signatory_id")
    designation = (fields.get("designation") or "").strip().lower()
    roles = SIGNING_ROLES.get(constitution)
    if roles and designation not in roles:
        run.add("SIGNATORY_ROLE_UNUSUAL", "PASS_WITH_WARNING", f"The ID says \"{fields.get('designation')}\". For a {constitution} we usually expect {' or '.join(sorted(roles))}, so we'll confirm this at e-sign.", "signatory_id", role=fields.get("designation") or "")


def _check_documents_agree(run: _Run, bill: dict[str, str] | None, signatory: dict[str, str] | None, gst_record: dict[str, str] | None) -> None:
    """With no GST record to compare against, at least the two documents must name the same business."""
    if gst_record or not bill or not signatory:
        return
    if not _same(bill.get("billed_to"), signatory.get("for_business")):
        run.add("DOCUMENTS_DISAGREE", "MANUAL_REVIEW", "The business named on your bill differs from the one on your ID.", "address_proof")


def validate_application(docs: dict[str, DocumentResult | None], applicant: Applicant) -> KycResult:
    run = _Run([])
    _check_presence(run, docs, applicant)
    gst_record = _check_gst(run, _readable_fields(docs.get("gst"), "gst"), applicant)
    trade_name = gst_record["trade_name"] if gst_record else None
    _check_udyam(run, _readable_fields(docs.get("udyam"), "udyam"), applicant, trade_name)
    _check_address_proof(run, _readable_fields(docs.get("address_proof"), "address_proof"), gst_record)
    _check_signatory(run, _readable_fields(docs.get("signatory_id"), "signatory_id"), gst_record, applicant)
    _check_documents_agree(run, _readable_fields(docs.get("address_proof"), "address_proof"), _readable_fields(docs.get("signatory_id"), "signatory_id"), gst_record)

    verdict = next((v for v in VERDICTS if any(c.outcome == v for c in run.checks)), "PASS")
    verified = {}
    if gst_record and gst_record["status"] == "Active" and verdict in {"PASS", "PASS_WITH_WARNING", "AUTO_RESOLVE"}:
        verified = {
            "gstin": gst_record["gstin"],
            "legal_name": gst_record["legal_name"],
            "constitution": gst_record["constitution"],
            "address": gst_record["principal_place_of_business"],
        }
    return KycResult(verdict=verdict, checks=run.checks, verified_fields=verified)
