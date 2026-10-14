"""This desktop program must never be built using a headless OpenCV wheel."""
import cv2


def test_opencv_has_calibration_window_backend():
    assert cv2.currentUIFramework(), "OpenCV has no window backend: calibration cannot run"
