#include "portfolio_engine/covariance.hpp"
#include "portfolio_engine/engine.hpp"
#include "portfolio_engine/incremental_statistics.hpp"
#include "portfolio_engine/simulation.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

struct Measurement {
  std::string operation;
  std::string workload;
  std::size_t assets{};
  std::size_t observations{};
  std::size_t paths{};
  std::size_t repetitions{};
  double median_ms{};
  double p95_ms{};
};

struct Workload {
  std::string name;
  std::size_t assets;
  std::size_t observations;
};

template <typename Function>
Measurement measure(std::string operation, const Workload& workload, std::size_t paths,
                    std::size_t repetitions, Function&& function) {
  for (int warmup = 0; warmup < 2; ++warmup) {
    function();
  }
  std::vector<double> elapsed;
  elapsed.reserve(repetitions);
  for (std::size_t repetition = 0; repetition < repetitions; ++repetition) {
    const auto start = Clock::now();
    function();
    const auto end = Clock::now();
    elapsed.push_back(std::chrono::duration<double, std::milli>(end - start).count());
  }
  std::sort(elapsed.begin(), elapsed.end());
  const std::size_t p95_index = static_cast<std::size_t>(
      std::ceil(0.95 * static_cast<double>(elapsed.size()))) - 1;
  return {std::move(operation), workload.name, workload.assets, workload.observations, paths,
          repetitions, elapsed[elapsed.size() / 2], elapsed[p95_index]};
}

std::vector<double> generate_prices(const Workload& workload) {
  std::vector<double> prices(workload.observations * workload.assets);
  for (std::size_t asset = 0; asset < workload.assets; ++asset) {
    double price = 50.0 + static_cast<double>(asset % 100);
    for (std::size_t observation = 0; observation < workload.observations; ++observation) {
      const auto centered = static_cast<int>((observation * 17 + asset * 13) % 23) - 11;
      price *= 1.0 + static_cast<double>(centered) / 100000.0;
      prices[observation * workload.assets + asset] = price;
    }
  }
  return prices;
}

std::vector<double> generate_returns(const Workload& workload) {
  std::vector<double> returns(workload.assets * workload.observations);
  for (std::size_t asset = 0; asset < workload.assets; ++asset) {
    for (std::size_t observation = 0; observation < workload.observations; ++observation) {
      const auto centered = static_cast<int>((observation * 17 + asset * 13) % 41) - 20;
      returns[asset * workload.observations + observation] =
          static_cast<double>(centered) / 10000.0;
    }
  }
  return returns;
}

std::string compiler_name() {
#if defined(__clang__)
  return "Clang " __clang_version__;
#elif defined(__GNUC__)
  return "GCC " __VERSION__;
#elif defined(_MSC_VER)
  return "MSVC";
#else
  return "unknown";
#endif
}

void write_json(std::ostream& output, const std::vector<Measurement>& measurements,
                std::size_t thread_count) {
  output << "{\n  \"schema_version\": 1,\n  \"language\": \"C++20\",\n"
         << "  \"compiler\": \"" << compiler_name() << "\",\n"
         << "  \"build_type\": \""
#ifdef NDEBUG
         << "Release"
#else
         << "Debug"
#endif
         << "\",\n  \"thread_count\": " << thread_count
         << ",\n  \"warmup_repetitions\": 2,\n  \"measurements\": [\n";
  for (std::size_t index = 0; index < measurements.size(); ++index) {
    const auto& item = measurements[index];
    output << "    {\"operation\": \"" << item.operation << "\", \"workload\": \""
           << item.workload << "\", \"assets\": " << item.assets
           << ", \"observations\": " << item.observations << ", \"paths\": " << item.paths
           << ", \"repetitions\": " << item.repetitions << ", \"median_ms\": "
           << std::fixed << std::setprecision(6) << item.median_ms << ", \"p95_ms\": "
           << item.p95_ms << '}' << (index + 1 == measurements.size() ? "\n" : ",\n");
  }
  output << "  ]\n}\n";
}

}  // namespace

