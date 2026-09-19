"""Product shots from the QC camera, stored as files beside the trajectories.

Stored under data/photos/{run_id}.jpg (gitignored via data/), and served by
GET /runs/{run_id}/photo.

Never puts the image into the journal — same rule as the viewport frames.
See docs/INTEGRATION_CONTRACT.md §5.
"""

from __future__ import annotations

from pathlib import Path

# The QC shot is square: it is a product image, not a viewport frame.
PHOTO_SIZE = 768
_SUFFIX = {"image/jpeg": ".jpg", "image/png": ".png"}


def photos_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pixi.toml").exists() and (parent / "moon.yml").exists():
            path = parent / "data" / "photos"
            path.mkdir(parents=True, exist_ok=True)
            return path
    path = here.parents[5] / "data" / "photos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe(run_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)


def photo_path(run_id: str, mime: str = "image/jpeg") -> Path:
    return photos_dir() / f"{_safe(run_id)}{_SUFFIX.get(mime, '.jpg')}"


def find_photo(run_id: str) -> Path | None:
    """The stored shot for a run, whichever format it was encoded in."""
    for mime in ("image/jpeg", "image/png"):
        path = photo_path(run_id, mime)
        if path.is_file():
            return path
    return None


def save_photo(run_id: str, payload: bytes, mime: str) -> Path:
    path = photo_path(run_id, mime)
    path.write_bytes(payload)
    return path
