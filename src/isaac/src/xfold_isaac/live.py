"""Watch an Isaac run from a browser: the camera as MJPEG, the phase as text.

``run.py --serve PORT`` starts it on 127.0.0.1 of the box; scripts/live.sh
tunnels the port over SSH and opens it on the laptop. Frames are the ones
the run renders anyway (``--fps`` per simulated second), so watching costs a
JPEG encode per frame and nothing else.
"""

from __future__ import annotations

import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>XFOLD on Isaac Sim</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body { margin: 0; background: #111; color: #ddd; font: 14px/1.4 system-ui, sans-serif; }
  header { padding: 10px 16px; display: flex; gap: 16px; align-items: baseline; flex-wrap: wrap; }
  b { color: #f0a030; } #msg { color: #aaa; }
  img { display: block; width: 100%; max-width: 1280px; margin: 0 auto; background: #000; }
</style></head><body>
<header><b>XFOLD · Isaac Sim</b><span id="phase">starting Isaac (first frames take ~1 min)</span>
<span id="t"></span><span id="msg"></span></header>
<img src="/stream" alt="live camera">
<script>
async function poll() {
  try {
    const s = await (await fetch('/status')).json();
    document.getElementById('phase').textContent = s.phase ? `${s.phase} · ${s.operation}` : 'starting';
    document.getElementById('t').textContent = s.t != null ? `t = ${s.t.toFixed(1)} s` : '';
    document.getElementById('msg').textContent = s.done ? `done: ${s.outcome ?? 'stopped'}` : (s.message || '');
  } catch (e) { document.getElementById('msg').textContent = 'run ended'; return; }
  setTimeout(poll, 500);
}
poll();
</script></body></html>
"""


class LiveView:
    def __init__(self, port: int, *, quality: int = 80) -> None:
        self.quality = quality
        self._frame: bytes | None = None
        self._seq = 0
        self._status: dict = {}
        self._cond = threading.Condition()
        view = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 — http.server's name
                if self.path == "/":
                    self._send(200, "text/html; charset=utf-8", PAGE.encode())
                elif self.path == "/status":
                    self._send(200, "application/json", json.dumps(view._status).encode())
                elif self.path == "/stream":
                    view._stream(self)
                else:
                    self._send(404, "text/plain", b"not found")

            def _send(self, code: int, kind: str, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        print(f"live view on 127.0.0.1:{port}", flush=True)

    def frame(self, rgb: np.ndarray) -> None:
        from PIL import Image

        buffer = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(rgb)).save(buffer, format="JPEG", quality=self.quality)
        with self._cond:
            self._frame = buffer.getvalue()
            self._seq += 1
            self._cond.notify_all()

    def status(self, **fields) -> None:
        self._status = {**self._status, **fields}

    def _stream(self, handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        seen = -1
        try:
            while True:
                with self._cond:
                    self._cond.wait_for(lambda: self._seq != seen, timeout=5.0)
                    frame, seen = self._frame, self._seq
                if frame is None:
                    continue
                handler.wfile.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(frame)).encode()
                    + b"\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
        except (BrokenPipeError, ConnectionResetError):
            return

    def linger(self, seconds: float) -> None:
        """Keep serving the last frame a little, so the page shows the end."""
        time.sleep(seconds)
        self._server.shutdown()