int main(int argc, char** argv) {
  using namespace portfolio_engine;
  bool full = false;
  std::string output_path;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--full") {
      full = true;
    } else if (argument == "--output" && index + 1 < argc) {
      output_path = argv[++index];
    } else {
      throw std::invalid_argument("usage: portfolio_engine_benchmarks [--full] [--output path]");
    }
  }

  const std::vector<Workload> workloads = full
      ? std::vector<Workload>{{"small", 10, 504}, {"medium", 100, 1260},
                              {"large", 1000, 1260}, {"stress", 5000, 252}}
      : std::vector<Workload>{{"small", 10, 504}, {"medium", 100, 1260}};
  std::vector<Measurement> measurements;
  volatile double checksum = 0.0;
  for (const auto& workload : workloads) {
    const auto prices = generate_prices(workload);
    const auto returns = generate_returns(workload);
    std::vector<double> quantities(prices.size(), 10.0);
    std::vector<std::int64_t> timestamps(workload.observations);
    std::iota(timestamps.begin(), timestamps.end(), 0);
    std::vector<double> cash(workload.observations, 10000.0);
    std::vector<double> flows(workload.observations, 0.0);
    const HistoricalPortfolioInput history{
        timestamps, MatrixView(prices, workload.observations, workload.assets),
        MatrixView(quantities, workload.observations, workload.assets), cash, flows};
    const std::size_t repetitions = workload.assets <= 100 ? 15 : 5;
    measurements.push_back(measure("batch_valuation", workload, 0, repetitions, [&] {
      const auto result = value_history(history);
      checksum = checksum + result.total_values.back();
    }));

    if (workload.assets <= (full ? 1000U : 100U)) {
      measurements.push_back(measure("sample_covariance", workload, 0, repetitions, [&] {
        const auto result = estimate_covariance(
            MatrixView(returns, workload.assets, workload.observations));
        checksum = checksum + result.covariance(0, 0);
      }));
    }
  }

  const Workload online{"online", 1, 1000000};
  const auto online_values = generate_returns(online);
  measurements.push_back(measure("running_variance", online, 0, 15, [&] {
    RunningStatistics statistics;
    statistics.initialize(online_values);
    checksum = checksum + statistics.sample_variance();
  }));

  const Workload simulation_workload{"simulation", 10, 1260};
  const auto simulation_returns = generate_returns(simulation_workload);
  std::vector<double> weights(simulation_workload.assets,
                              1.0 / static_cast<double>(simulation_workload.assets));
  std::vector<double> covariance(simulation_workload.assets * simulation_workload.assets, 0.0);
  for (std::size_t asset = 0; asset < simulation_workload.assets; ++asset) {
    covariance[asset * simulation_workload.assets + asset] = 0.0001;
  }
  SimulationConfig simulation_config;
  simulation_config.paths = full ? 1000000 : 100000;
  simulation_config.horizon_days = 10;
  simulation_config.seed = 42;
  simulation_config.thread_count = 1;
  const std::size_t simulation_repetitions = full ? 3 : 7;
  measurements.push_back(measure("normal_simulation_single_thread", simulation_workload,
                                 simulation_config.paths, simulation_repetitions, [&] {
    const auto result = simulate(weights,
                                 MatrixView(simulation_returns, simulation_workload.assets,
                                            simulation_workload.observations),
                                 MatrixView(covariance, simulation_workload.assets,
                                            simulation_workload.assets),
                                 simulation_config);
    checksum = checksum + result.mean;
  }));
  simulation_config.thread_count = 0;
  measurements.push_back(measure("normal_simulation_auto_threads", simulation_workload,
                                 simulation_config.paths, simulation_repetitions, [&] {
    const auto result = simulate(weights,
                                 MatrixView(simulation_returns, simulation_workload.assets,
                                            simulation_workload.observations),
                                 MatrixView(covariance, simulation_workload.assets,
                                            simulation_workload.assets),
                                 simulation_config);
    checksum = checksum + result.mean;
  }));

  if (output_path.empty()) {
    write_json(std::cout, measurements, std::thread::hardware_concurrency());
  } else {
    std::ofstream output(output_path);
    if (!output) {
      throw std::runtime_error("could not open benchmark output path");
    }
    write_json(output, measurements, std::thread::hardware_concurrency());
  }
  if (!std::isfinite(checksum)) {
    return 1;
  }
  return 0;
}
