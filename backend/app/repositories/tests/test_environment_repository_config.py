from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock

from app.models.config import UIConfig
from app.repositories.environment_repository import EnvironmentRepository


def test_save_ui_config_replaces_file_and_removes_temp_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"autosave_enabled": false}', encoding="utf-8")
    repo = EnvironmentRepository()
    replacements: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def tracking_replace(source: Path, target: Path) -> Path:
        replacements.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", tracking_replace)

    repo.save_ui_config(path, UIConfig(autosave_enabled=True))

    assert UIConfig.model_validate_json(path.read_text(encoding="utf-8")).autosave_enabled is True
    assert len(replacements) == 1
    temp_path, target_path = replacements[0]
    assert temp_path.parent == path.parent
    assert temp_path != path
    assert target_path == path
    assert not temp_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_concurrent_save_ui_config_uses_independent_temp_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.json"
    repo = EnvironmentRepository()
    write_barrier = Barrier(2)
    replace_barrier = Barrier(2)
    first_replace_done = Event()
    replacements: list[tuple[Path, Path, bool]] = []
    replacements_lock = Lock()
    original_replace = Path.replace
    original_write_text = Path.write_text

    def synchronized_write_text(destination: Path, data: str, **kwargs) -> int:
        written = original_write_text(destination, data, **kwargs)
        if destination == path.with_suffix(path.suffix + ".tmp"):
            write_barrier.wait(timeout=5)
        return written

    def synchronized_replace(source: Path, target: Path) -> Path:
        saved = UIConfig.model_validate_json(source.read_text(encoding="utf-8"))
        with replacements_lock:
            replacement_order = len(replacements)
            replacements.append((source, target, saved.autosave_enabled))
        replace_barrier.wait(timeout=5)
        if replacement_order == 0:
            try:
                return original_replace(source, target)
            finally:
                first_replace_done.set()
        first_replace_done.wait(timeout=5)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "write_text", synchronized_write_text)
    monkeypatch.setattr(Path, "replace", synchronized_replace)

    configs = [
        UIConfig(autosave_enabled=False),
        UIConfig(autosave_enabled=True),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(repo.save_ui_config, path, config) for config in configs]
        exceptions = [future.exception(timeout=5) for future in futures]

    assert exceptions == [None, None]
    assert len(replacements) == 2
    assert len({source for source, _, _ in replacements}) == 2
    assert {target for _, target, _ in replacements} == {path}
    assert {autosave_enabled for _, _, autosave_enabled in replacements} == {False, True}
    assert UIConfig.model_validate_json(
        path.read_text(encoding="utf-8")
    ).autosave_enabled in {False, True}
    assert list(tmp_path.glob("*.tmp")) == []
