"""Import-boundary coverage for the speciation service."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_speciation_service_imports_in_clean_process() -> None:
    backend_dir = Path(__file__).resolve().parents[4]

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.services.species.speciation import SpeciationService; "
                "print(SpeciationService.__name__)"
            ),
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("SpeciationService")
