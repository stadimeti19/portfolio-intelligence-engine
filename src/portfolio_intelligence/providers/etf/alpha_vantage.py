from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Protocol

from portfolio_intelligence.domain.etfs import (
    AllocationType,
    EtfHolding,
    EtfMetadata,
    EtfProvider,
    SectorWeight,
)
from portfolio_intelligence.providers.etf.base import (
    EtfCompositionNotFoundError,
    EtfCompositionValidationError,
)
from portfolio_intelligence.providers.etf.csv_provider import _weight
from portfolio_intelligence.providers.etf.validation import (
    normalize_holdings,
    normalize_sector_weights,
)
from portfolio_intelligence.providers.market_data.errors import MissingAPIKeyError, RateLimitError
from portfolio_intelligence.providers.market_data.http import HttpResponse, JsonHttpClient

BASE_URL = "https://www.alphavantage.co/query"
_UTC = timezone.utc  # noqa: UP017


class AlphaVantageEtfHttpClient(Protocol):
    def get_json(self, url: str, params: dict[str, str]) -> HttpResponse: ...


class AlphaVantageEtfCompositionProvider:
    name = "alphavantage"

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: int = 15,
        max_retries: int = 3,
        http_client: AlphaVantageEtfHttpClient | None = None,
        weight_tolerance: float = 0.01,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("ALPHA_VANTAGE_API_KEY is required for ETF composition")
        self.api_key = api_key
        self.http_client = http_client or JsonHttpClient(
            timeout_seconds=timeout_seconds, max_retries=max_retries
        )
        self.weight_tolerance = weight_tolerance
        self._payloads: dict[str, tuple[dict[str, Any], datetime]] = {}

    def get_holdings(self, symbol: str) -> list[EtfHolding]:
        symbol = symbol.upper()
        payload, retrieved = self._profile(symbol)
        rows = payload.get("holdings")
        if not isinstance(rows, list) or not rows:
            raise EtfCompositionNotFoundError(f"Alpha Vantage returned no holdings for {symbol}")
        as_of = _as_of(payload)
        holdings: list[EtfHolding] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            constituent = str(row.get("symbol") or row.get("ticker") or "").strip()
            if not constituent:
                continue
            allocation_type = (
                AllocationType.CASH
                if constituent.upper() in {"CASH", "CASH & EQUIVALENTS"}
                else AllocationType.SECURITY
            )
            holdings.append(
                EtfHolding(
                    fund_symbol=symbol,
                    constituent_symbol=constituent,
                    name=str(row.get("description") or row.get("name") or "") or None,
                    weight=_vendor_weight(row.get("weight")),
                    sector=str(row.get("sector") or "") or None,
                    allocation_type=allocation_type,
                    as_of_date=as_of,
                    provider=EtfProvider.ALPHA_VANTAGE,
                    retrieval_time=retrieved,
                )
            )
        return normalize_holdings(holdings, weight_tolerance=self.weight_tolerance)

    def get_sector_weights(self, symbol: str) -> list[SectorWeight]:
        symbol = symbol.upper()
        payload, retrieved = self._profile(symbol)
        rows = payload.get("sectors")
        if not isinstance(rows, list):
            return []
        as_of = _as_of(payload)
        weights = [
            SectorWeight(
                fund_symbol=symbol,
                sector=str(row.get("sector") or row.get("name") or "Unknown"),
                weight=_vendor_weight(row.get("weight")),
                as_of_date=as_of,
                provider=EtfProvider.ALPHA_VANTAGE,
                retrieval_time=retrieved,
            )
            for row in rows
            if isinstance(row, dict)
        ]
        return normalize_sector_weights(weights, weight_tolerance=self.weight_tolerance)

    def get_metadata(self, symbol: str) -> EtfMetadata:
        symbol = symbol.upper()
        payload, retrieved = self._profile(symbol)
        return EtfMetadata(
            symbol=symbol,
            name=_string(payload, "name", "fund_name"),
            description=_string(payload, "description"),
            net_assets=_number(payload.get("net_assets")),
            expense_ratio=_optional_vendor_weight(
                payload.get("net_expense_ratio") or payload.get("expense_ratio")
            ),
            as_of_date=_as_of(payload),
            provider=EtfProvider.ALPHA_VANTAGE,
            retrieval_time=retrieved,
        )

    def _profile(self, symbol: str) -> tuple[dict[str, Any], datetime]:
        if symbol in self._payloads:
            return self._payloads[symbol]
        response = self.http_client.get_json(
            BASE_URL,
            {"function": "ETF_PROFILE", "symbol": symbol, "apikey": self.api_key},
        )
        payload = response.payload
        if not isinstance(payload, dict):
            raise EtfCompositionValidationError("Alpha Vantage ETF response must be an object")
        message = str(payload.get("Information") or payload.get("Note") or "")
        if message:
            if "rate" in message.lower() or "limit" in message.lower():
                raise RateLimitError("Alpha Vantage rate limit reached")
            raise EtfCompositionValidationError(f"Alpha Vantage ETF response error: {message}")
        if "Error Message" in payload or not payload:
            raise EtfCompositionNotFoundError(f"Alpha Vantage has no ETF profile for {symbol}")
        result = (payload, datetime.now(_UTC))
        self._payloads[symbol] = result
        return result


def _vendor_weight(value: Any) -> float:
    if value is None:
        raise EtfCompositionValidationError("Alpha Vantage ETF response is missing a weight")
    return _weight(str(value))


def _optional_vendor_weight(value: Any) -> float | None:
    return _vendor_weight(value) if value not in {None, "", "None"} else None


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "")) if value not in {None, "", "None"} else None
    except ValueError as exc:
        raise EtfCompositionValidationError(f"invalid numeric ETF metadata: {value!r}") from exc


def _string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in {None, "", "None"}:
            return str(value)
    return None


def _as_of(payload: dict[str, Any]) -> date | None:
    raw = _string(payload, "as_of_date", "latest_update", "last_updated")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise EtfCompositionValidationError(f"invalid ETF as-of date: {raw!r}") from exc
