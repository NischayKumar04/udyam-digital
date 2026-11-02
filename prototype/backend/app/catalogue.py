"""Loads product_catalogue.csv into typed products."""
import csv
from dataclasses import dataclass
from functools import lru_cache

from .config import CATALOGUE_CSV

CONNECTION_PRODUCTS = frozenset({"P01", "P02", "P03", "P04", "P05", "P06"})


@dataclass(frozen=True)
class Product:
    id: str
    category: str
    name: str
    description: str
    unit: str
    price_min: int
    price_max: int
    setup_fee: int
    min_contract_months: int
    city_tiers: frozenset[int]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: frozenset[str]
    install_days: int
    target_segments: frozenset[str]

    @property
    def is_connection(self) -> bool:
        return self.id in CONNECTION_PRODUCTS


def _parse(row: dict[str, str]) -> Product:
    return Product(
        id=row["product_id"],
        category=row["category"],
        name=row["product_name"],
        description=row["description"],
        unit=row["unit"],
        price_min=int(row["price_min_inr_per_month"]),
        price_max=int(row["price_max_inr_per_month"]),
        setup_fee=int(row["one_time_setup_inr"]),
        min_contract_months=int(row["min_contract_months"]),
        city_tiers=frozenset(int(t) for t in row["available_city_tiers"].split(";")),
        min_employees=int(row["min_employees"]),
        min_sites=int(row["min_sites"]),
        requires_gstin=row["requires_gstin"] == "Y",
        requires_one_of=frozenset(row["requires_one_of"].split("|")) if row["requires_one_of"] else frozenset(),
        install_days=int(row["typical_install_days"]),
        target_segments=frozenset(row["target_segments"].split(";")),
    )


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Product]:
    with CATALOGUE_CSV.open(encoding="utf-8", newline="") as f:
        return {row["product_id"]: _parse(row) for row in csv.DictReader(f)}
