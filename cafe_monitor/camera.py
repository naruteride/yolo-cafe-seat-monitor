"""Context-managed frame capture. All backends return OpenCV-style BGR arrays."""

from contextlib import ExitStack
from math import isfinite
from pathlib import Path


class Camera:
    def __init__(self, source=0, width=640, height=480):
        if isinstance(source, str) and source.isdecimal():
            source = int(source)
        self.source = source
        self.size = (width, height)
        self._devices = ExitStack()
        self._capture = None
        self._picamera = None
        self.media_seconds = None
        self._frame_period = None

    def __enter__(self):
        with ExitStack() as devices:
            if self.source == "picamera2":
                try:
                    from picamera2 import Picamera2
                except ImportError as exc:
                    raise RuntimeError(
                        "CSI 카메라는 python3-picamera2와 --system-site-packages 가상환경이 필요합니다."
                    ) from exc
                camera = Picamera2()
                devices.callback(camera.close)
                # Picamera2's RGB888 layout is B, G, R in a NumPy array.
                config = camera.create_video_configuration(
                    main={"size": self.size, "format": "RGB888"}
                )
                camera.configure(config)
                camera.start()
                self._picamera = camera
            else:
                import cv2

                source = self.source
                if not isinstance(source, int):
                    if not Path(source).is_file():
                        raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {source}")
                    source = str(source)
                capture = cv2.VideoCapture(source)
                devices.callback(capture.release)
                if not capture.isOpened():
                    raise RuntimeError(f"카메라 또는 영상 파일을 열 수 없습니다: {source}")
                if isinstance(source, int):
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.size[0])
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.size[1])
                    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                else:
                    fps = capture.get(cv2.CAP_PROP_FPS)
                    self._frame_period = 1 / fps if isfinite(fps) and fps > 0 else 1 / 30
                self._capture = capture
            self._devices = devices.pop_all()
        return self

    def read(self):
        if self._picamera is not None:
            return self._picamera.capture_array("main")
        if self._capture is None:
            raise RuntimeError("카메라가 열려 있지 않습니다.")
        ok, frame = self._capture.read()
        if ok and frame is not None:
            if self._frame_period is not None:
                import cv2

                timestamp = self._capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
                previous = self.media_seconds
                if isfinite(timestamp) and timestamp >= 0 and (previous is None or timestamp > previous):
                    self.media_seconds = timestamp
                else:
                    # Some file backends always report zero or omit presentation timestamps.
                    self.media_seconds = 0 if previous is None else previous + self._frame_period
            return frame
        if isinstance(self.source, int):
            raise RuntimeError("USB 카메라 프레임을 읽을 수 없습니다.")
        raise EOFError("영상 재생이 끝났습니다.")

    def __exit__(self, *exc):
        self._picamera = self._capture = None
        self.media_seconds = self._frame_period = None
        self._devices.close()
