import json
import logging
import sys
from pathlib import Path

import pytest

from ....security.save_paths import InvalidSaveNameError
from ..save_manager import SaveManager


HISTORICAL_DISPLAY_NAME = "历史 存档-1"


def write_historical_save(root: Path, folder_name: str, display_name: str) -> Path:
    save_dir = root / folder_name
    save_dir.mkdir(parents=True)
    (save_dir / "metadata.json").write_text(
        json.dumps(
            {
                "save_name": display_name,
                "turn_index": 0,
                "species_count": 0,
                "scenario": "原初大陆",
                "last_saved": "2026-07-13T00:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (save_dir / "game_state.json").write_text(
        json.dumps({"turn_index": 0}),
        encoding="utf-8",
    )
    return save_dir


def test_constructor_stores_resolved_root(tmp_path: Path) -> None:
    unresolved_root = tmp_path / "parent" / ".." / "saves"

    manager = SaveManager(unresolved_root)

    assert manager.saves_dir == unresolved_root.resolve()
    assert manager.saves_dir.is_absolute()


def test_historical_folder_is_found_by_metadata_without_rename(
    tmp_path: Path,
) -> None:
    root = tmp_path / "saves"
    historical = write_historical_save(
        root,
        "save_20200101_000000_old-folder",
        HISTORICAL_DISPLAY_NAME,
    )
    manager = SaveManager(root)

    assert manager.get_save_dir(HISTORICAL_DISPLAY_NAME) == historical.resolve()
    assert HISTORICAL_DISPLAY_NAME in {
        save["name"] for save in manager.list_saves()
    }
    assert historical.exists()
    assert historical.name == "save_20200101_000000_old-folder"


def test_historical_integrity_and_compression_preserve_original_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "saves"
    folder_name = "save_20200101_000000_historical-folder"
    historical = write_historical_save(root, folder_name, HISTORICAL_DISPLAY_NAME)
    manager = SaveManager(root)

    integrity = manager.check_save_integrity(HISTORICAL_DISPLAY_NAME)
    migration = manager.migrate_save_to_compressed(HISTORICAL_DISPLAY_NAME)

    assert integrity["valid"] is True
    assert integrity["turn_index"] == 0
    assert migration["success"] is True
    assert (historical / "game_state.json.gz").is_file()
    assert not (historical / "game_state.json").exists()
    assert manager.get_save_dir(HISTORICAL_DISPLAY_NAME) == historical.resolve()
    assert historical.name == folder_name


@pytest.mark.parametrize(
    "method_name",
    [
        "create_save",
        "save_game",
        "load_game",
        "delete_save",
        "get_save_dir",
        "check_save_integrity",
        "migrate_save_to_compressed",
    ],
)
def test_public_entrypoints_reject_traversal_before_file_access_or_logging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    method_name: str,
) -> None:
    manager = SaveManager(tmp_path / "saves")

    def fail_file_access(*args: object, **kwargs: object) -> None:
        raise AssertionError("file access occurred before save-name validation")

    caplog.set_level(logging.DEBUG)
    method = getattr(manager, method_name)
    with monkeypatch.context() as path_access:
        for attribute in ("exists", "glob", "mkdir", "read_text"):
            path_access.setattr(Path, attribute, fail_file_access)

        with pytest.raises(InvalidSaveNameError):
            if method_name == "save_game":
                method("../outside", turn_index=0)
            else:
                method("../outside")

    assert "../outside" not in caplog.text


def test_direct_user_named_folder_is_not_a_save_lookup_path(tmp_path: Path) -> None:
    root = tmp_path / "saves"
    manager = SaveManager(root)
    direct_folder = root / "direct-folder"
    direct_folder.mkdir()

    assert manager.get_save_dir("direct-folder") is None
    assert direct_folder.exists()


def test_outside_glob_candidate_is_ignored_without_path_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = SaveManager(tmp_path / "saves")
    outside = tmp_path / "outside"
    outside.mkdir()
    original_glob = Path.glob

    def fake_glob(path: Path, pattern: str):
        if path == manager.saves_dir and pattern == "save_*":
            return iter([outside])
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", fake_glob)
    caplog.set_level(logging.WARNING)

    assert list(manager._iter_save_dirs()) == []
    assert manager.list_saves() == []
    stats = manager.get_storage_stats()
    assert stats["save_count"] == 0
    assert stats["largest_save"] is None

    warning_text = "\n".join(record.getMessage() for record in caplog.records)
    output_text = json.dumps(stats, ensure_ascii=False)
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert str(outside.resolve()) not in warning_text
    assert str(manager.saves_dir) not in warning_text
    assert str(outside.resolve()) not in output_text
    assert str(manager.saves_dir) not in output_text


def test_directory_symlink_escape_is_skipped_when_supported(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path / "saves")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = manager.saves_dir / "save_symlink_escape"

    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        if sys.platform == "win32" and getattr(error, "winerror", None) in {5, 1314}:
            pytest.skip("Windows denied directory symlink creation")
        raise

    assert list(manager._iter_save_dirs()) == []


def test_bad_metadata_is_skipped_and_later_valid_match_is_found(
    tmp_path: Path,
) -> None:
    root = tmp_path / "saves"

    (root / "save_000_missing").mkdir(parents=True)

    invalid_json = root / "save_001_invalid_json"
    invalid_json.mkdir()
    (invalid_json / "metadata.json").write_text("{", encoding="utf-8")

    invalid_encoding = root / "save_002_invalid_encoding"
    invalid_encoding.mkdir()
    (invalid_encoding / "metadata.json").write_bytes(b"\xff")

    non_object = root / "save_003_non_object"
    non_object.mkdir()
    (non_object / "metadata.json").write_text("[]", encoding="utf-8")

    unreadable = root / "save_004_unreadable"
    unreadable.mkdir()
    (unreadable / "metadata.json").mkdir()

    valid = write_historical_save(
        root,
        "save_999_valid",
        HISTORICAL_DISPLAY_NAME,
    )
    manager = SaveManager(root)

    assert manager.get_save_dir(HISTORICAL_DISPLAY_NAME) == valid.resolve()


def test_create_save_contains_directory_and_preserves_display_name(
    tmp_path: Path,
) -> None:
    manager = SaveManager(tmp_path / "saves")

    metadata = manager.create_save(HISTORICAL_DISPLAY_NAME)

    created = list(manager.saves_dir.glob("save_*"))
    assert len(created) == 1
    created_dir = created[0].resolve()
    assert manager.saves_dir in created_dir.parents
    assert created_dir != manager.saves_dir
    assert created_dir.name.endswith(f"_{HISTORICAL_DISPLAY_NAME[:20]}")
    persisted_metadata = json.loads(
        (created_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["save_name"] == HISTORICAL_DISPLAY_NAME
    assert persisted_metadata["save_name"] == HISTORICAL_DISPLAY_NAME


def test_storage_stats_omit_save_root(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path / "saves")

    stats = manager.get_storage_stats()

    assert "saves_dir" not in stats
    assert str(manager.saves_dir) not in json.dumps(stats, ensure_ascii=False)


def test_storage_stats_redact_filesystem_errors_from_response_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = tmp_path / "saves"
    contained = write_historical_save(
        root,
        "save_20200101_000000_stats-error",
        HISTORICAL_DISPLAY_NAME,
    ).resolve()
    manager = SaveManager(root)
    sensitive_error = OSError(
        f"scan failed for {manager.saves_dir} and {contained}"
    )

    def fail_rglob(path: Path, pattern: str):
        assert path == contained
        assert pattern == "*"
        raise sensitive_error

    caplog.set_level(logging.ERROR)
    with monkeypatch.context() as file_scan:
        file_scan.setattr(Path, "rglob", fail_rglob)
        stats = manager.get_storage_stats()

    assert stats == {
        "save_count": 1,
        "total_size_mb": 0,
        "largest_save": None,
        "habitat_stats": {},
        "error": "无法获取存储统计信息",
    }
    assert any(
        record.getMessage() == "[存档管理器] 获取存储统计失败"
        for record in caplog.records
    )

    output_text = json.dumps(stats, ensure_ascii=False)
    for sensitive_value in (
        str(manager.saves_dir),
        str(contained),
        str(sensitive_error),
    ):
        assert sensitive_value not in output_text
        assert sensitive_value not in caplog.text
