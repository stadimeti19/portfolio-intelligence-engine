from __future__ import annotations

from typing import Protocol

from portfolio_intelligence.domain.etfs import EtfHolding, EtfMetadata, SectorWeight


class EtfCompositionProvider(Protocol):
    name: str

    def get_holdings(self, symbol: str) -> list[EtfHolding]: ...

    def get_sector_weights(self, symbol: str) -> list[SectorWeight]: ...

    def get_metadata(self, symbol: str) -> EtfMetadata: ...


class EtfCompositionError(RuntimeError):
    pass


class EtfCompositionNotFoundError(EtfCompositionError):
    pass


class EtfCompositionValidationError(EtfCompositionError, ValueError):
    pass
