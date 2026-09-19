"""Live viewport frame hub — separate from the journal bus.

Contract: docs/INTEGRATION_CONTRACT.md
Do not put JPEG bytes in journal events.

Primary browser transport: long-poll ``GET /viewport/frame?after_seq=&wait_ms=``
(multipart MJPEG remains for curl/VLC only — Safari/Chrome often paint it black).
"""

from __future__ import annotations

import struct
import threading
import time
import zlib
from collections.abc import Iterator
from io import BytesIO
from typing import Any, Literal

import numpy as np

ViewportSource = Literal["mujoco", "none"]


def _encode_png_rgb(rgb: np.ndarray) -> bytes:
    """Minimal RGB PNG encoder (no Pillow required)."""
    h, w, c = rgb.shape
    assert c == 3 and rgb.dtype == np.uint8
    raw = b"".join(b"\x00" + rgb[i].tobytes() for i in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def encode_frame(rgb: np.ndarray, *, quality: int = 72) -> tuple[bytes, str]:
    """Return (bytes, mime). Prefer JPEG via Pillow when available."""
    try:
        from PIL import Image

        buf = BytesIO()
        Image.fromarray(rgb).save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return _encode_png_rgb(rgb), "image/png"


class ViewportHub:
    """Latest frame buffer. Thread-safe; never blocks physics long."""

    def __init__(self) -> None:
        self._lock = threading.Condition()
        self._jpeg: bytes | None = None
        self._mime = "image/jpeg"
        self._seq = 0
        self._source: ViewportSource = "none"
        self._last_ts = 0.0
        self._width = 0
        self._height = 0

    @property
    def available(self) -> bool:
        with self._lock:
            return self._jpeg is not None and self._source != "none"

    @property
    def source(self) -> ViewportSource:
        with self._lock:
            return self._source

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def set_source(self, source: ViewportSource) -> None:
        with self._lock:
            self._source = source

    def set_frame_size(self, width: int, height: int) -> None:
        with self._lock:
            self._width = int(width)
            self._height = int(height)

    def publish(self, frame: bytes, *, mime: str = "image/jpeg") -> None:
        with self._lock:
            self._jpeg = frame
            self._mime = mime
            self._seq += 1
            self._last_ts = time.monotonic()
            self._lock.notify_all()

    def latest(self) -> tuple[bytes, str, int] | None:
        with self._lock:
            if self._jpeg is None:
                return None
            return self._jpeg, self._mime, self._seq

    def meta(self) -> dict[str, Any]:
        with self._lock:
            age_ms = (
                int((time.monotonic() - self._last_ts) * 1000)
                if self._jpeg is not None and self._last_ts > 0
                else None
            )
            return {
                "available": self._jpeg is not None and self._source != "none",
                "source": self._source,
                "seq": self._seq,
                "ageMs": age_ms,
                "mime": self._mime if self._jpeg is not None else None,
                "width": self._width or None,
                "height": self._height or None,
                "transport": "long-poll",
            }

    def wait_newer(
        self, after_seq: int = 0, timeout: float = 1.5
    ) -> tuple[bytes, str, int] | None:
        """Block until ``seq > after_seq`` or timeout. Returns latest frame if any."""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._lock:
            while True:
                if self._jpeg is not None and self._seq > after_seq:
                    return self._jpeg, self._mime, self._seq
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if self._jpeg is None:
                        return None
                    # Timeout: still hand back current frame so client can paint.
                    return self._jpeg, self._mime, self._seq
                self._lock.wait(timeout=remaining)

    def wait_frame(self, after_seq: int = 0, timeout: float = 1.0) -> tuple[bytes, str, int] | None:
        """Legacy alias used by MJPEG generator."""
        return self.wait_newer(after_seq=after_seq, timeout=timeout)

    def mjpeg_sync(self, fps: float = 12.0) -> Iterator[bytes]:
        """Legacy multipart generator for curl/VLC — not used by the dashboard."""
        boundary = b"frame"
        interval = 1.0 / max(fps, 1.0)
        last_seq = 0
        while True:
            got = self.wait_newer(after_seq=last_seq, timeout=interval)
            if got is None:
                time.sleep(interval)
                continue
            payload, mime, last_seq = got
            yield (
                b"--" + boundary + b"\r\n"
                b"Content-Type: " + mime.encode() + b"\r\n"
                b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n"
                + payload
                + b"\r\n"
            )
