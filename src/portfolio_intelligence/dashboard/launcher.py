from __future__ import annotations

import importlib.util
import subprocess
import sys
from importlib.resources import files


class DashboardDependencyError(RuntimeError):
    pass


def launch_dashboard(*, port: int = 8501, address: str = "localhost") -> int:
    if importlib.util.find_spec("streamlit") is None:
        raise DashboardDependencyError(
            'Streamlit is not installed. Install it with: pip install -e ".[dashboard]"'
        )
    app_path = files("portfolio_intelligence").joinpath("dashboard/app.py")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            address,
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ],
        check=False,
    )
    return result.returncode
