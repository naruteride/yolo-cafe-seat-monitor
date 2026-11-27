import json
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from cafe_monitor.viewer import LocalViewer


class ViewerTests(unittest.TestCase):
    def test_frame_lifecycle_and_matching_ids(self):
        viewer = LocalViewer("replay")
        self.assertEqual(viewer.camera_status()["state"], "starting")
        self.assertEqual(viewer.frame()[0], 503)
        self.assertTrue(viewer.seat_status()["stale"])
        seats = [{"id": "A", "state": "EMPTY", "items": []}]
        with patch("cafe_monitor.viewer.time.monotonic", return_value=10):
            for i in range(4):
                viewer.update_frame(bytes([i + 1]), "2026-02-03T00:00:00Z", 3.21,
                                    [{"label": "cup", "confidence": .84}], seats)
            self.assertEqual(viewer.camera_status()["frameId"], 4)
            self.assertEqual(viewer.frame(1)[0], 409)
            self.assertEqual(viewer.frame(2), (200, 2, bytes([2])))
            self.assertEqual(viewer.frame(), (200, 4, bytes([4])))
            self.assertFalse(viewer.seat_status()["stale"])
            self.assertEqual(viewer.seat_status()["snapshot"]["mode"], "demo")
        with patch("cafe_monitor.viewer.time.monotonic", return_value=20):
            self.assertEqual(viewer.camera_status()["state"], "error")
            self.assertEqual(viewer.camera_status()["objects"], [])
            self.assertEqual(viewer.frame(4)[0], 503)
            self.assertTrue(viewer.seat_status()["stale"])
        viewer.update_frame(b"fresh", "later", 4, [])
        self.assertEqual(viewer.camera_status()["state"], "running")
        viewer.error("USB 연결 끊김")
        self.assertEqual(viewer.camera_status()["message"], "USB 연결 끊김")
        self.assertEqual(viewer.frame()[0], 503)
        viewer.stopped()
        self.assertEqual(viewer.camera_status()["state"], "stopped")

    def test_demo_seats_do_not_create_camera_frames(self):
        viewer = LocalViewer("demo")
        viewer.stopped("시연 중")
        viewer.update_seats("now", [{"id": "A"}])
        self.assertFalse(viewer.seat_status()["stale"])
        self.assertEqual(viewer.frame()[0], 503)
        self.assertEqual(viewer.camera_status()["frameId"], 0)

    def test_http_contract(self):
        with LocalViewer(port=0) as viewer:
            conn = HTTPConnection("127.0.0.1", viewer.port, timeout=2)
            self.addCleanup(conn.close)

            def read(path, headers=None):
                conn.request("GET", path, headers=headers or {})
                reply = conn.getresponse()
                return reply, reply.read()

            resp, data = read("/")
            self.assertEqual(resp.status, 200)
            self.assertIn(b"data-local-camera", data)
            self.assertEqual(read("/api/camera/frame.jpg")[0].status, 503)
            viewer.update_frame(b"my-jpeg", "now", 4, [{"label": "cup"}])
            self.assertEqual(json.loads(read("/api/camera/status")[1])["frameId"], 1)
            resp, data = read("/api/camera/frame.jpg?id=1")
            self.assertEqual((resp.status, data), (200, b"my-jpeg"))
            self.assertEqual(resp.getheader("Content-Type"), "image/jpeg")
            self.assertEqual(resp.getheader("X-Frame-Id"), "1")
            self.assertEqual(resp.getheader("Cache-Control"), "no-store")
            self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))
            self.assertEqual(read("/api/camera/frame.jpg?id=bad")[0].status, 400)
            self.assertEqual(read("/api/camera/frame.jpg?id=2")[0].status, 409)
            self.assertEqual(read("/api/camera/status", {"Host": "other.test"})[0].status, 403)
            self.assertEqual(read("/../monitor.json")[0].status, 404)


if __name__ == "__main__":
    unittest.main()
