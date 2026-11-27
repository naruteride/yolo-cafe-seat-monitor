# 좌석 모니터용 탐지 모델

기본 가중치 `cafe-yoloe26n.pt`는 사람, 백팩, 핸드백, 컵, 노트북, 휴대전화, 연필을 출력합니다. YOLOE-26n의 객체 탐지 헤드에 클래스별 텍스트와 주석이 달린 이미지의 시각적 특징을 결합해 저장했습니다. 추론 시에는 인터넷 연결과 텍스트 인코더가 필요 없습니다. 서로 다른 모습의 연필을 찾는 두 출력은 앱에서 같은 물건 종류로 집계합니다. [Ultralytics YOLOE](https://docs.ultralytics.com/models/yoloe/)

## 사용한 자료

- 제공된 `cafe_coco80`의 학습 사진 60장 중 주석이 있는 사진에서 여섯 클래스의 특징을 추출했습니다. 원본 데이터의 사진·출처 목록은 `cafe_coco80/photo_credits.csv`에 있습니다.
- 연필은 LVIS v1의 나무·흑연 연필 주석을 사용했습니다. 연필 학습 사진은 35장, 연필 상자는 71개입니다. 사진 한 장이 제공된 학습 사진과 겹쳐, 합친 학습 분할은 94장입니다. 원본 사진, 제공자 정보, 라이선스 및 변환된 주석은 `lvis_pencils.json`에 있습니다. [LVIS 데이터셋](https://www.lvisdataset.org/) · [COCO 데이터셋](https://cocodataset.org/)
- `pencil_photo_check.json`에는 모델 확정 전에 별도로 수집한 책상 사진 세 장의 출처와 수작업 주석, 확정 후 측정값이 있습니다.

## 객체 탐지 검증

입력 크기 512, 신뢰도 0.35, 겹침 비율(IoU) 0.5 이상에서 같은 클래스의 정답 상자와 예측 상자를 일대일로 대응시켰습니다. 정밀도는 감지 결과 중 맞은 비율, 재현율은 주석이 있는 실제 객체 중 찾은 비율입니다.

| 모델 및 평가 범위 | 일치 | 오탐 | 누락 | 정밀도 | 재현율 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 기본 모델 · 제공된 검증 사진 20장, 6종 | 45 | 29 | 27 | 60.8% | 62.5% |
| 기본 모델 · 연필 주석 사진을 합친 25장, 7종 | 60 | 48 | 56 | 55.6% | 51.7% |
| NCNN FP16 · 같은 25장, 7종 | 57 | 48 | 59 | 54.3% | 49.1% |
| 기본 모델 · 연필 주석이 있는 5장의 연필만 | 2 | 3 | 19 | 40.0% | 9.5% |

원래의 검증 사진 20장은 연필 주석이 없어 그 사진에서 나온 연필 예측을 점수에서 제외했습니다. 검증 분할은 모델과 설정 선택에도 사용했습니다. **최종 모델 선택 후 따로 확인한 책상 사진에서는 연필 3개 중 1개를 찾았습니다.** 메모지 위 연필은 찾았고 키보드·공책 위 연필은 놓쳤습니다. 작은 연필만 남은 자리는 공석으로 잘못 표시될 수 있습니다. 카페 좌석 판정 정확도와 Raspberry Pi 4의 처리 FPS는 현장 영상과 실기기로 측정해야 합니다.

## 검증 및 재생성

기본 검증은 저장소 루트, 프로젝트 가상환경에서 실행합니다.

```sh
python -m cafe_monitor.evaluate
python models/prepare_pencil_dataset.py ../cafe-validation
python -m cafe_monitor.evaluate --data ../cafe-validation/data.yaml
python -m cafe_monitor.evaluate --model models/cafe-yoloe26n_ncnn_model --data ../cafe-validation/data.yaml
```

두 번째 명령은 사진별 출처에서 이미지를 다운로드해 새 디렉터리를 만듭니다. 같은 모델을 재생성하려면 PC의 별도 환경에서 아래 명령을 실행합니다. 사전 학습 가중치와 MobileCLIP 가중치는 처음 한 번 다운로드됩니다.

```sh
python -m pip install 'ultralytics==8.4.220' 'git+https://github.com/ultralytics/CLIP.git@7ffa84b3bfa40c42ecc1c77147a855e69cb2dd40'
project_dir="$PWD"
mkdir -p ../cafe-model-build
cd ../cafe-model-build
python "$project_dir/models/build_model.py" ../cafe-validation --output rebuilt.pt
```

프로젝트에 포함된 기본 가중치의 SHA-256은 `bd4cf3f52382239d4ef5f438219f66d89cd1cb3ed7853dd7144064920fb5e43a`입니다. Ultralytics 모델 라이선스 원문은 [ULTRALYTICS-LICENSE.txt](ULTRALYTICS-LICENSE.txt)에 있습니다.

## Raspberry Pi용 NCNN

`cafe-yoloe26n_ncnn_model/`은 입력 512×512, FP16으로 내보낸 동일 모델입니다. 가중치·네트워크 구조·클래스 메타데이터가 함께 들어 있습니다. 프로젝트 가상환경에서 NCNN을 설치하면 파이에서 변환 없이 실행할 수 있습니다.

```sh
python -m pip install 'ncnn==1.0.20261020'
python -m cafe_monitor --model models/cafe-yoloe26n_ncnn_model --preview
```

같은 카메라 위치에서 기본 모델과 비교해 감지 결과와 FPS를 확인하세요. 상시 운영할 때는 `monitor.json`의 `model`을 `models/cafe-yoloe26n_ncnn_model`로 설정하고 `image_size`를 512로 유지합니다. 다른 입력 크기로 내보낼 때는 PC에서 아래 명령의 `imgsz`를 변경합니다. [Ultralytics Raspberry Pi 가이드](https://docs.ultralytics.com/guides/raspberry-pi/)

```sh
python -m pip install 'ncnn==1.0.20261020' 'pnnx==20260526'
yolo export model=rebuilt.pt format=ncnn imgsz=512 quantize=16 device=cpu
```
