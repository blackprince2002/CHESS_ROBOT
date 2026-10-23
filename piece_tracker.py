"""
Piece Tracker Module (uses grid_mask for the 12x8 mat)
Detects moves by comparing per-square grayscale intensity between frames.
Ultra-lightweight: ~3ms per frame on RPi 4.
"""

import cv2
import numpy as np
import chess
from grid_mask import GridMask, CELL_PX, BOARD_COLS, ROWS

class PieceTracker:
    def __init__(self, grid):
        self.grid = grid
        self.baseline = None          # warped grayscale of the board after last confirmed move
        self.stability_count = 0
        self.last_gray = None

    def set_baseline(self, warped_frame):
        """Save the current warped frame as the reference (call after each confirmed move)."""
        self.baseline = cv2.cvtColor(warped_frame, cv2.COLOR_BGR2GRAY)
        self.baseline = cv2.GaussianBlur(self.baseline, (5, 5), 0)
        self.last_gray = self.baseline.copy()
        self.stability_count = 0

    def _square_region(self, col, row, margin=14):
        """Returns (y1, y2, x1, x2) for a square's inner region in warped space."""
        x1 = col * CELL_PX + margin
        y1 = row * CELL_PX + margin
        x2 = (col + 1) * CELL_PX - margin
        y2 = (row + 1) * CELL_PX - margin
        return y1, y2, x1, x2

    def is_stable(self, warped_frame, threshold=10.0, required=12):
        """
        Returns True once the board has been visually still for `required` consecutive frames.
        This ensures the player's hand has left the board.
        """
        gray = cv2.cvtColor(warped_frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self.last_gray is not None:
            # Only check the playable area (first 8 columns)
            play_curr = gray[:, :BOARD_COLS * CELL_PX]
            play_last = self.last_gray[:, :BOARD_COLS * CELL_PX]
            motion = np.mean(cv2.absdiff(play_curr, play_last))
            if motion < threshold:
                self.stability_count += 1
            else:
                self.stability_count = 0
        self.last_gray = gray
        return self.stability_count >= required

    def compute_diff_scores(self, warped_frame):
        """
        Returns an 8x8 array of per-square change scores (playable board only).
        Higher score = more visual change since baseline.
        """
        if self.baseline is None:
            return np.zeros((ROWS, BOARD_COLS))

        gray = cv2.cvtColor(warped_frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        diff = cv2.absdiff(self.baseline, gray)

        scores = np.zeros((ROWS, BOARD_COLS))
        for row in range(ROWS):
            for col in range(BOARD_COLS):
                y1, y2, x1, x2 = self._square_region(col, row)
                scores[row, col] = np.mean(diff[y1:y2, x1:x2])
        return scores

    def detect_move(self, warped_frame, legal_moves):
        """
        Matches the observed square changes against legal moves.
        Returns (best_move, confidence_score) or (None, score).
        """
        scores = self.compute_diff_scores(warped_frame)

        best_move = None
        best_score = -1.0

        for move in legal_moves:
            from_sq = move.from_square
            to_sq = move.to_square

            from_col = chess.square_rank(from_sq)
            from_row = chess.square_file(from_sq)
            to_col = chess.square_rank(to_sq)
            to_row = chess.square_file(to_sq)

            score = scores[from_row, from_col] + scores[to_row, to_col]

            # Castling bonus (4 squares change instead of 2)
            if move in legal_moves and (
                (from_sq == chess.E1 and to_sq in (chess.G1, chess.C1)) or
                (from_sq == chess.E8 and to_sq in (chess.G8, chess.C8))
            ):
                score *= 1.3

            if score > best_score:
                best_score = score
                best_move = move

        THRESHOLD = 18.0
        if best_score >= THRESHOLD:
            return best_move, best_score
        return None, best_score

    def diff_heatmap(self, warped_frame):
        """Returns a colour heatmap image of per-square changes (for the web dashboard)."""
        scores = self.compute_diff_scores(warped_frame)
        heatmap = np.zeros((ROWS * CELL_PX, BOARD_COLS * CELL_PX, 3), dtype=np.uint8)

        max_s = max(scores.max(), 1.0)
        for row in range(ROWS):
            for col in range(BOARD_COLS):
                intensity = int(255 * min(scores[row, col] / max_s, 1.0))
                colour = (0, intensity, 255 - intensity)  # blue -> green
                y1, y2 = row * CELL_PX, (row + 1) * CELL_PX
                x1, x2 = col * CELL_PX, (col + 1) * CELL_PX
                cv2.rectangle(heatmap, (x1, y1), (x2, y2), colour, -1)
                # Label (row 0..7 = file a..h, col 0..7 = rank 1..8)
                name = "abcdefgh"[row] + str(col + 1)
                cv2.putText(heatmap, f"{name} {scores[row,col]:.0f}",
                            (x1 + 8, y1 + CELL_PX // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        return heatmap
