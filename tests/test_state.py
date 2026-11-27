import unittest
from typing import NamedTuple

from cafe_monitor.state import Seat, SeatMonitor


class Observation(NamedTuple):
    label: str
    xyxy: tuple


def at(label, x=0.25, y=0.5):
    return Observation(label, (x - 0.05, y - 0.05, x + 0.05, y + 0.05))


LEFT = Seat("L", "왼쪽", [(0, 0), (0.5, 0), (0.5, 1), (0, 1)])
RIGHT = Seat("R", "오른쪽", [(0.5, 0), (1, 0), (1, 1), (0.5, 1)])


class SeatMonitorTests(unittest.TestCase):
    def test_person_departure_threshold_return_and_removal(self):
        monitor = SeatMonitor([LEFT], confirm_frames=1, grace_seconds=0, abandoned_seconds=5)
        cup = at("cup")
        person = at("person")
        scenarios = [
            (0, [], "EMPTY", 0),
            (1, [person, cup], "OCCUPIED", 0),
            (3, [cup], "AWAY", 0),
            (7.9, [cup], "AWAY", 4),
            (8, [cup], "ABANDONED", 5),
            (9, [person, cup], "OCCUPIED", 0),
            (10, [cup], "AWAY", 0),
            (11, [], "EMPTY", 0),
            (15, [cup], "AWAY", 0),
        ]
        for now, seen, state, elapsed in scenarios:
            with self.subTest(now=now):
                [row] = monitor.update(seen, now)
                self.assertEqual((row["state"], row["awaySeconds"]), (state, elapsed))

    def test_streaks_count_frames_and_grace_recovers_brief_occlusion(self):
        monitor = SeatMonitor([LEFT], confirm_frames=2, grace_seconds=2)
        cup = at("cup")
        for now, seen, items in [
            (0, [cup, cup], []),
            (1, [], []),
            (2, [cup], []),
            (3, [cup], ["cup"]),
            (4, [], ["cup"]),
            (5, [cup], ["cup"]),
            (7, [], ["cup"]),
            (7.1, [], []),
            (8, [cup], []),
        ]:
            with self.subTest(now=now):
                self.assertEqual(monitor.update(seen, now)[0]["items"], items)

    def test_polygons_limit_assignment_and_ties_go_to_first_seat(self):
        triangle = Seat("T", "테이블", [(0, 0), (0.5, 0), (0, 1)])
        monitor = SeatMonitor([triangle, LEFT, RIGHT], confirm_frames=1)
        rows = monitor.update([
            at("cup", 0.1, 0.2),
            at("person", 0.45, 0.7),   # outside triangle, inside left rectangle
            at("cell phone", 0.5, 0.5),  # on shared left/right edge
            at("backpack", 0.8, 0.3),
        ], 0)
        self.assertEqual([r["items"] for r in rows], [["cup"], ["cell phone"], ["backpack"]])
        self.assertEqual([r["state"] for r in rows], ["AWAY", "OCCUPIED", "AWAY"])

    def test_each_seat_maintains_its_own_timer(self):
        monitor = SeatMonitor([LEFT, RIGHT], confirm_frames=1, grace_seconds=0, abandoned_seconds=4)
        monitor.update([at("pencil")], 0)
        left, right = monitor.update([at("pencil"), at("cup", 0.75)], 4)
        self.assertEqual((left["state"], right["state"]), ("ABANDONED", "AWAY"))
        self.assertEqual((left["awaySeconds"], right["awaySeconds"]), (4, 0))

    def test_outage_requires_fresh_confirmation_and_new_timer(self):
        monitor = SeatMonitor([LEFT], confirm_frames=2, max_gap_seconds=5, abandoned_seconds=4)
        for now in [0, 1, 5]:
            [row] = monitor.update([at("laptop")], now)
        self.assertEqual(row["state"], "ABANDONED")
        self.assertEqual(monitor.update([at("laptop")], 90)[0]["state"], "EMPTY")
        [row] = monitor.update([at("laptop")], 91)
        self.assertEqual((row["state"], row["awaySeconds"]), ("AWAY", 0))

    def test_invalid_roi_and_duplicate_ids_are_rejected(self):
        for vertices in ([], [(0, 0), (0.5, 0.5), (1, 1)], [(0, 0), (1, 0), (1, 2)]):
            with self.assertRaises(ValueError):
                Seat("bad", "좌석", vertices)
        with self.assertRaises(ValueError):
            SeatMonitor([LEFT, LEFT])
