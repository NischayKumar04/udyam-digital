"""Mock GSTIN and Udyam registries, backed by the data pack's CSVs.

Lookups are by exact identifier only. Business names repeat across the data (several
unrelated "Star Electronics" exist), so nothing here searches by name.
"""
import csv
from functools import lru_cache
from pathlib import Path

from .config import GSTIN_REGISTRY_CSV, UDYAM_REGISTRY_CSV


def _load(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {row[key]: row for row in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _gstin_table() -> dict[str, dict[str, str]]:
    return _load(GSTIN_REGISTRY_CSV, "gstin")


@lru_cache(maxsize=1)
def _udyam_table() -> dict[str, dict[str, str]]:
    return _load(UDYAM_REGISTRY_CSV, "udyam_number")


def lookup_gstin(gstin: str) -> dict[str, str] | None:
    return _gstin_table().get(gstin)


def lookup_udyam(udyam_number: str) -> dict[str, str] | None:
    return _udyam_table().get(udyam_number)
