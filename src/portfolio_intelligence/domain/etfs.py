from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

_UTC = timezone.utc  # noqa: UP017


class EtfProvider(str, Enum):
    ALPHA_VANTAGE = "alphavantage"
    CSV = "csv"
    DEMO = "demo"
    CACHE = "cache"
    FALLBACK = "fallback"


class DataQualityStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    INCOMPLETE = "incomplete"


class AllocationType(str, Enum):
    SECURITY = "security"
    CASH = "cash"
    OTHER = "other"


class SectorExposureMethod(str, Enum):
    DIRECT = "direct"
    CONSTITUENT = "constituent"
    ETF_SECTOR_ALLOCATION = "etf_sector_allocation"
    UNCLASSIFIED = "unclassified"


class EtfHolding(BaseModel):
    """A normalized ETF constituent. Weights are decimal fractions, not percentages."""

    model_config = ConfigDict(frozen=True)

    fund_symbol: str
    constituent_symbol: str
    weight: float = Field(ge=0.0)
    name: str | None = None
    sector: str | None = None
    allocation_type: AllocationType = AllocationType.SECURITY
    as_of_date: date | None = None
    provider: EtfProvider
    retrieval_time: datetime = Field(default_factory=lambda: datetime.now(_UTC))
    data_quality: DataQualityStatus = DataQualityStatus.FRESH

    @field_validator("fund_symbol", "constituent_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("symbol must not be empty")
        return value


class SectorWeight(BaseModel):
    model_config = ConfigDict(frozen=True)

    fund_symbol: str
    sector: str
    weight: float = Field(ge=0.0)
    as_of_date: date | None = None
    provider: EtfProvider
    retrieval_time: datetime = Field(default_factory=lambda: datetime.now(_UTC))
    data_quality: DataQualityStatus = DataQualityStatus.FRESH

    @field_validator("fund_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class EtfMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str | None = None
    description: str | None = None
    net_assets: float | None = Field(default=None, ge=0.0)
    expense_ratio: float | None = Field(default=None, ge=0.0)
    as_of_date: date | None = None
    provider: EtfProvider
    retrieval_time: datetime = Field(default_factory=lambda: datetime.now(_UTC))
    data_quality: DataQualityStatus = DataQualityStatus.FRESH
    stale: bool = False
    fallback_used: bool = False
    missing_constituents: list[str] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class SecurityExposure(BaseModel):
    symbol: str
    direct_value: float = 0.0
    indirect_value: float = 0.0
    effective_value: float = 0.0
    direct_weight: float = 0.0
    indirect_weight: float = 0.0
    effective_weight: float = 0.0
    contributing_etfs: dict[str, float] = Field(default_factory=dict)
    sector: str | None = None
    as_of_dates: list[date] = Field(default_factory=list)


class SectorExposure(BaseModel):
    sector: str
    value: float
    weight: float
    methods: list[SectorExposureMethod] = Field(default_factory=list)


class EtfOverlap(BaseModel):
    left_symbol: str
    right_symbol: str
    shared_constituents: list[str]
    weighted_overlap: float
    top_overlapping_securities: list[dict[str, float | str]] = Field(default_factory=list)
    sector_overlap: float
    formula: str = "sum(min(left constituent weight, right constituent weight))"


class ConcentrationMetrics(BaseModel):
    largest_security_weight: float
    largest_sector_weight: float
    top_five_effective_holdings: list[SecurityExposure] = Field(default_factory=list)
    hhi: float
    effective_number_of_holdings: float
    warnings: list[str] = Field(default_factory=list)


class EtfExposureReport(BaseModel):
    securities: list[SecurityExposure] = Field(default_factory=list)
    sectors: list[SectorExposure] = Field(default_factory=list)
    concentration: ConcentrationMetrics | None = None
    etf_overlaps: list[EtfOverlap] = Field(default_factory=list)
    data_as_of: dict[str, date | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    look_through: bool = True
    total_portfolio_value: float = 0.0
