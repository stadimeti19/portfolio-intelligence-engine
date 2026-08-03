from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from portfolio_intelligence.domain.explanations import ExplanationRequest, PortfolioExplanation


class ExplanationCache:
    """Local cache for already-paid explanation responses.

    Its key is derived only from the already privacy-filtered request content.
    Stored entries contain the structured response, never raw transactions or
    credentials.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def key_for(self, request: ExplanationRequest, model: str) -> str:
        content = {
            "structured_report_content": request.report_content,
            "explanation_type": request.explanation_type.value,
            "model": model,
            "prompt_version": request.prompt_version,
        }
        serialized = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def read(self, key: str) -> PortfolioExplanation | None:
        path = self.directory / f"{key}.json"
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
            return PortfolioExplanation.model_validate(content["explanation"])
        except (FileNotFoundError, OSError, ValueError, KeyError, ValidationError):
            return None

    def write(self, key: str, explanation: PortfolioExplanation) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{key}.json"
        payload = {"explanation": explanation.model_dump(mode="json")}
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
