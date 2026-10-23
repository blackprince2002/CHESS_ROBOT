"""
Camera-only test (no Arduino needed).
Opens the USB webcam, measures FPS, and saves:
  snapshot_raw.jpg    - what the camera sees
  snapshot_warped.jpg - the 800x800 top-down board (after calibration)
"""

import glob
import time
import cv2
import config
from board_detector import BoardDetector


def find_camera():
    for path in sorted(glob.glob("/dev/video[0-9]")):
        idx = int(path.replace("/dev/video", ""))
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                return idx, cap
        cap.release()
    return None, None


def main():
    idx, cap = find_camera()
    if cap is None:
        print("NO CAMERA FOUND. Is the USB webcam plugged into the Pi?")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)

    # Let auto-exposure settle
    for _ in range(15):
        cap.read()

    start = time.time()
    frames = 0
    frame = None
    while time.time() - start < 3.0:
        ok, f = cap.read()
        if ok:
            frame = f
            frames += 1
    fps = frames / (time.time() - start)
    cap.release()

    h, w = frame.shape[:2]
    print(f"Camera index : /dev/video{idx}")
    print(f"Resolution   : {w}x{h}")
    print(f"Capture FPS  : {fps:.1f}")

    cv2.imwrite("snapshot_raw.jpg", frame)

    detector = BoardDetector()
    if detector.matrix is None:
        found = detector.auto_detect_corners(frame)
        print(f"Board auto-detect: {'FOUND' if found else 'NOT FOUND (using center crop)'}")
    else:
        print("Board auto-detect: using saved board_calibration.json")

    t0 = time.time()
    warped = detector.warp_board(frame)
    print(f"Warp time    : {(time.time() - t0) * 1000:.1f} ms")

    # Draw the 8x8 grid so we can check alignment by eye
    sq = config.WARPED_BOARD_SIZE // 8
    for i in range(9):
        cv2.line(warped, (i * sq, 0), (i * sq, config.WARPED_BOARD_SIZE), (0, 0, 255), 2)
        cv2.line(warped, (0, i * sq), (config.WARPED_BOARD_SIZE, i * sq), (0, 0, 255), 2)
    cv2.imwrite("snapshot_warped.jpg", warped)
    print("Saved snapshot_raw.jpg and snapshot_warped.jpg")


if __name__ == "__main__":
    main()
