from __future__ import annotations

from collections import defaultdict

from portfolio_intelligence.domain.etfs import (
    AllocationType,
    DataQualityStatus,
    EtfHolding,
    SectorWeight,
)
from portfolio_intelligence.providers.etf.base import EtfCompositionValidationError


def normalize_holdings(
    holdings: list[EtfHolding],
    *,
    duplicate_policy: str = "combine",
    weight_tolerance: float = 0.01,
    represent_remainder: bool = True,
) -> list[EtfHolding]:
    if duplicate_policy not in {"combine", "reject"}:
        raise ValueError("duplicate_policy must be 'combine' or 'reject'")
    combined: dict[tuple[str, AllocationType], EtfHolding] = {}
    duplicates: set[str] = set()
    for holding in holdings:
        key = (holding.constituent_symbol, holding.allocation_type)
        if key in combined:
            duplicates.add(holding.constituent_symbol)
            if duplicate_policy == "reject":
                continue
            prior = combined[key]
            sector = prior.sector or holding.sector
            if prior.sector and holding.sector and prior.sector != holding.sector:
                sector = None
            combined[key] = prior.model_copy(
                update={"weight": prior.weight + holding.weight, "sector": sector}
            )
        else:
            combined[key] = holding
    if duplicates and duplicate_policy == "reject":
        names = ", ".join(sorted(duplicates))
        raise EtfCompositionValidationError(f"duplicate ETF constituents: {names}")
    result = list(combined.values())
    total = sum(item.weight for item in result)
    if total > 1.0 + weight_tolerance:
        raise EtfCompositionValidationError(
            f"ETF constituent weights total {total:.2%}, above the allowed "
            f"{1.0 + weight_tolerance:.2%}"
        )
    if total > 1.0:
        result = [item.model_copy(update={"weight": item.weight / total}) for item in result]
        total = 1.0
    if represent_remainder and total < 1.0 - 1e-9 and result:
        first = result[0]
        result.append(
            EtfHolding(
                fund_symbol=first.fund_symbol,
                constituent_symbol="OTHER",
                name="Unreported / other allocation",
                weight=1.0 - total,
                sector="Unknown",
                allocation_type=AllocationType.OTHER,
                as_of_date=first.as_of_date,
                provider=first.provider,
                retrieval_time=first.retrieval_time,
                data_quality=DataQualityStatus.INCOMPLETE,
            )
        )
    return sorted(result, key=lambda item: (-item.weight, item.constituent_symbol))


def normalize_sector_weights(
    weights: list[SectorWeight], *, weight_tolerance: float = 0.01
) -> list[SectorWeight]:
    if not weights:
        return []
    combined: dict[str, float] = defaultdict(float)
    exemplar: dict[str, SectorWeight] = {}
    for item in weights:
        sector = item.sector.strip() or "Unknown"
        combined[sector] += item.weight
        exemplar[sector] = item
    total = sum(combined.values())
    if total > 1.0 + weight_tolerance:
        raise EtfCompositionValidationError(
            f"ETF sector weights total {total:.2%}, above the allowed {1.0 + weight_tolerance:.2%}"
        )
    divisor = total if total > 1.0 else 1.0
    output = [
        exemplar[name].model_copy(update={"sector": name, "weight": value / divisor})
        for name, value in combined.items()
    ]
    if total < 1.0 - 1e-9:
        first = weights[0]
        output.append(
            first.model_copy(
                update={
                    "sector": "Unknown",
                    "weight": 1.0 - total,
                    "data_quality": DataQualityStatus.INCOMPLETE,
                }
            )
        )
    return sorted(output, key=lambda item: (-item.weight, item.sector))
