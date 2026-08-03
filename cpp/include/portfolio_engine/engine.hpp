#pragma once

#include "portfolio_engine/matrix.hpp"
#include "portfolio_engine/types.hpp"

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <span>
#include <string>
#include <unordered_set>
#include <vector>

namespace portfolio_engine {

struct EngineConfig {
  double annualization_factor{252.0};
  double confidence_level{0.95};
};

struct HistoricalPortfolioInput {
  std::span<const std::int64_t> timestamps;
  MatrixView prices;
  MatrixView quantities;
  std::span<const double> cash_balances;
  std::span<const double> external_cash_flows;
};

struct ValuationResult {
  Matrix position_values;
  Matrix weights;
  std::vector<double> invested_values;
  std::vector<double> total_values;
  std::vector<double> returns;
};

struct PortfolioSnapshot {
  std::int64_t timestamp{};
  std::vector<double> prices;
  std::vector<double> quantities;
  std::vector<double> position_values;
  std::vector<double> weights;
  double cash{};
  double invested_value{};
  double total_value{};
};

struct RiskSnapshot {
  std::size_t observations{};
  double annualized_volatility{};
  double maximum_drawdown{};
  double value_at_risk{};
  double expected_shortfall{};
};

struct PriceUpdate {
  std::size_t asset{};
  std::int64_t timestamp{};
  double price{};
};

struct PositionUpdate {
  std::size_t asset{};
  std::int64_t timestamp{};
  double quantity_delta{};
};

struct CashUpdate {
  std::int64_t timestamp{};
  double amount{};
};

[[nodiscard]] ValuationResult value_history(const HistoricalPortfolioInput& input);

class PortfolioAnalyticsEngine {
 public:
  explicit PortfolioAnalyticsEngine(EngineConfig config = {});

  PortfolioAnalyticsEngine(const PortfolioAnalyticsEngine&) = delete;
  PortfolioAnalyticsEngine& operator=(const PortfolioAnalyticsEngine&) = delete;

  void load_history(std::vector<std::string> symbols, const HistoricalPortfolioInput& input);
  void apply_price_update(const PriceUpdate& update);
  void apply_position_update(const PositionUpdate& update);
  void apply_cash_update(const CashUpdate& update);

  [[nodiscard]] bool empty() const;
  [[nodiscard]] std::size_t asset_count() const;
  [[nodiscard]] PortfolioSnapshot snapshot() const;
  [[nodiscard]] RiskSnapshot calculate_risk() const;
  [[nodiscard]] ScenarioResult run_scenario(std::span<const double> asset_shocks) const;
  [[nodiscard]] std::vector<double> portfolio_returns() const;
  [[nodiscard]] std::vector<double> value_history() const;

 private:
  void require_loaded() const;
  void validate_update(std::size_t asset, std::int64_t timestamp, double value,
                       const char* kind);
  void rebuild_snapshot_values();

  EngineConfig config_;
  mutable std::mutex mutex_;
  std::vector<std::string> symbols_;
  std::vector<std::int64_t> timestamps_;
  std::vector<double> total_values_;
  std::vector<double> returns_;
  PortfolioSnapshot current_;
  std::unordered_set<std::string> applied_updates_;
};

}  // namespace portfolio_engine
