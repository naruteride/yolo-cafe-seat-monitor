"""Resolve detector classes from the loaded weights and return normalized boxes."""

from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path


DEFAULT_ITEMS = ("backpack", "handbag", "cup", "laptop", "cell phone", "pencil")
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "cafe-yoloe26n.pt"


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    xyxy: tuple[float, float, float, float]


def _label_key(label):
    return " ".join(label.casefold().replace("_", " ").split())


class YoloDetector:
    def __init__(self, model_path=DEFAULT_MODEL, image_size=512, confidence=0.35, item_labels=None):
        from ultralytics import YOLO

        path = Path(model_path)
        if path.is_dir() and path.name.endswith("_ncnn_model"):
            from ultralytics.utils import YAML

            metadata = YAML.load(path / "metadata.yaml")
            if metadata.get("imgsz") != [image_size, image_size]:
                raise ValueError(f"NCNN 입력 크기 {metadata.get('imgsz')}에 맞게 image_size를 설정하세요.")
        self.model = YOLO(str(model_path), task="detect")
        self.image_size = image_size
        self.confidence = confidence
        items = DEFAULT_ITEMS if item_labels is None else item_labels
        wanted = {_label_key(name) for name in items}
        wanted.add("person")
        # COCO and the six-class cafe dataset assign different IDs to the same names.
        self.labels = {
            int(class_id): _label_key(name)
            for class_id, name in self.model.names.items()
            if _label_key(name) in wanted
        }
        active = set(self.labels.values())
        if "person" not in active or len(active) < 2:
            raise ValueError(
                "모델 클래스 이름에 person과 설정된 소지품 중 하나 이상이 필요합니다. "
                f"모델에 등록된 클래스: {list(self.model.names.values())}"
            )
        self.missing_labels = sorted(wanted - active)

    def detect(self, frame):
        result = self.model.predict(
            source=frame,
            imgsz=self.image_size,
            conf=self.confidence,
            classes=list(self.labels),
            device="cpu",
            verbose=False,
        )[0]
        if result.boxes is None:
            return []
        return [
            Detection(self.labels[int(class_id)], score, tuple(bounds))
            for class_id, score, bounds in zip(
                result.boxes.cls.tolist(),
                result.boxes.conf.tolist(),
                result.boxes.xyxyn.tolist(),
            )
            if int(class_id) in self.labels
        ]

    def detect_seats(self, frame, seats):
        """Use the model's full input resolution for each table in a wide shot."""
        height, width = frame.shape[:2]
        detections = []
        for seat in seats:
            xs, ys = zip(*seat.polygon)
            # Keep context around people and objects that straddle the table boundary.
            pad_x, pad_y = (max(xs) - min(xs)) * 0.15, (max(ys) - min(ys)) * 0.15
            left = max(0, floor((min(xs) - pad_x) * width))
            right = min(width, ceil((max(xs) + pad_x) * width))
            top = max(0, floor((min(ys) - pad_y) * height))
            bottom = min(height, ceil((max(ys) + pad_y) * height))
            for obj in self.detect(frame[top:bottom, left:right]):
                x1, y1, x2, y2 = obj.xyxy
                box = ((left + x1 * (right-left)) / width, (top + y1 * (bottom-top)) / height,
                       (left + x2 * (right-left)) / width, (top + y2 * (bottom-top)) / height)
                if seat.contains((box[0] + box[2]) / 2, (box[1] + box[3]) / 2):
                    detections.append(Detection(obj.label, obj.confidence, box))
        return detections
