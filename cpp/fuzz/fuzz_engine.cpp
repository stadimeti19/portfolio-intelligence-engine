#include "portfolio_engine/covariance.hpp"
#include "portfolio_engine/engine.hpp"
#include "portfolio_engine/incremental_statistics.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <exception>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
  if (size < 2) {
    return 0;
  }
  const std::size_t assets = 1 + data[0] % 8;
  const std::size_t observations = 2 + data[1] % 32;
  const std::size_t required = assets * observations * sizeof(double);
  if (size - 2 < required) {
    return 0;
  }
  std::vector<double> values(assets * observations);
  std::memcpy(values.data(), data + 2, required);

  try {
    const portfolio_engine::MatrixView matrix(values, assets, observations);
    static_cast<void>(portfolio_engine::estimate_covariance(matrix));
    portfolio_engine::RunningStatistics statistics;
    statistics.initialize(matrix.row(0));
    if (statistics.count() >= 2) {
      static_cast<void>(statistics.sample_variance());
    }
  } catch (const std::exception&) {
    // Rejected non-finite and malformed numerical inputs are expected fuzz outcomes.
  }
  return 0;
}
