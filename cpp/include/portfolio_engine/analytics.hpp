#pragma once

#include "portfolio_engine/types.hpp"

#include <span>
#include <string>
#include <unordered_map>
#include <vector>

namespace portfolio_engine {

void validate_finite(std::span<const double> values, const char* name);
std::vector<double> calculate_returns(std::span<const double> prices);
double cumulative_return(std::span<const double> returns);
double annualized_return(std::span<const double> returns, double periods_per_year = 252.0);
double sample_stddev(std::span<const double> returns);
double annualized_volatility(std::span<const double> returns, double periods_per_year = 252.0);
double sharpe_ratio(std::span<const double> returns, double risk_free_rate = 0.0,
                    double periods_per_year = 252.0);
double sortino_ratio(std::span<const double> returns, double risk_free_rate = 0.0,
                     double periods_per_year = 252.0);
DrawdownResult maximum_drawdown(std::span<const double> values);
double beta(std::span<const double> asset_returns, std::span<const double> benchmark_returns);
double historical_var(std::span<const double> returns, double confidence_level);
double expected_shortfall(std::span<const double> returns, double confidence_level);
std::vector<std::vector<double>> covariance_matrix(const std::vector<std::vector<double>>& returns);
std::vector<std::vector<double>> correlation_matrix(const std::vector<std::vector<double>>& returns);
RiskContributionResult risk_contributions(std::span<const double> weights,
                                           const std::vector<std::vector<double>>& covariance);
ScenarioResult apply_scenario(
    const std::vector<std::string>& symbols,
    std::span<const double> values,
    const std::vector<std::string>& sectors,
    const std::vector<std::string>& asset_types,
    const std::unordered_map<std::string, double>& symbol_shocks,
    const std::unordered_map<std::string, double>& sector_shocks,
    const std::unordered_map<std::string, double>& asset_type_shocks);

}  // namespace portfolio_engine

