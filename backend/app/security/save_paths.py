from pathlib import Path


RESERVED_WINDOWS_DEVICE_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
)

_ALLOWED_NAME_CHARACTERS = {" ", "_", "-"}
_INVALID_NAME_MESSAGE = "Invalid save name."
_BOUNDARY_MESSAGE = "Save directory is outside the configured save root."


class SavePathError(ValueError):
    """Base error for save-name and save-path policy violations."""


class InvalidSaveNameError(SavePathError):
    """Raised when a save name does not meet the security policy."""


class SavePathBoundaryError(SavePathError):
    """Raised when a save directory is not strictly inside the save root."""


def validate_save_name(value: str) -> str:
    """Return an unchanged safe save name or reject it."""
    if not 1 <= len(value) <= 50:
        raise InvalidSaveNameError(_INVALID_NAME_MESSAGE)
    if value[-1] in {" ", "."}:
        raise InvalidSaveNameError(_INVALID_NAME_MESSAGE)
    if value.upper() in RESERVED_WINDOWS_DEVICE_NAMES:
        raise InvalidSaveNameError(_INVALID_NAME_MESSAGE)
    if not all(
        character.isalnum() or character in _ALLOWED_NAME_CHARACTERS
        for character in value
    ):
        raise InvalidSaveNameError(_INVALID_NAME_MESSAGE)
    return value


def resolve_save_directory(
    saves_dir: str | Path,
    candidate: str | Path,
) -> Path:
    """Resolve a candidate that must be strictly inside the save root."""
    try:
        resolved_root = Path(saves_dir).resolve()
        resolved_candidate = Path(candidate).resolve()
    except (OSError, RuntimeError, ValueError):
        raise SavePathBoundaryError(_BOUNDARY_MESSAGE) from None

    if resolved_root not in resolved_candidate.parents:
        raise SavePathBoundaryError(_BOUNDARY_MESSAGE)
    return resolved_candidate
