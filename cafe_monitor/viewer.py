"""Loopback-only browser dashboard for the camera process."""

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Lock, Thread
import time
from urllib.parse import parse_qs


PUBLIC = Path(__file__).resolve().parents[1] / "web" / "public"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/board.css": ("board.css", "text/css; charset=utf-8"),
    "/board.js": ("board.js", "text/javascript; charset=utf-8"),
}
LOCAL_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?", re.IGNORECASE)
FRAME_TTL = 10.0
SEAT_TTL = 30.0


class LocalViewer:
    def __init__(self, mode="live", port=8765):
        if mode not in ("live", "demo", "replay"):
            raise ValueError("카메라 소스 모드를 확인하세요.")
        self.mode = mode
        self.port = port
        self._lock = Lock()
        self._server = None
        self._thread = None
        self._state = "starting"
        self._message = "첫 카메라 프레임을 기다리고 있습니다."
        self._frame_id = 0
        # Keep a short window so status and JPEG can be fetched in separate requests.
        self._frames = deque(maxlen=3)
        self._observed_at = None
        self._fps = 0.0
        self._objects = []
        self._snapshot = None
        self._snapshot_time = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), _ViewerHandler)
        self._server.viewer = self
        self.port = self._server.server_port
        self._thread = Thread(target=self._server.serve_forever, name="camera-viewer", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()
        self.stopped()

    def _clear(self, state, message):
        with self._lock:
            self._state = state
            self._message = message
            self._frames.clear()
            self._objects = []
            self._fps = 0.0

    def starting(self, message):
        self._clear("starting", message)

    def error(self, message):
        self._clear("error", message)

    def stopped(self, message="카메라가 중지되었습니다."):
        self._clear("stopped", message)

    def _set_seats(self, observed_at, seats, captured_at):
        self._snapshot = {"mode": "live" if self.mode == "live" else "demo",
                          "observedAt": observed_at, "seats": deepcopy(seats)}
        self._snapshot_time = captured_at

    def update_seats(self, observed_at, seats):
        """Accept synthetic seat observations without claiming camera activity."""
        with self._lock:
            self._set_seats(observed_at, seats, time.monotonic())

    def update_frame(self, jpeg, observed_at, fps, objects, seats=None, *, captured_at=None):
        """Atomically expose one annotated JPEG, its detections, and confirmed seats."""
        if not jpeg:
            raise ValueError("표시할 JPEG 프레임이 비어 있습니다.")
        captured_at = time.monotonic() if captured_at is None else captured_at
        with self._lock:
            self._frame_id += 1
            self._frames.append((self._frame_id, captured_at, bytes(jpeg)))
            self._observed_at = observed_at
            self._fps = round(fps, 1)
            self._objects = deepcopy(objects)
            self._state = "running"
            self._message = ""
            if seats is not None:
                self._set_seats(observed_at, seats, captured_at)

    def _frame_fresh(self, now):
        return bool(self._frames) and now - self._frames[-1][1] < FRAME_TTL

    def camera_status(self):
        with self._lock:
            running = self._frame_fresh(time.monotonic())
            stale = self._state == "running" and not running
            return {"mode": self.mode, "state": "error" if stale else self._state,
                    "message": "새 카메라 프레임이 도착하지 않습니다." if stale else self._message,
                    "frameId": self._frame_id, "observedAt": self._observed_at,
                    "fps": self._fps if running else 0.0, "objects": self._objects if running else []}

    def frame(self, frame_id=None):
        with self._lock:
            now = time.monotonic()
            if not self._frame_fresh(now):
                return 503, None, b""
            for current_id, received, jpeg in reversed(self._frames):
                if frame_id is None or current_id == frame_id:
                    if now - received < FRAME_TTL:
                        return 200, current_id, jpeg
                    break
            return 409, None, b""

    def seat_status(self):
        with self._lock:
            now = time.monotonic()
            stale = self._snapshot_time is None or now - self._snapshot_time >= SEAT_TTL
            if self.mode != "demo" and not self._frame_fresh(now):
                stale = True
            return {"snapshot": self._snapshot, "stale": stale,
                    "serverTime": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}


class _ViewerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # The dashboard polls both frame endpoints continually.

    def _reply(self, status, content_type, data, *, frame_id=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if frame_id is not None:
            self.send_header("X-Frame-Id", str(frame_id))
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # A browser can cancel an image request as a tab closes.

    def _json(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._reply(status, "application/json; charset=utf-8", data)

    def do_GET(self):
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or not LOCAL_HOST.fullmatch(hosts[0]):
            return self._json(403, {"error": "Local viewer only"})
        path, _, query = self.path.partition("?")
        viewer = self.server.viewer
        if path == "/api/camera/status":
            return self._json(200, viewer.camera_status())
        if path == "/api/status":
            return self._json(200, viewer.seat_status())
        if path == "/api/camera/frame.jpg":
            values = parse_qs(query, keep_blank_values=True).get("id")
            frame_id = None
            if values is not None:
                if len(values) != 1 or not re.fullmatch(r"[0-9]{1,18}", values[0]):
                    return self._json(400, {"error": "Invalid frame id"})
                frame_id = int(values[0])
            status, current_id, jpeg = viewer.frame(frame_id)
            if status != 200:
                return self._json(status, {"error": "Frame unavailable"})
            return self._reply(200, "image/jpeg", jpeg, frame_id=current_id)
        if path not in ASSETS:
            return self._json(404, {"error": "Not found"})
        name, content_type = ASSETS[path]
        try:
            data = (PUBLIC / name).read_bytes()
        except OSError:
            return self._json(503, {"error": "Dashboard asset unavailable"})
        if name == "index.html":
            data = data.replace(b'<html lang="ko">', b'<html lang="ko" data-local-camera>', 1)
        self._reply(200, content_type, data)

    do_HEAD = do_GET
