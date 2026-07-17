from __future__ import annotations

from pydantic import BaseModel, Field


class ScenarioDefinition(BaseModel):
    name: str
    description: str
    symbol_shocks: dict[str, float] = Field(default_factory=dict)
    sector_shocks: dict[str, float] = Field(default_factory=dict)
    asset_type_shocks: dict[str, float] = Field(default_factory=dict)


class ScenarioPositionImpact(BaseModel):
    symbol: str
    starting_value: float
    shock: float
    pnl: float
    ending_value: float


class ScenarioResult(BaseModel):
    name: str
    description: str
    starting_value: float
    ending_value: float
    pnl: float
    percent_pnl: float
    impacts: list[ScenarioPositionImpact]
