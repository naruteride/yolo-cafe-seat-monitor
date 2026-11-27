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


def preview(frame, seats, rows, detections, fps):
    import cv2

    colors = {"EMPTY": (120, 200, 120), "OCCUPIED": (40, 215, 240),
              "AWAY": (18, 145, 245), "ABANDONED": (40, 45, 240)}
    for obj in detections:
        x1, y1, x2, y2 = obj.xyxy
        start = pixels(frame, (x1, y1))
        cv2.rectangle(frame, start, pixels(frame, (x2, y2)), (220, 180, 40), 1)
        cv2.putText(frame, f"{obj.label} {obj.confidence:.2f}", start,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 180, 40), 1)
    for seat, row in zip(seats, rows):
        color = colors[row["state"]]
        outline(cv2, frame, seat.polygon, color)
        x, y = pixels(frame, seat.polygon[0])
        cv2.putText(frame, f"{seat.id} {row['state']} {row['awaySeconds']}s", (x, max(y, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(frame, f"{fps:.1f} FPS | Q to quit", (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.imshow("Cafe seat monitor", frame)
    return cv2.waitKey(1) & 0xff not in (ord("q"), 27)


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
