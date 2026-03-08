"""Path validation helpers."""

from __future__ import annotations

from pathlib import Path

from pathvalidate import validate_filepath


def validate_path(raw: str) -> Path:
    """
    Validate and resolve a file path.

    Raises:
        ValueError: If path is invalid or contains unsafe characters.
        FileNotFoundError: Not raised here — callers decide whether
                           the path must already exist.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Path cannot be empty.")

    # pathvalidate raises ValidationError (subclass of ValueError) for bad paths
    validate_filepath(raw, platform="auto")

    return Path(raw).resolve()


def is_safe_path(path: Path, base: Path) -> bool:
    """Return True if *path* is inside *base* (no directory traversal)."""
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
