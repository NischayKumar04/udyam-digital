"""Reads KYC documents locally: quality check, OCR, then field extraction.

Everything runs on this machine. No image goes to an AI provider or gets written to
disk, which keeps personal data out of free-tier APIs that may use it for training.
"""
import math
import re
import statistics
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from .identifiers import repair_gstin_ocr

# Variance of the Laplacian: clean scans score about 1,000, the blurred K04 about 1.
BLUR_THRESHOLD = 100.0
# OCR is fast enough at this size and still reads the smallest text on the page.
MAX_OCR_SIDE = 1400

DOCUMENT_TITLES = {
    "gst": ("gst", "registration"),
    "udyam": ("udyam", "registration"),
    "signatory_id": ("signatory",),
    "address_proof": ("bill",),
}

TABLE_LABELS = {
    "gst": {
        "gstin": ["GSTIN"],
        "legal_name": ["Legal name"],
        "trade_name": ["Trade name"],
        "constitution": ["Constitution"],
        "address": ["Address of principal", "place of business"],
        "date_of_liability": ["Date of liability"],
        "registration_type": ["Type of registration"],
    },
    "udyam": {
        "udyam_number": ["Udyam reg. number"],
        "enterprise_name": ["Enterprise name"],
        "major_activity": ["Major activity"],
        "city": ["City"],
        "state": ["State"],
        "date_of_registration": ["Date of registration"],
    },
    "address_proof": {
        "consumer_no": ["Consumer no."],
        "billed_to": ["Billed to"],
        "address": ["Supply address"],
        "bill_date": ["Bill date"],
        "units_consumed": ["Units consumed"],
        "amount_due": ["Amount due (INR)"],
    },
}

STACKED_LABELS = {
    "signatory_id": {
        "name": "Name",
        "designation": "Designation",
        "for_business": "For business",
        "id_no": "ID no.",
        "valid_till": "Valid till",
    },
}


_KNOWN_DESIGNATIONS = {"officeadmin": "Office admin", "designatedpartner": "Designated partner", "managingdirector": "Managing director"}


@dataclass
class OcrLine:
    text: str
    x: float
    y: float
    confidence: float


@dataclass
class DocumentResult:
    slot: str
    readable: bool
    blur_score: float
    detected_type: str | None = None
    fields: dict[str, str] = field(default_factory=dict)


@lru_cache(maxsize=1)
def _engine() -> RapidOCR:
    return RapidOCR()


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _is_label(text: str, label: str) -> bool:
    return SequenceMatcher(None, _alnum(text), _alnum(label)).ratio() >= 0.8


def decode_image(data: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None


def blur_score(image: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def read_lines(image: np.ndarray) -> list[OcrLine]:
    """OCR the page and return lines with their positions, with any tilt removed."""
    # The watermark is pink, which is almost white in the red channel. Black text stays black.
    red = image[:, :, 2]
    scale = min(1.0, MAX_OCR_SIDE / max(red.shape))
    if scale < 1.0:
        red = cv2.resize(red, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    result, _ = _engine()(cv2.cvtColor(red, cv2.COLOR_GRAY2BGR))
    if not result:
        return []

    # A tilted scan still reads fine, but its rows stop lining up. Measure the tilt from
    # the long text boxes and undo it on the coordinates, so labels meet their values.
    angles = [
        math.atan2(box[1][1] - box[0][1], box[1][0] - box[0][0])
        for box, _, _ in result
        if box[1][0] - box[0][0] > 100
    ]
    angle = statistics.median(angles) if angles else 0.0
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)
    lines = [
        OcrLine(text, (box[0][0] * cos_a - box[0][1] * sin_a) / scale, (box[0][0] * sin_a + box[0][1] * cos_a) / scale, float(conf))
        for box, text, conf in result
    ]
    return sorted(lines, key=lambda line: line.y)


def detect_type(lines: list[OcrLine]) -> str | None:
    title = " ".join(line.text.lower() for line in lines[:3])
    for doc_type, words in DOCUMENT_TITLES.items():
        if all(word in title for word in words):
            return doc_type
    return None


def _extract_table(lines: list[OcrLine], labels: dict[str, list[str]]) -> dict[str, str]:
    """Certificates and bills: a label on the left, its value on the same row to the right."""
    label_rows: list[tuple[float, str]] = []
    label_lines = set()
    for line in lines:
        for field_name, options in labels.items():
            if any(_is_label(line.text, option) for option in options):
                label_rows.append((line.y, field_name))
                label_lines.add(id(line))
                break
    if not label_rows:
        return {}

    label_right_edge = 450  # labels end before this x on the page
    row_gap = 70
    parts: dict[str, list[str]] = {}
    for line in lines:
        if id(line) in label_lines or line.x < label_right_edge:
            continue
        same_row = [row for row in label_rows if abs(row[0] - line.y) <= row_gap / 2]
        # A wrapped second line has no label on its own row, so it belongs to the label above it.
        above = [row for row in label_rows if 0 < line.y - row[0] <= row_gap * 1.5]
        if same_row:
            parts.setdefault(min(same_row, key=lambda row: abs(row[0] - line.y))[1], []).append(line.text)
        elif above:
            parts.setdefault(max(above, key=lambda row: row[0])[1], []).append(line.text)
    return {name: "".join(values).strip() for name, values in parts.items()}


def _extract_stacked(lines: list[OcrLine], labels: dict[str, str]) -> dict[str, str]:
    """ID cards: each label sits directly above its value."""
    fields = {}
    for i, line in enumerate(lines):
        for field_name, label in labels.items():
            if field_name not in fields and _is_label(line.text, label) and i + 1 < len(lines):
                fields[field_name] = lines[i + 1].text.strip()
                break
    return fields


def _tidy(fields: dict[str, str]) -> dict[str, str]:
    if "gstin" in fields:
        fields["gstin"] = repair_gstin_ocr(fields["gstin"])
    if "udyam_number" in fields:
        fields["udyam_number"] = re.sub(r"\s", "", fields["udyam_number"]).upper()
    if "address" in fields:
        fields["address"] = re.sub(r"\s*-\s*(\d{6})$", r" - \1", fields["address"])
    # OCR often drops the space between words on a short line.
    for name_field in ("name", "legal_name", "trade_name", "enterprise_name", "billed_to", "for_business"):
        if name_field in fields:
            fields[name_field] = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fields[name_field])
    if "designation" in fields:
        fields["designation"] = _KNOWN_DESIGNATIONS.get(_alnum(fields["designation"]), fields["designation"])
    return fields


def read_document(slot: str, data: bytes) -> DocumentResult:
    image = decode_image(data)
    if image is None:
        return DocumentResult(slot, readable=False, blur_score=0.0)
    score = blur_score(image)
    if score < BLUR_THRESHOLD:
        return DocumentResult(slot, readable=False, blur_score=score)

    lines = read_lines(image)
    detected = detect_type(lines)
    doc_type = detected or slot
    if doc_type in TABLE_LABELS:
        fields = _extract_table(lines, TABLE_LABELS[doc_type])
    else:
        fields = _extract_stacked(lines, STACKED_LABELS.get(doc_type, {}))
    return DocumentResult(slot, readable=bool(fields), blur_score=score, detected_type=detected, fields=_tidy(fields))
