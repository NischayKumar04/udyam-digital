import csv

import pytest

from app.config import GSTIN_REGISTRY_CSV, UDYAM_REGISTRY_CSV
from app.identifiers import (
    check_gstin,
    gstin_check_char,
    is_valid_udyam_format,
    mask_gstin,
    mask_name,
    mask_udyam,
    repair_gstin_ocr,
)
from app.registry import lookup_gstin, lookup_udyam


def test_every_registry_gstin_passes_format_state_and_checksum():
    with GSTIN_REGISTRY_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3534
    bad = [r["gstin"] for r in rows if not check_gstin(r["gstin"]).valid]
    assert bad == []
    # The state code embedded in the GSTIN agrees with the registry's state.
    assert all(check_gstin(r["gstin"]).state == r["state"] for r in rows)


def test_every_registry_udyam_number_passes_format():
    with UDYAM_REGISTRY_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2723
    assert all(is_valid_udyam_format(r["udyam_number"]) for r in rows)


def test_k06_altered_gstin_fails_checksum_and_misses_registry():
    result = check_gstin("08YKZXS8189L1ZO")
    assert not result.valid
    assert "checksum" in result.errors[0]
    assert lookup_gstin("08YKZXS8189L1ZO") is None
    assert check_gstin("08YKZXS5189L1ZO").valid  # the number the registry and the lead hold


def test_k01_gstin_is_valid_but_cancelled():
    assert check_gstin("37IHKXV5167L1ZS").valid
    assert lookup_gstin("37IHKXV5167L1ZS")["status"] == "Cancelled"


def test_k05_udyam_is_found_from_the_lead_record():
    record = lookup_udyam("UDYAM-KL-00-5521886")
    assert record["enterprise_name"] == "Balaji Realty LLP"
    assert record["city"] == "Kochi"


@pytest.mark.parametrize("raw, reason", [
    ("", "pattern"),
    ("27PZSXS1936O1Z", "pattern"),  # 14 characters
    ("27PZSXS1936O1AH", "pattern"),  # 14th character must be Z
    ("99PZSXS1936O1ZH", "state code"),
    ("27PZSQS1936O1ZH", "entity type"),  # Q isn't a PAN entity type
])
def test_bad_gstins_explain_why(raw, reason):
    result = check_gstin(raw)
    assert not result.valid
    assert reason in " ".join(result.errors)


def test_lowercase_and_spaces_are_tolerated():
    assert check_gstin(" 27pzsxs1936o1zh ").gstin == "27PZSXS1936O1ZH"
    assert check_gstin(" 27pzsxs1936o1zh ").valid


@pytest.mark.parametrize("ocr_text, expected", [
    ("27PZSX51936O1ZH", "27PZSXS1936O1ZH"),  # S read as 5 in a letter position
    ("27PZSXS19360 1ZH", "27PZSXS1936O1ZH"),  # O read as 0 in the PAN's final letter
    ("2TPZSXS1936O1ZH".replace("T", "7"), "27PZSXS1936O1ZH"),
    ("19E0GXH4115Y1ZL", "19EOGXH4115Y1ZL"),  # K02, where O and 0 look alike
    ("08YKZXS5189L1Z0", "08YKZXS5189L1ZO"),  # check character 0 vs O, settled by the checksum
    ("27PZSXS1936O1ZH", "27PZSXS1936O1ZH"),  # already right
])
def test_ocr_repair_fixes_lookalike_characters(ocr_text, expected):
    assert repair_gstin_ocr(ocr_text) == expected


@pytest.mark.parametrize("ocr_text", ["08YKZXS8189L1ZO", "08YKZXS8189L1Z0"])
def test_ocr_repair_cannot_hide_a_changed_digit(ocr_text):
    assert not check_gstin(repair_gstin_ocr(ocr_text)).valid


def test_check_char_matches_a_known_good_gstin():
    assert gstin_check_char("27PZSXS1936O1Z") == "H"


def test_masks_hide_the_middle_of_identifiers():
    assert mask_gstin("27PZSXS1936O1ZH") == "27**********1ZH"
    assert mask_udyam("UDYAM-MH-00-6131836") == "UDYAM-MH-00-***1836"
    assert mask_name("Neha Kaur") == "N*** K***"
