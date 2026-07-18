#include "portfolio_engine/analytics.hpp"

#include <cassert>
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

bool close(double left, double right, double tolerance = 1e-9) {
  return std::abs(left - right) <= tolerance;
}

void expect_throw(auto fn) {
  bool threw = false;
  try {
    fn();
  } catch (const std::invalid_argument&) {
    threw = true;
  }
  assert(threw);
}

}  // namespace

int main() {
  using namespace portfolio_engine;

  const std::vector<double> prices{100.0, 110.0, 99.0, 108.9};
  const auto returns = calculate_returns(prices);
  assert(returns.size() == 3);
  assert(close(returns[0], 0.10));
  assert(close(returns[1], -0.10));
  assert(close(cumulative_return(returns), 0.089));
  assert(annualized_return(returns, 252.0) > 0.0);
  assert(annualized_volatility(returns, 252.0) > 0.0);

  const std::vector<double> varied_returns{0.01, -0.02, 0.03, -0.01, 0.02};
  assert(std::isfinite(sharpe_ratio(varied_returns, 0.0, 252.0)));
  assert(std::isfinite(sortino_ratio(varied_returns, 0.0, 252.0)));

  const std::vector<double> values{100.0, 120.0, 90.0, 95.0, 121.0};
  const auto drawdown = maximum_drawdown(values);
  assert(close(drawdown.drawdown, -0.25));
  assert(drawdown.peak_index == 1);
  assert(drawdown.trough_index == 2);
  assert(drawdown.recovery_index == 4);

  const std::vector<double> asset{0.01, 0.02, -0.01, 0.03};
  const std::vector<double> benchmark{0.005, 0.01, -0.005, 0.015};
  assert(close(beta(asset, benchmark), 2.0));
  expect_throw([] { beta(std::vector<double>{0.1, 0.2}, std::vector<double>{0.0, 0.0}); });

  const std::vector<double> tail{-0.10, -0.04, 0.01, 0.02, 0.03};
  assert(close(historical_var(tail, 0.8), 0.04));
  assert(expected_shortfall(tail, 0.8) >= historical_var(tail, 0.8));
  expect_throw([] { historical_var(std::vector<double>{0.01}, 1.2); });

  const std::vector<std::vector<double>> matrix_returns{
      {0.01, 0.02, 0.03, 0.04},
      {0.02, 0.04, 0.06, 0.08},
      {0.04, 0.03, 0.02, 0.01},
  };
  const auto cov = covariance_matrix(matrix_returns);
  const auto corr = correlation_matrix(matrix_returns);
  assert(close(cov[0][1], cov[1][0]));
  assert(close(corr[0][1], 1.0));
  assert(close(corr[0][2], -1.0));

  const std::vector<double> weights{0.6, 0.4};
  const std::vector<std::vector<double>> sigma{{0.04, 0.01}, {0.01, 0.09}};
  const auto rc = risk_contributions(weights, sigma);
  double component_sum = 0.0;
  for (double value : rc.component_contribution) {
    component_sum += value;
  }
  assert(close(component_sum, rc.portfolio_volatility));
  expect_throw([] {
    risk_contributions(std::vector<double>{0.5, 0.5},
                       std::vector<std::vector<double>>{{0.01, -1.0}, {-1.0, 0.01}});
  });
  expect_throw([] {
    risk_contributions(std::vector<double>{0.5, 0.5},
                       std::vector<std::vector<double>>{{0.01, std::numeric_limits<double>::quiet_NaN()},
                                                        {0.0, 0.01}});
  });

  const auto scenario = apply_scenario(
      std::vector<std::string>{"NVDA", "BND"},
      std::vector<double>{1000.0, 500.0},
      std::vector<std::string>{"Technology", "Fixed Income"},
      std::vector<std::string>{"Equity", "Bond"},
      {{"NVDA", -0.05}},
      {{"Technology", -0.10}},
      {{"Bond", 0.02}});
  assert(close(scenario.pnl, -140.0));
  assert(close(scenario.ending_value, 1360.0));

  expect_throw([] { calculate_returns(std::vector<double>{100.0, 0.0, 101.0}); });
  expect_throw([] { annualized_return(std::vector<double>{0.1}, 252.0); });
  expect_throw([] { covariance_matrix(std::vector<std::vector<double>>{{0.1}, {0.2}}); });

  std::cout << "portfolio_engine_tests passed\n";
  return 0;
}
