# 카페 좌석 감지 연습용 COCO 80장

COCO 2017의 공식 val2017 사진에서 수업 제안서에 지정된 6종을 골랐습니다. 같은 사진이 이 묶음의 train과 val에 중복되지 않습니다. COCO의 공식 분할과 이 실습용 분할은 다릅니다. COCO 원본 벤치마크 성능 측정에 이 분할을 사용하면 안 됩니다.

이미지 원본은 그대로 유지했고, 목표 여섯 종류의 원본 경계 상자를 모두 YOLO 좌표로 변환했습니다. 대상 종류에 crowd 표기가 있는 사진은 제외했습니다. 다섯 소지품 각각을 충분히 포함하도록 골랐고, 사람 없는 소지품 사진과 사람·대상 소지품 표기가 없는 테이블 사진을 함께 넣었습니다. 공석·일시 비움·장기 방치는 이 자료에 표시되어 있지 않습니다. 고정 카메라 영상에서 테이블별 공간과 타이머로 판정합니다.

ZIP을 압축 해제한 뒤 cafe_coco80 폴더 안에서 실행하는 예시입니다. 첫 모델 다운로드에 인터넷이 필요합니다.

    yolo detect train model=yolo26n.pt data=data.yaml epochs=15 imgsz=320 batch=4

이 데이터로 학습한 모델의 출력 순서는 person=0, backpack=1, handbag=2, cup=3, laptop=4, cell phone=5입니다. 기본 COCO 가중치의 클래스 번호와 다릅니다.

## 출처

COCO Consortium, COCO 2017. https://cocodataset.org/
경계 상자 주석은 COCO Consortium의 CC BY 4.0 자료에서 6종만 골라 좌표 형식을 변환했습니다. https://creativecommons.org/licenses/by/4.0/
COCO 이용 조건 https://cocodataset.org/dataset/termsofuse.htm
사진은 개별 Flickr 촬영자 소유입니다. 각 사진의 제목, 촬영자, 원본 페이지 및 COCO에 기록된 사진별 라이선스(CC BY 2.0 또는 CC BY-SA 2.0)는 photo_credits.csv에 있습니다.

## 분포

중복 집계가 가능한 항목은 사진에 나타난 각 객체 종류입니다.

| 종류 | 학습 사진 | 검증 사진 |
| --- | ---: | ---: |
| person | 39 | 10 |
| backpack | 11 | 3 |
| handbag | 11 | 4 |
| cup | 19 | 7 |
| laptop | 16 | 3 |
| cell phone | 14 | 4 |
| 테이블 배경 (여섯 종 표기 없음) | 5 | 3 |
| 사람 없이 소지품 표기 | 16 | 7 |
| 사람만 표기 | 5 | 2 |
| 사람과 소지품 모두 표기 | 34 | 8 |
| 전체 | 60 | 20 |
