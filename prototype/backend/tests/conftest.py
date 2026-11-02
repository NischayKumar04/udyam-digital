import csv
from functools import lru_cache

from app.config import LEADS_CSV


@lru_cache(maxsize=1)
def _leads() -> tuple[dict[str, str], ...]:
    with LEADS_CSV.open(encoding="utf-8", newline="") as f:
        return tuple(csv.DictReader(f))


def all_leads() -> tuple[dict[str, str], ...]:
    return _leads()


def activated_leads() -> list[dict[str, str]]:
    return [lead for lead in _leads() if lead["outcome"] == "Activated"]
