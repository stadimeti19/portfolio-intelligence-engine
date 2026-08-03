#include "portfolio_engine/engine.hpp"

#include "portfolio_engine/analytics.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>

namespace portfolio_engine {
namespace {

void validate_config(const EngineConfig& config) {
  if (!std::isfinite(config.annualization_factor) || config.annualization_factor <= 0.0) {
    throw std::invalid_argument("annualization_factor must be positive and finite");
  }
  if (!std::isfinite(config.confidence_level) || config.confidence_level <= 0.0 ||
      config.confidence_level >= 1.0) {
    throw std::invalid_argument("confidence_level must be between zero and one");
  }
}

void validate_history(const HistoricalPortfolioInput& input) {
  const std::size_t observations = input.timestamps.size();
  const std::size_t assets = input.prices.columns();
  if (observations == 0 || assets == 0) {
    throw std::invalid_argument("history requires at least one observation and one asset");
  }
  if (input.prices.rows() != observations || input.quantities.rows() != observations ||
      input.quantities.columns() != assets || input.cash_balances.size() != observations ||
      input.external_cash_flows.size() != observations) {
    throw std::invalid_argument("historical input shapes do not match");
  }
  for (std::size_t row = 0; row < observations; ++row) {
    if (row > 0 && input.timestamps[row] <= input.timestamps[row - 1]) {
      throw std::invalid_argument("timestamps must be strictly increasing");
    }
    if (!std::isfinite(input.cash_balances[row]) ||
        !std::isfinite(input.external_cash_flows[row])) {
      throw std::invalid_argument("cash arrays contain NaN or infinite values");
    }
    for (std::size_t asset = 0; asset < assets; ++asset) {
      const double price = input.prices(row, asset);
      const double quantity = input.quantities(row, asset);
      if (!std::isfinite(price) || !std::isfinite(quantity)) {
        throw std::invalid_argument("prices and quantities must be finite");
      }
      if (price < 0.0 || (quantity != 0.0 && price <= 0.0)) {
        throw std::invalid_argument("prices must be positive for non-zero positions");
      }
    }
  }
}

std::string update_key(const char* kind, std::size_t asset, std::int64_t timestamp) {
  return std::string(kind) + ':' + std::to_string(asset) + ':' + std::to_string(timestamp);
}

}  // namespace

ValuationResult value_history(const HistoricalPortfolioInput& input) {
  validate_history(input);
  const std::size_t observations = input.timestamps.size();
  const std::size_t assets = input.prices.columns();
  ValuationResult result{
      Matrix{observations, assets, std::vector<double>(observations * assets)},
      Matrix{observations, assets, std::vector<double>(observations * assets)},
      std::vector<double>(observations),
      std::vector<double>(observations),
      {}};
  result.returns.reserve(observations > 0 ? observations - 1 : 0);

  for (std::size_t row = 0; row < observations; ++row) {
    double invested = 0.0;
    for (std::size_t asset = 0; asset < assets; ++asset) {
      const double value = input.prices(row, asset) * input.quantities(row, asset);
      result.position_values(row, asset) = value;
      invested += value;
    }
    const double total = invested + input.cash_balances[row];
    if (!std::isfinite(total) || total <= 0.0) {
      throw std::invalid_argument("total portfolio values must be positive and finite");
    }
    result.invested_values[row] = invested;
    result.total_values[row] = total;
    for (std::size_t asset = 0; asset < assets; ++asset) {
      result.weights(row, asset) = result.position_values(row, asset) / total;
    }
    if (row > 0) {
      result.returns.push_back(
          (total - input.external_cash_flows[row]) / result.total_values[row - 1] - 1.0);
    }
  }
  return result;
}

PortfolioAnalyticsEngine::PortfolioAnalyticsEngine(EngineConfig config) : config_(config) {
  validate_config(config_);
}

void PortfolioAnalyticsEngine::load_history(std::vector<std::string> symbols,
                                            const HistoricalPortfolioInput& input) {
  validate_history(input);
  if (symbols.size() != input.prices.columns()) {
    throw std::invalid_argument("symbol count must equal the number of price columns");
  }
  std::unordered_set<std::string> unique_symbols;
  for (const auto& symbol : symbols) {
    if (symbol.empty() || !unique_symbols.insert(symbol).second) {
      throw std::invalid_argument("symbols must be non-empty and unique");
    }
  }
  auto valuation = portfolio_engine::value_history(input);

  std::scoped_lock lock(mutex_);
  symbols_ = std::move(symbols);
  timestamps_.assign(input.timestamps.begin(), input.timestamps.end());
  total_values_ = std::move(valuation.total_values);
  returns_ = std::move(valuation.returns);
  const std::size_t last = timestamps_.size() - 1;
  current_.timestamp = timestamps_[last];
  current_.prices.assign(input.prices.row(last).begin(), input.prices.row(last).end());
  current_.quantities.assign(input.quantities.row(last).begin(), input.quantities.row(last).end());
  current_.cash = input.cash_balances[last];
  current_.position_values.resize(symbols_.size());
  current_.weights.resize(symbols_.size());
  applied_updates_.clear();
  rebuild_snapshot_values();
}

void PortfolioAnalyticsEngine::require_loaded() const {
  if (symbols_.empty()) {
    throw std::logic_error("portfolio engine has no loaded history");
  }
}

void PortfolioAnalyticsEngine::validate_update(std::size_t asset, std::int64_t timestamp,
                                               double value, const char* kind) {
  require_loaded();
  if (asset >= symbols_.size()) {
    throw std::out_of_range("asset index is out of range");
  }
  if (timestamp < current_.timestamp) {
    throw std::invalid_argument("updates cannot precede the current engine timestamp");
  }
  if (!std::isfinite(value)) {
    throw std::invalid_argument("update value must be finite");
  }
  const auto key = update_key(kind, asset, timestamp);
  if (!applied_updates_.insert(key).second) {
    throw std::invalid_argument("duplicate portfolio update");
  }
}

void PortfolioAnalyticsEngine::rebuild_snapshot_values() {
  current_.invested_value = 0.0;
  for (std::size_t asset = 0; asset < symbols_.size(); ++asset) {
    const double value = current_.prices[asset] * current_.quantities[asset];
    current_.position_values[asset] = value;
    current_.invested_value += value;
  }
  current_.total_value = current_.cash + current_.invested_value;
  if (!std::isfinite(current_.total_value) || current_.total_value <= 0.0) {
    throw std::invalid_argument("update produces a non-positive portfolio value");
  }
  for (std::size_t asset = 0; asset < symbols_.size(); ++asset) {
    current_.weights[asset] = current_.position_values[asset] / current_.total_value;
  }
}

void PortfolioAnalyticsEngine::apply_price_update(const PriceUpdate& update) {
  std::scoped_lock lock(mutex_);
  if (update.price <= 0.0) {
    throw std::invalid_argument("price must be positive");
  }
  validate_update(update.asset, update.timestamp, update.price, "price");
  const double previous = current_.prices[update.asset];
  const auto previous_timestamp = current_.timestamp;
  current_.prices[update.asset] = update.price;
  current_.timestamp = update.timestamp;
  try {
    rebuild_snapshot_values();
  } catch (...) {
    current_.prices[update.asset] = previous;
    current_.timestamp = previous_timestamp;
    applied_updates_.erase(update_key("price", update.asset, update.timestamp));
    rebuild_snapshot_values();
    throw;
  }
}

void PortfolioAnalyticsEngine::apply_position_update(const PositionUpdate& update) {
  std::scoped_lock lock(mutex_);
  validate_update(update.asset, update.timestamp, update.quantity_delta, "position");
  const double previous = current_.quantities[update.asset];
  const auto previous_timestamp = current_.timestamp;
  current_.quantities[update.asset] += update.quantity_delta;
  current_.timestamp = update.timestamp;
  try {
    rebuild_snapshot_values();
  } catch (...) {
    current_.quantities[update.asset] = previous;
    current_.timestamp = previous_timestamp;
    applied_updates_.erase(update_key("position", update.asset, update.timestamp));
    rebuild_snapshot_values();
    throw;
  }
}

void PortfolioAnalyticsEngine::apply_cash_update(const CashUpdate& update) {
  std::scoped_lock lock(mutex_);
  require_loaded();
  if (update.timestamp < current_.timestamp) {
    throw std::invalid_argument("updates cannot precede the current engine timestamp");
  }
  if (!std::isfinite(update.amount)) {
    throw std::invalid_argument("cash update amount must be finite");
  }
  const auto key = update_key("cash", 0, update.timestamp);
  if (!applied_updates_.insert(key).second) {
    throw std::invalid_argument("duplicate portfolio update");
  }
  const double previous = current_.cash;
  const auto previous_timestamp = current_.timestamp;
  current_.cash += update.amount;
  current_.timestamp = update.timestamp;
  try {
    rebuild_snapshot_values();
  } catch (...) {
    current_.cash = previous;
    current_.timestamp = previous_timestamp;
    applied_updates_.erase(key);
    rebuild_snapshot_values();
    throw;
  }
}

bool PortfolioAnalyticsEngine::empty() const {
  std::scoped_lock lock(mutex_);
  return symbols_.empty();
}

std::size_t PortfolioAnalyticsEngine::asset_count() const {
  std::scoped_lock lock(mutex_);
  return symbols_.size();
}

PortfolioSnapshot PortfolioAnalyticsEngine::snapshot() const {
  std::scoped_lock lock(mutex_);
  require_loaded();
  return current_;
}

RiskSnapshot PortfolioAnalyticsEngine::calculate_risk() const {
  std::scoped_lock lock(mutex_);
  require_loaded();
  if (returns_.size() < 2) {
    throw std::logic_error("risk calculation requires at least three portfolio observations");
  }
  const auto drawdown = maximum_drawdown(total_values_);
  return RiskSnapshot{returns_.size(),
                      annualized_volatility(returns_, config_.annualization_factor),
                      drawdown.drawdown,
                      historical_var(returns_, config_.confidence_level),
                      expected_shortfall(returns_, config_.confidence_level)};
}

ScenarioResult PortfolioAnalyticsEngine::run_scenario(std::span<const double> asset_shocks) const {
  std::scoped_lock lock(mutex_);
  require_loaded();
  if (asset_shocks.size() != symbols_.size()) {
    throw std::invalid_argument("scenario shocks must match the number of assets");
  }
  validate_finite(asset_shocks, "asset_shocks");
  ScenarioResult result{current_.total_value, current_.total_value, 0.0, 0.0, {}};
  result.impacts.reserve(symbols_.size());
  for (std::size_t asset = 0; asset < symbols_.size(); ++asset) {
    const double pnl = current_.position_values[asset] * asset_shocks[asset];
    result.pnl += pnl;
    result.impacts.push_back({symbols_[asset], current_.position_values[asset],
                              asset_shocks[asset], pnl,
                              current_.position_values[asset] + pnl});
  }
  result.ending_value += result.pnl;
  result.percent_pnl = result.pnl / result.starting_value;
  return result;
}

std::vector<double> PortfolioAnalyticsEngine::portfolio_returns() const {
  std::scoped_lock lock(mutex_);
  require_loaded();
  return returns_;
}

std::vector<double> PortfolioAnalyticsEngine::value_history() const {
  std::scoped_lock lock(mutex_);
  require_loaded();
  return total_values_;
}

}  // namespace portfolio_engine
