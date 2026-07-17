from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from portfolio_intelligence.domain.transactions import Transaction


@dataclass(frozen=True)
class CsvValidationError:
    line_number: int
    message: str


class CsvPortfolioSource:
    required_columns = {
        "transaction_id",
        "date",
        "type",
        "symbol",
        "quantity",
        "price",
        "fee",
        "currency",
    }

    def __init__(self, path: str | Path, source_name: str = "csv") -> None:
        self.path = Path(path)
        self.source_name = source_name
        self.errors: list[CsvValidationError] = []

    def load_transactions(self) -> list[Transaction]:
        transactions, errors = self.parse()
        if errors:
            messages = "; ".join(f"line {e.line_number}: {e.message}" for e in errors)
            raise ValueError(messages)
        return transactions

    def parse(self) -> tuple[list[Transaction], list[CsvValidationError]]:
        self.errors = []
        transactions: list[Transaction] = []
        seen_ids: set[str] = set()
        with self.path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = self.required_columns - set(reader.fieldnames or [])
            if missing:
                return [], [CsvValidationError(1, f"missing required columns: {sorted(missing)}")]
            for import_order, row in enumerate(reader, start=1):
                line_number = import_order + 1
                transaction_id = (row.get("transaction_id") or "").strip()
                if transaction_id in seen_ids:
                    self.errors.append(CsvValidationError(line_number, "duplicate transaction_id"))
                    continue
                seen_ids.add(transaction_id)
                try:
                    transaction = Transaction.model_validate(
                        {
                            "transaction_id": transaction_id,
                            "effective_date": row.get("date"),
                            "type": (row.get("type") or "").strip().upper(),
                            "symbol": (row.get("symbol") or "").strip() or None,
                            "quantity": float(row.get("quantity") or 0),
                            "price": float(row.get("price") or 0),
                            "fee": float(row.get("fee") or 0),
                            "currency": (row.get("currency") or "USD").strip().upper(),
                            "source": self.source_name,
                            "import_order": import_order,
                        }
                    )
                except (ValueError, ValidationError) as exc:
                    self.errors.append(CsvValidationError(line_number, str(exc)))
                else:
                    transactions.append(transaction)
        transactions.sort(key=lambda tx: (tx.effective_date, tx.import_order, tx.transaction_id))
        return transactions, self.errors
