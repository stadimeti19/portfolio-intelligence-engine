from __future__ import annotations

from sqlalchemy.orm import Session

from portfolio_intelligence.domain.transactions import Transaction
from portfolio_intelligence.storage.models import StoredTransaction


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def existing_ids(self) -> set[str]:
        return {row[0] for row in self.session.query(StoredTransaction.transaction_id).all()}

    def add_transactions(self, transactions: list[Transaction]) -> None:
        existing = self.existing_ids()
        duplicates = [tx.transaction_id for tx in transactions if tx.transaction_id in existing]
        if duplicates:
            raise ValueError(f"duplicate transaction IDs already imported: {duplicates}")
        for tx in transactions:
            self.session.add(
                StoredTransaction(
                    transaction_id=tx.transaction_id,
                    effective_date=tx.effective_date,
                    transaction_type=tx.transaction_type.value,
                    symbol=tx.symbol,
                    quantity=tx.quantity,
                    price=tx.price,
                    fee=tx.fee,
                    currency=tx.currency,
                    source=tx.source,
                    import_order=tx.import_order,
                )
            )
        self.session.commit()
