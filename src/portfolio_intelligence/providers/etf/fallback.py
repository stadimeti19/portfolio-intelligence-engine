from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from portfolio_intelligence.domain.etfs import EtfHolding, EtfMetadata, SectorWeight
from portfolio_intelligence.providers.etf.base import EtfCompositionProvider

T = TypeVar("T")


class FallbackEtfCompositionProvider:
    def __init__(
        self, primary: EtfCompositionProvider, fallback: EtfCompositionProvider | None
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name if fallback is None else f"{primary.name}+{fallback.name}"
        self.last_provider: str | None = None
        self.last_error: Exception | None = None
        self._fallback_symbols: set[str] = set()

    def get_holdings(self, symbol: str) -> list[EtfHolding]:
        return self._call(symbol, lambda provider: provider.get_holdings(symbol))

    def get_sector_weights(self, symbol: str) -> list[SectorWeight]:
        return self._call(symbol, lambda provider: provider.get_sector_weights(symbol))

    def get_metadata(self, symbol: str) -> EtfMetadata:
        result = self._call(symbol, lambda provider: provider.get_metadata(symbol))
        if self.fallback is not None and self.last_provider == self.fallback.name:
            return result.model_copy(update={"fallback_used": True})
        return result

    def refresh(self, symbol: str) -> EtfMetadata:
        def operation(provider: EtfCompositionProvider) -> EtfMetadata:
            refresh = getattr(provider, "refresh", None)
            if callable(refresh):
                return refresh(symbol)
            provider.get_holdings(symbol)
            provider.get_sector_weights(symbol)
            return provider.get_metadata(symbol)

        self._fallback_symbols.discard(symbol.upper())
        result = self._call(symbol, operation)
        if self.fallback is not None and self.last_provider == self.fallback.name:
            return result.model_copy(update={"fallback_used": True})
        return result

    def _call(self, symbol: str, operation: Callable[[EtfCompositionProvider], T]) -> T:
        normalized = symbol.upper()
        if normalized in self._fallback_symbols and self.fallback is not None:
            self.last_provider = self.fallback.name
            return operation(self.fallback)
        try:
            result = operation(self.primary)
        except Exception as exc:
            self.last_error = exc
            if self.fallback is None:
                raise
            result = operation(self.fallback)
            self._fallback_symbols.add(normalized)
            self.last_provider = self.fallback.name
            return result
        self.last_provider = self.primary.name
        return result
