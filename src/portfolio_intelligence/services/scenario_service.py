from __future__ import annotations

from pathlib import Path

from portfolio_intelligence.domain.assets import Asset
from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.domain.scenarios import (
    ScenarioDefinition,
    ScenarioPositionImpact,
    ScenarioResult,
)
from portfolio_intelligence.scenarios.loader import load_scenarios


class ScenarioService:
    def __init__(self, scenario_path: str | Path, assets: dict[str, Asset]) -> None:
        self.scenario_path = Path(scenario_path)
        self.assets = assets
        self.scenarios = load_scenarios(self.scenario_path)

    def list_scenarios(self) -> dict[str, ScenarioDefinition]:
        return self.scenarios

    def run(self, name: str, positions: list[Position], cash: float = 0.0) -> ScenarioResult:
        if name not in self.scenarios:
            raise ValueError(f"unknown scenario: {name}")
        scenario = self.scenarios[name]
        impacts: list[ScenarioPositionImpact] = []
        starting_value = cash + sum(position.market_value for position in positions)
        total_pnl = 0.0
        for position in positions:
            asset = self.assets.get(position.symbol)
            shock = 0.0
            if asset is not None:
                shock += scenario.asset_type_shocks.get(asset.asset_type.value, 0.0)
                shock += scenario.sector_shocks.get(asset.sector, 0.0)
            shock += scenario.symbol_shocks.get(position.symbol, 0.0)
            pnl = position.market_value * shock
            total_pnl += pnl
            impacts.append(
                ScenarioPositionImpact(
                    symbol=position.symbol,
                    starting_value=position.market_value,
                    shock=shock,
                    pnl=pnl,
                    ending_value=position.market_value + pnl,
                )
            )
        ending_value = starting_value + total_pnl
        return ScenarioResult(
            name=name,
            description=scenario.description,
            starting_value=starting_value,
            ending_value=ending_value,
            pnl=total_pnl,
            percent_pnl=total_pnl / starting_value if starting_value else 0.0,
            impacts=sorted(impacts, key=lambda impact: abs(impact.pnl), reverse=True),
        )
