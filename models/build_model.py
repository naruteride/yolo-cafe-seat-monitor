"""Rebuild the fixed YOLOE-26n detector from the two documented training splits.

In a working directory with ultralytics==8.4.220 and ultralytics/CLIP, run
python /path/to/models/build_model.py /path/to/prepared_cafe_dataset
The official yoloe-26n-seg.pt and mobileclip2_b.ts are downloaded on first use.
"""

import argparse
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.nn.functional import normalize
from ultralytics import YOLOE
from ultralytics.models.yolo.yoloe.predict import YOLOEVPDetectPredictor
from ultralytics.utils import YAML

ROOT = Path(__file__).resolve().parents[1]
SUPPLIED = ROOT / "cafe_coco80"
# Wood pencil in hand, yellow desk pencil, and a group of art pencils (LVIS train).
PENCIL_REFERENCES = {122678, 122116, 381257}


@torch.inference_mode()
def visual_prototypes(model, dataset, size, *, pencil_only=False, selected=None):
    predictor = YOLOEVPDetectPredictor(overrides={"imgsz": size, "device": "cpu", "verbose": False})
    predictor.setup_model(model=model.model, verbose=False)
    observations = defaultdict(list)
    for label_file in sorted((dataset / "labels" / "train").glob("*.txt")):
        if selected is not None and int(label_file.stem) not in selected:
            continue
        rows = [list(map(float, line.split())) for line in label_file.read_text().splitlines() if line.strip()]
        if pencil_only:
            rows = [row for row in rows if row[0] == 6]
        if not rows:
            continue
        anns = np.asarray(rows, dtype=np.float32)
        image = cv2.imread(str(dataset / "images" / "train" / label_file.with_suffix(".jpg").name))
        if image is None:
            raise ValueError(f"Unreadable training image for {label_file}")
        h, w = image.shape[:2]
        centers, sizes = anns[:, 1:3], anns[:, 3:5]
        boxes = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1) * [w, h, w, h]
        classes, prompt_ids = np.unique(anns[:, 0].astype(int), return_inverse=True)
        predictor.set_prompts({"bboxes": boxes, "cls": prompt_ids})
        vectors = predictor.get_vpe(image)[0]
        for class_id, vector in zip(classes, vectors):
            observations[class_id].append(vector)
    # Give each photo equal weight, including crowded photos with many boxes.
    return {i: normalize(torch.stack(vectors).mean(0), dim=0) for i, vectors in observations.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="models/prepare_pencil_dataset.py output directory")
    parser.add_argument("--output", type=Path, default=ROOT / "models" / "cafe-yoloe26n.pt")
    args = parser.parse_args()
    names = list(YAML.load(SUPPLIED / "data.yaml")["names"].values())
    model = YOLOE("yoloe-26n.yaml", task="detect").load("yoloe-26n-seg.pt")
    model.model.eval()
    text = model.get_text_pe(names)[0]
    pencil_text = model.get_text_pe(["a long thin yellow pencil"])[0, 0]
    visual = visual_prototypes(model, SUPPLIED, 640)
    pencils = visual_prototypes(model, args.dataset, 416, pencil_only=True)
    closeups = visual_prototypes(model, args.dataset, 640, pencil_only=True, selected=PENCIL_REFERENCES)
    # Weight visual evidence more strongly for the bag and phone labels.
    fractions = (0.10, 0.30, 0.15, 0.10, 0.10, 0.35)
    vectors = [normalize((1 - f) * text[i] + f * visual[i], dim=0) for i, f in enumerate(fractions)]
    # Two pencil appearances share one application label in the exported model metadata.
    vectors.append(normalize(0.75 * pencil_text + 0.25 * closeups[6], dim=0))
    vectors.append(normalize(0.55 * pencil_text + 0.45 * pencils[6], dim=0))
    model.set_classes(names + ["pencil", "pencil"], torch.stack(vectors).unsqueeze(0))
    model.model.model[-1].fuse(model.model.pe)
    model.fuse(verbose=False)
    model.ckpt = {"train_args": {"task": "detect"}}
    model.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
