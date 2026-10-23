"""
Grid mask for the 12x8 mat (61 x 40 cm):
  columns 0-7  (a-h)  -> playable 8x8 chessboard
  columns 8-11        -> 4x8 = 32 empty boxes for captured pieces

The camera is fixed, so the 4 outer corners of the whole grid (in camera pixels)
are set once below. Everything else (cell positions, masks, warp) is derived.

Run:  python3 grid_mask.py            -> captures a frame, saves overlay + masks
      python3 grid_mask.py image.jpg  -> uses an existing image instead
"""

import json
import os
import sys
import cv2
import numpy as np

COLS, ROWS = 12, 8
BOARD_COLS = 8                 # a-h
CELL_PX = 100                  # size of one cell in the warped image
WARP_W, WARP_H = COLS * CELL_PX, ROWS * CELL_PX   # 1200 x 800

# Outer corners of the full 12x8 grid in the 640x480 camera image:
# Top-Left, Top-Right, Bottom-Right, Bottom-Left
DEFAULT_CORNERS = [(25, 44), (632, 42), (632, 447), (25, 447)]
CORNERS_FILE = "grid_corners.json"


def load_corners():
    if os.path.exists(CORNERS_FILE):
        with open(CORNERS_FILE) as f:
            return np.array(json.load(f)["corners"], dtype=np.float32)
    return np.array(DEFAULT_CORNERS, dtype=np.float32)


def save_corners(corners):
    with open(CORNERS_FILE, "w") as f:
        json.dump({"corners": [list(map(float, c)) for c in corners]}, f, indent=2)


class GridMask:
    def __init__(self, corners=None):
        self.corners = load_corners() if corners is None else np.array(corners, dtype=np.float32)
        dst = np.array([[0, 0], [WARP_W - 1, 0], [WARP_W - 1, WARP_H - 1], [0, WARP_H - 1]], dtype=np.float32)
        self.M = cv2.getPerspectiveTransform(self.corners, dst)
        self.Minv = cv2.getPerspectiveTransform(dst, self.corners)

    # ---------- coordinates ----------
    def warp(self, frame):
        """Top-down 1200x800 view of the whole mat."""
        return cv2.warpPerspective(frame, self.M, (WARP_W, WARP_H))

    def cell_to_image_poly(self, col, row):
        """4 camera-pixel corners of a cell. col 0..11, row 0..7 (row 0 = rank 8)."""
        pts = np.array([[[col * CELL_PX, row * CELL_PX],
                         [(col + 1) * CELL_PX, row * CELL_PX],
                         [(col + 1) * CELL_PX, (row + 1) * CELL_PX],
                         [col * CELL_PX, (row + 1) * CELL_PX]]], dtype=np.float32)
        return cv2.perspectiveTransform(pts, self.Minv)[0]

    @staticmethod
    def square_name(col, row):
        # Physical board orientation: columns 0..7 are ranks 1..8 (White on left, Black on right)
        # rows 0..7 are files a..h (top to bottom)
        return "abcdefgh"[row] + str(col + 1)

    @staticmethod
    def capture_slot_index(col, row):
        """Capture boxes numbered 0..31 (col 8..11, row 0..7)."""
        return (col - BOARD_COLS) * ROWS + row

    # ---------- masks (in warped space) ----------
    def masks(self):
        playable = np.zeros((WARP_H, WARP_W), np.uint8)
        playable[:, :BOARD_COLS * CELL_PX] = 255
        capture = np.zeros((WARP_H, WARP_W), np.uint8)
        capture[:, BOARD_COLS * CELL_PX:] = 255
        return playable, capture

    def camera_masks(self, shape):
        """Same masks projected back into the camera image."""
        playable, capture = self.masks()
        size = (shape[1], shape[0])
        flags = cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP
        return (cv2.warpPerspective(playable, self.M, size, flags=flags),
                cv2.warpPerspective(capture, self.M, size, flags=flags))

    # ---------- drawing ----------
    def draw_overlay(self, frame):
        out = frame.copy()
        layer = out.copy()
        for row in range(ROWS):
            for col in range(COLS):
                poly = self.cell_to_image_poly(col, row).astype(np.int32)
                colour = (0, 200, 0) if col < BOARD_COLS else (0, 140, 255)
                cv2.fillPoly(layer, [poly], colour)
        out = cv2.addWeighted(layer, 0.25, out, 0.75, 0)

        for row in range(ROWS):
            for col in range(COLS):
                poly = self.cell_to_image_poly(col, row).astype(np.int32)
                colour = (0, 255, 0) if col < BOARD_COLS else (0, 165, 255)
                cv2.polylines(out, [poly], True, colour, 1)
                c = poly.mean(axis=0).astype(int)
                label = self.square_name(col, row) if col < BOARD_COLS else str(self.capture_slot_index(col, row))
                cv2.putText(out, label, (c[0] - 9, c[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.32,
                            (0, 0, 255) if col < BOARD_COLS else (255, 0, 0), 1)
        for p in self.corners:
            cv2.circle(out, tuple(int(v) for v in p), 5, (255, 0, 255), -1)
        return out


def main():
    if len(sys.argv) > 1:
        frame = cv2.imread(sys.argv[1])
    else:
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        for _ in range(15):
            cap.read()
        ok, frame = cap.read()
        cap.release()
        if not ok:
            print("Could not read from camera (is cam_stream.py still running?)")
            return
        cv2.imwrite("frame.jpg", frame)

    g = GridMask()
    cv2.imwrite("overlay.jpg", g.draw_overlay(frame))
    cv2.imwrite("warped_mat.jpg", g.warp(frame))
    cam_play, cam_cap = g.camera_masks(frame.shape)
    cv2.imwrite("mask_playable.png", cam_play)
    cv2.imwrite("mask_capture.png", cam_cap)
    save_corners(g.corners)
    print("Saved overlay.jpg, warped_mat.jpg, mask_playable.png, mask_capture.png, grid_corners.json")


if __name__ == "__main__":
    main()
