"""Assemble the supplied COCO subset with pencil-labelled LVIS images for training."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent
SUPPLIED = HERE.parent / "cafe_coco80"


def add_lvis_image(stage, row):
    name, split = row["file"], row["split"]
    image = stage / "images" / split / name
    if not image.exists():
        with urlopen(row["source"], timeout=30) as response, image.open("wb") as output:
            shutil.copyfileobj(response, output)
    (stage / "labels" / split / image.with_suffix(".txt").name).write_text(
        "\n".join(row["annotations"]) + "\n", encoding="utf-8"
    )


def prepare(destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("새 데이터셋을 저장할 빈 경로(아직 생성되지 않은 폴더)를 지정하세요.")
    manifest = json.loads((HERE / "lvis_pencils.json").read_text(encoding="utf-8"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temp:
        stage = Path(temp) / "dataset"
        for kind in ("images", "labels"):
            shutil.copytree(SUPPLIED / kind, stage / kind)
        shutil.copy2(SUPPLIED / "photo_credits.csv", stage)
        shutil.copy2(HERE / "lvis_pencils.json", stage)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda row: add_lvis_image(stage, row), manifest["images"]))
        config = (SUPPLIED / "data.yaml").read_text(encoding="utf-8").rstrip()
        (stage / "data.yaml").write_text(
            f"path: {json.dumps(str(destination), ensure_ascii=False)}\n{config}\n  6: pencil\n",
            encoding="utf-8",
        )
        stage.rename(destination)
    return destination / "data.yaml"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="새 데이터셋 폴더 경로")
    print(prepare(parser.parse_args().destination))
