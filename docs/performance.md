# Native Engine Performance

This report records measurements, including results that do not favor C++. It does not treat a
different algorithm as a language speed comparison.

## Why These Workloads Are Native

Batch valuation provides one validated representation shared by the stateful engine, Python API,
and native executable. Its main value is coherence and predictable allocation, not a demonstrated
speedup over NumPy. Online statistics and state updates avoid reconstructing complete histories.
Covariance estimators centralize methodology and diagnostics, although the current scalar estimator
does not outperform accelerated NumPy. Simulation is native because it performs path-level random
generation, correlation, compounding, and tail aggregation and scales across bounded worker threads.

Python intentionally retains CLI commands, configuration, providers, CSV and brokerage adapters,
the transaction ledger, SQLAlchemy/SQLite, reports, dashboard code, explanations, and fallback
logic. Optimization remains unimplemented until a tested convex solver is selected.

## Methodology

Measurements below were taken on 2026-08-02 in this workspace:

- Apple Silicon `arm64`, macOS 15.6.1 (the sandbox did not expose the exact CPU model);
- Apple Clang 17.0.0;
- CMake Release build with compiler defaults plus strict warnings;
- Python 3.11.15 and NumPy 2.4.6 using Apple's Accelerate backend;
- 8 hardware threads reported by `std::thread::hardware_concurrency`;
- two warm-up iterations;
- 15 repetitions for valuation/covariance/running variance and 7 for simulation;
- median and p95 wall-clock time from `steady_clock`/`perf_counter_ns`;
- deterministic generated data, identical shapes and valuation/covariance formulas.

Run `make benchmark-report` to regenerate quick results. Passing `--full` to both benchmark
executables adds the 1,000- and 5,000-asset inputs. JSON files are written under `build/` and are
not source data.

## Results

| Operation | Workload | C++ median | C++ p95 | NumPy median | NumPy/C++ |
|---|---:|---:|---:|---:|---:|
| Batch valuation | 10 assets × 504 days | 0.0116 ms | 0.0118 ms | 0.0082 ms | 0.70× |
| Batch valuation | 100 assets × 1,260 days | 0.3020 ms | 0.5088 ms | 0.0650 ms | 0.21× |
| Sample covariance | 10 assets × 504 days | 0.0457 ms | 0.0585 ms | 0.0232 ms | 0.51× |
| Sample covariance | 100 assets × 1,260 days | 5.9177 ms | 7.3233 ms | 0.2500 ms | 0.04× |

These results do **not** support a C++ speedup claim for batch valuation or sample covariance.
NumPy is already faster, especially where Accelerate supplies optimized matrix operations. Small
portfolio latency is negligible in both implementations. The native versions remain useful as the
state engine's canonical kernels, but Python workflows should not cross the extension boundary only
to make these isolated operations faster.

Native-only throughput measurements:

| Operation | Configuration | 1 thread median | Auto (8) median | Scaling |
|---|---:|---:|---:|---:|
| Normal simulation | 10 assets, 100,000 paths, 10 days | 142.003 ms | 34.414 ms | 4.13× |
| Running variance | 1,000,000 observations | 5.090 ms | n/a | 196.5M observations/s |

The simulation measurement supports a native thread-scaling claim, not a C++-versus-NumPy speedup
claim. A language comparison is withheld because the current NumPy random generator and vectorized
path implementation would not use the same stream-partitioning algorithm.

Fixed block streams make the path array exactly equal for one and four threads in native and Python
binding tests. At 100,000 paths the 8-thread execution is materially faster. The benchmark does not
yet characterize the small-path crossover point, so no claim is made for small simulations.

## Memory And Allocation Status

The batch API allocates two `observations × assets` output matrices plus three vectors. The stateful
engine retains total values/returns and only the latest per-asset snapshot; it does not retain both
full output matrices. Simulation allocates one `paths` output vector plus per-worker `assets` scratch
vectors and a single Cholesky factor. NumPy inputs are viewed without conversion and copied only
when the engine takes ownership.

Peak resident memory was not successfully exposed by the sandbox's `/usr/bin/time` implementation,
so this revision makes no measured memory-reduction claim. Allocation counts and large-workload peak
RSS remain benchmark gaps.

## Reproducibility And Limitations

- Normal simulation uses `std::mt19937_64` seeded per fixed 256-path block. Each worker owns its RNG;
  no mutable generator is shared.
- Thread count changes scheduling but not block seeds or output positions.
- Floating-point output is deterministic for a fixed build/toolchain; libm and standard-library
  differences can affect cross-platform bitwise equality.
- Shrinkage currently uses a caller-provided fixed intensity and a diagonal target. It is not an
  automatically estimated Ledoit-Wolf implementation.
- Exact eigenvalue diagnostics use a Jacobi solver for at most 64 assets. Larger matrices still get
  symmetry, PSD, and participation-ratio diagnostics; spectral fields are reported unavailable.
- The native covariance implementation is scalar and is a clear optimization candidate only after
  choosing a portable BLAS/Eigen dependency.
- Student-t simulation, event checkpoints, solver-backed optimization, benchmark boundary overhead,
  allocation profiling, and a Python-comparable simulation algorithm remain future work.

## Validation Status

On the measurement host, the native Release suite and demo passed, as did separate AddressSanitizer,
UndefinedBehaviorSanitizer, and ThreadSanitizer builds. The five new extension differential tests and
the four existing binding-reference tests passed against the freshly built module. The full Python
suite passed 82 tests; the new extension-only module was skipped in that interpreter because it was
not installed there.

The libFuzzer source and opt-in CMake target are present, but the local Xcode toolchain did not ship
`libclang_rt.fuzzer_osx.a`, so the fuzz executable could not link and no fuzz-duration claim is made.
CI can build the target with a Clang distribution that includes the libFuzzer runtime.
