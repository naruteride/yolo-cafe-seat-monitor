"""Local OpenCV views for aligning the camera and checking inference."""

import json
import os
from tempfile import NamedTemporaryFile

from .state import Seat


def pixels(frame, point):
    height, width = frame.shape[:2]
    return round(point[0] * (width - 1)), round(point[1] * (height - 1))


def outline(cv2, frame, points, color, closed=True):
    if not points:
        return
    corners = [pixels(frame, pt) for pt in points]
    for start, end in zip(corners, corners[1:]):
        cv2.line(frame, start, end, color, 2)
    if closed and len(corners) >= 3:
        cv2.line(frame, corners[-1], corners[0], color, 2)


def caption(cv2, frame, text, anchor, color):
    """Keep labels readable at the image edges and over bright objects."""
    height, width = frame.shape[:2]
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    x = max(0, min(anchor[0], width - tw - 6))
    y = max(th + 4, min(anchor[1], height - baseline - 2))
    cv2.rectangle(frame, (x, y-th-3), (x+tw+5, y+baseline), (26, 29, 27), -1)
    cv2.putText(frame, text, (x+2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def annotate(frame, seats, rows, detections, fps, ready=True):
    """Draw the same inference result for the browser and the desktop window."""
    import cv2

    colors = {"EMPTY": (120, 200, 120), "OCCUPIED": (40, 215, 240),
              "AWAY": (18, 145, 245), "ABANDONED": (40, 45, 240)}
    for seat, row in zip(seats, rows):
        color = colors[row["state"]] if ready else (180, 180, 180)
        outline(cv2, frame, seat.polygon, color)
        status = f"{row['state']} {row['awaySeconds']}s" if ready else "Checking..."
        caption(cv2, frame, f"{seat.id} {status}", pixels(frame, seat.polygon[0]), color)
    for idx, obj in enumerate(detections, 1):
        x1, y1, x2, y2 = obj.xyxy
        corner = pixels(frame, (x1, y1))
        ink = (255, 220, 80) if obj.label == "person" else (130, 245, 235)
        cv2.rectangle(frame, corner, pixels(frame, (x2, y2)), ink, 2)
        caption(cv2, frame, f"#{idx} {obj.label} {obj.confidence:.0%}", corner, ink)
    caption(cv2, frame, f"{fps:.1f} FPS", (4, frame.shape[0] - 6), (240, 240, 240))
    return frame


def show_window(frame):
    import cv2

    window = "Cafe seat monitor (Q to quit)"
    cv2.imshow(window, frame)
    return cv2.waitKey(1) & 0xff not in (ord("q"), 27)


def jpeg_bytes(frame):
    import cv2

    ok, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise RuntimeError("카메라 프레임을 JPEG 영상으로 변환하지 못했습니다.")
    return data.tobytes()


def calibrate(frame, config, path):
    """Save polygons together only after the last table is accepted."""
    import cv2

    window = "Seat calibration"
    height, width = frame.shape[:2]
    points = []
    polygons = []
    title = "Click corners | Enter: accept | U: undo | Esc: cancel"

    def click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append([round(x / max(1, width - 1), 5), round(y / max(1, height - 1), 5)])

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, click)
    for row in config["seats"]:
        points.clear()
        while True:
            view = frame.copy()
            for previous in polygons:
                outline(cv2, view, previous, (100, 190, 100))
            outline(cv2, view, points, (0, 195, 255))
            for point in points:
                cv2.circle(view, pixels(view, point), 4, (0, 195, 255), -1)
            for n, line in enumerate((str(row["id"]), title)):
                cv2.putText(view, line, (7, 20 + n * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 2)
            cv2.imshow(window, view)
            key = cv2.waitKey(40) & 0xff
            if key in (27, ord("q")) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return False
            if key == ord("u") and points:
                points.pop()
            if key in (10, 13):
                try:
                    Seat(row["id"], row["label"], points)
                except ValueError as err:
                    print(err, flush=True)
                    continue
                polygons.append(points.copy())
                break

    for row, polygon in zip(config["seats"], polygons):
        row["polygon"] = polygon
    with NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(file.name, path)
    return True
