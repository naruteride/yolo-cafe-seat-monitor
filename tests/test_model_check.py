import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from cafe_monitor.__main__ import main
from cafe_monitor.detector import DEFAULT_MODEL


class ModelCheckTests(unittest.TestCase):
    def run_check(self, model):
        with (
            patch.object(sys, "argv", ["cafe_monitor", "--check-model", "--model", str(model)]),
            patch("cafe_monitor.__main__.Camera") as camera,
            patch("cafe_monitor.__main__.Indicators") as gpio,
            patch("cafe_monitor.viewer.LocalViewer") as viewer,
        ):
            result = main()
        camera.assert_not_called()
        gpio.assert_not_called()
        viewer.assert_not_called()
        return result

    def test_model_check_runs_one_prediction_and_reports_its_failure(self):
        numpy = MagicMock()
        with patch.dict(sys.modules, numpy=numpy), patch("cafe_monitor.__main__.YoloDetector") as load:
            detector = load.return_value
            detector.labels = {0: "person", 1: "cup"}
            detector.missing_labels = []
            self.assertEqual(self.run_check(DEFAULT_MODEL), 0)
            detector.detect.assert_called_once_with(numpy.zeros.return_value)

            detector.detect.side_effect = RuntimeError("backend inference error")
            with self.assertLogs(level="ERROR") as log:
                self.assertNotEqual(self.run_check(DEFAULT_MODEL), 0)
            self.assertIn("backend inference error", " ".join(log.output))

    def test_missing_model_identifies_file_and_does_not_load_detector(self):
        with TemporaryDirectory() as temp, patch("cafe_monitor.__main__.YoloDetector") as load:
            missing = Path(temp) / "missing.pt"
            with self.assertLogs(level="ERROR") as log:
                self.assertNotEqual(self.run_check(missing), 0)
            self.assertIn(str(missing), " ".join(log.output))
            load.assert_not_called()

    def test_missing_ultralytics_identifies_interpreter_and_install_command(self):
        error = ModuleNotFoundError("No module named 'ultralytics'", name="ultralytics")
        with patch("cafe_monitor.__main__.YoloDetector", side_effect=error), self.assertLogs(level="ERROR") as log:
            self.assertNotEqual(self.run_check(DEFAULT_MODEL), 0)
        output = " ".join(log.output)
        self.assertIn(sys.executable, output)
        self.assertIn("ultralytics", output)
        self.assertIn(".venv/bin/python -m pip install -r requirements-pi.txt", output)


if __name__ == "__main__":
    unittest.main()
