#include "portfolio_engine/analytics.hpp"
#include "portfolio_engine/covariance.hpp"
#include "portfolio_engine/engine.hpp"
#include "portfolio_engine/incremental_statistics.hpp"
#include "portfolio_engine/simulation.hpp"

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <span>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

namespace {

std::span<const double> as_span(const std::vector<double>& values) {
  return std::span<const double>(values.data(), values.size());
}

struct ArrayHistory {
  py::buffer_info timestamps;
  py::buffer_info prices;
  py::buffer_info quantities;
  py::buffer_info cash;
  py::buffer_info flows;

  [[nodiscard]] portfolio_engine::HistoricalPortfolioInput view() const {
    if (timestamps.ndim != 1 || prices.ndim != 2 || quantities.ndim != 2 || cash.ndim != 1 ||
        flows.ndim != 1) {
      throw std::invalid_argument(
          "expected one-dimensional timestamps/cash arrays and two-dimensional matrix arrays");
    }
    const auto observations = static_cast<std::size_t>(timestamps.shape[0]);
    const auto price_rows = static_cast<std::size_t>(prices.shape[0]);
    const auto assets = static_cast<std::size_t>(prices.shape[1]);
    const auto quantity_rows = static_cast<std::size_t>(quantities.shape[0]);
    const auto quantity_assets = static_cast<std::size_t>(quantities.shape[1]);
    if (price_rows != observations || quantity_rows != observations ||
        quantity_assets != assets || static_cast<std::size_t>(cash.shape[0]) != observations ||
        static_cast<std::size_t>(flows.shape[0]) != observations) {
      throw std::invalid_argument("historical NumPy array shapes do not match");
    }
    return {
        std::span<const std::int64_t>(static_cast<const std::int64_t*>(timestamps.ptr), observations),
        portfolio_engine::MatrixView(
            std::span<const double>(static_cast<const double*>(prices.ptr), observations * assets),
            observations, assets),
        portfolio_engine::MatrixView(
            std::span<const double>(static_cast<const double*>(quantities.ptr),
                                    observations * assets),
            observations, assets),
        std::span<const double>(static_cast<const double*>(cash.ptr), observations),
        std::span<const double>(static_cast<const double*>(flows.ptr), observations)};
  }
};

ArrayHistory inspect_history(
    const py::array_t<std::int64_t, py::array::c_style>& timestamps,
    const py::array_t<double, py::array::c_style>& prices,
    const py::array_t<double, py::array::c_style>& quantities,
    const py::array_t<double, py::array::c_style>& cash,
    const py::array_t<double, py::array::c_style>& flows) {
  return {timestamps.request(), prices.request(), quantities.request(), cash.request(),
          flows.request()};
}

py::array_t<double> matrix_array(const portfolio_engine::Matrix& matrix) {
  py::array_t<double> output(
      {static_cast<py::ssize_t>(matrix.rows), static_cast<py::ssize_t>(matrix.columns)});
  if (!matrix.data.empty()) {
    std::memcpy(output.mutable_data(), matrix.data.data(), matrix.data.size() * sizeof(double));
  }
  return output;
}

py::array_t<double> vector_array(const std::vector<double>& values) {
  py::array_t<double> output(static_cast<py::ssize_t>(values.size()));
  if (!values.empty()) {
    std::memcpy(output.mutable_data(), values.data(), values.size() * sizeof(double));
  }
  return output;
}

portfolio_engine::SimulationResult simulate_numpy(
    const py::array_t<double, py::array::c_style>& weights,
    const py::array_t<double, py::array::c_style>& return_history,
    const py::array_t<double, py::array::c_style>& covariance,
    const portfolio_engine::SimulationConfig& config) {
  const auto weight_info = weights.request();
  const auto history_info = return_history.request();
  const auto covariance_info = covariance.request();
  if (weight_info.ndim != 1 || history_info.ndim != 2 || covariance_info.ndim != 2) {
    throw std::invalid_argument("simulation expects a vector and two matrices");
  }
  const auto assets = static_cast<std::size_t>(weight_info.shape[0]);
  const auto observations = static_cast<std::size_t>(history_info.shape[1]);
  const auto history_assets = static_cast<std::size_t>(history_info.shape[0]);
  const auto covariance_rows = static_cast<std::size_t>(covariance_info.shape[0]);
  const auto covariance_columns = static_cast<std::size_t>(covariance_info.shape[1]);
  const auto weight_view = std::span<const double>(
      static_cast<const double*>(weight_info.ptr), assets);
  const portfolio_engine::MatrixView history_view(
      std::span<const double>(static_cast<const double*>(history_info.ptr),
                              history_assets * observations),
      history_assets, observations);
  const portfolio_engine::MatrixView covariance_view(
      std::span<const double>(static_cast<const double*>(covariance_info.ptr),
                              covariance_rows * covariance_columns),
      covariance_rows, covariance_columns);
  py::gil_scoped_release release;
  return portfolio_engine::simulate(weight_view, history_view, covariance_view, config);
}

}  // namespace

