"""Runs real OCR on every specimen document and checks each applicant's verdict."""
import csv
import json
import re
from difflib import SequenceMatcher
from functools import lru_cache

import pytest

from app.config import KYC_DOCS_DIR, LEADS_CSV, REPO_ROOT, TODAY
from app.kyc_checks import Applicant, validate_application
from app.kyc_ocr import blur_score, decode_image, read_document

FIXTURE = json.loads((REPO_ROOT / "analysis" / "kyc_expected_results.json").read_text(encoding="utf-8"))["applicants"]
SLOT_FILES = {"gst": "gst_certificate", "udyam": "udyam_certificate", "signatory_id": "signatory_id", "address_proof": "address_proof"}
FIELDS_TO_COMPARE = {
    "gst": ("gst_certificate", ["legal_name", "trade_name", "address", "date_of_liability"]),
    "udyam": ("udyam_certificate", ["udyam_number", "enterprise_name", "city", "state"]),
    "signatory_id": ("signatory_id", ["name", "designation", "id_no", "valid_till"]),
    "address_proof": ("address_proof", ["billed_to", "bill_date"]),
}
with LEADS_CSV.open(encoding="utf-8", newline="") as f:
    LEADS = {row["lead_id"]: row for row in csv.DictReader(f)}


@lru_cache(maxsize=None)
def documents(applicant_id: str):
    docs = {}
    for slot, suffix in SLOT_FILES.items():
        path = KYC_DOCS_DIR / f"{applicant_id}_{suffix}.png"
        docs[slot] = read_document(slot, path.read_bytes()) if path.exists() else None
    return docs


def applicant_for(entry) -> Applicant:
    lead = LEADS[entry["lead_id"]]
    return Applicant(contact_name=lead["contact_name"], gstin_on_file=lead["gstin"] or None, udyam_on_file=lead["udyam_number"] or None)


def result_for(entry):
    return validate_application(documents(entry["id"]), applicant_for(entry))


def codes(entry) -> set[str]:
    return {check.code for check in result_for(entry).checks}


def entry(applicant_id: str):
    return next(a for a in FIXTURE if a["id"] == applicant_id)


def norm(text) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


@pytest.mark.slow
@pytest.mark.parametrize("applicant", FIXTURE, ids=lambda a: a["id"])
def test_verdict_matches_expected(applicant):
    result = result_for(applicant)
    assert result.verdict == applicant["expected_verdict"], result.checks


@pytest.mark.slow
@pytest.mark.parametrize("applicant_id, code", [
    ("K01", "GSTIN_INACTIVE"),
    ("K01", "UDYAM_NUMBER_BLANK"),
    ("K04", "DOCUMENT_UNREADABLE"),
    ("K05", "UDYAM_FROM_REGISTRY"),
    ("K06", "GSTIN_INVALID"),
    ("K07", "LEGAL_NAME_MISMATCH"),
    ("K10", "SIGNATORY_NOT_APPLICANT"),
    ("K11", "ADDRESS_PROOF_STALE"),
])
def test_each_planted_problem_is_caught_for_the_right_reason(applicant_id, code):
    assert code in codes(entry(applicant_id))


@pytest.mark.slow
@pytest.mark.parametrize("applicant_id", ["K03", "K12"])
def test_clean_applicants_raise_nothing(applicant_id):
    assert result_for(entry(applicant_id)).checks == []


@pytest.mark.slow
@pytest.mark.parametrize("applicant", FIXTURE, ids=lambda a: a["id"])
def test_ocr_reads_each_field_correctly(applicant):
    """Identifiers and dates must be exact; free text may have small OCR slips."""
    docs = documents(applicant["id"])
    exact = {"udyam_number", "id_no", "valid_till", "bill_date", "date_of_liability"}
    for slot, (section, field_names) in FIELDS_TO_COMPARE.items():
        doc, expected = docs.get(slot), applicant.get(section)
        if doc is None or expected is None or not doc.readable:
            continue
        for name in field_names:
            got, want = norm(doc.fields.get(name)), norm(expected.get(name))
            detail = (slot, name, doc.fields.get(name), expected.get(name))
            if name in exact:
                assert got == want, detail
            else:
                assert SequenceMatcher(None, got, want).ratio() >= 0.92, detail


