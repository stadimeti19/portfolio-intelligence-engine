#include "portfolio_engine/incremental_statistics.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace portfolio_engine {
namespace {

void require_finite(double value) {
  if (!std::isfinite(value)) {
    throw std::invalid_argument("observation must be finite");
  }
}

}  // namespace

void RunningStatistics::add(double value) {
  require_finite(value);
  ++count_;
  const double delta = value - mean_;
  mean_ += delta / static_cast<double>(count_);
  m2_ += delta * (value - mean_);
}

void RunningStatistics::initialize(std::span<const double> values) {
  reset();
  for (double value : values) {
    add(value);
  }
}

void RunningStatistics::reset() noexcept {
  count_ = 0;
  mean_ = 0.0;
  m2_ = 0.0;
}

double RunningStatistics::mean() const {
  if (count_ == 0) {
    throw std::logic_error("mean requires at least one observation");
  }
  return mean_;
}

double RunningStatistics::sample_variance() const {
  if (count_ < 2) {
    throw std::logic_error("sample variance requires at least two observations");
  }
  return std::max(0.0, m2_ / static_cast<double>(count_ - 1));
}

double RunningStatistics::sample_standard_deviation() const {
  return std::sqrt(sample_variance());
}

void RunningCovariance::add(double left, double right) {
  require_finite(left);
  require_finite(right);
  ++count_;
  const double left_delta = left - left_mean_;
  const double right_delta = right - right_mean_;
  left_mean_ += left_delta / static_cast<double>(count_);
  right_mean_ += right_delta / static_cast<double>(count_);
  co_moment_ += left_delta * (right - right_mean_);
  right_m2_ += right_delta * (right - right_mean_);
}

void RunningCovariance::initialize(std::span<const double> left, std::span<const double> right) {
  if (left.size() != right.size()) {
    throw std::invalid_argument("covariance inputs must have the same length");
  }
  reset();
  for (std::size_t index = 0; index < left.size(); ++index) {
    add(left[index], right[index]);
  }
}

void RunningCovariance::reset() noexcept {
  count_ = 0;
  left_mean_ = 0.0;
  right_mean_ = 0.0;
  co_moment_ = 0.0;
  right_m2_ = 0.0;
}

double RunningCovariance::covariance() const {
  if (count_ < 2) {
    throw std::logic_error("covariance requires at least two observations");
  }
  return co_moment_ / static_cast<double>(count_ - 1);
}

double RunningCovariance::beta() const {
  if (count_ < 2 || std::abs(right_m2_) < 1e-18) {
    throw std::logic_error("beta requires non-zero benchmark variance");
  }
  return co_moment_ / right_m2_;
}

RollingVolatility::RollingVolatility(std::size_t window, double periods_per_year)
    : window_(window), periods_per_year_(periods_per_year) {
  if (window_ < 2) {
    throw std::invalid_argument("rolling window must be at least two");
  }
  if (!std::isfinite(periods_per_year_) || periods_per_year_ <= 0.0) {
    throw std::invalid_argument("periods_per_year must be positive and finite");
  }
}

void RollingVolatility::remove_oldest() {
  const double value = values_.front();
  values_.pop_front();
  if (count_ == 1) {
    count_ = 0;
    mean_ = 0.0;
    m2_ = 0.0;
    return;
  }
  const auto new_count = count_ - 1;
  const double new_mean = (static_cast<double>(count_) * mean_ - value) /
                          static_cast<double>(new_count);
  m2_ -= (value - mean_) * (value - new_mean);
  m2_ = std::max(0.0, m2_);
  count_ = new_count;
  mean_ = new_mean;
}

void RollingVolatility::add(double value) {
  require_finite(value);
  if (values_.size() == window_) {
    remove_oldest();
  }
  values_.push_back(value);
  ++count_;
  const double delta = value - mean_;
  mean_ += delta / static_cast<double>(count_);
  m2_ += delta * (value - mean_);
}

void RollingVolatility::initialize(std::span<const double> values) {
  values_.clear();
  count_ = 0;
  mean_ = 0.0;
  m2_ = 0.0;
  for (double value : values) {
    add(value);
  }
}

double RollingVolatility::volatility() const {
  if (count_ < 2) {
    throw std::logic_error("rolling volatility requires at least two observations");
  }
  return std::sqrt(std::max(0.0, m2_ / static_cast<double>(count_ - 1))) *
         std::sqrt(periods_per_year_);
}

void DrawdownState::add(double portfolio_value) {
  if (!std::isfinite(portfolio_value) || portfolio_value <= 0.0) {
    throw std::invalid_argument("portfolio value must be positive and finite");
  }
  const std::size_t index = count++;
  if (count == 1 || portfolio_value > peak) {
    peak = portfolio_value;
    peak_index = index;
  }
  current_drawdown = portfolio_value / peak - 1.0;
  if (current_drawdown < maximum_drawdown) {
    maximum_drawdown = current_drawdown;
    trough_index = index;
  }
}

void DrawdownState::initialize(std::span<const double> values) {
  *this = {};
  for (double value : values) {
    add(value);
  }
}

}  // namespace portfolio_engine
