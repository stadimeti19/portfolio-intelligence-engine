#pragma once

#include <cstddef>
#include <deque>
#include <span>

namespace portfolio_engine {

class RunningStatistics {
 public:
  void add(double value);
  void initialize(std::span<const double> values);
  void reset() noexcept;

  [[nodiscard]] std::size_t count() const noexcept { return count_; }
  [[nodiscard]] double mean() const;
  [[nodiscard]] double sample_variance() const;
  [[nodiscard]] double sample_standard_deviation() const;

 private:
  std::size_t count_{};
  double mean_{};
  double m2_{};
};

class RunningCovariance {
 public:
  void add(double left, double right);
  void initialize(std::span<const double> left, std::span<const double> right);
  void reset() noexcept;

  [[nodiscard]] std::size_t count() const noexcept { return count_; }
  [[nodiscard]] double covariance() const;
  [[nodiscard]] double beta() const;

 private:
  std::size_t count_{};
  double left_mean_{};
  double right_mean_{};
  double co_moment_{};
  double right_m2_{};
};

class RollingVolatility {
 public:
  explicit RollingVolatility(std::size_t window, double periods_per_year = 252.0);
  void add(double value);
  void initialize(std::span<const double> values);

  [[nodiscard]] std::size_t count() const noexcept { return values_.size(); }
  [[nodiscard]] std::size_t window() const noexcept { return window_; }
  [[nodiscard]] double volatility() const;

 private:
  void remove_oldest();

  std::size_t window_;
  double periods_per_year_;
  std::deque<double> values_;
  std::size_t count_{};
  double mean_{};
  double m2_{};
};

struct DrawdownState {
  std::size_t count{};
  double peak{};
  double current_drawdown{};
  double maximum_drawdown{};
  std::size_t peak_index{};
  std::size_t trough_index{};

  void add(double portfolio_value);
  void initialize(std::span<const double> values);
};

}  // namespace portfolio_engine
