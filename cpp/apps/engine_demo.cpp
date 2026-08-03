#include "portfolio_engine/engine.hpp"
#include "portfolio_engine/simulation.hpp"

#include <cstdint>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
  using namespace portfolio_engine;
  std::size_t paths = 10000;
  if (argc == 2) {
    paths = static_cast<std::size_t>(std::stoull(argv[1]));
  }

  constexpr std::size_t observations = 252;
  constexpr std::size_t assets = 3;
  std::vector<std::int64_t> timestamps(observations);
  std::vector<double> prices(observations * assets);
  std::vector<double> quantities(observations * assets);
  std::vector<double> cash(observations, 5000.0);
  std::vector<double> flows(observations, 0.0);
  std::vector<double> asset_returns(assets * (observations - 1));
  for (std::size_t day = 0; day < observations; ++day) {
    timestamps[day] = static_cast<std::int64_t>(day);
    for (std::size_t asset = 0; asset < assets; ++asset) {
      const double trend = 1.0 + static_cast<double>(asset + 1) * 0.0002;
      const double cycle = static_cast<double>(static_cast<int>((day + asset * 3) % 11) - 5) *
                           0.0001;
      prices[day * assets + asset] =
          day == 0 ? 100.0 + 20.0 * static_cast<double>(asset)
                   : prices[(day - 1) * assets + asset] * (trend + cycle);
      quantities[day * assets + asset] = 20.0 + 10.0 * static_cast<double>(asset);
      if (day > 0) {
        asset_returns[asset * (observations - 1) + (day - 1)] =
            prices[day * assets + asset] / prices[(day - 1) * assets + asset] - 1.0;
      }
    }
  }

  const HistoricalPortfolioInput history{
      timestamps, MatrixView(prices, observations, assets),
      MatrixView(quantities, observations, assets), cash, flows};
  PortfolioAnalyticsEngine engine;
  engine.load_history({"ALPHA", "BETA", "GAMMA"}, history);
  const auto snapshot = engine.snapshot();
  const auto risk = engine.calculate_risk();
  const auto scenario = engine.run_scenario(std::vector<double>{-0.10, -0.05, 0.02});

  const std::vector<double> covariance{
      0.00010, 0.00003, 0.00002,
      0.00003, 0.00020, 0.00004,
      0.00002, 0.00004, 0.00015,
  };
  SimulationConfig simulation_config;
  simulation_config.paths = paths;
  simulation_config.horizon_days = 10;
  simulation_config.seed = 42;
  simulation_config.thread_count = 0;
  const auto simulation = simulate(
      std::vector<double>{0.3, 0.4, 0.3},
      MatrixView(asset_returns, assets, observations - 1),
      MatrixView(covariance, assets, assets), simulation_config);

  std::cout << std::fixed << std::setprecision(6)
            << "Native portfolio engine demo\n"
            << "assets=" << engine.asset_count() << " observations=" << observations << '\n'
            << "portfolio_value=" << snapshot.total_value << '\n'
            << "annualized_volatility=" << risk.annualized_volatility << '\n'
            << "maximum_drawdown=" << risk.maximum_drawdown << '\n'
            << "scenario_pnl=" << scenario.pnl << '\n'
            << "simulation_paths=" << simulation.paths << " threads=" << simulation.thread_count
            << " seed=" << simulation.seed << '\n'
            << "simulation_var=" << simulation.value_at_risk
            << " expected_shortfall=" << simulation.expected_shortfall << '\n';
  return 0;
}
