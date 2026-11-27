"""Assign YOLO detections to table regions and track item-only occupancy."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .detector import Detection

Point = tuple[float, float]


def _finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class Seat:
    id: str
    label: str
    polygon: tuple[Point, ...]

    def __post_init__(self):
        if not all(isinstance(s, str) and s.strip() for s in (self.id, self.label)):
            raise ValueError("좌석 id와 label에 이름을 입력하세요.")
        if not isinstance(self.polygon, (list, tuple)):
            raise ValueError(f"{self.id}: polygon에는 꼭짓점 목록이 필요합니다.")
        points = []
        for point in self.polygon:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError(f"{self.id}: 각 꼭짓점을 [x, y]로 지정하세요.")
            if not all(_finite_number(n) and 0 <= n <= 1 for n in point):
                raise ValueError(f"{self.id}: 좌표는 0부터 1 사이여야 합니다.")
            points.append(tuple(point))
        if len(points) > 1 and points[0] == points[-1]:
            points.pop()
        if len(points) < 3 or len(set(points)) != len(points):
            raise ValueError(f"{self.id}: 서로 다른 꼭짓점이 3개 이상 필요합니다.")
        area2 = sum(x * points[i-1][1] - y * points[i-1][0]
                    for i, (x, y) in enumerate(points))
        if abs(area2) < 1e-12:
            raise ValueError(f"{self.id}: 좌석 영역의 면적을 확인하세요.")
        object.__setattr__(self, "polygon", tuple(points))

    def contains(self, x: float, y: float) -> bool:
        """Ray casting for simple polygons, including their edges."""
        inside = False
        x1, y1 = self.polygon[-1]
        for x2, y2 in self.polygon:
            cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
            if (abs(cross) < 1e-12 and min(x1, x2) <= x <= max(x1, x2)
                    and min(y1, y2) <= y <= max(y1, y2)):
                return True
            if (y1 > y) != (y2 > y):
                crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < crossing_x:
                    inside = not inside
            x1, y1 = x2, y2
        return inside


@dataclass
class _Presence:
    streak: int = 0
    last_confirmed: float | None = None


@dataclass
class _SeatHistory:
    labels: dict[str, _Presence] = field(default_factory=dict)
    away_since: float | None = None


class SeatMonitor:
    def __init__(
        self,
        seats: Iterable[Seat],
        confirm_frames: int = 3,
        grace_seconds: float = 2.0,
        abandoned_seconds: float = 600.0,
        max_gap_seconds: float = 30.0,
    ):
        self.seats = tuple(seats)
        if not self.seats or len({s.id for s in self.seats}) != len(self.seats):
            raise ValueError("좌석을 하나 이상 등록하고 고유한 id를 사용하세요.")
        if type(confirm_frames) is not int or confirm_frames < 1:
            raise ValueError("confirm_frames는 1 이상의 정수여야 합니다.")
        if not _finite_number(grace_seconds) or grace_seconds < 0:
            raise ValueError("grace_seconds는 0 이상의 유한한 수여야 합니다.")
        for name, value in (("abandoned_seconds", abandoned_seconds),
                            ("max_gap_seconds", max_gap_seconds)):
            if not _finite_number(value) or value <= 0:
                raise ValueError(f"{name}는 0보다 큰 유한한 수여야 합니다.")
        self.confirm_frames = confirm_frames
        self.grace_seconds = grace_seconds
        self.abandoned_seconds = abandoned_seconds
        self.max_gap_seconds = max_gap_seconds
        self.reset()

    def reset(self):
        """Start a new uninterrupted observation period, e.g. after camera loss."""
        self._history = {s.id: _SeatHistory() for s in self.seats}
        self._last_frame: float | None = None

    def update(self, detections: Iterable[Detection], now: float | None = None) -> list[dict]:
        """Update once per successful frame. Supply monotonic seconds for replay."""
        if now is None:
            now = time.monotonic()
        if not _finite_number(now) or (self._last_frame is not None and now < self._last_frame):
            raise ValueError("프레임 시간은 단조 증가하는 유한한 수여야 합니다.")
        if self._last_frame is not None and now - self._last_frame > self.max_gap_seconds:
            self.reset()
        self._last_frame = now
        labels = {s.id: set() for s in self.seats}
        for detection in detections:
            x1, y1, x2, y2 = detection.xyxy
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            for seat in self.seats:
                if seat.contains(cx, cy):
                    labels[seat.id].add(detection.label)
                    break
        return [self._update_seat(seat, labels[seat.id], now) for seat in self.seats]

    def _update_seat(self, seat: Seat, observed: set[str], now: float) -> dict:
        history = self._history[seat.id]
        present = set()
        for label in history.labels.keys() | observed:
            evidence = history.labels.setdefault(label, _Presence())
            within_grace = (evidence.last_confirmed is not None
                            and now - evidence.last_confirmed <= self.grace_seconds)
            if label in observed:
                evidence.streak += 1
                if within_grace or evidence.streak >= self.confirm_frames:
                    evidence.last_confirmed = now
                    present.add(label)
            elif within_grace:
                evidence.streak = 0
                present.add(label)
            else:
                del history.labels[label]

        items = sorted(present - {"person"})
        elapsed = 0.0
        if "person" in present:
            state = "OCCUPIED"
            history.away_since = None
        elif items:
            if history.away_since is None:
                history.away_since = now
            elapsed = now - history.away_since
            state = "ABANDONED" if elapsed >= self.abandoned_seconds else "AWAY"
        else:
            state = "EMPTY"
            history.away_since = None
        return {"id": seat.id, "label": seat.label, "state": state,
                "items": items, "awaySeconds": int(elapsed)}
