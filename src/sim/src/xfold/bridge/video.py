"""H.264 video of a run, written as HLS while the run is still going.

One ffmpeg per run, fed raw RGB frames by the viewport producer. Output lands
in ``data/video/{run_id}/`` (gitignored via ``data/``):

    init.mp4        fMP4 initialisation segment
    seg00000.m4s …  two-second media segments
    index.m3u8      grows as segments land; gains #EXT-X-ENDLIST at close

That one file is both transports. While the run is live the playlist has no
ENDLIST and the player tails it, a couple of segments behind — the delay we
trade for H.264 instead of re-encoded JPEG stills. When the run finishes the
ENDLIST turns the same playlist into a VOD, so replay scrubs a real video
instead of asking the bridge to re-render a frame per seek.

Never puts video bytes in the journal — same rule as the viewport frames.
See docs/INTEGRATION_CONTRACT.md §5.
"""

from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

SEGMENT_SECONDS = 2
# ffmpeg takes the input as a fixed frame rate, so a render loop that cannot
# keep up would silently produce a sped-up video — a 65 s run came out as 8 s
# of footage on software GL. Missing slots are filled by repeating the last
# frame, so video time tracks wall time whatever the renderer manages. Capped
# so one long stall cannot dump a huge burst into the encoder.
_MAX_PAD_SECONDS = 2.0
# Frames the writer may fall behind before it starts dropping. ffmpeg at
# veryfast/640x360 is far quicker than realtime, so this should stay empty;
# it exists so a stalled encoder can never block the render thread.
_QUEUE_DEPTH = 48

PLAYLIST = "index.m3u8"
_INIT = "init.mp4"
# What `GET /runs/{id}/video/{file}` is allowed to serve.
_SERVABLE = re.compile(r"^(init\.mp4|seg\d{5}\.m4s|index\.m3u8)$")

_MIME = {".m3u8": "application/vnd.apple.mpegurl", ".mp4": "video/mp4", ".m4s": "video/iso.segment"}


def video_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pixi.toml").exists() and (parent / "moon.yml").exists():
            path = parent / "data" / "video"
            break
    else:
        path = here.parents[5] / "data" / "video"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe(run_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)


def run_dir(run_id: str) -> Path:
    return video_dir() / _safe(run_id)


def servable(run_id: str, name: str) -> tuple[Path, str] | None:
    """(path, mime) for a file the video routes may serve, else None.

    The name is matched against a fixed pattern rather than sanitised, so no
    caller-supplied path can escape the run's directory.
    """
    if not _SERVABLE.match(name):
        return None
    path = run_dir(run_id) / name
    if not path.is_file():
        return None
    return path, _MIME.get(path.suffix, "application/octet-stream")


def has_video(run_id: str) -> bool:
    return (run_dir(run_id) / PLAYLIST).is_file()


def ffmpeg_exe() -> str | None:
    """A usable ffmpeg: the imageio-ffmpeg binary, else one on PATH."""
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:  # noqa: BLE001 — not installed, or no binary for this arch
        pass
    return shutil.which("ffmpeg")


