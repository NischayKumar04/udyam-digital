"""GSTIN, Udyam and mobile number checks, OCR repair and masking."""
import re
from dataclasses import dataclass, field

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
_MOBILE_RE = re.compile(r"(?:\+?91|0)?([6-9]\d{9})")

# The 4th PAN character is the entity type. 'X' isn't a real type, but the data
# pack's README uses it everywhere and tells us to accept it.
_PAN_ENTITY_TYPES = frozenset("PCHFATBLJGX")

GST_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}

# Characters OCR confuses, by what the position in a GSTIN must hold.
_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "G": "6", "B": "8"})
_TO_LETTER = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"})
_LOOKALIKES = {"0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "S": "5", "8": "B", "B": "8", "2": "Z", "Z": "2", "6": "G", "G": "6"}


def gstin_check_char(first_14: str) -> str:
    total = 0
    for i, ch in enumerate(first_14):
        product = _ALPHABET.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _ALPHABET[(36 - total % 36) % 36]


@dataclass(frozen=True)
class GstinCheck:
    gstin: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    state: str | None = None


def check_gstin(raw: str) -> GstinCheck:
    gstin = re.sub(r"\s", "", raw or "").upper()
    if not _GSTIN_RE.match(gstin):
        return GstinCheck(gstin, False, ["GSTIN must be 15 characters in the pattern 22AAAAA0000A1Z5."])
    errors = []
    state = GST_STATE_CODES.get(gstin[:2])
    if state is None:
        errors.append(f"'{gstin[:2]}' isn't a valid GST state code.")
    if gstin[5] not in _PAN_ENTITY_TYPES:
        errors.append(f"'{gstin[5]}' isn't a valid PAN entity type.")
    if gstin_check_char(gstin[:14]) != gstin[14]:
        errors.append("The last character doesn't match the GSTIN checksum, so a character is wrong or was changed.")
    return GstinCheck(gstin, not errors, errors, state)


def repair_gstin_ocr(text: str) -> str:
    """Fix letter/digit mix-ups OCR makes, using what each position must hold.

    Only swaps lookalike characters, so a digit changed to another digit (a tampered
    number) stays wrong and still fails the checksum. Returns the best guess even
    when it doesn't validate, so the caller can report why.
    """
    s = re.sub(r"[^0-9A-Za-z]", "", text or "").upper()
    if len(s) != 15:
        return s
    coerced = (
        s[:2].translate(_TO_DIGIT) + s[2:7].translate(_TO_LETTER) + s[7:11].translate(_TO_DIGIT)
        + s[11].translate(_TO_LETTER) + s[12] + "Z" + s[14]
    )
    for entity in {coerced[12], _LOOKALIKES.get(coerced[12], coerced[12])}:
        if entity == "0":
            continue
        for check in {coerced[14], _LOOKALIKES.get(coerced[14], coerced[14])}:
            candidate = coerced[:12] + entity + "Z" + check
            if check_gstin(candidate).valid:
                return candidate
    return coerced


def is_valid_udyam_format(raw: str) -> bool:
    return bool(_UDYAM_RE.match((raw or "").strip().upper()))


def mask_gstin(gstin: str) -> str:
    return f"{gstin[:2]}{'*' * (len(gstin) - 5)}{gstin[-3:]}" if len(gstin) > 5 else "*" * len(gstin)


def mask_udyam(udyam: str) -> str:
    return f"{udyam[:12]}***{udyam[-4:]}" if len(udyam) > 16 else "*" * len(udyam)


def mask_name(name: str) -> str:
    return " ".join(f"{word[0]}{'*' * (len(word) - 1)}" for word in name.split())


def normalize_mobile(raw: str) -> str | None:
    """The 10 digits of an Indian mobile number, or None if it isn't one."""
    match = _MOBILE_RE.fullmatch(re.sub(r"[\s-]", "", raw or ""))
    return match.group(1) if match else None


def mask_mobile(mobile: str) -> str:
    return f"{mobile[:2]}{'*' * (len(mobile) - 4)}{mobile[-2:]}"
