"""
Board Detector & Perspective Transform Module
Finds the chessboard in the camera view and warps it to a clean 800x800 square image.
"""

import cv2
import numpy as np
import json
import os
import config

CALIBRATION_FILE = "board_calibration.json"

class BoardDetector:
    def __init__(self, target_size=config.WARPED_BOARD_SIZE):
        self.target_size = target_size
        self.corners = self.load_calibration()
        self.matrix = None
        if self.corners is not None:
            self.compute_perspective_matrix()

    def load_calibration(self):
        """Loads saved 4 corner points if available."""
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE, "r") as f:
                    data = json.load(f)
                    pts = np.array(data["corners"], dtype=np.float32)
                    print(f"[BoardDetector] Loaded saved corners from {CALIBRATION_FILE}")
                    return pts
            except Exception as e:
                print(f"[BoardDetector] Failed to load calibration: {e}")
        return None

    def save_calibration(self, corners):
        """Saves the 4 corners: [Top-Left (a8), Top-Right (h8), Bottom-Right (h1), Bottom-Left (a1)]."""
        self.corners = np.array(corners, dtype=np.float32)
        with open(CALIBRATION_FILE, "w") as f:
            json.dump({"corners": self.corners.tolist()}, f, indent=4)
        self.compute_perspective_matrix()
        print(f"[BoardDetector] Calibration saved to {CALIBRATION_FILE}")

    def compute_perspective_matrix(self):
        """Calculates the perspective warp matrix to a square grid."""
        dst = np.array([
            [0, 0],
            [self.target_size - 1, 0],
            [self.target_size - 1, self.target_size - 1],
            [0, self.target_size - 1]
        ], dtype=np.float32)
        self.matrix = cv2.getPerspectiveTransform(self.corners, dst)

    def auto_detect_corners(self, frame):
        """
        Attempts automatic chessboard or contour detection.
        Fallback to finding largest 4-sided polygon contour.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 1. Try finding chessboard corners (internal corners for 7x7)
        ret, corners = cv2.findChessboardCorners(gray, (7, 7), None)
        if ret:
            # Extrapolate outer 4 corners from internal grid
            c = corners.reshape(-1, 2)
            tl = c[0] - (c[8] - c[0])
            tr = c[6] + (c[6] - c[5])
            br = c[48] + (c[48] - c[40])
            bl = c[42] - (c[43] - c[42])
            pts = np.array([tl, tr, br, bl], dtype=np.float32)
            self.save_calibration(pts)
            return True

        # 2. Contour-based detection for the board boundary
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for cnt in contours:
            perimeter = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * perimeter, True)
            if len(approx) == 4 and cv2.contourArea(cnt) > (frame.shape[0] * frame.shape[1] * 0.15):
                pts = approx.reshape(4, 2).astype(np.float32)
                # Sort points: [Top-Left, Top-Right, Bottom-Right, Bottom-Left]
                rect = self._order_points(pts)
                self.save_calibration(rect)
                return True
                
        return False

    def _order_points(self, pts):
        """Orders coordinates: Top-Left, Top-Right, Bottom-Right, Bottom-Left."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]  # Top-Left has smallest sum
        rect[2] = pts[np.argmax(s)]  # Bottom-Right has largest sum

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # Top-Right has smallest diff
        rect[3] = pts[np.argmax(diff)]  # Bottom-Left has largest diff
        return rect

    def warp_board(self, frame):
        """Warps the camera frame into a rectified 800x800 top-down view."""
        if self.matrix is None:
            # If not calibrated, use center crop as fallback
            h, w = frame.shape[:2]
            side = min(h, w)
            y1 = (h - side) // 2
            x1 = (w - side) // 2
            cropped = frame[y1:y1+side, x1:x1+side]
            return cv2.resize(cropped, (self.target_size, self.target_size))
        
        return cv2.warpPerspective(frame, self.matrix, (self.target_size, self.target_size))

    def get_square_crop(self, warped_board, col, row, margin=8):
        """
        Extracts a single square's image patch (with optional inner margin to ignore border lines).
        col: 0 to 7 (a to h)
        row: 0 to 7 (8 to 1 from top to bottom)
        """
        sq_size = self.target_size // 8
        x1 = col * sq_size + margin
        y1 = row * sq_size + margin
        x2 = (col + 1) * sq_size - margin
        y2 = (row + 1) * sq_size - margin
        return warped_board[y1:y2, x1:x2]