@pytest.mark.slow
def test_rotated_scan_still_gives_the_exact_gstin():
    assert documents("K02")["gst"].fields["gstin"] == "19EOGXH4115Y1ZL"


@pytest.mark.slow
def test_wrong_document_in_a_slot_is_caught():
    bill = (KYC_DOCS_DIR / "K03_address_proof.png").read_bytes()
    docs = dict(documents("K03"))
    docs["gst"] = read_document("gst", bill)
    result = validate_application(docs, applicant_for(entry("K03")))
    assert "WRONG_DOCUMENT" in {c.code for c in result.checks}
    assert result.verdict == "REUPLOAD"


def test_blur_score_separates_the_blurred_scan_from_the_rest():
    blurred = blur_score(decode_image((KYC_DOCS_DIR / "K04_gst_certificate.png").read_bytes()))
    clean = blur_score(decode_image((KYC_DOCS_DIR / "K03_gst_certificate.png").read_bytes()))
    assert blurred < 100 < clean


def test_garbage_upload_is_unreadable_not_a_crash():
    assert not read_document("gst", b"this is not an image").readable


def test_lookup_only_journey_needs_just_the_signatory_id():
    """An active GSTIN with installation at the registered address needs no other uploads."""
    docs = {"gst": None, "udyam": None, "signatory_id": None, "address_proof": None}
    result = validate_application(docs, Applicant(
        gstin_on_file="27XUIXG0767D1ZP", udyam_on_file="UDYAM-MH-00-9516696", install_address_same_as_gst=True,
    ))
    by_code = {c.code: c for c in result.checks}
    assert {"GST_FROM_REGISTRY", "UDYAM_FROM_REGISTRY", "ADDRESS_FROM_GST"} <= set(by_code)
    assert by_code["DOCUMENT_MISSING"].document == "signatory_id"
    assert result.verdict == "REUPLOAD"


def test_a_cancelled_gstin_is_rejected_even_without_a_certificate():
    docs = {"gst": None, "udyam": None, "signatory_id": None, "address_proof": None}
    result = validate_application(docs, Applicant(gstin_on_file="37IHKXV5167L1ZS"))
    assert "GSTIN_INACTIVE" in {c.code for c in result.checks}
    assert result.verdict == "REJECT"


def test_today_is_fixed_by_the_data_pack():
    assert TODAY.isoformat() == "2026-07-15"


def test_no_gst_path_asks_only_for_id_and_address_proof():
    docs = {"gst": None, "udyam": None, "signatory_id": None, "address_proof": None}
    result = validate_application(docs, Applicant(no_gst_path=True))
    by_document = {c.document: c.code for c in result.checks}
    assert by_document["gst"] == "GST_NOT_NEEDED"
    assert by_document["udyam"] == "UDYAM_NOT_PROVIDED"
    assert by_document["signatory_id"] == "DOCUMENT_MISSING"
    assert by_document["address_proof"] == "DOCUMENT_MISSING"


def test_a_cancelled_gstin_is_never_treated_as_the_no_gst_path():
    result = validate_application({"gst": None}, Applicant(gstin_on_file="37IHKXV5167L1ZS", no_gst_path=True))
    codes_found = {c.code for c in result.checks}
    assert "GSTIN_INACTIVE" in codes_found
    assert "GST_NOT_NEEDED" not in codes_found


@pytest.mark.slow
def test_no_gst_path_passes_on_id_and_bill_alone():
    full = documents("K03")
    docs = {"gst": None, "udyam": None, "signatory_id": full["signatory_id"], "address_proof": full["address_proof"]}
    result = validate_application(docs, Applicant(contact_name="Joseph Singh", no_gst_path=True))
    assert result.verdict == "PASS_WITH_WARNING"  # only the note that no Udyam was provided


@pytest.mark.slow
def test_no_gst_path_still_catches_documents_that_disagree():
    docs = {"gst": None, "udyam": None, "signatory_id": documents("K03")["signatory_id"], "address_proof": documents("K12")["address_proof"]}
    result = validate_application(docs, Applicant(no_gst_path=True))
    assert "DOCUMENTS_DISAGREE" in {c.code for c in result.checks}
