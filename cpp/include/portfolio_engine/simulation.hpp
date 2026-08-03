#pragma once

#include "portfolio_engine/matrix.hpp"

#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace portfolio_engine {

enum class SimulationMethod { kNormal, kHistoricalBootstrap };

struct SimulationConfig {
  std::size_t paths{10000};
  std::size_t horizon_days{1};
  std::uint64_t seed{42};
  std::size_t thread_count{1};
  double confidence_level{0.95};
  SimulationMethod method{SimulationMethod::kNormal};
};

struct SimulationResult {
  std::vector<double> path_returns;
  double value_at_risk{};
  double expected_shortfall{};
  double minimum{};
  double maximum{};
  double mean{};
  double standard_deviation{};
  std::size_t paths{};
  std::size_t horizon_days{};
  std::uint64_t seed{};
  std::size_t thread_count{};
  std::string method;
};

[[nodiscard]] SimulationResult simulate(std::span<const double> weights,
                                        MatrixView return_history,
                                        MatrixView covariance,
                                        const SimulationConfig& config);

}  // namespace portfolio_engine
