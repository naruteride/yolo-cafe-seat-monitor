# 자리봄 · 카페 좌석 모니터

라즈베리파이 4 한 대와 고정 카메라로 여러 테이블을 관찰합니다. 파이에서 YOLO가 사람과 소지품을 찾고, 각 테이블의 상태를 판정해 LED와 부저를 제어합니다. 손님이나 관리자는 웹에서 이용 가능한 자리 수, 테이블별 상태, 감지된 물건과 비움 시간을 확인할 수 있습니다. 한 테이블을 한 자리로 집계하는 설정을 기본으로 제공합니다.

## 실제 카메라 영상과 인식 결과 보기

프로젝트 가상환경에 의존성을 준비한 뒤 저장소 루트에서 실행합니다. 파이는 아래 Raspberry Pi OS 설치 절차를 따릅니다. macOS는 Python 3.12 환경에서 `python3.12 -m venv .venv`, `.venv/bin/python -m pip install -r requirements-pi.txt`로 준비할 수 있습니다. USB 웹캠과 노트북 내장 카메라는 기본 장치 번호 `0`을 사용합니다.

```sh
npm --prefix web run camera
```

[카메라 운영 화면](http://127.0.0.1:3000/)을 엽니다. 실제 프레임이 들어오면 **카메라 작동 중** 표시와 함께 영상에 물체별 번호, 탐지 상자, 클래스와 신뢰도가 나타납니다. 아래 한글 목록에서 같은 번호의 물건을 확인할 수 있습니다. FPS는 카메라 처리 속도이며 브라우저 미리보기는 파이의 부하를 줄이기 위해 초당 최대 5장으로 갱신합니다.

카메라를 열 수 없거나 연결이 끊기면 화면에 원인이 표시되고 5초 후 다시 시도합니다. 장치 번호를 바꿀 때는 실행 중인 모니터를 Ctrl+C로 종료한 뒤 `npm --prefix web run camera -- --source 1`로 다시 시작하세요. CSI 카메라는 `--source picamera2`를 사용합니다. macOS에서는 처음 실행한 앱의 카메라 접근 권한을 허용해야 합니다.

Node.js가 없는 파이에서는 `.venv/bin/python -m cafe_monitor --viewer`를 실행한 뒤 [파이 운영 화면](http://127.0.0.1:8765/)을 엽니다. 디스플레이가 없는 파이는 노트북에서 `ssh -N -L 8765:127.0.0.1:8765 사용자명@파이주소`를 실행하고 노트북 브라우저로 같은 주소를 엽니다. 자동 실행 서비스가 이미 카메라를 사용 중이면 그 서비스의 운영 화면에 접속하세요. Vercel의 공개 대시보드에는 좌석 정보만 전송됩니다.

## 카메라 없이 웹에서 시연하기

Node.js 22와 Python 3.10 이상이 설치된 컴퓨터에서 저장소 루트의 다음 명령을 실행합니다. 파이썬 패키지 설치 없이 사용할 수 있습니다.

```sh
npm --prefix web run demo
```

브라우저에서 [로컬 좌석 현황](http://127.0.0.1:3000)을 엽니다. 두 테이블에 사람과 물건이 나타나고 사라지며, 파이에서 사용하는 것과 같은 판정 코드로 네 가지 상태를 순환합니다. 화면에 **시연 데이터**라고 표시됩니다. 시연 중 장기 방치 기준은 6초입니다. Ctrl+C로 종료합니다.

## 라즈베리파이 4에 설치하기

Raspberry Pi OS **64-bit Bookworm**, 시스템 Python 3.11을 기준으로 합니다. 저장소를 파이에 복사하거나 복제하고 프로젝트 루트에서 실행합니다. 첫 패키지 설치에는 인터넷이 필요합니다. 추론 가중치는 프로젝트에 포함되어 있습니다.

```sh
sudo apt update
sudo apt install -y python3-venv python3-gpiozero python3-lgpio python3-picamera2
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -r requirements-pi.txt
```

USB 웹캠은 기본 번호 `0`을 사용합니다. CSI 리본 카메라는 `monitor.json`의 `source`를 `"picamera2"`로 설정하거나 실행할 때 `--source picamera2`를 붙입니다. 카메라를 실제 설치 위치에 고정한 뒤 영역을 보정하세요.

```sh
python -m cafe_monitor --calibrate
python -m cafe_monitor --preview
```

보정 창에서는 안내된 테이블의 꼭짓점을 테두리 순서대로 클릭하고 Enter를 누릅니다. U는 직전 점을 취소하고 Esc는 전체 보정을 취소합니다. 마지막 테이블까지 확정하면 선택한 설정 파일에 저장합니다. 미리보기에는 탐지 상자, 클래스, 테이블 상태와 처리 FPS가 표시됩니다. Q로 종료합니다. 보정과 미리보기에는 로컬 디스플레이가 필요합니다.

화면 없이 설치할 경우 `monitor.json`의 `seats`를 직접 편집할 수 있습니다. 테이블마다 고유한 `id`, 표시용 `label`, 다각형 `polygon`을 지정합니다. 좌상단은 `[0, 0]`, 우하단은 `[1, 1]`입니다. 영역에는 **앉은 사람의 몸통과 테이블 위 물건의 중심점**이 모두 들어가야 합니다. 겹친 영역에 있는 객체는 설정 순서상 첫 테이블에 배정됩니다. 설치 장소별 파일은 `--config 경로.json`으로 선택합니다. 설정 파일 안의 상대 경로는 그 파일 위치를 기준으로 합니다.

## 실제 운영과 하드웨어

```sh
python gpio_test.py                          # 배선 점검
python -m cafe_monitor --gpio                # 화면 없이 운영
python -m cafe_monitor --preview --gpio --abandoned-seconds 10
```

`--gpio`를 생략하면 카메라와 웹 송신만 동작합니다. 핀 번호는 BCM 기준입니다. 초록 LED는 17, 노랑은 27, 빨강은 22, 능동 부저 제어 입력은 18입니다. 각 LED에는 직렬 저항을 사용합니다. 부저는 GPIO 전류 한도에 맞는 3.3V 제어 입력 모듈이나 드라이버를 사용하고 접지를 공유합니다.

| 테이블 상태 | 판정 기준 | 공용 표시등 한 세트의 동작 |
| --- | --- | --- |
| 이용 가능 · EMPTY | 사람과 물건 모두 없음 | 모든 자리가 비면 초록 |
| 이용 중 · OCCUPIED | 사람이 있음 | 노랑 |
| 일시 비움 · AWAY | 사람 없이 물건만 남아 기준 시간 미만 | 노랑 |
| 장기 방치 · ABANDONED | 물건만 남은 시간이 기준 이상 | 빨강 점멸, 경보 진입 시 부저 두 번 |

여러 테이블이 서로 다른 상태일 때 장기 방치 경보가 우선합니다. 웹에서는 각 테이블을 개별적으로 확인할 수 있습니다. 기본값은 연속 3프레임 확인, 잠깐의 가림 2초 허용, 장기 방치 600초입니다. 사람이 돌아오거나 물건을 치우면 해당 타이머가 초기화됩니다. 프로그램 재시작 또는 30초를 넘는 관측 공백 뒤에는 새 관측부터 시간을 셉니다.

`monitor.json`의 `image_size`(기본 512), `confidence`(0.35), `abandoned_seconds`를 현장에 맞게 조절합니다. 특히 연필·휴대전화처럼 작은 물건은 카메라 거리와 해상도의 영향을 받습니다. 넓게 촬영할 때는 카메라가 지원하는 `capture_size`(예: `[1280, 720]`)로 설정하고 `python -m cafe_monitor --preview --seat-crops`를 실행해 보세요. 이 모드는 테이블마다 영상을 잘라 같은 해상도로 추론하므로 한 프레임의 추론 횟수가 테이블 수만큼 늘어납니다. 미리보기에서 FPS와 감지 결과를 확인한 뒤 `seat_crops`를 `true`로 저장하면 상시 적용됩니다.

실제 설치 높이에서 사람이 앉기 → 소지품을 두고 떠나기 → 경보 → 복귀 → 물건 치우기 순서로 확인하세요. 현장 영상을 재생할 때는 `python -m cafe_monitor --source sample.mp4 --preview`를 사용합니다. 파일 재생의 비움 시간은 영상 타임스탬프 기준이며, 웹에는 시연으로 표시됩니다.

## Vercel 웹 연결

1. 저장소를 Vercel 프로젝트로 가져와 **Root Directory**를 `web`, **Framework Preset**을 `Other`로 설정합니다. 저장소 루트의 파이썬·모델 파일은 파이에서 실행합니다.
2. Vercel Marketplace에서 **Upstash Redis**를 연결합니다. 프로젝트 환경 변수에 `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`이 있어야 합니다. `KV_REST_API_URL`과 `KV_REST_API_TOKEN` 이름도 지원합니다.
3. `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`로 송신용 토큰을 한 번 생성합니다. Vercel의 `MONITOR_TOKEN`과 파이의 `MONITOR_TOKEN`에 같은 값을 사용합니다. Vercel에서 운영 환경 변수를 설정한 뒤 배포합니다.
4. 파이에서 아래와 같이 실제 배포 주소를 설정하고 실행합니다. Redis 자격 증명은 Vercel 서버에서만 사용합니다.

```sh
export MONITOR_ENDPOINT='https://YOUR-PROJECT.vercel.app/api/status'
read -rsp 'MONITOR_TOKEN: ' MONITOR_TOKEN; echo
export MONITOR_TOKEN
.venv/bin/python -m cafe_monitor --gpio
```

브라우저에서 배포 주소의 첫 화면을 엽니다. 첫 관측 전에는 연결 대기 상태이며, 5초마다 최신 집계가 갱신됩니다. 30초 동안 새 관측이 도착하지 않으면 실시간 집계는 숨기고 마지막 시각과 좌석 기록을 표시합니다. 웹 송신에 실패해도 파이의 좌석 판정과 GPIO 제어는 계속됩니다. 파이의 시계는 자동 동기화를 켜 두세요.

`GET /api/status`는 공개 현황을 읽습니다. 파이만 `Authorization: Bearer <MONITOR_TOKEN>`으로 `POST /api/status`를 호출합니다. 전송 내용은 관측 시각·모드와 테이블별 ID, 이름, 상태, 물건 종류, 비움 시간입니다. 영상과 탐지 상자 좌표는 파이에 머뭅니다. Redis에는 파이 한 대의 최신 관측 한 건을 저장합니다. 뒤늦게 도착한 이전 관측은 최신 상태를 덮어쓰지 않습니다. [Vercel Functions](https://vercel.com/docs/functions/runtimes/node-js) · [Upstash REST API](https://upstash.com/docs/redis/features/restapi)

## 부팅 후 자동 실행

저장소가 파이의 `~/yolo-cafe-seat-monitor`에 있을 때 아래 사용자 서비스를 사용할 수 있습니다. 다른 경로라면 `deploy/cafe-monitor.service`의 두 프로젝트 경로를 수정합니다. `monitor.json`에 사용할 카메라 소스를 먼저 지정합니다.

```sh
mkdir -p ~/.config/systemd/user
install -m 644 deploy/cafe-monitor.service ~/.config/systemd/user/
touch ~/.config/cafe-monitor.env
chmod 600 ~/.config/cafe-monitor.env
nano ~/.config/cafe-monitor.env
```

환경 파일에 `MONITOR_ENDPOINT=https://실제도메인/api/status`와 `MONITOR_TOKEN=발급한값`을 한 줄씩 입력합니다. 웹 송신 없이 운영할 때는 환경 파일을 생략합니다. 서비스는 GPIO 사용을 기본으로 합니다.

```sh
systemctl --user daemon-reload
systemctl --user enable --now cafe-monitor.service
loginctl enable-linger "$USER"
journalctl --user -u cafe-monitor.service -f
```

서비스는 카메라 운영 화면을 파이의 8765번 포트에서 제공합니다. 이전 버전을 설치한 파이는 수정된 서비스 파일을 다시 복사한 뒤 `systemctl --user daemon-reload`, `systemctl --user restart cafe-monitor`를 실행합니다. 배선 점검·보정 때는 `systemctl --user stop cafe-monitor`로 먼저 중지하고 완료 후 다시 시작합니다.

## 프로그램 구성

- `cafe_monitor/` — 카메라 입력, YOLO 추론, 다각형 매핑, 타이머, GPIO와 웹 송신. 실행 진입점은 `python -m cafe_monitor`입니다.
- `monitor.json` — 카메라·모델과 설치 장소별 테이블 좌표.
- `models/`, `cafe_coco80/` — 가중치와 모델 준비 자료, 제공된 이미지·주석 및 사진별 출처.
- `web/` — 한국어 대시보드, Vercel 함수와 로컬 시연 서버.
- `seat_monitor.py`, `seat_monitor2.py` — 개발에 참고한 초기 좌석 판정·GPIO 코드.

가중치 재생성, 실제 사진의 검증 결과, Pi용 NCNN 실행 방법은 [모델 안내서](models/README.md)에 있습니다. 기본 모델은 제공된 검증 사진 20장에서 6종 객체 72개 중 45개를 찾았습니다. 연필은 추가 검증 사진에 표시된 21개 중 2개를 찾았습니다. 연필 한 자루로 유지되는 자리를 판정할 때 특히 주의가 필요합니다.

```sh
python3 -m unittest discover -s tests -v
npm --prefix web test
```
