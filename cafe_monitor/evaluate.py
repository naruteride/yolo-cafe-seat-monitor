"""Evaluate the production detector against YOLO detection labels in images/val."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from .detector import YoloDetector

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Counts:
    matched: int = 0
    predicted: int = 0
    annotated: int = 0


def load_boxes(path, names):
    boxes = {name: [] for name in names.values()}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            class_id, cx, cy, width, height = line.split()
            label = names[int(class_id)]
            cx, cy, width, height = map(float, (cx, cy, width, height))
            if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < width <= 1 and 0 < height <= 1):
                raise ValueError("invalid normalized box")
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number} YOLO 주석을 확인하세요.") from exc
        boxes[label].append((cx - width / 2, cy - height / 2,
                             cx + width / 2, cy + height / 2))
    return boxes


def intersection_over_union(a, b):
    width = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = width * height
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / (area_a + area_b - intersection)


def score_frame(counts, annotations, detections, iou_threshold):
    # Each annotation matches at most one prediction of the same class and frame.
    remaining = {label: list(boxes) for label, boxes in annotations.items()}
    for label, boxes in annotations.items():
        counts[label].annotated += len(boxes)
    for detection in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if detection.label not in remaining:
            continue  # This frame has no reliable annotations for this class.
        totals = counts[detection.label]
        totals.predicted += 1
        boxes = remaining[detection.label]
        if boxes:
            overlaps = [intersection_over_union(detection.xyxy, box) for box in boxes]
            best = max(range(len(overlaps)), key=overlaps.__getitem__)
            if overlaps[best] >= iou_threshold:
                totals.matched += 1
                boxes.pop(best)


def evaluate(data_path, detector, iou_threshold):
    import cv2
    from ultralytics.utils import YAML

    data = YAML.load(data_path)
    names = data["names"]
    if isinstance(names, list):
        names = dict(enumerate(names))
    names = {int(i): label for i, label in names.items()}
    base = data_path.parent / data.get("path", ".")
    image_dir = base / data["val"]
    if image_dir.parent.name != "images":
        raise ValueError("검증 이미지 경로를 images/<분할 이름> 형식으로 지정하세요.")
    label_dir = image_dir.parent.parent / "labels" / image_dir.name
    images = sorted(p for p in image_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not images:
        raise ValueError(f"검증 이미지가 없습니다: {image_dir}")
    counts = {label: Counts() for label in names.values()}
    pencil_manifest = base / "lvis_pencils.json"
    pencil_annotated = None
    if pencil_manifest.is_file():
        source = json.loads(pencil_manifest.read_text(encoding="utf-8"))
        pencil_annotated = {row["file"] for row in source["images"]}
    for path in images:
        annotations = load_boxes(label_dir / f"{path.stem}.txt", names)
        if pencil_annotated is not None and path.name not in pencil_annotated:
            # The original six-class photos do not label the presence/absence of pencils.
            annotations.pop("pencil", None)
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {path}")
        score_frame(counts, annotations, detector.detect(frame), iou_threshold)
    return len(images), counts


def print_counts(label, counts):
    tp, pred, gt = counts.matched, counts.predicted, counts.annotated
    precision = f"{tp / pred:.3f}" if pred else "n/a"
    recall = f"{tp / gt:.3f}" if gt else "n/a"
    print(f"{label:<14} {gt:4} {tp:4} {pred - tp:4} {gt - tp:4} {precision:>10} {recall:>8}")


def main():
    defaults = json.loads((ROOT / "monitor.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description="실제 감지기로 YOLO 검증 분할의 정밀도·재현율을 계산합니다.")
    parser.add_argument("--model", default=ROOT / defaults["model"])
    parser.add_argument("--data", type=Path, default=ROOT / "cafe_coco80" / "data.yaml")
    parser.add_argument("--imgsz", type=int, default=defaults["image_size"])
    parser.add_argument("--confidence", type=float, default=defaults["confidence"])
    parser.add_argument("--iou", type=float, default=0.5)
    args = parser.parse_args()
    if args.imgsz <= 0 or not 0 < args.iou <= 1 or not 0 <= args.confidence <= 1:
        parser.error("imgsz > 0, 0 < iou <= 1, 0 <= confidence <= 1 조건을 확인하세요.")
    detector = YoloDetector(args.model, args.imgsz, args.confidence)
    images, counts = evaluate(args.data, detector, args.iou)
    print(f"images={images}  imgsz={args.imgsz}  confidence={args.confidence}  IoU≥{args.iou}")
    print(f"{'class':<14} {'GT':>4} {'TP':>4} {'FP':>4} {'FN':>4} {'precision':>10} {'recall':>8}")
    for label, row in counts.items():
        print_counts(label, row)
    combined = Counts(sum(c.matched for c in counts.values()), sum(c.predicted for c in counts.values()),
                      sum(c.annotated for c in counts.values()))
    print_counts("micro", combined)
    excluded = sorted(set(detector.labels.values()) - counts.keys())
    if excluded:
        print(f"데이터셋에 주석이 없어 평가에서 제외한 클래스: {', '.join(excluded)}")


if __name__ == "__main__":
    main()
