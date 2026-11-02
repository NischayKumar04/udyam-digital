"""Turns a bundle into one transparent monthly price.

The catalogue gives each product a price range. We start at the top of the range and
step down a quarter of the range for each of these, never going below the bottom:
  - a 12-month contract (two steps for 24 months)
  - an add-on bought with an Accel connection
  - a micro business

Each product's price doesn't depend on which other add-ons are selected, so switching
one on always adds exactly its own price to the bill.
"""
from pydantic import BaseModel, Field

from .catalogue import Product, load_catalogue
from .config import GST_RATE
from .product_text import describe
from .rules import BusinessFacts, bundle_violations


class LineItem(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1)


class QuoteLine(BaseModel):
    product_id: str
    name: str
    description: str
    unit: str
    quantity: int
    unit_price: int
    list_unit_price: int
    monthly: int
    setup_total: int
    install_days: int


class ContractOption(BaseModel):
    months: int
    monthly_subtotal: int


class ViolationOut(BaseModel):
    product_id: str
    code: str
    message: str


class Quote(BaseModel):
    lines: list[QuoteLine]
    monthly_subtotal: int
    list_monthly_subtotal: int
    monthly_saving: int
    gst_rate: float
    monthly_gst: int
    monthly_total: int
    one_time_setup: int
    one_time_gst: int
    one_time_total: int
    pay_now: int
    contract_months: int
    contract_options: list[ContractOption]
    expected_activation_days: int
    valid: bool
    violations: list[ViolationOut]


def price_position(product: Product, contract_months: int, has_connection: bool, segment: str | None) -> float:
    """Where the price sits in the product's range: 1.0 is the top, 0.0 the bottom."""
    steps = 0
    if contract_months >= 24:
        steps += 2
    elif contract_months >= 12:
        steps += 1
    if has_connection and not product.is_connection:
        steps += 1
    if segment == "micro":
        steps += 1
    return max(0.0, 1.0 - 0.25 * steps)


def unit_price(product: Product, position: float) -> int:
    return int(product.price_min + (product.price_max - product.price_min) * position + 0.5)


def _monthly_subtotal(items: dict[str, int], contract_months: int, segment: str | None) -> int:
    catalogue = load_catalogue()
    has_connection = any(catalogue[p].is_connection for p in items)
    return sum(
        unit_price(catalogue[p], price_position(catalogue[p], contract_months, has_connection, segment)) * qty
        for p, qty in items.items()
    )


def build_quote(
    lines: list[LineItem],
    facts: BusinessFacts,
    segment: str | None = None,
    contract_months: int | None = None,
    language: str = "English",
) -> Quote:
    catalogue = load_catalogue()
    unknown = sorted({line.product_id for line in lines} - catalogue.keys())
    if unknown:
        raise ValueError(f"Not in the catalogue: {', '.join(unknown)}")

    items: dict[str, int] = {}
    for line in lines:
        items[line.product_id] = items.get(line.product_id, 0) + line.quantity

    required = max((catalogue[p].min_contract_months for p in items), default=1)
    contract = max(contract_months or required, required)
    has_connection = any(catalogue[p].is_connection for p in items)

    quote_lines = []
    for product_id in sorted(items):
        product, quantity = catalogue[product_id], items[product_id]
        price = unit_price(product, price_position(product, contract, has_connection, segment))
        quote_lines.append(QuoteLine(
            product_id=product_id,
            name=product.name,
            description=product.description,
            unit=product.unit,
            quantity=quantity,
            unit_price=price,
            list_unit_price=product.price_max,
            monthly=price * quantity,
            setup_total=product.setup_fee * quantity,
            install_days=product.install_days,
        ))

    subtotal = sum(line.monthly for line in quote_lines)
    list_subtotal = sum(line.list_unit_price * line.quantity for line in quote_lines)
    setup = sum(line.setup_total for line in quote_lines)
    monthly_gst = round(subtotal * GST_RATE)
    setup_gst = round(setup * GST_RATE)
    violations = bundle_violations(set(items), facts)

    return Quote(
        lines=quote_lines,
        monthly_subtotal=subtotal,
        list_monthly_subtotal=list_subtotal,
        monthly_saving=list_subtotal - subtotal,
        gst_rate=GST_RATE,
        monthly_gst=monthly_gst,
        monthly_total=subtotal + monthly_gst,
        one_time_setup=setup,
        one_time_gst=setup_gst,
        one_time_total=setup + setup_gst,
        pay_now=setup + setup_gst + subtotal + monthly_gst,
        contract_months=contract,
        contract_options=[
            ContractOption(months=m, monthly_subtotal=_monthly_subtotal(items, m, segment))
            for m in sorted({required, 12, 24})
            if m >= required
        ],
        expected_activation_days=max((line.install_days for line in quote_lines), default=0),
        valid=not violations,
        violations=[ViolationOut(product_id=v.product_id, code=v.code.value, message=describe(v, language)) for v in violations],
    )
