import ast
from pathlib import Path


SPECIES_DIR = Path(__file__).resolve().parent.parent
SPECIATION_PATH = SPECIES_DIR / "speciation.py"
PROCESS_PATH = SPECIES_DIR / "speciation_process.py"


def _source_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _function_lengths(path: Path) -> dict[str, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node.end_lineno - node.lineno + 1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno is not None
    }


def test_speciation_facade_stays_within_m5_file_limit() -> None:
    assert len(_source_lines(SPECIATION_PATH)) <= 3000


def test_process_async_stays_within_m5_coordinator_limit() -> None:
    assert _function_lengths(SPECIATION_PATH)["process_async"] <= 500


def test_process_phase_responsibilities_stay_bounded() -> None:
    oversized = {
        name: length
        for name, length in _function_lengths(PROCESS_PATH).items()
        if length > 250
    }

    assert oversized == {}
