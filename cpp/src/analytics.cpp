#include "portfolio_engine/analytics.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>

namespace portfolio_engine {
namespace {

constexpr double kEpsilon = 1e-12;

double mean(std::span<const double> values) {
  if (values.empty()) {
    throw std::invalid_argument("mean requires at least one observation");
  }
  return std::accumulate(values.begin(), values.end(), 0.0) / static_cast<double>(values.size());
}

double covariance(std::span<const double> left, std::span<const double> right) {
  if (left.size() != right.size()) {
    throw std::invalid_argument("covariance inputs must have the same length");
  }
  if (left.size() < 2) {
    throw std::invalid_argument("covariance requires at least two observations");
  }
  validate_finite(left, "left");
  validate_finite(right, "right");
  const double left_mean = mean(left);
  const double right_mean = mean(right);
  double total = 0.0;
  for (std::size_t i = 0; i < left.size(); ++i) {
    total += (left[i] - left_mean) * (right[i] - right_mean);
  }
  return total / static_cast<double>(left.size() - 1);
}

}  // namespace

void validate_finite(std::span<const double> values, const char* name) {
  for (double value : values) {
    if (!std::isfinite(value)) {
      throw std::invalid_argument(std::string(name) + " contains NaN or infinite values");
    }
  }
}

std::vector<double> calculate_returns(std::span<const double> prices) {
  validate_finite(prices, "prices");
  if (prices.size() < 2) {
    return {};
  }
  std::vector<double> returns;
  returns.reserve(prices.size() - 1);
  for (std::size_t i = 1; i < prices.size(); ++i) {
    if (prices[i - 1] <= 0.0) {
      throw std::invalid_argument("prices must be positive to calculate returns");
    }
    returns.push_back((prices[i] / prices[i - 1]) - 1.0);
  }
  return returns;
}

double cumulative_return(std::span<const double> returns) {
  validate_finite(returns, "returns");
  double growth = 1.0;
  for (double value : returns) {
    growth *= (1.0 + value);
  }
  return growth - 1.0;
}

double annualized_return(std::span<const double> returns, double periods_per_year) {
  validate_finite(returns, "returns");
  if (periods_per_year <= 0.0) {
    throw std::invalid_argument("periods_per_year must be positive");
  }
  if (returns.size() < 2) {
    throw std::invalid_argument("annualized_return requires at least two return observations");
  }
  const double cumulative = cumulative_return(returns);
  if (cumulative <= -1.0) {
    return -1.0;
  }
  return std::pow(1.0 + cumulative, periods_per_year / static_cast<double>(returns.size())) - 1.0;
}

double sample_stddev(std::span<const double> returns) {
  validate_finite(returns, "returns");
  if (returns.size() < 2) {
    throw std::invalid_argument("sample standard deviation requires at least two observations");
  }
  const double avg = mean(returns);
  double sum_sq = 0.0;
  for (double value : returns) {
    const double diff = value - avg;
    sum_sq += diff * diff;
  }
  return std::sqrt(sum_sq / static_cast<double>(returns.size() - 1));
}

double annualized_volatility(std::span<const double> returns, double periods_per_year) {
  if (periods_per_year <= 0.0) {
    throw std::invalid_argument("periods_per_year must be positive");
  }
  return sample_stddev(returns) * std::sqrt(periods_per_year);
}

double sharpe_ratio(std::span<const double> returns, double risk_free_rate, double periods_per_year) {
  validate_finite(returns, "returns");
  if (returns.size() < 2) {
    throw std::invalid_argument("sharpe_ratio requires at least two observations");
  }
  const double excess_period = risk_free_rate / periods_per_year;
  std::vector<double> excess;
  excess.reserve(returns.size());
  for (double value : returns) {
    excess.push_back(value - excess_period);
  }
  const double vol = sample_stddev(excess);
  if (std::abs(vol) < kEpsilon) {
    throw std::invalid_argument("sharpe_ratio is undefined for zero volatility");
  }
  return (mean(excess) / vol) * std::sqrt(periods_per_year);
}

double sortino_ratio(std::span<const double> returns, double risk_free_rate, double periods_per_year) {
  validate_finite(returns, "returns");
  if (returns.size() < 2) {
    throw std::invalid_argument("sortino_ratio requires at least two observations");
  }
  const double target = risk_free_rate / periods_per_year;
  double downside_sq = 0.0;
  std::size_t downside_count = 0;
  for (double value : returns) {
    const double downside = std::min(0.0, value - target);
    if (downside < 0.0) {
      downside_sq += downside * downside;
      ++downside_count;
    }
  }
  if (downside_count == 0) {
    throw std::invalid_argument("sortino_ratio is undefined with no downside observations");
  }
  const double downside_dev = std::sqrt(downside_sq / static_cast<double>(returns.size()));
  if (downside_dev < kEpsilon) {
    throw std::invalid_argument("sortino_ratio is undefined for zero downside deviation");
  }
  std::vector<double> excess;
  excess.reserve(returns.size());
  for (double value : returns) {
    excess.push_back(value - target);
  }
  return (mean(excess) / downside_dev) * std::sqrt(periods_per_year);
}

DrawdownResult maximum_drawdown(std::span<const double> values) {
  validate_finite(values, "values");
  if (values.empty()) {
    throw std::invalid_argument("maximum_drawdown requires at least one observation");
  }
  std::size_t peak = 0;
  std::size_t best_peak = 0;
  std::size_t trough = 0;
  double max_drawdown = 0.0;
  for (std::size_t i = 0; i < values.size(); ++i) {
    if (values[i] <= 0.0) {
      throw std::invalid_argument("portfolio values must be positive for drawdown");
    }
    if (values[i] > values[peak]) {
      peak = i;
    }
    const double drawdown = (values[i] / values[peak]) - 1.0;
    if (drawdown < max_drawdown) {
      max_drawdown = drawdown;
      best_peak = peak;
      trough = i;
    }
  }
  long recovery_index = -1;
  if (max_drawdown < 0.0) {
    for (std::size_t i = trough + 1; i < values.size(); ++i) {
      if (values[i] >= values[best_peak]) {
        recovery_index = static_cast<long>(i);
        break;
      }
    }
  }
  const std::size_t drawdown_duration = trough >= best_peak ? trough - best_peak : 0;
  const long recovery_duration = recovery_index >= 0 ? recovery_index - static_cast<long>(trough) : -1;
  return {max_drawdown, best_peak, trough, recovery_index, drawdown_duration, recovery_duration};
}

double beta(std::span<const double> asset_returns, std::span<const double> benchmark_returns) {
  const double bench_var = covariance(benchmark_returns, benchmark_returns);
  if (std::abs(bench_var) < kEpsilon) {
    throw std::invalid_argument("beta is undefined for zero benchmark variance");
  }
  return covariance(asset_returns, benchmark_returns) / bench_var;
}

double historical_var(std::span<const double> returns, double confidence_level) {
  validate_finite(returns, "returns");
  if (confidence_level <= 0.0 || confidence_level >= 1.0) {
    throw std::invalid_argument("confidence_level must be between 0 and 1");
  }
  if (returns.empty()) {
    throw std::invalid_argument("historical_var requires at least one return observation");
  }
  std::vector<double> losses;
  losses.reserve(returns.size());
  for (double value : returns) {
    losses.push_back(-value);
  }
  std::sort(losses.begin(), losses.end());
  const double raw_index = std::ceil(confidence_level * static_cast<double>(losses.size())) - 1.0;
  const auto index = static_cast<std::size_t>(std::clamp(raw_index, 0.0, static_cast<double>(losses.size() - 1)));
  return losses[index];
}

double expected_shortfall(std::span<const double> returns, double confidence_level) {
  const double var_value = historical_var(returns, confidence_level);
  std::vector<double> tail_losses;
  for (double value : returns) {
    const double loss = -value;
    if (loss >= var_value - kEpsilon) {
      tail_losses.push_back(loss);
    }
  }
  return std::accumulate(tail_losses.begin(), tail_losses.end(), 0.0) /
         static_cast<double>(tail_losses.size());
}

std::vector<std::vector<double>> covariance_matrix(const std::vector<std::vector<double>>& returns) {
  if (returns.empty()) {
    throw std::invalid_argument("covariance_matrix requires at least one asset");
  }
  const std::size_t observations = returns.front().size();
  if (observations < 2) {
    throw std::invalid_argument("covariance_matrix requires at least two observations");
  }
  for (const auto& row : returns) {
    if (row.size() != observations) {
      throw std::invalid_argument("all return series must have the same length");
    }
  }
  std::vector<std::vector<double>> matrix(returns.size(), std::vector<double>(returns.size(), 0.0));
  for (std::size_t i = 0; i < returns.size(); ++i) {
    for (std::size_t j = i; j < returns.size(); ++j) {
      const double value = covariance(returns[i], returns[j]);
      matrix[i][j] = value;
      matrix[j][i] = value;
    }
  }
  return matrix;
}

std::vector<std::vector<double>> correlation_matrix(const std::vector<std::vector<double>>& returns) {
  auto cov = covariance_matrix(returns);
  std::vector<double> stddevs(cov.size(), 0.0);
  for (std::size_t i = 0; i < cov.size(); ++i) {
    stddevs[i] = std::sqrt(std::max(0.0, cov[i][i]));
  }
  for (std::size_t i = 0; i < cov.size(); ++i) {
    for (std::size_t j = 0; j < cov.size(); ++j) {
      if (stddevs[i] < kEpsilon || stddevs[j] < kEpsilon) {
        cov[i][j] = (i == j && stddevs[i] >= kEpsilon) ? 1.0 : 0.0;
      } else {
        cov[i][j] = cov[i][j] / (stddevs[i] * stddevs[j]);
      }
    }
  }
  return cov;
}

RiskContributionResult risk_contributions(std::span<const double> weights,
                                           const std::vector<std::vector<double>>& covariance) {
  validate_finite(weights, "weights");
  if (weights.empty() || covariance.size() != weights.size()) {
    throw std::invalid_argument("weights and covariance dimensions must match");
  }
  for (const auto& row : covariance) {
    if (row.size() != weights.size()) {
      throw std::invalid_argument("covariance matrix must be square");
    }
    validate_finite(row, "covariance");
  }
  std::vector<double> sigma_w(weights.size(), 0.0);
  for (std::size_t i = 0; i < weights.size(); ++i) {
    for (std::size_t j = 0; j < weights.size(); ++j) {
      sigma_w[i] += covariance[i][j] * weights[j];
    }
  }
  double variance = 0.0;
  for (std::size_t i = 0; i < weights.size(); ++i) {
    variance += weights[i] * sigma_w[i];
  }
  if (variance < -kEpsilon) {
    throw std::invalid_argument("portfolio variance cannot be negative");
  }
  variance = std::max(0.0, variance);
  const double volatility = std::sqrt(variance);
  std::vector<double> marginal(weights.size(), 0.0);
  std::vector<double> component(weights.size(), 0.0);
  std::vector<double> percent(weights.size(), 0.0);
  if (volatility > kEpsilon) {
    for (std::size_t i = 0; i < weights.size(); ++i) {
      marginal[i] = sigma_w[i] / volatility;
      component[i] = weights[i] * marginal[i];
      percent[i] = component[i] / volatility;
    }
  }
  return {variance, volatility, marginal, component, percent};
}

ScenarioResult apply_scenario(
    const std::vector<std::string>& symbols,
    std::span<const double> values,
    const std::vector<std::string>& sectors,
    const std::vector<std::string>& asset_types,
    const std::unordered_map<std::string, double>& symbol_shocks,
    const std::unordered_map<std::string, double>& sector_shocks,
    const std::unordered_map<std::string, double>& asset_type_shocks) {
  validate_finite(values, "values");
  if (symbols.size() != values.size() || sectors.size() != values.size() ||
      asset_types.size() != values.size()) {
    throw std::invalid_argument("scenario inputs must have matching lengths");
  }
  ScenarioResult result{0.0, 0.0, 0.0, 0.0, {}};
  result.impacts.reserve(values.size());
  for (std::size_t i = 0; i < values.size(); ++i) {
    double shock = 0.0;
    if (const auto found = asset_type_shocks.find(asset_types[i]); found != asset_type_shocks.end()) {
      shock += found->second;
    }
    if (const auto found = sector_shocks.find(sectors[i]); found != sector_shocks.end()) {
      shock += found->second;
    }
    if (const auto found = symbol_shocks.find(symbols[i]); found != symbol_shocks.end()) {
      shock += found->second;
    }
    const double pnl = values[i] * shock;
    result.starting_value += values[i];
    result.pnl += pnl;
    result.impacts.push_back({symbols[i], values[i], shock, pnl, values[i] + pnl});
  }
  result.ending_value = result.starting_value + result.pnl;
  result.percent_pnl = result.starting_value > kEpsilon ? result.pnl / result.starting_value : 0.0;
  return result;
}

}  // namespace portfolio_engine
