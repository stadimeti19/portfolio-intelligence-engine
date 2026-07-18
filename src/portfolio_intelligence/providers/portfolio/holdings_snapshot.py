from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from portfolio_intelligence.domain.transactions import Transaction
from portfolio_intelligence.providers.portfolio.csv_source import CsvValidationError

ALLOWED_HOLDING_FIELDS = {
    "symbol",
    "description",
    "quantity",
    "current_price",
    "market_value",
    "cost_basis_total",
    "average_cost_basis",
    "asset_type",
    "currency",
}

FIDELITY_COLUMN_MAP = {
    "symbol": "symbol",
    "description": "description",
    "quantity": "quantity",
    "lastprice": "current_price",
    "currentvalue": "market_value",
    "costbasistotal": "cost_basis_total",
    "averagecostbasis": "average_cost_basis",
    "type": "asset_type",
}

NORMALIZED_COLUMN_MAP = {
    "symbol": "symbol",
    "description": "description",
    "quantity": "quantity",
    "shares": "quantity",
    "currentprice": "current_price",
    "lastprice": "current_price",
    "marketvalue": "market_value",
    "currentvalue": "market_value",
    "costbasistotal": "cost_basis_total",
    "costbasis": "cost_basis_total",
    "averagecostbasis": "average_cost_basis",
    "averagecost": "average_cost_basis",
    "avgcost": "average_cost_basis",
    "assettype": "asset_type",
    "type": "asset_type",
    "currency": "currency",
}


class HoldingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    quantity: float
    description: str | None = None
    current_price: float | None = None
    market_value: float | None = None
    cost_basis_total: float | None = None
    average_cost_basis: float | None = None
    asset_type: str | None = None
    currency: str = "USD"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value

    @field_validator("current_price", "market_value", "cost_basis_total", "average_cost_basis")
    @classmethod
    def nonnegative_optional(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("holding values must be nonnegative")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper() or "USD"
        if normalized != "USD":
            raise ValueError("only USD holdings are supported")
        return normalized

    @property
    def synthetic_purchase_price(self) -> float:
        if self.average_cost_basis and self.average_cost_basis > 0:
            return self.average_cost_basis
        if self.cost_basis_total and self.cost_basis_total > 0:
            return self.cost_basis_total / self.quantity
        if self.current_price and self.current_price > 0:
            return self.current_price
        if self.market_value and self.market_value > 0:
            return self.market_value / self.quantity
        raise ValueError(f"{self.symbol} needs average cost, cost basis, price, or value")


@dataclass(frozen=True)
class HoldingsImportResult:
    holdings: list[HoldingSnapshot]
    errors: list[CsvValidationError]
    retained_columns: list[str]
    ignored_columns: list[str]
    source_format: str

    @property
    def total_cost_basis(self) -> float:
        return sum(holding.synthetic_purchase_price * holding.quantity for holding in self.holdings)


class HoldingsSnapshotSource:
    def __init__(
        self,
        path: str | Path,
        *,
        source_format: str = "auto",
        snapshot_start: date | None = None,
    ) -> None:
        self.path = Path(path)
        self.source_format = source_format
        self.snapshot_start = snapshot_start or _default_snapshot_start()

    def load_transactions(self) -> list[Transaction]:
        result = load_holdings_snapshot(self.path, source_format=self.source_format)
        if result.errors:
            messages = "; ".join(
                f"line {error.line_number}: {error.message}" for error in result.errors
            )
            raise ValueError(messages)
        return holdings_to_transactions(result.holdings, as_of=self.snapshot_start)


def load_holdings_snapshot(
    path: str | Path, *, source_format: str = "auto"
) -> HoldingsImportResult:
    path = Path(path)
    rows, fieldnames = _read_rows(path)
    normalized_headers = {_normalize_header(name): name for name in fieldnames}
    detected_format = _detect_format(normalized_headers, source_format)
    mapping = FIDELITY_COLUMN_MAP if detected_format == "fidelity" else NORMALIZED_COLUMN_MAP
    retained_original = [
        original for normalized, original in normalized_headers.items() if normalized in mapping
    ]
    ignored_original = [
        original for normalized, original in normalized_headers.items() if normalized not in mapping
    ]
    holdings: list[HoldingSnapshot] = []
    errors: list[CsvValidationError] = []
    for index, row in enumerate(rows, start=2):
        normalized_row = {
            mapping[normalized]: row.get(original)
            for normalized, original in normalized_headers.items()
            if normalized in mapping
        }
        try:
            holding = _holding_from_row(normalized_row)
        except ValueError as exc:
            errors.append(CsvValidationError(index, str(exc)))
        else:
            holdings.append(holding)
    return HoldingsImportResult(
        holdings=holdings,
        errors=errors,
        retained_columns=retained_original,
        ignored_columns=ignored_original,
        source_format=detected_format,
    )


def holdings_to_transactions(holdings: list[HoldingSnapshot], *, as_of: date) -> list[Transaction]:
    total_cost = sum(holding.synthetic_purchase_price * holding.quantity for holding in holdings)
    transactions = [
        Transaction.model_validate(
            {
                "transaction_id": f"snapshot-deposit-{as_of.isoformat()}",
                "effective_date": as_of,
                "type": "DEPOSIT",
                "symbol": None,
                "quantity": 0,
                "price": total_cost,
                "fee": 0,
                "currency": "USD",
                "source": "holdings_snapshot",
                "import_order": 0,
            }
        )
    ]
    for import_order, holding in enumerate(holdings, start=1):
        transactions.append(
            Transaction.model_validate(
                {
                    "transaction_id": f"snapshot-buy-{holding.symbol}-{import_order}",
                    "effective_date": as_of,
                    "type": "BUY",
                    "symbol": holding.symbol,
                    "quantity": holding.quantity,
                    "price": holding.synthetic_purchase_price,
                    "fee": 0,
                    "currency": holding.currency,
                    "source": "holdings_snapshot",
                    "import_order": import_order,
                }
            )
        )
    return transactions


def write_clean_holdings(path: str | Path, holdings: list[HoldingSnapshot]) -> Path:
    output_path = Path(path)
    columns = [
        "symbol",
        "quantity",
        "average_cost_basis",
        "cost_basis_total",
        "current_price",
        "market_value",
        "asset_type",
        "description",
        "currency",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for holding in holdings:
            writer.writerow(
                {
                    "symbol": holding.symbol,
                    "quantity": holding.quantity,
                    "average_cost_basis": holding.average_cost_basis or "",
                    "cost_basis_total": holding.cost_basis_total or "",
                    "current_price": holding.current_price or "",
                    "market_value": holding.market_value or "",
                    "asset_type": holding.asset_type or "",
                    "description": holding.description or "",
                    "currency": holding.currency,
                }
            )
    return output_path


def upsert_clean_holding(path: str | Path, holding: HoldingSnapshot) -> Path:
    output_path = Path(path)
    existing: list[HoldingSnapshot] = []
    if output_path.exists():
        result = load_holdings_snapshot(output_path, source_format="generic")
        if result.errors:
            messages = "; ".join(
                f"line {error.line_number}: {error.message}" for error in result.errors
            )
            raise ValueError(messages)
        existing = result.holdings
    by_symbol = {item.symbol: item for item in existing}
    by_symbol[holding.symbol] = holding
    return write_clean_holdings(output_path, [by_symbol[symbol] for symbol in sorted(by_symbol)])


def parse_pasted_holdings(text: str) -> HoldingsImportResult:
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    if not rows:
        return HoldingsImportResult(
            [], [CsvValidationError(1, "no holdings were pasted")], [], [], "paste"
        )
    delimiter = _detect_paste_delimiter(rows[0])
    header = _split_paste_line(rows[0], delimiter)
    normalized_headers = {_normalize_header(name): name for name in header}
    mapping = NORMALIZED_COLUMN_MAP
    retained_original = [
        original for normalized, original in normalized_headers.items() if normalized in mapping
    ]
    ignored_original = [
        original for normalized, original in normalized_headers.items() if normalized not in mapping
    ]
    holdings: list[HoldingSnapshot] = []
    errors: list[CsvValidationError] = []
    for index, line in enumerate(rows[1:], start=2):
        values = _split_paste_line(line, delimiter)
        raw = dict(zip(header, values, strict=False))
        normalized_row = {
            mapping[normalized]: raw.get(original)
            for normalized, original in normalized_headers.items()
            if normalized in mapping
        }
        try:
            holding = _holding_from_row(normalized_row)
        except ValueError as exc:
            errors.append(CsvValidationError(index, str(exc)))
        else:
            holdings.append(holding)
    return HoldingsImportResult(
        holdings=holdings,
        errors=errors,
        retained_columns=retained_original,
        ignored_columns=ignored_original,
        source_format="paste",
    )


def write_snapshot_transactions(
    path: str | Path, holdings: list[HoldingSnapshot], *, as_of: date
) -> Path:
    output_path = Path(path)
    columns = ["transaction_id", "date", "type", "symbol", "quantity", "price", "fee", "currency"]
    transactions = holdings_to_transactions(holdings, as_of=as_of)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for transaction in transactions:
            writer.writerow(
                {
                    "transaction_id": transaction.transaction_id,
                    "date": transaction.effective_date.isoformat(),
                    "type": transaction.transaction_type.value,
                    "symbol": transaction.symbol or "",
                    "quantity": transaction.quantity,
                    "price": transaction.price,
                    "fee": transaction.fee,
                    "currency": transaction.currency,
                }
            )
    return output_path


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    sample = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(sample[:4096], delimiters=",\t")
    except csv.Error:
        dialect = csv.excel
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError(f"holdings file has no header row: {path}")
        return [dict(row) for row in reader], fieldnames


def _detect_paste_delimiter(header: str) -> str:
    if "\t" in header:
        return "\t"
    if "," in header:
        return ","
    return "whitespace"


def _split_paste_line(line: str, delimiter: str) -> list[str]:
    if delimiter == "whitespace":
        return re.split(r"\s{2,}", line.strip())
    return [value.strip() for value in line.split(delimiter)]


def _detect_format(headers: dict[str, str], requested: str) -> str:
    normalized = requested.lower()
    if normalized != "auto":
        if normalized not in {"fidelity", "generic"}:
            raise ValueError(f"unsupported holdings format: {requested}")
        return normalized
    fidelity_markers = {"accountname", "lastprice", "currentvalue", "averagecostbasis"}
    if len(fidelity_markers & set(headers)) >= 2:
        return "fidelity"
    return "generic"


def _holding_from_row(row: dict[str, Any]) -> HoldingSnapshot:
    symbol = str(row.get("symbol") or "").strip()
    quantity = _parse_number(row.get("quantity"))
    average_cost = _parse_optional_number(row.get("average_cost_basis"))
    cost_basis_total = _parse_optional_number(row.get("cost_basis_total"))
    current_price = _parse_optional_number(row.get("current_price"))
    market_value = _parse_optional_number(row.get("market_value"))
    if average_cost is None and cost_basis_total is not None and quantity > 0:
        average_cost = cost_basis_total / quantity
    if cost_basis_total is None and average_cost is not None:
        cost_basis_total = average_cost * quantity
    holding = HoldingSnapshot(
        symbol=symbol,
        quantity=quantity,
        description=_optional_text(row.get("description")),
        current_price=current_price,
        market_value=market_value,
        cost_basis_total=cost_basis_total,
        average_cost_basis=average_cost,
        asset_type=_optional_text(row.get("asset_type")),
        currency=str(row.get("currency") or "USD"),
    )
    _ = holding.synthetic_purchase_price
    return holding


def _parse_number(value: Any) -> float:
    parsed = _parse_optional_number(value)
    if parsed is None:
        raise ValueError("numeric value is required")
    return parsed


def _parse_optional_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"--", "n/a", "N/A"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[$,%]", "", text).replace(",", "").replace("(", "").replace(")", "")
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid numeric value: {text}") from exc
    return -parsed if negative else parsed


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _default_snapshot_start() -> date:
    return date.today() - timedelta(days=365)
