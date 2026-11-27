import time
import cv2
from ultralytics import YOLO

# 1. 모델 및 영상 입력 설정
MODEL_PATH = "yolo11n.pt"  # 라즈베리파이에서 느리면 onnx / ncnn 변환 모델 사용 가능
SOURCE = 0  # 0: USB 웹캠 또는 OpenCV로 잡히는 카메라 인덱스
IMG_SIZE = 416  # 라즈베리파이 속도 조절용 (320, 416, 640 등 테스트)
CONF_THRES = 0.4

# 탐지할 클래스 (COCO 기준: person=0, backpack=24, handbag=26, cup=41, laptop=63)
PERSON_CLASS_ID = 0
ITEM_CLASS_IDS = {24, 26, 41, 63}

# 2. 테이블 ROI 영역 설정 (정규화 좌표 x1, y1, x2, y2: 0.0 ~ 1.0)
# 해상도가 바뀌어도 비율로 유지되도록 설정
TABLES_ROI = {
    "Table_1": (0.05, 0.25, 0.48, 0.85),
    "Table_2": (0.52, 0.25, 0.95, 0.85),
}

# 3. 상태 판정 및 타이머 파라미터 (초 단위)
# 실제 운영 시에는 AWAY_TO_ABANDONED_SEC를 늘리고, 시연 시에는 짧게(예: 10초) 둡니다.
CONFIRM_FRAMES = 3          # 연속 N프레임 이상 보여야 탐지 인정 (프레임 튐 방지)
GRACE_SEC = 2.0             # 사람이 잠깐 가려졌을 때 바로 상태가 튀지 않게 버티는 시간
AWAY_TO_ABANDONED_SEC = 10.0  # 사람이 없는 채 소지품만 남은 상태로 '장기 방치' 전환 시간

# 상태 상수
STATE_EMPTY = "EMPTY"          # 공석
STATE_OCCUPIED = "OCCUPIED"    # 이용 중
STATE_AWAY = "AWAY"            # 일시 비움
STATE_ABANDONED = "ABANDONED"  # 장기 방치

# 상태별 화면 표시 색상 (BGR)
STATE_COLORS = {
    STATE_EMPTY: (120, 200, 120),      # 연초록
    STATE_OCCUPIED: (0, 220, 255),     # 노랑
    STATE_AWAY: (0, 140, 255),         # 주황
    STATE_ABANDONED: (0, 0, 255),      # 빨강
}


def box_center_in_roi(box_xyxy, roi_norm, frame_w, frame_h):
    """바운딩 박스 중심점이 테이블 ROI 내부에 있는지 판별"""
    x1, y1, x2, y2 = box_xyxy
    cx = ((x1 + x2) / 2.0) / frame_w
    cy = ((y1 + y2) / 2.0) / frame_h
    rx1, ry1, rx2, ry2 = roi_norm
    return (rx1 <= cx <= rx2) and (ry1 <= cy <= ry2)


class TableTracker:
    def __init__(self, name):
        self.name = name
        self.state = STATE_EMPTY
        self.person_streak = 0
        self.item_streak = 0
        self.last_person_seen = None
        self.last_item_seen = None
        self.away_start_time = None

    def update(self, raw_person, raw_item, now):
        # 연속 프레임 카운트로 순간 오탐/누락 완화
        self.person_streak = self.person_streak + 1 if raw_person else 0
        self.item_streak = self.item_streak + 1 if raw_item else 0

        person_confirmed = self.person_streak >= CONFIRM_FRAMES
        item_confirmed = self.item_streak >= CONFIRM_FRAMES

        if person_confirmed:
            self.last_person_seen = now
        if item_confirmed:
            self.last_item_seen = now

        # 짧은 가림(GRACE_SEC)을 감안한 유효 존재 여부
        has_person = person_confirmed or (
            self.last_person_seen is not None and (now - self.last_person_seen) <= GRACE_SEC
        )
        has_item = item_confirmed or (
            self.last_item_seen is not None and (now - self.last_item_seen) <= GRACE_SEC
        )

        # 4단계 상태 머신 전이
        if has_person:
            self.state = STATE_OCCUPIED
            self.away_start_time = None
        else:
            # 사람이 없는 상태
            if has_item:
                if self.away_start_time is None:
                    self.away_start_time = now
                    self.state = STATE_AWAY
                else:
                    elapsed_away = now - self.away_start_time
                    if elapsed_away >= AWAY_TO_ABANDONED_SEC:
                        self.state = STATE_ABANDONED
                    else:
                        self.state = STATE_AWAY
            else:
                # 사람도 소지품도 없음
                self.state = STATE_EMPTY
                self.away_start_time = None

    def get_away_elapsed(self, now):
        if self.away_start_time is None:
            return 0.0
        return max(0.0, now - self.away_start_time)


