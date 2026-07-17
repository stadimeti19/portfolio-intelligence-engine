from __future__ import annotations

from pathlib import Path

import yaml

from portfolio_intelligence.domain.scenarios import ScenarioDefinition


def load_scenarios(path: str | Path) -> dict[str, ScenarioDefinition]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw_scenarios = data.get("scenarios", {})
    scenarios: dict[str, ScenarioDefinition] = {}
    for name, payload in raw_scenarios.items():
        scenarios[name] = ScenarioDefinition(name=name, **payload)
    return scenarios
