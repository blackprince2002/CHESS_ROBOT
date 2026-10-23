"""
Chess Engine & Game Logic Module
Manages board state, move legality, FEN string, and Stockfish AI calculation.
"""

import chess
import chess.engine
import os
import config

class ChessGame:
    def __init__(self, stockfish_path=config.STOCKFISH_PATH):
        self.board = chess.Board()
        self.stockfish_path = stockfish_path
        self.engine = None
        self.init_engine()

    def init_engine(self):
        """Initializes the Stockfish engine process."""
        if os.path.exists(self.stockfish_path):
            try:
                self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
                self.engine.configure({"Skill Level": config.ENGINE_SKILL_LEVEL})
                print(f"[ChessEngine] Stockfish engine loaded successfully from {self.stockfish_path}")
            except Exception as e:
                print(f"[ChessEngine] Failed to initialize Stockfish: {e}")
                self.engine = None
        else:
            print(f"[ChessEngine] Stockfish binary not found at {self.stockfish_path}. Using random legal fallback.")

    def get_legal_moves(self):
        """Returns the list of currently legal moves."""
        return list(self.board.legal_moves)

    def is_player_turn(self, player_color=chess.WHITE):
        """Returns True if it is the human player's turn to move."""
        return self.board.turn == player_color

    def apply_move(self, move):
        """Applies a legal move to the chess board."""
        if move in self.board.legal_moves:
            san = self.board.san(move)
            self.board.push(move)
            print(f"[ChessGame] Move played: {move.uci()} ({san})")
            return True, san
        return False, None

    def get_best_engine_move(self, time_limit=config.ENGINE_THINK_TIME):
        """Queries Stockfish for the robot's best counter-move."""
        if self.board.is_game_over():
            return None

        if self.engine is not None:
            try:
                result = self.engine.play(self.board, chess.engine.Limit(time=time_limit))
                return result.move
            except Exception as e:
                print(f"[ChessEngine] Engine query error: {e}")

        # Fallback if engine is unavailable: pick first legal move
        legal = list(self.board.legal_moves)
        return legal[0] if legal else None

    def is_game_over(self):
        return self.board.is_game_over()

    def get_status_text(self):
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            return f"Checkmate! {winner} wins."
        if self.board.is_stalemate():
            return "Draw by stalemate."
        if self.board.is_check():
            turn = "White" if self.board.turn == chess.WHITE else "Black"
            return f"Check! {turn}'s turn."
        turn = "White" if self.board.turn == chess.WHITE else "Black"
        return f"{turn} to move."

    def close(self):
        if self.engine is not None:
            self.engine.quit()
