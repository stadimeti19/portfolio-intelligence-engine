#include "portfolio_engine/analytics.hpp"

#include <chrono>
#include <iostream>
#include <vector>

int main() {
  std::vector<double> prices;
  prices.reserve(5000);
  double price = 100.0;
  for (int i = 0; i < 5000; ++i) {
    price *= 1.0 + (static_cast<double>((i % 17) - 8) / 10000.0);
    prices.push_back(price);
  }

  const auto start = std::chrono::steady_clock::now();
  double sink = 0.0;
  for (int i = 0; i < 1000; ++i) {
    const auto returns = portfolio_engine::calculate_returns(prices);
    sink += portfolio_engine::cumulative_return(returns);
    sink += portfolio_engine::annualized_volatility(returns, 252.0);
    sink += portfolio_engine::historical_var(returns, 0.95);
    sink += portfolio_engine::expected_shortfall(returns, 0.95);
  }
  const auto end = std::chrono::steady_clock::now();
  const auto millis = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
  std::cout << "analytics benchmark: 1000 iterations over 5000 prices in " << millis
            << " ms (checksum " << sink << ")\n";
  return 0;
}

