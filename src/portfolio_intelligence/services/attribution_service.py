from __future__ import annotations

from portfolio_intelligence.domain.portfolios import PortfolioSnapshot


class AttributionService:
    def contribution(
        self, first: PortfolioSnapshot, last: PortfolioSnapshot
    ) -> list[dict[str, float | str]]:
        starting_total = first.total_portfolio_value
        if starting_total <= 0:
            return []
        contributions: list[dict[str, float | str]] = []
        for symbol, starting_value in first.position_values.items():
            ending_value = last.position_values.get(symbol, 0.0)
            if starting_value <= 0:
                continue
            asset_return = (ending_value / starting_value) - 1.0
            starting_weight = starting_value / starting_total
            contributions.append(
                {
                    "symbol": symbol,
                    "asset_return": asset_return,
                    "starting_weight": starting_weight,
                    "percentage_point_contribution": starting_weight * asset_return,
                    "dollar_pnl_contribution": ending_value - starting_value,
                }
            )
        return sorted(
            contributions,
            key=lambda row: abs(float(row["percentage_point_contribution"])),
            reverse=True,
        )
