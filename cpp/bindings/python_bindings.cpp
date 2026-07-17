#include "portfolio_engine/analytics.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

namespace {

std::span<const double> as_span(const std::vector<double>& values) {
  return std::span<const double>(values.data(), values.size());
}

}  // namespace

PYBIND11_MODULE(portfolio_engine, m) {
  m.doc() = "C++ portfolio analytics engine";

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

  m.def("calculate_returns", [](const std::vector<double>& prices) {
    return portfolio_engine::calculate_returns(as_span(prices));
  });
  m.def("cumulative_return", [](const std::vector<double>& returns) {
    return portfolio_engine::cumulative_return(as_span(returns));
  });
  m.def("annualized_return", [](const std::vector<double>& returns, double periods_per_year) {
    return portfolio_engine::annualized_return(as_span(returns), periods_per_year);
  }, py::arg("returns"), py::arg("periods_per_year") = 252.0);
  m.def("annualized_volatility", [](const std::vector<double>& returns, double periods_per_year) {
    return portfolio_engine::annualized_volatility(as_span(returns), periods_per_year);
  }, py::arg("returns"), py::arg("periods_per_year") = 252.0);
  m.def("sharpe_ratio", [](const std::vector<double>& returns, double risk_free_rate,
                           double periods_per_year) {
    return portfolio_engine::sharpe_ratio(as_span(returns), risk_free_rate, periods_per_year);
  }, py::arg("returns"), py::arg("risk_free_rate") = 0.0, py::arg("periods_per_year") = 252.0);
  m.def("sortino_ratio", [](const std::vector<double>& returns, double risk_free_rate,
                            double periods_per_year) {
    return portfolio_engine::sortino_ratio(as_span(returns), risk_free_rate, periods_per_year);
  }, py::arg("returns"), py::arg("risk_free_rate") = 0.0, py::arg("periods_per_year") = 252.0);
  m.def("maximum_drawdown", [](const std::vector<double>& values) {
    return portfolio_engine::maximum_drawdown(as_span(values));
  });
  m.def("beta", [](const std::vector<double>& asset_returns,
                   const std::vector<double>& benchmark_returns) {
    return portfolio_engine::beta(as_span(asset_returns), as_span(benchmark_returns));
  });
  m.def("historical_var", [](const std::vector<double>& returns, double confidence_level) {
    return portfolio_engine::historical_var(as_span(returns), confidence_level);
  });
  m.def("expected_shortfall", [](const std::vector<double>& returns, double confidence_level) {
    return portfolio_engine::expected_shortfall(as_span(returns), confidence_level);
  });
  m.def("covariance_matrix", &portfolio_engine::covariance_matrix);
  m.def("correlation_matrix", &portfolio_engine::correlation_matrix);
  m.def("risk_contributions", [](const std::vector<double>& weights,
                                 const std::vector<std::vector<double>>& covariance) {
    return portfolio_engine::risk_contributions(as_span(weights), covariance);
  });
  m.def("apply_scenario", [](const std::vector<std::string>& symbols,
                             const std::vector<double>& values,
                             const std::vector<std::string>& sectors,
                             const std::vector<std::string>& asset_types,
                             const std::unordered_map<std::string, double>& symbol_shocks,
                             const std::unordered_map<std::string, double>& sector_shocks,
                             const std::unordered_map<std::string, double>& asset_type_shocks) {
    return portfolio_engine::apply_scenario(symbols, as_span(values), sectors, asset_types,
                                            symbol_shocks, sector_shocks, asset_type_shocks);
  });
}

