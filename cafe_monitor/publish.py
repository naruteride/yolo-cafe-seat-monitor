"""Send the latest metadata snapshot without blocking camera inference."""

import json
import logging
from http.client import HTTPException
from threading import Condition, Thread
from time import monotonic
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Publisher:
    def __init__(self, endpoint, token, interval=5.0):
        self.endpoint = endpoint
        if endpoint:
            address = urlsplit(endpoint)
            local = address.scheme == "http" and address.hostname in ("localhost", "127.0.0.1", "::1")
            if not address.hostname or address.username or address.password or not (local or address.scheme == "https"):
                raise ValueError("MONITOR_ENDPOINT에는 HTTPS 주소 또는 로컬 HTTP 주소를 입력하세요.")
            if not token:
                raise ValueError("웹에 전송하려면 MONITOR_TOKEN을 설정하세요.")
            if not token.isascii() or any(not 33 <= ord(char) <= 126 for char in token):
                raise ValueError("MONITOR_TOKEN에는 공백 없는 ASCII 토큰을 사용하세요.")
        self.token = token
        self.interval = interval
        self._signal = Condition()
        self._latest = None
        self._closing = False
        self._thread = None
        self._opener = build_opener(_NoRedirect())

    def __enter__(self):
        if self.endpoint:
            self._thread = Thread(target=self._run, name="status-publisher", daemon=True)
            self._thread.start()
        return self

    def offer(self, snapshot):
        if self._thread:
            with self._signal:
                self._latest = snapshot
                self._signal.notify()

    def _run(self):
        next_send = 0.0
        while True:
            with self._signal:
                self._signal.wait_for(lambda: self._latest is not None or self._closing)
                while not self._closing and monotonic() < next_send:
                    self._signal.wait(timeout=max(0, next_send - monotonic()))
                snapshot = self._latest
                self._latest = None
                closing = self._closing
            if snapshot is not None:
                data = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
                request = Request(self.endpoint, data=data, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                })
                try:
                    with self._opener.open(request, timeout=4):
                        pass
                except (OSError, HTTPException) as error:
                    logging.warning("웹 전송 실패 (%s). 다음 관측에서 다시 시도합니다.", error)
                next_send = monotonic() + self.interval
            if closing:
                return

    def __exit__(self, *exc):
        if self._thread:
            with self._signal:
                self._closing = True
                self._signal.notify()
            self._thread.join(timeout=9)
