"""Run with python -m cafe_monitor from the project directory."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import signal
from threading import Event
import time

from .camera import Camera
from .detector import Detection, YoloDetector
from .gpio import Indicators
from .publish import Publisher
from .state import Seat, SeatMonitor

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "monitor.json"


def options():
    parser = argparse.ArgumentParser(description="카페 좌석 모니터")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="좌석 및 판정 설정 JSON")
    parser.add_argument("--source", help="USB 카메라 번호, picamera2 또는 영상 파일")
    parser.add_argument("--model", help="기본 모델을 교체할 가중치 또는 NCNN 디렉터리")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="카메라 없이 합성 관측으로 4단계 시연")
    mode.add_argument("--preview", action="store_true", help="화면에 ROI와 탐지 결과 표시 (Q로 종료)")
    mode.add_argument("--calibrate", action="store_true", help="카메라 화면을 클릭해 설정 파일의 좌석 영역 보정")
    parser.add_argument("--gpio", action="store_true", help="LED·능동 부저 사용")
    parser.add_argument("--seat-crops", action="store_true", help="작은 물건을 위해 테이블마다 잘라서 추론")
    parser.add_argument("--abandoned-seconds", type=float, help="장기 방치 기준 시간 재설정")
    parser.add_argument("--frames", type=int, help="지정한 프레임 수만 처리하고 종료")
    args = parser.parse_args()
    if args.frames is not None and args.frames < 1:
        parser.error("--frames 값은 1 이상이어야 합니다.")
    return args


def load_settings(args):
    with args.config.open(encoding="utf-8") as file:
        config = json.load(file)
    seats = [Seat(**row) for row in config["seats"]]
    # Keep locally valid seat definitions publishable by the dashboard API.
    def valid_text(value, limit):
        return len(value.encode("utf-16-le")) // 2 <= limit and all(
            ord(char) >= 32 and ord(char) != 127 for char in value)
    if len(seats) > 128 or any(not valid_text(s.id, 64) or not valid_text(s.label, 80) for s in seats):
        raise ValueError("좌석은 최대 128개이며 id는 64자, label은 80자까지입니다. 제어문자는 사용할 수 없습니다.")
    abandoned = args.abandoned_seconds
    if abandoned is None:
        abandoned = 6 if args.demo else config["abandoned_seconds"]
    monitor = SeatMonitor(seats, config["confirm_frames"], config["grace_seconds"], abandoned)
    size = config["image_size"]
    if type(size) is not int or size < 32 or size % 32:
        raise ValueError("image_size는 32의 양의 배수여야 합니다.")
    conf = config["confidence"]
    if type(conf) not in (int, float) or not 0 < conf <= 1:
        raise ValueError("confidence는 0보다 크고 1 이하여야 합니다.")
    dimensions = config.get("capture_size", [640, 480])
    if not isinstance(dimensions, list) or len(dimensions) != 2 or not all(type(v) is int and v > 0 for v in dimensions):
        raise ValueError("capture_size에는 양의 정수 [너비, 높이]를 입력하세요.")
    if type(config.get("seat_crops", False)) is not bool:
        raise ValueError("seat_crops에는 true 또는 false를 입력하세요.")
    return config, monitor


def resolve_source(args, config):
    source = args.source if args.source is not None else config["source"]
    if type(source) is int and source >= 0:
        return source
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source에는 카메라 번호, picamera2 또는 영상 경로를 지정하세요.")
    if source.isdecimal() or source == "picamera2" or args.source is not None:
        return source
    return str(args.config.parent / source)


def demo_boxes(monitor):
    """Place one synthetic object inside each polygon, including concave regions."""
    positions = []
    for seat in monitor.seats:
        # Mid-scanline intervals bounded by consecutive polygon vertices.
        ys = sorted(set(y for _, y in seat.polygon))
        for bottom, top in zip(ys, ys[1:]):
            cy = (bottom + top) / 2
            xs = sorted(x1 + (cy-y1) * (x2-x1) / (y2-y1)
                        for (x1, y1), (x2, y2) in zip(seat.polygon, seat.polygon[1:] + seat.polygon[:1])
                        if min(y1, y2) < cy < max(y1, y2))
            if len(xs) >= 2:
                cx = (xs[0] + xs[1]) / 2
                positions.append((cx, cy, cx, cy))
                break
    return positions


def demo_frame(elapsed, period, positions):
    detections = []
    for index, box in enumerate(positions):
        phase = (elapsed + index * period / 2) % period
        if 3 <= phase < period - 4:
            detections.append(Detection("backpack" if index % 2 == 0 else "cup", 1.0, box))
        if 3 <= phase < 8 or period - 6 <= phase < period - 4:
            detections.append(Detection("person", 1.0, box))
    return detections


def run(args):
    config, monitor = load_settings(args)
    source = resolve_source(args, config)
    dimensions = config.get("capture_size", [640, 480])
    if args.calibrate:
        import cv2
        from .display import calibrate

        with ExitStack() as stack:
            camera = stack.enter_context(Camera(source, *dimensions))
            stack.callback(cv2.destroyAllWindows)
            saved = calibrate(camera.read(), config, args.config)
            logging.info("좌석 영역을 저장했습니다." if saved else "보정을 취소했습니다.")
        return

    stop = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    with ExitStack() as stack:
        publisher = Publisher(os.environ.get("MONITOR_ENDPOINT"), os.environ.get("MONITOR_TOKEN"))
        if args.demo:
            positions = demo_boxes(monitor)
            period = 20.0 + monitor.abandoned_seconds + monitor.grace_seconds
            logging.info("시연 모드 · 장기 방치 기준 %g초", monitor.abandoned_seconds)
        else:
            model_path = args.model or args.config.parent / config["model"]
            if not Path(model_path).exists():
                raise ValueError(f"모델 경로를 확인하세요: {model_path}")
            detector = YoloDetector(model_path, config["image_size"], config["confidence"])
            if detector.missing_labels:
                logging.warning("현재 가중치에 없는 클래스: %s", ", ".join(detector.missing_labels))
            logging.info("활성 클래스: %s", ", ".join(dict.fromkeys(detector.labels.values())))
            camera = stack.enter_context(Camera(source, *dimensions))
            use_crops = args.seat_crops or config.get("seat_crops", False)
            if args.preview:
                import cv2
                from .display import preview
                stack.callback(cv2.destroyAllWindows)
        stack.enter_context(publisher)
        indicators = stack.enter_context(Indicators(enabled=args.gpio))
        started = time.monotonic()
        last_capture = None
        last_sample = None
        frames = 0
        warmup = 0
        previous = None
        while not stop.is_set() and (args.frames is None or frames < args.frames):
            if not args.demo:
                try:
                    frame = camera.read()
                except EOFError:
                    break
            now = time.monotonic()
            observed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            if args.demo:
                detections = demo_frame(now - started, period, positions)
            elif use_crops:
                detections = detector.detect_seats(frame, monitor.seats)
            else:
                detections = detector.detect(frame)
            media_time = None if args.demo else camera.media_seconds
            sample_time = now if media_time is None else media_time
            rows = monitor.update(detections, sample_time)
            after_gap = last_sample is None or sample_time - last_sample > monitor.max_gap_seconds
            warmup = 1 if after_gap else warmup + 1
            fps = 1 / max(0.001, now-last_capture) if last_capture is not None else 0
            last_capture = now
            last_sample = sample_time
            if warmup >= monitor.confirm_frames:
                indicators.update(row["state"] for row in rows)
                states = [(row["id"], row["state"], tuple(row["items"])) for row in rows]
                if states != previous:
                    logging.info(" | ".join(f"{row['label']} {row['state']} ({row['awaySeconds']}s)" for row in rows))
                    previous = states
                replay = args.demo or media_time is not None
                publisher.offer({"observedAt": observed_at, "mode": "demo" if replay else "live", "seats": rows})
            else:
                indicators.update([])
            frames += 1
            if args.preview and not preview(frame, monitor.seats, rows, detections, fps):
                break
            if args.demo:
                stop.wait(0.25)
        logging.info("%d프레임 처리 후 종료했습니다.", frames)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run(options())
    except (OSError, RuntimeError, ValueError, ImportError, KeyError, TypeError) as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
