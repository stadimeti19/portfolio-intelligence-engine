from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text())
    return {(item["operation"], item["workload"]): item for item in payload["measurements"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cpp", type=Path)
    parser.add_argument("python", type=Path)
    args = parser.parse_args()
    cpp = load(args.cpp)
    python = load(args.python)
    print("| Operation | Workload | C++ median (ms) | NumPy median (ms) | NumPy/C++ |")
    print("|---|---:|---:|---:|---:|")
    for key in sorted(cpp.keys() & python.keys()):
        cpp_value = float(cpp[key]["median_ms"])
        python_value = float(python[key]["median_ms"])
        ratio = python_value / cpp_value if cpp_value else float("inf")
        print(
            f"| {key[0]} | {key[1]} | {cpp_value:.3f} | "
            f"{python_value:.3f} | {ratio:.2f}x |"
        )


if __name__ == "__main__":
    main()
