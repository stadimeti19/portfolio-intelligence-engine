#include "portfolio_engine/simulation.hpp"

#include "portfolio_engine/analytics.hpp"
#include "portfolio_engine/incremental_statistics.hpp"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <thread>

namespace portfolio_engine {
namespace {

constexpr std::size_t kBlockSize = 256;

std::uint64_t mix_seed(std::uint64_t seed, std::size_t block) {
  std::uint64_t value = seed + 0x9e3779b97f4a7c15ULL * (block + 1);
  value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
  value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

std::vector<double> means(MatrixView history) {
  std::vector<double> result(history.rows(), 0.0);
  for (std::size_t asset = 0; asset < history.rows(); ++asset) {
    result[asset] = std::accumulate(history.row(asset).begin(), history.row(asset).end(), 0.0) /
                    static_cast<double>(history.columns());
  }
  return result;
}

std::vector<double> cholesky(MatrixView covariance) {
  const std::size_t assets = covariance.rows();
  std::vector<double> lower(assets * assets, 0.0);
  for (std::size_t row = 0; row < assets; ++row) {
    for (std::size_t column = 0; column <= row; ++column) {
      double sum = covariance(row, column);
      for (std::size_t k = 0; k < column; ++k) {
        sum -= lower[row * assets + k] * lower[column * assets + k];
      }
      if (row == column) {
        if (sum < -1e-12) {
          throw std::invalid_argument("covariance matrix is not positive semidefinite");
        }
        lower[row * assets + column] = std::sqrt(std::max(sum, 0.0));
      } else if (lower[column * assets + column] > 1e-15) {
        lower[row * assets + column] = sum / lower[column * assets + column];
      } else if (std::abs(sum) > 1e-12) {
        throw std::invalid_argument("covariance matrix has an invalid singular structure");
      }
    }
  }
  return lower;
}

void validate_inputs(std::span<const double> weights, MatrixView history, MatrixView covariance,
                     const SimulationConfig& config) {
  if (weights.empty() || history.rows() != weights.size() || history.columns() < 2 ||
      covariance.rows() != weights.size() || covariance.columns() != weights.size()) {
    throw std::invalid_argument("simulation input dimensions do not match");
  }
  validate_finite(weights, "weights");
  validate_finite(history.data(), "return_history");
  validate_finite(covariance.data(), "covariance");
  if (config.paths == 0 || config.horizon_days == 0) {
    throw std::invalid_argument("simulation paths and horizon_days must be positive");
  }
  if (config.confidence_level <= 0.0 || config.confidence_level >= 1.0 ||
      !std::isfinite(config.confidence_level)) {
    throw std::invalid_argument("confidence_level must be between zero and one");
  }
  for (std::size_t row = 0; row < covariance.rows(); ++row) {
    for (std::size_t column = row + 1; column < covariance.columns(); ++column) {
      if (std::abs(covariance(row, column) - covariance(column, row)) > 1e-10) {
        throw std::invalid_argument("covariance matrix must be symmetric");
      }
    }
  }
}

}  // namespace

SimulationResult simulate(std::span<const double> weights, MatrixView return_history,
                          MatrixView covariance, const SimulationConfig& config) {
  validate_inputs(weights, return_history, covariance, config);
  const std::size_t assets = weights.size();
  const std::size_t block_count = (config.paths + kBlockSize - 1) / kBlockSize;
  const std::size_t requested_threads = config.thread_count == 0
                                            ? std::thread::hardware_concurrency()
                                            : config.thread_count;
  const std::size_t thread_count =
      std::max<std::size_t>(1, std::min({requested_threads, block_count, config.paths}));
  std::vector<double> output(config.paths);
  const auto asset_means = means(return_history);
  const auto lower = config.method == SimulationMethod::kNormal ? cholesky(covariance)
                                                                : std::vector<double>{};
  std::atomic_size_t next_block{0};

  auto worker = [&]() {
    std::vector<double> independent(assets);
    std::vector<double> asset_returns(assets);
    while (true) {
      const std::size_t block = next_block.fetch_add(1, std::memory_order_relaxed);
      if (block >= block_count) {
        return;
      }
      std::mt19937_64 generator(mix_seed(config.seed, block));
      std::normal_distribution<double> normal(0.0, 1.0);
      std::uniform_int_distribution<std::size_t> history_row(0, return_history.columns() - 1);
      const std::size_t begin = block * kBlockSize;
      const std::size_t end = std::min(config.paths, begin + kBlockSize);
      for (std::size_t path = begin; path < end; ++path) {
        double growth = 1.0;
        for (std::size_t day = 0; day < config.horizon_days; ++day) {
          double portfolio_return = 0.0;
          if (config.method == SimulationMethod::kHistoricalBootstrap) {
            const std::size_t observation = history_row(generator);
            for (std::size_t asset = 0; asset < assets; ++asset) {
              portfolio_return += weights[asset] * return_history(asset, observation);
            }
          } else {
            for (double& value : independent) {
              value = normal(generator);
            }
            for (std::size_t asset = 0; asset < assets; ++asset) {
              double value = asset_means[asset];
              for (std::size_t column = 0; column <= asset; ++column) {
                value += lower[asset * assets + column] * independent[column];
              }
              asset_returns[asset] = value;
              portfolio_return += weights[asset] * value;
            }
          }
          growth *= 1.0 + portfolio_return;
        }
        output[path] = growth - 1.0;
      }
    }
  };

  std::vector<std::thread> workers;
  workers.reserve(thread_count > 1 ? thread_count - 1 : 0);
  for (std::size_t index = 1; index < thread_count; ++index) {
    workers.emplace_back(worker);
  }
  worker();
  for (auto& thread : workers) {
    thread.join();
  }

  RunningStatistics stats;
  stats.initialize(output);
  const auto [minimum, maximum] = std::minmax_element(output.begin(), output.end());
  SimulationResult result;
  result.value_at_risk = historical_var(output, config.confidence_level);
  result.expected_shortfall = expected_shortfall(output, config.confidence_level);
  result.minimum = *minimum;
  result.maximum = *maximum;
  result.mean = stats.mean();
  result.standard_deviation = stats.sample_standard_deviation();
  result.paths = config.paths;
  result.horizon_days = config.horizon_days;
  result.seed = config.seed;
  result.thread_count = thread_count;
  result.method = config.method == SimulationMethod::kNormal ? "normal" : "historical_bootstrap";
  result.path_returns = std::move(output);
  return result;
}

}  // namespace portfolio_engine
