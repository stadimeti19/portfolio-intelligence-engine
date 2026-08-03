#include "portfolio_engine/analytics.hpp"
#include "portfolio_engine/covariance.hpp"
#include "portfolio_engine/engine.hpp"
#include "portfolio_engine/incremental_statistics.hpp"
#include "portfolio_engine/simulation.hpp"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

#define CHECK(condition)                                                                   \
  do {                                                                                     \
    if (!(condition)) {                                                                    \
      throw std::runtime_error(std::string("check failed at line ") +                     \
                               std::to_string(__LINE__) + ": " #condition);               \
    }                                                                                      \
  } while (false)

bool close(double left, double right, double tolerance = 1e-9) {
  return std::abs(left - right) <= tolerance;
}

void expect_throw(auto fn) {
  bool threw = false;
  try {
    fn();
  } catch (const std::exception&) {
    threw = true;
  }
  CHECK(threw);
}

void test_analytics() {
  using namespace portfolio_engine;
  const std::vector<double> prices{100.0, 110.0, 99.0, 108.9};
  const auto returns = calculate_returns(prices);
  CHECK(returns.size() == 3);
  CHECK(close(returns[0], 0.10));
  CHECK(close(returns[1], -0.10));
  CHECK(close(cumulative_return(returns), 0.089));
  CHECK(annualized_return(returns, 252.0) > 0.0);
  CHECK(annualized_volatility(returns, 252.0) > 0.0);

  const std::vector<double> varied_returns{0.01, -0.02, 0.03, -0.01, 0.02};
  CHECK(std::isfinite(sharpe_ratio(varied_returns, 0.0, 252.0)));
  CHECK(std::isfinite(sortino_ratio(varied_returns, 0.0, 252.0)));

  const std::vector<double> values{100.0, 120.0, 90.0, 95.0, 121.0};
  const auto drawdown = maximum_drawdown(values);
  CHECK(close(drawdown.drawdown, -0.25));
  CHECK(drawdown.peak_index == 1);
  CHECK(drawdown.trough_index == 2);
  CHECK(drawdown.recovery_index == 4);

  const std::vector<double> asset{0.01, 0.02, -0.01, 0.03};
  const std::vector<double> benchmark{0.005, 0.01, -0.005, 0.015};
  CHECK(close(beta(asset, benchmark), 2.0));
  expect_throw([] { beta(std::vector<double>{0.1, 0.2}, std::vector<double>{0.0, 0.0}); });

  const std::vector<double> tail{-0.10, -0.04, 0.01, 0.02, 0.03};
  CHECK(close(historical_var(tail, 0.8), 0.04));
  CHECK(expected_shortfall(tail, 0.8) >= historical_var(tail, 0.8));
  expect_throw([] { historical_var(std::vector<double>{0.01}, 1.2); });

  const std::vector<std::vector<double>> matrix_returns{
      {0.01, 0.02, 0.03, 0.04},
      {0.02, 0.04, 0.06, 0.08},
      {0.04, 0.03, 0.02, 0.01},
  };
  const auto cov = covariance_matrix(matrix_returns);
  const auto corr = correlation_matrix(matrix_returns);
  CHECK(close(cov[0][1], cov[1][0]));
  CHECK(close(corr[0][1], 1.0));
  CHECK(close(corr[0][2], -1.0));

  const std::vector<double> weights{0.6, 0.4};
  const std::vector<std::vector<double>> sigma{{0.04, 0.01}, {0.01, 0.09}};
  const auto rc = risk_contributions(weights, sigma);
  double component_sum = 0.0;
  for (double value : rc.component_contribution) {
    component_sum += value;
  }
  CHECK(close(component_sum, rc.portfolio_volatility));
  expect_throw([] {
    risk_contributions(std::vector<double>{0.5, 0.5},
                       std::vector<std::vector<double>>{{0.01, -1.0}, {-1.0, 0.01}});
  });
  expect_throw([] {
    risk_contributions(
        std::vector<double>{0.5, 0.5},
        std::vector<std::vector<double>>{
            {0.01, std::numeric_limits<double>::quiet_NaN()}, {0.0, 0.01}});
  });

  const auto scenario = apply_scenario(
      std::vector<std::string>{"NVDA", "BND"}, std::vector<double>{1000.0, 500.0},
      std::vector<std::string>{"Technology", "Fixed Income"},
      std::vector<std::string>{"Equity", "Bond"}, {{"NVDA", -0.05}},
      {{"Technology", -0.10}}, {{"Bond", 0.02}});
  CHECK(close(scenario.pnl, -140.0));
  CHECK(close(scenario.ending_value, 1360.0));

  expect_throw([] { calculate_returns(std::vector<double>{100.0, 0.0, 101.0}); });
  expect_throw([] { annualized_return(std::vector<double>{0.1}, 252.0); });
  expect_throw([] { covariance_matrix(std::vector<std::vector<double>>{{0.1}, {0.2}}); });
}

void test_batch_valuation_and_engine_state() {
  using namespace portfolio_engine;
  const std::vector<std::int64_t> timestamps{1, 2, 3};
  const std::vector<double> prices{100.0, 50.0, 110.0, 50.0, 99.0, 60.0};
  const std::vector<double> quantities{1.0, 2.0, 1.0, 2.0, 1.0, 2.0};
  const std::vector<double> cash{50.0, 150.0, 150.0};
  const std::vector<double> flows{0.0, 100.0, 0.0};
  const HistoricalPortfolioInput history{timestamps, MatrixView(prices, 3, 2),
                                         MatrixView(quantities, 3, 2), cash, flows};
  const auto valuation = value_history(history);
  CHECK(valuation.position_values.rows == 3);
  CHECK(valuation.position_values.columns == 2);
  CHECK(close(valuation.total_values[0], 250.0));
  CHECK(close(valuation.total_values[1], 360.0));
  CHECK(close(valuation.total_values[2], 369.0));
  CHECK(close(valuation.returns[0], 0.04));
  CHECK(close(valuation.returns[1], 0.025));
  CHECK(close(valuation.weights(2, 0) + valuation.weights(2, 1), 219.0 / 369.0));

  PortfolioAnalyticsEngine engine({252.0, 0.95});
  CHECK(engine.empty());
  engine.load_history({"A", "B"}, history);
  CHECK(!engine.empty());
  CHECK(engine.asset_count() == 2);
  auto snapshot = engine.snapshot();
  CHECK(close(snapshot.total_value, 369.0));
  CHECK(close(snapshot.cash + snapshot.invested_value, snapshot.total_value));
  const auto risk = engine.calculate_risk();
  CHECK(risk.observations == 2);
  CHECK(std::isfinite(risk.annualized_volatility));

  engine.apply_price_update({0, 4, 101.0});
  snapshot = engine.snapshot();
  CHECK(snapshot.timestamp == 4);
  CHECK(close(snapshot.total_value, 371.0));
  expect_throw([&] { engine.apply_price_update({0, 4, 102.0}); });
  engine.apply_position_update({1, 4, 1.0});
  snapshot = engine.snapshot();
  CHECK(close(snapshot.total_value, 431.0));
  engine.apply_cash_update({5, 25.0});
  snapshot = engine.snapshot();
  CHECK(close(snapshot.total_value, 456.0));

  const auto scenario = engine.run_scenario(std::vector<double>{-0.10, 0.05});
  CHECK(close(scenario.starting_value, 456.0));
  CHECK(close(scenario.pnl, -1.1));
  CHECK(close(scenario.ending_value, scenario.starting_value + scenario.pnl));
  expect_throw([&] { static_cast<void>(engine.run_scenario(std::vector<double>{0.1})); });

  const std::vector<std::int64_t> bad_timestamps{1, 1, 3};
  const HistoricalPortfolioInput bad_history{bad_timestamps, MatrixView(prices, 3, 2),
                                             MatrixView(quantities, 3, 2), cash, flows};
  expect_throw([&] { static_cast<void>(value_history(bad_history)); });
}

void test_incremental_statistics_match_batch() {
  using namespace portfolio_engine;
  std::mt19937_64 generator(42);
  std::normal_distribution<double> distribution(0.001, 0.02);
  std::vector<double> values(1000);
  std::vector<double> benchmark(1000);
  for (std::size_t index = 0; index < values.size(); ++index) {
    benchmark[index] = distribution(generator);
    values[index] = 0.5 * benchmark[index] + distribution(generator);
  }

  RunningStatistics stats;
  stats.initialize(values);
  CHECK(close(stats.sample_standard_deviation(), sample_stddev(values), 1e-14));
  RunningStatistics chunked;
  for (double value : values) {
    chunked.add(value);
  }
  CHECK(close(chunked.mean(), stats.mean(), 1e-15));
  CHECK(close(chunked.sample_variance(), stats.sample_variance(), 1e-15));

  RunningCovariance covariance;
  covariance.initialize(values, benchmark);
  CHECK(close(covariance.beta(), beta(values, benchmark), 1e-14));

  RollingVolatility rolling(20, 252.0);
  rolling.initialize(values);
  const std::vector<double> last_window(values.end() - 20, values.end());
  CHECK(close(rolling.volatility(), annualized_volatility(last_window, 252.0), 1e-13));

  DrawdownState drawdown;
  const std::vector<double> portfolio_values{100.0, 120.0, 90.0, 95.0, 121.0};
  drawdown.initialize(portfolio_values);
  CHECK(close(drawdown.maximum_drawdown, maximum_drawdown(portfolio_values).drawdown));
  CHECK(drawdown.trough_index == 2);
}

void test_covariance_estimators_and_diagnostics() {
  using namespace portfolio_engine;
  const std::vector<double> history{
      0.01, 0.02, 0.03, 0.04,
      0.02, 0.04, 0.06, 0.08,
      0.04, 0.03, 0.02, 0.01,
  };
  const MatrixView view(history, 3, 4);
  const auto sample = estimate_covariance(view);
  const auto reference = covariance_matrix({
      {0.01, 0.02, 0.03, 0.04},
      {0.02, 0.04, 0.06, 0.08},
      {0.04, 0.03, 0.02, 0.01},
  });
  CHECK(close(sample.covariance(0, 1), reference[0][1]));
  CHECK(sample.diagnostics.symmetric);
  CHECK(sample.diagnostics.positive_semidefinite);
  CHECK(sample.diagnostics.spectral_diagnostics_exact);
  CHECK(sample.diagnostics.smallest_eigenvalue >= -1e-12);

  CovarianceRequest request;
  request.method = CovarianceMethod::kExponentiallyWeighted;
  request.decay_factor = 0.9;
  const auto ew = estimate_covariance(view, request);
  CHECK(ew.covariance.rows == 3);
  CHECK(ew.diagnostics.positive_semidefinite);

  request.method = CovarianceMethod::kShrinkage;
  request.shrinkage_intensity = 0.5;
  const auto shrinkage = estimate_covariance(view, request);
  CHECK(close(shrinkage.covariance(0, 1), sample.covariance(0, 1) * 0.5));
  CHECK(close(shrinkage.diagnostics.shrinkage_intensity, 0.5));

  request.method = CovarianceMethod::kDiagonal;
  const auto diagonal = estimate_covariance(view, request);
  CHECK(diagonal.covariance(0, 1) == 0.0);
  CHECK(close(diagonal.covariance(1, 1), sample.covariance(1, 1)));

  request.decay_factor = 1.0;
  request.method = CovarianceMethod::kExponentiallyWeighted;
  expect_throw([&] { static_cast<void>(estimate_covariance(view, request)); });
}

void test_simulation_reproducibility() {
  using namespace portfolio_engine;
  const std::vector<double> weights{0.6, 0.4};
  const std::vector<double> history{
      0.01, -0.02, 0.015, 0.005, -0.01,
      0.005, -0.01, 0.010, 0.002, -0.004,
  };
  const std::vector<double> covariance{0.0004, 0.0001, 0.0001, 0.0002};
  SimulationConfig config;
  config.paths = 4096;
  config.horizon_days = 5;
  config.seed = 1234;
  config.thread_count = 1;
  auto single = simulate(weights, MatrixView(history, 2, 5), MatrixView(covariance, 2, 2), config);
  config.thread_count = 4;
  const auto parallel =
      simulate(weights, MatrixView(history, 2, 5), MatrixView(covariance, 2, 2), config);
  CHECK(single.path_returns == parallel.path_returns);
  CHECK(close(single.value_at_risk, parallel.value_at_risk));
  CHECK(single.expected_shortfall >= single.value_at_risk - 1e-12);
  CHECK(single.minimum <= single.mean && single.mean <= single.maximum);

  config.method = SimulationMethod::kHistoricalBootstrap;
  const auto bootstrap =
      simulate(weights, MatrixView(history, 2, 5), MatrixView(covariance, 2, 2), config);
  CHECK(bootstrap.method == "historical_bootstrap");
  CHECK(bootstrap.path_returns.size() == config.paths);

  config.paths = 0;
  expect_throw([&] {
    static_cast<void>(
        simulate(weights, MatrixView(history, 2, 5), MatrixView(covariance, 2, 2), config));
  });
}

}  // namespace

int main() {
  try {
    test_analytics();
    test_batch_valuation_and_engine_state();
    test_incremental_statistics_match_batch();
    test_covariance_estimators_and_diagnostics();
    test_simulation_reproducibility();
    std::cout << "portfolio_engine_tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
