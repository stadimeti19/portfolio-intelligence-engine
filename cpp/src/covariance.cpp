#include "portfolio_engine/covariance.hpp"

#include "portfolio_engine/analytics.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <vector>

namespace portfolio_engine {
namespace {

constexpr std::size_t kExactSpectralLimit = 64;

Matrix sample_covariance(MatrixView history) {
  const std::size_t assets = history.rows();
  const std::size_t observations = history.columns();
  std::vector<double> means(assets);
  for (std::size_t asset = 0; asset < assets; ++asset) {
    means[asset] = std::accumulate(history.row(asset).begin(), history.row(asset).end(), 0.0) /
                   static_cast<double>(observations);
  }
  Matrix output{assets, assets, std::vector<double>(assets * assets)};
  for (std::size_t left = 0; left < assets; ++left) {
    for (std::size_t right = left; right < assets; ++right) {
      double total = 0.0;
      for (std::size_t observation = 0; observation < observations; ++observation) {
        total += (history(left, observation) - means[left]) *
                 (history(right, observation) - means[right]);
      }
      const double value = total / static_cast<double>(observations - 1);
      output(left, right) = value;
      output(right, left) = value;
    }
  }
  return output;
}

Matrix exponentially_weighted_covariance(MatrixView history, double decay) {
  const std::size_t assets = history.rows();
  const std::size_t observations = history.columns();
  std::vector<double> weights(observations);
  double weight = 1.0;
  for (std::size_t reverse = 0; reverse < observations; ++reverse) {
    weights[observations - reverse - 1] = weight;
    weight *= decay;
  }
  const double weight_sum = std::accumulate(weights.begin(), weights.end(), 0.0);
  for (double& value : weights) {
    value /= weight_sum;
  }
  const double squared_weight_sum =
      std::inner_product(weights.begin(), weights.end(), weights.begin(), 0.0);
  if (1.0 - squared_weight_sum <= 1e-15) {
    throw std::invalid_argument("decay_factor produces fewer than two effective observations");
  }
  std::vector<double> means(assets, 0.0);
  for (std::size_t asset = 0; asset < assets; ++asset) {
    for (std::size_t observation = 0; observation < observations; ++observation) {
      means[asset] += weights[observation] * history(asset, observation);
    }
  }
  Matrix output{assets, assets, std::vector<double>(assets * assets)};
  for (std::size_t left = 0; left < assets; ++left) {
    for (std::size_t right = left; right < assets; ++right) {
      double total = 0.0;
      for (std::size_t observation = 0; observation < observations; ++observation) {
        total += weights[observation] * (history(left, observation) - means[left]) *
                 (history(right, observation) - means[right]);
      }
      const double value = total / (1.0 - squared_weight_sum);
      output(left, right) = value;
      output(right, left) = value;
    }
  }
  return output;
}

bool positive_semidefinite(const Matrix& matrix) {
  const std::size_t size = matrix.rows;
  std::vector<double> lower(size * size, 0.0);
  for (std::size_t row = 0; row < size; ++row) {
    for (std::size_t column = 0; column <= row; ++column) {
      double sum = matrix(row, column);
      for (std::size_t k = 0; k < column; ++k) {
        sum -= lower[row * size + k] * lower[column * size + k];
      }
      if (row == column) {
        if (sum < -1e-12) {
          return false;
        }
        lower[row * size + column] = std::sqrt(std::max(0.0, sum));
      } else if (lower[column * size + column] > 1e-15) {
        lower[row * size + column] = sum / lower[column * size + column];
      } else if (std::abs(sum) > 1e-10) {
        return false;
      }
    }
  }
  return true;
}

std::vector<double> jacobi_eigenvalues(const Matrix& input) {
  Matrix matrix = input;
  const std::size_t size = matrix.rows;
  const std::size_t max_iterations = 50 * size * size;
  for (std::size_t iteration = 0; iteration < max_iterations; ++iteration) {
    std::size_t p = 0;
    std::size_t q = 0;
    double largest = 0.0;
    for (std::size_t row = 0; row < size; ++row) {
      for (std::size_t column = row + 1; column < size; ++column) {
        if (std::abs(matrix(row, column)) > largest) {
          largest = std::abs(matrix(row, column));
          p = row;
          q = column;
        }
      }
    }
    if (largest <= 1e-14) {
      break;
    }
    const double angle = 0.5 * std::atan2(2.0 * matrix(p, q), matrix(q, q) - matrix(p, p));
    const double cosine = std::cos(angle);
    const double sine = std::sin(angle);
    const double pp = matrix(p, p);
    const double qq = matrix(q, q);
    const double pq = matrix(p, q);
    matrix(p, p) = cosine * cosine * pp - 2.0 * sine * cosine * pq + sine * sine * qq;
    matrix(q, q) = sine * sine * pp + 2.0 * sine * cosine * pq + cosine * cosine * qq;
    matrix(p, q) = 0.0;
    matrix(q, p) = 0.0;
    for (std::size_t index = 0; index < size; ++index) {
      if (index == p || index == q) {
        continue;
      }
      const double ip = matrix(index, p);
      const double iq = matrix(index, q);
      matrix(index, p) = cosine * ip - sine * iq;
      matrix(p, index) = matrix(index, p);
      matrix(index, q) = sine * ip + cosine * iq;
      matrix(q, index) = matrix(index, q);
    }
  }
  std::vector<double> eigenvalues(size);
  for (std::size_t index = 0; index < size; ++index) {
    eigenvalues[index] = matrix(index, index);
  }
  return eigenvalues;
}

CovarianceDiagnostics diagnostics(const Matrix& covariance, std::size_t observations,
                                  double shrinkage) {
  CovarianceDiagnostics result;
  result.observations = observations;
  result.assets = covariance.rows;
  result.symmetric = true;
  for (std::size_t row = 0; row < covariance.rows; ++row) {
    for (std::size_t column = row + 1; column < covariance.columns; ++column) {
      result.symmetric = result.symmetric &&
                         std::abs(covariance(row, column) - covariance(column, row)) <= 1e-12;
    }
  }
  result.positive_semidefinite = positive_semidefinite(covariance);
  result.shrinkage_intensity = shrinkage;
  double trace = 0.0;
  double frobenius_squared = 0.0;
  for (std::size_t row = 0; row < covariance.rows; ++row) {
    trace += covariance(row, row);
    for (std::size_t column = 0; column < covariance.columns; ++column) {
      frobenius_squared += covariance(row, column) * covariance(row, column);
    }
  }
  result.effective_rank = frobenius_squared > 0.0 ? trace * trace / frobenius_squared : 0.0;
  const double unavailable = std::numeric_limits<double>::quiet_NaN();
  result.smallest_eigenvalue = unavailable;
  result.largest_eigenvalue = unavailable;
  result.condition_number = unavailable;
  if (covariance.rows <= kExactSpectralLimit) {
    const auto eigenvalues = jacobi_eigenvalues(covariance);
    const auto [smallest, largest] = std::minmax_element(eigenvalues.begin(), eigenvalues.end());
    result.smallest_eigenvalue = *smallest;
    result.largest_eigenvalue = *largest;
    result.condition_number = *smallest > 1e-15
                                  ? *largest / *smallest
                                  : std::numeric_limits<double>::infinity();
    result.spectral_diagnostics_exact = true;
  }
  return result;
}

}  // namespace

CovarianceEstimate estimate_covariance(MatrixView return_history, const CovarianceRequest& request) {
  if (return_history.rows() == 0 || return_history.columns() < 2) {
    throw std::invalid_argument("covariance estimation requires assets and two observations");
  }
  validate_finite(return_history.data(), "return_history");
  if (!std::isfinite(request.decay_factor) || request.decay_factor <= 0.0 ||
      request.decay_factor >= 1.0) {
    throw std::invalid_argument("decay_factor must be between zero and one");
  }
  if (!std::isfinite(request.shrinkage_intensity) || request.shrinkage_intensity < 0.0 ||
      request.shrinkage_intensity > 1.0) {
    throw std::invalid_argument("shrinkage_intensity must be between zero and one");
  }

  Matrix covariance = request.method == CovarianceMethod::kExponentiallyWeighted
                          ? exponentially_weighted_covariance(return_history, request.decay_factor)
                          : sample_covariance(return_history);
  double applied_shrinkage = 0.0;
  if (request.method == CovarianceMethod::kShrinkage) {
    applied_shrinkage = request.shrinkage_intensity;
    for (std::size_t row = 0; row < covariance.rows; ++row) {
      for (std::size_t column = 0; column < covariance.columns; ++column) {
        if (row != column) {
          covariance(row, column) *= 1.0 - applied_shrinkage;
        }
      }
    }
  } else if (request.method == CovarianceMethod::kDiagonal) {
    for (std::size_t row = 0; row < covariance.rows; ++row) {
      for (std::size_t column = 0; column < covariance.columns; ++column) {
        if (row != column) {
          covariance(row, column) = 0.0;
        }
      }
    }
  }
  return {covariance, diagnostics(covariance, return_history.columns(), applied_shrinkage)};
}

}  // namespace portfolio_engine