def main():
    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(SOURCE)

    if not cap.isOpened():
        raise RuntimeError("카메라를 열 수 없습니다. 연결 및 인덱스를 확인하세요.")

    trackers = {name: TableTracker(name) for name in TABLES_ROI}
    prev_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("프레임을 읽지 못했습니다.")
            break

        now = time.time()
        dt = now - prev_time
        prev_time = now
        fps = (1.0 / dt) if dt > 0 else 0.0

        h, w, _ = frame.shape

        # YOLO 추론 수행
        target_classes = [PERSON_CLASS_ID] + list(ITEM_CLASS_IDS)
        results = model.predict(
            source=frame,
            imgsz=IMG_SIZE,
            conf=CONF_THRES,
            classes=target_classes,
            verbose=False,
        )

        boxes = results[0].boxes
        table_person_detected = {name: False for name in TABLES_ROI}
        table_item_detected = {name: False for name in TABLES_ROI}

        # 탐지된 객체를 테이블 ROI에 매핑
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls[0].item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0].item())

                for t_name, roi in TABLES_ROI.items():
                    if box_center_in_roi((x1, y1, x2, y2), roi, w, h):
                        if cls_id == PERSON_CLASS_ID:
                            table_person_detected[t_name] = True
                        elif cls_id in ITEM_CLASS_IDS:
                            table_item_detected[t_name] = True

                # 탐지 바운딩 박스 그리기
                label = f"{model.names[cls_id]} {conf:.2f}"
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 200, 0), 2)
                cv2.putText(
                    frame,
                    label,
                    (int(x1), max(20, int(y1) - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 200, 0),
                    1,
                )

        # 테이블별 상태 갱신 및 시각화
        for t_name, roi in TABLES_ROI.items():
            tracker = trackers[t_name]
            tracker.update(
                raw_person=table_person_detected[t_name],
                raw_item=table_item_detected[t_name],
                now=now,
            )

            rx1, ry1, rx2, ry2 = roi
            px1, py1, px2, py2 = int(rx1 * w), int(ry1 * h), int(rx2 * w), int(ry2 * h)
            color = STATE_COLORS[tracker.state]

            # ROI 영역 박스
            cv2.rectangle(frame, (px1, py1), (px2, py2), color, 2)

            # 상태 및 자리 비움 경과 시간 텍스트
            elapsed = tracker.get_away_elapsed(now)
            info_text = f"{t_name}: {tracker.state}"
            if tracker.state in (STATE_AWAY, STATE_ABANDONED):
                info_text += f" ({elapsed:.1f}s)"

            cv2.putText(
                frame,
                info_text,
                (px1 + 8, py1 + 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )

        # [여기에 브레드보드 LED / 부저 GPIO 제어 함수 호출 추가 가능]
        # 예: update_gpio(trackers["Table_1"].state, trackers["Table_2"].state)

        cv2.putText(
            frame,
            f"FPS: {fps:.1f} | imgsz: {IMG_SIZE}",
            (15, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        cv2.imshow("Cafe Seat Monitor", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
