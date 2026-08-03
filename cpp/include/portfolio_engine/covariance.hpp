#pragma once

#include "portfolio_engine/matrix.hpp"

#include <cstddef>

namespace portfolio_engine {

enum class CovarianceMethod { kSample, kExponentiallyWeighted, kShrinkage, kDiagonal };

struct CovarianceRequest {
  CovarianceMethod method{CovarianceMethod::kSample};
  double decay_factor{0.94};
  double shrinkage_intensity{0.10};
};

struct CovarianceDiagnostics {
  std::size_t observations{};
  std::size_t assets{};
  bool symmetric{};
  bool positive_semidefinite{};
  bool spectral_diagnostics_exact{};
  double smallest_eigenvalue{};
  double largest_eigenvalue{};
  double condition_number{};
  double effective_rank{};
  double shrinkage_intensity{};
};

struct CovarianceEstimate {
  Matrix covariance;
  CovarianceDiagnostics diagnostics;
};

[[nodiscard]] CovarianceEstimate estimate_covariance(MatrixView return_history,
                                                      const CovarianceRequest& request = {});

}  // namespace portfolio_engine