class RunVideo:
    """ffmpeg writing HLS for one run. Frames in, segments out."""

    def __init__(
        self, run_id: str, width: int, height: int, fps: float, clock=None
    ) -> None:
        self.run_id = run_id
        # What video time follows: wall time by default. An engine slower than
        # realtime (Isaac) passes its sim clock, so replay, which seeks the
        # video to sim time, lines up; frames offered faster than that clock
        # advances are then skipped rather than stretching the video.
        self._clock = clock or time.monotonic
        self._sim_clock = clock is not None
        self.width = width
        self.height = height
        self.fps = max(1.0, float(fps))
        self.dropped = 0
        self.frames = 0
        self.padded = 0
        self._t0: float | None = None
        self._base = 0
        self._last: bytes | None = None
        self._proc: subprocess.Popen | None = None
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=_QUEUE_DEPTH)
        self._writer: threading.Thread | None = None
        self._closed = False

    @property
    def ok(self) -> bool:
        return self._proc is not None and not self._closed

    @property
    def dir(self) -> Path:
        return run_dir(self.run_id)

    def start(self) -> bool:
        exe = ffmpeg_exe()
        if exe is None:
            return False
        out = self.dir
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        gop = max(1, int(round(self.fps * SEGMENT_SECONDS)))
        args = [
            exe, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}", "-r", f"{self.fps:g}",
            "-i", "pipe:0",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-crf", "23",
            # A keyframe exactly per segment, so every segment stands alone.
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-f", "hls",
            "-hls_time", str(SEGMENT_SECONDS),
            "-hls_list_size", "0",          # keep every segment: live now, VOD later
            "-hls_playlist_type", "event",  # no sliding window; ENDLIST only on close
            "-hls_flags", "independent_segments+temp_file",
            "-hls_segment_type", "fmp4",
            "-hls_fmp4_init_filename", _INIT,
            "-hls_segment_filename", str(out / "seg%05d.m4s"),
            str(out / PLAYLIST),
        ]
        try:
            self._proc = subprocess.Popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[video] could not start ffmpeg: {exc}", flush=True)
            self._proc = None
            return False
        self._writer = threading.Thread(
            target=self._pump, name=f"xfold-video-{self.run_id}", daemon=True
        )
        self._writer.start()
        print(
            f"[video] {self.run_id} → {out}/{PLAYLIST} "
            f"({self.width}x{self.height} @ {self.fps:g}fps)",
            flush=True,
        )
        return True

    def write(self, rgb: np.ndarray) -> None:
        """Queue one frame, padding any slots the renderer missed.

        Never blocks the caller; drops if ffmpeg somehow lags behind.
        """
        if not self.ok:
            return
        now = self._clock()
        if self._t0 is None or now < self._t0:
            # A sim clock restarts at each run; carry on from the frames
            # already written rather than waiting for the old time again.
            self._t0 = now
            self._base = self.frames
        want = self._base + int((now - self._t0) * self.fps)
        if self._sim_clock and self.frames > want:
            return
        blob = np.ascontiguousarray(rgb, dtype=np.uint8).tobytes()
        missing = want - self.frames
        if missing > 0 and self._last is not None:
            for _ in range(min(missing, int(self.fps * _MAX_PAD_SECONDS))):
                if not self._put(self._last):
                    break
                self.padded += 1
        self._put(blob)
        self._last = blob

    def _put(self, blob: bytes) -> bool:
        try:
            self._queue.put_nowait(blob)
        except queue.Full:
            self.dropped += 1
            return False
        self.frames += 1
        return True

    def _pump(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdin is not None
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                proc.stdin.write(item)
        except (BrokenPipeError, ValueError, OSError):
            pass  # ffmpeg died; close() reports it
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    def close(self, timeout: float = 10.0) -> Path | None:
        """Flush, let ffmpeg write #EXT-X-ENDLIST, return the playlist."""
        if self._closed:
            return None
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # Drain enough to get the sentinel in; the tail is a frame or two.
            try:
                while True:
                    self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        if self._writer:
            self._writer.join(timeout=timeout)
        proc = self._proc
        if proc is None:
            return None
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
        if proc.returncode not in (0, None):
            err = b""
            if proc.stderr is not None:
                try:
                    err = proc.stderr.read() or b""
                except Exception:
                    pass
            print(
                f"[video] {self.run_id} ffmpeg exit {proc.returncode}: "
                f"{err.decode('utf-8', 'replace')[:300]}",
                flush=True,
            )
        playlist = self.dir / PLAYLIST
        if playlist.is_file():
            print(
                f"[video] {self.run_id} closed · {self.frames} frames "
                f"({self.frames / self.fps:.1f}s)"
                + (f" · {self.padded} padded" if self.padded else "")
                + (f" · {self.dropped} dropped" if self.dropped else ""),
                flush=True,
            )
            return playlist
        return None


class VideoManager:
    """Routes the producer's frames into one RunVideo per run.

    The producer thread knows nothing about runs; it hands every frame here
    with whichever run is active. A new run id opens a recorder, and the run
    going away closes it — which is what writes #EXT-X-ENDLIST and turns the
    playlist into a VOD.
    """

    def __init__(
        self, width: int, height: int, fps: float, on_open=None, clock=None
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.on_open = on_open
        self.clock = clock
        self.available = ffmpeg_exe() is not None
        self._lock = threading.Lock()
        self._current: RunVideo | None = None

    def frame(self, run_id: str | None, rgb: np.ndarray) -> None:
        if not self.available:
            return
        with self._lock:
            current = self._current
            if current is not None and current.run_id != run_id:
                current.close()
                self._current = current = None
            if run_id is None:
                return
            if current is None:
                fresh = RunVideo(run_id, self.width, self.height, self.fps, self.clock)
                if not fresh.start():
                    self.available = False
                    return
                self._current = current = fresh
                if self.on_open is not None:
                    self.on_open(run_id)
            current.write(rgb)

    def end(self, run_id: str) -> None:
        """Force-close this run's recorder so delete can purge the folder."""
        with self._lock:
            current = self._current
            if current is not None and current.run_id == run_id:
                current.close()
                self._current = None

    def sync(self, run_id: str | None) -> None:
        """Close the recording if its run is no longer the live one.

        For sessions that write frames themselves: once the run ends they
        stop writing, and this is what still closes the video (ENDLIST).
        """
        with self._lock:
            current = self._current
            if current is not None and current.run_id != run_id:
                current.close()
                self._current = None

    def close(self) -> None:
        with self._lock:
            if self._current is not None:
                self._current.close()
                self._current = None
