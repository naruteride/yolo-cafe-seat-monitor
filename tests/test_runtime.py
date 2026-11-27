from contextlib import nullcontext
import json
from threading import Event
import unittest
from unittest.mock import MagicMock, patch

from cafe_monitor.detector import Detection, YoloDetector
from cafe_monitor.publish import Publisher
from cafe_monitor.state import Seat


class RuntimeTests(unittest.TestCase):
    def test_crop_detections_use_camera_coordinates_and_exclude_margin(self):
        seat = Seat("right", "오른쪽", [(0.5, 0), (1, 0), (1, 1), (0.5, 1)])
        frame = MagicMock(shape=(100, 200, 3))
        model = object.__new__(YoloDetector)
        model.detect = lambda crop: [
            Detection("cup", 0.9, (0.4, 0.2, 0.6, 0.4)),
            Detection("pencil", 0.8, (0, 0.2, 0.05, 0.4)),
        ]
        results = model.detect_seats(frame, [seat])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].label, "cup")
        self.assertAlmostEqual(results[0].xyxy[0], (85 + 115 * 0.4) / 200)
        self.assertEqual(results[0].xyxy[1], 0.2)

    def test_offline_capture_keeps_only_newest_unsent_observation(self):
        started, release = Event(), Event()
        snapshots = []

        def slow_send(request, timeout):
            snapshots.append(json.loads(request.data))
            if not started.is_set():
                started.set()
                release.wait(2)
                raise OSError("offline")
            return nullcontext()

        out = Publisher("https://example.org/api/status", "test-token", interval=0)
        with patch.object(out._opener, "open", side_effect=slow_send), self.assertLogs(level="WARNING"):
            with out:
                out.offer({"n": 1})
                self.assertTrue(started.wait(2))
                out.offer({"n": 2})
                out.offer({"n": 3})
                release.set()
        self.assertEqual(snapshots, [{"n": 1}, {"n": 3}])


if __name__ == "__main__":
    unittest.main()
