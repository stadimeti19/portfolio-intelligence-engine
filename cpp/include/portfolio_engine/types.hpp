#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace portfolio_engine {

struct DrawdownResult {
  double drawdown;
  std::size_t peak_index;
  std::size_t trough_index;
  long recovery_index;
  std::size_t drawdown_duration;
  long recovery_duration;
};

struct RiskContributionResult {
  double portfolio_variance;
  double portfolio_volatility;
  std::vector<double> marginal_contribution;
  std::vector<double> component_contribution;
  std::vector<double> percent_contribution;
};

struct ScenarioPositionImpact {
  std::string symbol;
  double starting_value;
  double shock;
  double pnl;
  double ending_value;
};

struct ScenarioResult {
  double starting_value;
  double ending_value;
  double pnl;
  double percent_pnl;
  std::vector<ScenarioPositionImpact> impacts;
};

}  // namespace portfolio_engine

