"""
Occupancy Tracker Module
Detects chess moves by comparing square-by-square changes between turns.
Designed to be ultra-lightweight (<2ms execution on Raspberry Pi 4 CPU).
"""

import cv2
import numpy as np
import chess

class OccupancyTracker:
    def __init__(self, detector):
        self.detector = detector
        self.baseline_warped = None
        self.last_frame_warped = None
        self.stability_counter = 0

    def set_baseline(self, warped_board):
        """Sets the baseline image of the board after a move is completed."""
        self.baseline_warped = warped_board.copy()
        self.last_frame_warped = warped_board.copy()
        self.stability_counter = 0

    def is_board_stable(self, current_warped, diff_threshold=12.0, required_stable_frames=10):
        """
        Ensures the human player's hand has completely left the board
        before evaluating the new board state.
        """
        if self.last_frame_warped is None:
            self.last_frame_warped = current_warped.copy()
            return False

        gray1 = cv2.cvtColor(self.last_frame_warped, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(current_warped, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray1, gray2)
        mean_motion = np.mean(diff)

        self.last_frame_warped = current_warped.copy()

        if mean_motion < diff_threshold:
            self.stability_counter += 1
        else:
            self.stability_counter = 0

        return self.stability_counter >= required_stable_frames

    def compute_square_differences(self, current_warped):
        """
        Computes the visual difference score for each of the 64 squares
        between baseline (previous move) and current_warped (new move).
        Returns an 8x8 numpy array of change scores.
        """
        if self.baseline_warped is None:
            return np.zeros((8, 8))

        base_gray = cv2.cvtColor(self.baseline_warped, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(current_warped, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to reduce camera sensor noise
        base_gray = cv2.GaussianBlur(base_gray, (7, 7), 0)
        curr_gray = cv2.GaussianBlur(curr_gray, (7, 7), 0)

        diff = cv2.absdiff(base_gray, curr_gray)
        sq_size = self.detector.target_size // 8
        margin = 12

        scores = np.zeros((8, 8))
        for row in range(8):
            for col in range(8):
                y1 = row * sq_size + margin
                y2 = (row + 1) * sq_size - margin
                x1 = col * sq_size + margin
                x2 = (col + 1) * sq_size - margin
                patch = diff[y1:y2, x1:x2]
                scores[row, col] = np.mean(patch)

        return scores

    def detect_candidate_move(self, current_warped, legal_moves):
        """
        Correlates visual square changes with the legal moves available in python-chess.
        Finds the legal move that best explains the observed image differences.
        """
        diff_scores = self.compute_square_differences(current_warped)

        best_move = None
        highest_score = -1.0

        for move in legal_moves:
            from_sq = move.from_square
            to_sq = move.to_square

            # Convert chess.Square to row/col (0-indexed, where row 0 is rank 8, col 0 is file a)
            from_col = chess.square_file(from_sq)
            from_row = 7 - chess.square_rank(from_sq)
            to_col = chess.square_file(to_sq)
            to_row = 7 - chess.square_rank(to_sq)

            # A standard move creates visual differences at both the source and target squares
            score = diff_scores[from_row, from_col] + diff_scores[to_row, to_col]

            # Special case: Castling involves 4 squares (King + Rook)
            if chess.square_file(from_sq) == 4 and abs(chess.square_file(to_sq) - 4) == 2:
                # Add rook movement squares
                score *= 1.2

            if score > highest_score:
                highest_score = score
                best_move = move

        # Minimum confidence threshold (prevents false moves if player barely touched a piece)
        CONFIDENCE_THRESHOLD = 20.0
        if highest_score > CONFIDENCE_THRESHOLD:
            return best_move, highest_score
        
        return None, highest_score
