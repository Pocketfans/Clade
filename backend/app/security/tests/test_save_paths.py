from pathlib import Path

import pytest

from app.security.save_paths import (
    InvalidSaveNameError,
    SavePathBoundaryError,
    SavePathError,
    resolve_save_directory,
    validate_save_name,
)


@pytest.mark.parametrize(
    "name",
    [
        "原初大陆",
        "历史 存档-1",
        "Save_2026",
        "Évolution 3",
        "１２３",
    ],
)
def test_validate_save_name_preserves_valid_unicode_exactly(name: str) -> None:
    assert validate_save_name(name) == name


WINDOWS_DEVICE_NAMES = [
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
]


@pytest.mark.parametrize(
    "name",
    [
        "",
        "a" * 51,
        ".",
        "..",
        "../outside",
        "..\\outside",
        "C:\\outside",
        "/absolute",
        "name.json",
        "line\nbreak",
        "control\x1fcharacter",
        "trailing ",
        "trailing.",
        "emoji😀",
        *(device for name in WINDOWS_DEVICE_NAMES for device in (name, name.lower())),
    ],
)
def test_validate_save_name_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(InvalidSaveNameError):
        validate_save_name(name)


def test_save_path_errors_share_a_public_base_type() -> None:
    assert issubclass(InvalidSaveNameError, SavePathError)
    assert issubclass(SavePathBoundaryError, SavePathError)


def test_invalid_name_error_does_not_echo_the_value() -> None:
    invalid_name = "../private-save"

    with pytest.raises(InvalidSaveNameError) as exc_info:
        validate_save_name(invalid_name)

    assert invalid_name not in str(exc_info.value)


def test_resolve_save_directory_returns_resolved_child(tmp_path: Path) -> None:
    saves_dir = tmp_path / "saves"
    candidate = saves_dir / "slot-one"

    assert resolve_save_directory(saves_dir, candidate) == candidate.resolve()


def test_resolve_save_directory_rejects_root_itself(tmp_path: Path) -> None:
    saves_dir = tmp_path / "saves"

    with pytest.raises(SavePathBoundaryError):
        resolve_save_directory(saves_dir, saves_dir)


@pytest.mark.parametrize("escape_kind", ["parent", "similar-prefix"])
def test_resolve_save_directory_rejects_escape_paths(
    tmp_path: Path,
    escape_kind: str,
) -> None:
    saves_dir = tmp_path / "saves"
    candidate = (
        saves_dir / ".." / "outside"
        if escape_kind == "parent"
        else tmp_path / "saves-backup" / "slot-one"
    )

    with pytest.raises(SavePathBoundaryError):
        resolve_save_directory(saves_dir, candidate)


def test_boundary_error_does_not_echo_root_or_candidate(tmp_path: Path) -> None:
    saves_dir = tmp_path / "private-saves"
    candidate = tmp_path / "private-outside"

    with pytest.raises(SavePathBoundaryError) as exc_info:
        resolve_save_directory(saves_dir, candidate)

    message = str(exc_info.value)
    assert str(saves_dir.resolve()) not in message
    assert str(candidate.resolve()) not in message


def test_resolve_save_directory_rejects_symlink_escape(tmp_path: Path) -> None:
    saves_dir = tmp_path / "saves"
    outside = tmp_path / "outside"
    saves_dir.mkdir()
    outside.mkdir()
    link = saves_dir / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Cannot create a directory symlink: {exc}")

    with pytest.raises(SavePathBoundaryError):
        resolve_save_directory(saves_dir, link / "slot-one")
