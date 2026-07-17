from __future__ import annotations

from portfolio_intelligence import _engine
from portfolio_intelligence.domain.assets import Asset
from portfolio_intelligence.domain.positions import Position


class RiskService:
    def concentration_warnings(
        self,
        positions: list[Position],
        assets: dict[str, Asset],
        position_threshold: float,
        sector_threshold: float,
    ) -> list[str]:
        warnings: list[str] = []
        for position in positions:
            if position.weight > position_threshold:
                warnings.append(
                    f"{position.symbol} weight {position.weight:.1%} "
                    f"exceeds {position_threshold:.0%}"
                )
        sector_weights: dict[str, float] = {}
        for position in positions:
            asset = assets.get(position.symbol)
            sector = asset.sector if asset is not None else "Unknown"
            sector_weights[sector] = sector_weights.get(sector, 0.0) + position.weight
        for sector, weight in sector_weights.items():
            if weight > sector_threshold:
                warnings.append(
                    f"{sector} sector weight {weight:.1%} exceeds {sector_threshold:.0%}"
                )
        return warnings

    def risk_contribution(
        self,
        positions: list[Position],
        asset_returns: dict[str, list[float]],
    ) -> list[dict[str, float | str]]:
        symbols = [position.symbol for position in positions if position.symbol in asset_returns]
        if len(symbols) < 2:
            return []
        observations = min(len(asset_returns[symbol]) for symbol in symbols)
        if observations < 2:
            return []
        returns = [asset_returns[symbol][-observations:] for symbol in symbols]
        covariance = _engine.covariance_matrix(returns)
        weights = [
            next(pos.weight for pos in positions if pos.symbol == symbol) for symbol in symbols
        ]
        result = _engine.risk_contributions(weights, covariance)
        return [
            {
                "symbol": symbol,
                "component": result.component_contribution[index],
                "percent": result.percent_contribution[index],
            }
            for index, symbol in enumerate(symbols)
        ]
