from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

import numpy as np


def generate_prices(assets: int, observations: int) -> np.ndarray:
    prices = np.empty((observations, assets), dtype=np.float64)
    for asset in range(assets):
        price = 50.0 + asset % 100
        for observation in range(observations):
            centered = (observation * 17 + asset * 13) % 23 - 11
            price *= 1.0 + centered / 100_000.0
            prices[observation, asset] = price
    return prices


def generate_returns(assets: int, observations: int) -> np.ndarray:
    asset = np.arange(assets, dtype=np.int64)[:, None]
    observation = np.arange(observations, dtype=np.int64)[None, :]
    return (((observation * 17 + asset * 13) % 41) - 20).astype(np.float64) / 10_000.0


def measure(function: Callable[[], object], repetitions: int) -> tuple[float, float]:
    for _ in range(2):
        function()
    samples: list[float] = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        function()
        samples.append((time.perf_counter_ns() - start) / 1_000_000.0)
    samples.sort()
    p95 = samples[max(0, int(np.ceil(0.95 * len(samples))) - 1)]
    return statistics.median(samples), p95


def batch_valuation(
    prices: np.ndarray, quantities: np.ndarray, cash: np.ndarray, flows: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    position_values = prices * quantities
    totals = position_values.sum(axis=1) + cash
    returns = (totals[1:] - flows[1:]) / totals[:-1] - 1.0
    return position_values, totals, returns


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    workloads = [("small", 10, 504), ("medium", 100, 1260)]
    if args.full:
        workloads += [("large", 1000, 1260), ("stress", 5000, 252)]
    measurements: list[dict[str, object]] = []
    for name, assets, observations in workloads:
        prices = generate_prices(assets, observations)
        quantities = np.full_like(prices, 10.0)
        cash = np.full(observations, 10_000.0)
        flows = np.zeros(observations)
        repetitions = 15 if assets <= 100 else 5

        median, p95 = measure(
            partial(batch_valuation, prices, quantities, cash, flows), repetitions
        )
        measurements.append(
            dict(
                operation="batch_valuation",
                workload=name,
                assets=assets,
                observations=observations,
                paths=0,
                repetitions=repetitions,
                median_ms=median,
                p95_ms=p95,
            )
        )
        if assets <= (1000 if args.full else 100):
            returns = generate_returns(assets, observations)
            median, p95 = measure(partial(np.cov, returns, ddof=1), repetitions)
            measurements.append(
                dict(
                    operation="sample_covariance",
                    workload=name,
                    assets=assets,
                    observations=observations,
                    paths=0,
                    repetitions=repetitions,
                    median_ms=median,
                    p95_ms=p95,
                )
            )
    payload = {
        "schema_version": 1,
        "language": f"Python {platform.python_version()} / NumPy {np.__version__}",
        "compiler": platform.python_compiler(),
        "thread_count": None,
        "warmup_repetitions": 2,
        "measurements": measurements,
    }
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