PYBIND11_MODULE(portfolio_engine, m) {
  m.doc() = "Stateful C++20 portfolio analytics engine";

  py::class_<portfolio_engine::DrawdownResult>(m, "DrawdownResult")
      .def_readonly("drawdown", &portfolio_engine::DrawdownResult::drawdown)
      .def_readonly("peak_index", &portfolio_engine::DrawdownResult::peak_index)
      .def_readonly("trough_index", &portfolio_engine::DrawdownResult::trough_index)
      .def_readonly("recovery_index", &portfolio_engine::DrawdownResult::recovery_index)
      .def_readonly("drawdown_duration", &portfolio_engine::DrawdownResult::drawdown_duration)
      .def_readonly("recovery_duration", &portfolio_engine::DrawdownResult::recovery_duration);

  py::class_<portfolio_engine::RiskContributionResult>(m, "RiskContributionResult")
      .def_readonly("portfolio_variance", &portfolio_engine::RiskContributionResult::portfolio_variance)
      .def_readonly("portfolio_volatility", &portfolio_engine::RiskContributionResult::portfolio_volatility)
      .def_readonly("marginal_contribution",
                    &portfolio_engine::RiskContributionResult::marginal_contribution)
      .def_readonly("component_contribution",
                    &portfolio_engine::RiskContributionResult::component_contribution)
      .def_readonly("percent_contribution",
                    &portfolio_engine::RiskContributionResult::percent_contribution);

  py::class_<portfolio_engine::ScenarioPositionImpact>(m, "ScenarioPositionImpact")
      .def_readonly("symbol", &portfolio_engine::ScenarioPositionImpact::symbol)
      .def_readonly("starting_value", &portfolio_engine::ScenarioPositionImpact::starting_value)
      .def_readonly("shock", &portfolio_engine::ScenarioPositionImpact::shock)
      .def_readonly("pnl", &portfolio_engine::ScenarioPositionImpact::pnl)
      .def_readonly("ending_value", &portfolio_engine::ScenarioPositionImpact::ending_value);

  py::class_<portfolio_engine::ScenarioResult>(m, "ScenarioResult")
      .def_readonly("starting_value", &portfolio_engine::ScenarioResult::starting_value)
      .def_readonly("ending_value", &portfolio_engine::ScenarioResult::ending_value)
      .def_readonly("pnl", &portfolio_engine::ScenarioResult::pnl)
      .def_readonly("percent_pnl", &portfolio_engine::ScenarioResult::percent_pnl)
      .def_readonly("impacts", &portfolio_engine::ScenarioResult::impacts);

  py::class_<portfolio_engine::EngineConfig>(m, "EngineConfig")
      .def(py::init([](double annualization_factor, double confidence_level) {
        return portfolio_engine::EngineConfig{annualization_factor, confidence_level};
      }), py::arg("annualization_factor") = 252.0, py::arg("confidence_level") = 0.95)
      .def_readwrite("annualization_factor", &portfolio_engine::EngineConfig::annualization_factor)
      .def_readwrite("confidence_level", &portfolio_engine::EngineConfig::confidence_level);

  py::class_<portfolio_engine::PortfolioSnapshot>(m, "PortfolioSnapshot")
      .def_readonly("timestamp", &portfolio_engine::PortfolioSnapshot::timestamp)
      .def_readonly("prices", &portfolio_engine::PortfolioSnapshot::prices)
      .def_readonly("quantities", &portfolio_engine::PortfolioSnapshot::quantities)
      .def_readonly("position_values", &portfolio_engine::PortfolioSnapshot::position_values)
      .def_readonly("weights", &portfolio_engine::PortfolioSnapshot::weights)
      .def_readonly("cash", &portfolio_engine::PortfolioSnapshot::cash)
      .def_readonly("invested_value", &portfolio_engine::PortfolioSnapshot::invested_value)
      .def_readonly("total_value", &portfolio_engine::PortfolioSnapshot::total_value);

  py::class_<portfolio_engine::RiskSnapshot>(m, "RiskSnapshot")
      .def_readonly("observations", &portfolio_engine::RiskSnapshot::observations)
      .def_readonly("annualized_volatility", &portfolio_engine::RiskSnapshot::annualized_volatility)
      .def_readonly("maximum_drawdown", &portfolio_engine::RiskSnapshot::maximum_drawdown)
      .def_readonly("value_at_risk", &portfolio_engine::RiskSnapshot::value_at_risk)
      .def_readonly("expected_shortfall", &portfolio_engine::RiskSnapshot::expected_shortfall);

  py::class_<portfolio_engine::ValuationResult>(m, "ValuationResult")
      .def_property_readonly("position_values", [](const portfolio_engine::ValuationResult& result) {
        return matrix_array(result.position_values);
      })
      .def_property_readonly("weights", [](const portfolio_engine::ValuationResult& result) {
        return matrix_array(result.weights);
      })
      .def_property_readonly("invested_values", [](const portfolio_engine::ValuationResult& result) {
        return vector_array(result.invested_values);
      })
      .def_property_readonly("total_values", [](const portfolio_engine::ValuationResult& result) {
        return vector_array(result.total_values);
      })
      .def_property_readonly("returns", [](const portfolio_engine::ValuationResult& result) {
        return vector_array(result.returns);
      });

  py::enum_<portfolio_engine::CovarianceMethod>(m, "CovarianceMethod")
      .value("SAMPLE", portfolio_engine::CovarianceMethod::kSample)
      .value("EXPONENTIALLY_WEIGHTED",
             portfolio_engine::CovarianceMethod::kExponentiallyWeighted)
      .value("SHRINKAGE", portfolio_engine::CovarianceMethod::kShrinkage)
      .value("DIAGONAL", portfolio_engine::CovarianceMethod::kDiagonal);

  py::class_<portfolio_engine::CovarianceRequest>(m, "CovarianceRequest")
      .def(py::init([](portfolio_engine::CovarianceMethod method, double decay_factor,
                       double shrinkage_intensity) {
        return portfolio_engine::CovarianceRequest{method, decay_factor, shrinkage_intensity};
      }), py::arg("method") = portfolio_engine::CovarianceMethod::kSample,
          py::arg("decay_factor") = 0.94, py::arg("shrinkage_intensity") = 0.10)
      .def_readwrite("method", &portfolio_engine::CovarianceRequest::method)
      .def_readwrite("decay_factor", &portfolio_engine::CovarianceRequest::decay_factor)
      .def_readwrite("shrinkage_intensity",
                     &portfolio_engine::CovarianceRequest::shrinkage_intensity);

  py::class_<portfolio_engine::CovarianceDiagnostics>(m, "CovarianceDiagnostics")
      .def_readonly("observations", &portfolio_engine::CovarianceDiagnostics::observations)
      .def_readonly("assets", &portfolio_engine::CovarianceDiagnostics::assets)
      .def_readonly("symmetric", &portfolio_engine::CovarianceDiagnostics::symmetric)
      .def_readonly("positive_semidefinite",
                    &portfolio_engine::CovarianceDiagnostics::positive_semidefinite)
      .def_readonly("spectral_diagnostics_exact",
                    &portfolio_engine::CovarianceDiagnostics::spectral_diagnostics_exact)
      .def_readonly("smallest_eigenvalue",
                    &portfolio_engine::CovarianceDiagnostics::smallest_eigenvalue)
      .def_readonly("largest_eigenvalue",
                    &portfolio_engine::CovarianceDiagnostics::largest_eigenvalue)
      .def_readonly("condition_number", &portfolio_engine::CovarianceDiagnostics::condition_number)
      .def_readonly("effective_rank", &portfolio_engine::CovarianceDiagnostics::effective_rank)
      .def_readonly("shrinkage_intensity",
                    &portfolio_engine::CovarianceDiagnostics::shrinkage_intensity);

  py::class_<portfolio_engine::CovarianceEstimate>(m, "CovarianceEstimate")
      .def_property_readonly("covariance", [](const portfolio_engine::CovarianceEstimate& result) {
        return matrix_array(result.covariance);
      })
      .def_readonly("diagnostics", &portfolio_engine::CovarianceEstimate::diagnostics);

  py::class_<portfolio_engine::RunningStatistics>(m, "RunningStatistics")
      .def(py::init<>())
      .def("add_observation", &portfolio_engine::RunningStatistics::add)
      .def("initialize", [](portfolio_engine::RunningStatistics& self,
                            const std::vector<double>& values) { self.initialize(values); })
      .def("reset", &portfolio_engine::RunningStatistics::reset)
      .def_property_readonly("count", &portfolio_engine::RunningStatistics::count)
      .def_property_readonly("mean", &portfolio_engine::RunningStatistics::mean)
      .def_property_readonly("sample_variance",
                             &portfolio_engine::RunningStatistics::sample_variance)
      .def_property_readonly("sample_standard_deviation",
                             &portfolio_engine::RunningStatistics::sample_standard_deviation);

  py::class_<portfolio_engine::RunningCovariance>(m, "RunningCovariance")
      .def(py::init<>())
      .def("add_observation", &portfolio_engine::RunningCovariance::add)
      .def("initialize", [](portfolio_engine::RunningCovariance& self,
                            const std::vector<double>& left,
                            const std::vector<double>& right) { self.initialize(left, right); })
      .def("reset", &portfolio_engine::RunningCovariance::reset)
      .def_property_readonly("count", &portfolio_engine::RunningCovariance::count)
      .def_property_readonly("covariance", &portfolio_engine::RunningCovariance::covariance)
      .def_property_readonly("beta", &portfolio_engine::RunningCovariance::beta);

  py::class_<portfolio_engine::RollingVolatility>(m, "RollingVolatility")
      .def(py::init<std::size_t, double>(), py::arg("window"),
           py::arg("periods_per_year") = 252.0)
      .def("add_observation", &portfolio_engine::RollingVolatility::add)
      .def("initialize", [](portfolio_engine::RollingVolatility& self,
                            const std::vector<double>& values) { self.initialize(values); })
      .def_property_readonly("count", &portfolio_engine::RollingVolatility::count)
      .def_property_readonly("window", &portfolio_engine::RollingVolatility::window)
      .def_property_readonly("volatility", &portfolio_engine::RollingVolatility::volatility);

  py::class_<portfolio_engine::PortfolioAnalyticsEngine>(m, "PortfolioAnalyticsEngine")
      .def(py::init<portfolio_engine::EngineConfig>(), py::arg("config") = portfolio_engine::EngineConfig{})
      .def("load_history",
           [](portfolio_engine::PortfolioAnalyticsEngine& self, std::vector<std::string> symbols,
              const py::array_t<std::int64_t, py::array::c_style>& timestamps,
              const py::array_t<double, py::array::c_style>& prices,
              const py::array_t<double, py::array::c_style>& quantities,
              const py::array_t<double, py::array::c_style>& cash_balances,
              const py::array_t<double, py::array::c_style>& external_cash_flows) {
             const auto arrays = inspect_history(timestamps, prices, quantities, cash_balances,
                                                 external_cash_flows);
             const auto history = arrays.view();
             py::gil_scoped_release release;
             self.load_history(std::move(symbols), history);
           },
           py::arg("symbols"), py::arg("timestamps").noconvert(), py::arg("prices").noconvert(),
           py::arg("quantities").noconvert(), py::arg("cash_balances").noconvert(),
           py::arg("external_cash_flows").noconvert())
      .def("apply_price_update",
           [](portfolio_engine::PortfolioAnalyticsEngine& self, std::size_t asset,
              std::int64_t timestamp, double price) {
             py::gil_scoped_release release;
             self.apply_price_update({asset, timestamp, price});
           })
      .def("apply_position_update",
           [](portfolio_engine::PortfolioAnalyticsEngine& self, std::size_t asset,
              std::int64_t timestamp, double quantity_delta) {
             py::gil_scoped_release release;
             self.apply_position_update({asset, timestamp, quantity_delta});
           })
      .def("apply_cash_update",
           [](portfolio_engine::PortfolioAnalyticsEngine& self, std::int64_t timestamp,
              double amount) {
             py::gil_scoped_release release;
             self.apply_cash_update({timestamp, amount});
           })
      .def_property_readonly("empty", &portfolio_engine::PortfolioAnalyticsEngine::empty)
      .def_property_readonly("asset_count", &portfolio_engine::PortfolioAnalyticsEngine::asset_count)
      .def("snapshot", &portfolio_engine::PortfolioAnalyticsEngine::snapshot,
           py::call_guard<py::gil_scoped_release>())
      .def("calculate_risk", &portfolio_engine::PortfolioAnalyticsEngine::calculate_risk,
           py::call_guard<py::gil_scoped_release>())
      .def("run_scenario", [](const portfolio_engine::PortfolioAnalyticsEngine& self,
                              const std::vector<double>& shocks) {
        py::gil_scoped_release release;
        return self.run_scenario(shocks);
      })
      .def_property_readonly("portfolio_returns",
                             &portfolio_engine::PortfolioAnalyticsEngine::portfolio_returns)
      .def_property_readonly("value_history",
                             &portfolio_engine::PortfolioAnalyticsEngine::value_history);

  py::enum_<portfolio_engine::SimulationMethod>(m, "SimulationMethod")
      .value("NORMAL", portfolio_engine::SimulationMethod::kNormal)
      .value("HISTORICAL_BOOTSTRAP", portfolio_engine::SimulationMethod::kHistoricalBootstrap);

  py::class_<portfolio_engine::SimulationConfig>(m, "SimulationConfig")
      .def(py::init([](std::size_t paths, std::size_t horizon_days, std::uint64_t seed,
                       std::size_t thread_count, double confidence_level,
                       portfolio_engine::SimulationMethod method) {
        return portfolio_engine::SimulationConfig{paths, horizon_days, seed, thread_count,
                                                   confidence_level, method};
      }), py::arg("paths") = 10000, py::arg("horizon_days") = 1, py::arg("seed") = 42,
          py::arg("thread_count") = 1, py::arg("confidence_level") = 0.95,
          py::arg("method") = portfolio_engine::SimulationMethod::kNormal)
      .def_readwrite("paths", &portfolio_engine::SimulationConfig::paths)
      .def_readwrite("horizon_days", &portfolio_engine::SimulationConfig::horizon_days)
      .def_readwrite("seed", &portfolio_engine::SimulationConfig::seed)
      .def_readwrite("thread_count", &portfolio_engine::SimulationConfig::thread_count)
      .def_readwrite("confidence_level", &portfolio_engine::SimulationConfig::confidence_level)
      .def_readwrite("method", &portfolio_engine::SimulationConfig::method);

  py::class_<portfolio_engine::SimulationResult>(m, "SimulationResult")
      .def_property_readonly("path_returns", [](const portfolio_engine::SimulationResult& result) {
        return vector_array(result.path_returns);
      })
      .def_readonly("value_at_risk", &portfolio_engine::SimulationResult::value_at_risk)
      .def_readonly("expected_shortfall", &portfolio_engine::SimulationResult::expected_shortfall)
      .def_readonly("minimum", &portfolio_engine::SimulationResult::minimum)
      .def_readonly("maximum", &portfolio_engine::SimulationResult::maximum)
      .def_readonly("mean", &portfolio_engine::SimulationResult::mean)
      .def_readonly("standard_deviation", &portfolio_engine::SimulationResult::standard_deviation)
      .def_readonly("paths", &portfolio_engine::SimulationResult::paths)
      .def_readonly("horizon_days", &portfolio_engine::SimulationResult::horizon_days)
      .def_readonly("seed", &portfolio_engine::SimulationResult::seed)
      .def_readonly("thread_count", &portfolio_engine::SimulationResult::thread_count)
      .def_readonly("method", &portfolio_engine::SimulationResult::method);

  m.def("value_history",
        [](const py::array_t<std::int64_t, py::array::c_style>& timestamps,
           const py::array_t<double, py::array::c_style>& prices,
           const py::array_t<double, py::array::c_style>& quantities,
           const py::array_t<double, py::array::c_style>& cash_balances,
           const py::array_t<double, py::array::c_style>& external_cash_flows) {
          const auto arrays = inspect_history(timestamps, prices, quantities, cash_balances,
                                              external_cash_flows);
          const auto history = arrays.view();
          py::gil_scoped_release release;
          return portfolio_engine::value_history(history);
        },
        py::arg("timestamps").noconvert(), py::arg("prices").noconvert(),
        py::arg("quantities").noconvert(), py::arg("cash_balances").noconvert(),
        py::arg("external_cash_flows").noconvert());

  m.def("simulate", &simulate_numpy, py::arg("weights").noconvert(),
        py::arg("return_history").noconvert(), py::arg("covariance").noconvert(),
        py::arg("config"));

  m.def("estimate_covariance",
        [](const py::array_t<double, py::array::c_style>& return_history,
           const portfolio_engine::CovarianceRequest& request) {
          const auto info = return_history.request();
          if (info.ndim != 2) {
            throw std::invalid_argument("return_history must be a two-dimensional matrix");
          }
          const auto assets = static_cast<std::size_t>(info.shape[0]);
          const auto observations = static_cast<std::size_t>(info.shape[1]);
          const portfolio_engine::MatrixView history(
              std::span<const double>(static_cast<const double*>(info.ptr),
                                      assets * observations),
              assets, observations);
          py::gil_scoped_release release;
          return portfolio_engine::estimate_covariance(history, request);
        },
        py::arg("return_history").noconvert(),
        py::arg("request") = portfolio_engine::CovarianceRequest{});

  m.def("calculate_returns", [](const std::vector<double>& prices) {
    return portfolio_engine::calculate_returns(as_span(prices));
  }, py::call_guard<py::gil_scoped_release>());
  m.def("cumulative_return", [](const std::vector<double>& returns) {
    return portfolio_engine::cumulative_return(as_span(returns));
  }, py::call_guard<py::gil_scoped_release>());
  m.def("annualized_return", [](const std::vector<double>& returns, double periods_per_year) {
    return portfolio_engine::annualized_return(as_span(returns), periods_per_year);
  }, py::arg("returns"), py::arg("periods_per_year") = 252.0,
     py::call_guard<py::gil_scoped_release>());
  m.def("annualized_volatility", [](const std::vector<double>& returns, double periods_per_year) {
    return portfolio_engine::annualized_volatility(as_span(returns), periods_per_year);
  }, py::arg("returns"), py::arg("periods_per_year") = 252.0,
     py::call_guard<py::gil_scoped_release>());
  m.def("sharpe_ratio", [](const std::vector<double>& returns, double risk_free_rate,
                           double periods_per_year) {
    return portfolio_engine::sharpe_ratio(as_span(returns), risk_free_rate, periods_per_year);
  }, py::arg("returns"), py::arg("risk_free_rate") = 0.0,
     py::arg("periods_per_year") = 252.0, py::call_guard<py::gil_scoped_release>());
  m.def("sortino_ratio", [](const std::vector<double>& returns, double risk_free_rate,
                            double periods_per_year) {
    return portfolio_engine::sortino_ratio(as_span(returns), risk_free_rate, periods_per_year);
  }, py::arg("returns"), py::arg("risk_free_rate") = 0.0,
     py::arg("periods_per_year") = 252.0, py::call_guard<py::gil_scoped_release>());
  m.def("maximum_drawdown", [](const std::vector<double>& values) {
    return portfolio_engine::maximum_drawdown(as_span(values));
  }, py::call_guard<py::gil_scoped_release>());
  m.def("beta", [](const std::vector<double>& asset_returns,
                   const std::vector<double>& benchmark_returns) {
    return portfolio_engine::beta(as_span(asset_returns), as_span(benchmark_returns));
  }, py::call_guard<py::gil_scoped_release>());
  m.def("historical_var", [](const std::vector<double>& returns, double confidence_level) {
    return portfolio_engine::historical_var(as_span(returns), confidence_level);
  }, py::call_guard<py::gil_scoped_release>());
  m.def("expected_shortfall", [](const std::vector<double>& returns, double confidence_level) {
    return portfolio_engine::expected_shortfall(as_span(returns), confidence_level);
  }, py::call_guard<py::gil_scoped_release>());
  m.def("covariance_matrix", &portfolio_engine::covariance_matrix,
        py::call_guard<py::gil_scoped_release>());
  m.def("correlation_matrix", &portfolio_engine::correlation_matrix,
        py::call_guard<py::gil_scoped_release>());
  m.def("risk_contributions", [](const std::vector<double>& weights,
                                 const std::vector<std::vector<double>>& covariance) {
    return portfolio_engine::risk_contributions(as_span(weights), covariance);
  }, py::call_guard<py::gil_scoped_release>());
  m.def("apply_scenario", [](const std::vector<std::string>& symbols,
                             const std::vector<double>& values,
                             const std::vector<std::string>& sectors,
                             const std::vector<std::string>& asset_types,
                             const std::unordered_map<std::string, double>& symbol_shocks,
                             const std::unordered_map<std::string, double>& sector_shocks,
                             const std::unordered_map<std::string, double>& asset_type_shocks) {
    return portfolio_engine::apply_scenario(symbols, as_span(values), sectors, asset_types,
                                            symbol_shocks, sector_shocks, asset_type_shocks);
  }, py::call_guard<py::gil_scoped_release>());
}
