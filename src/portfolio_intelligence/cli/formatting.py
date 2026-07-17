from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def print_json(data: Any) -> None:
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    console.print(json.dumps(payload, indent=2, default=str))


def money(value: float) -> str:
    return f"${value:,.2f}"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    output = Table(title=title)
    for column in columns:
        output.add_column(column)
    for row in rows:
        output.add_row(*row)
    console.print(output)
