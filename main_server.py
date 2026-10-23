"""
Main Autonomous Chess Coordinator Server
Orchestrates: Camera Capture -> Board Warp -> Move Detection -> Stockfish AI -> Arm Trajectory Execution
Includes an embedded live web dashboard on port 5000 so you can watch in real time.
"""

import cv2
import chess
import numpy as np
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import config
from board_detector import BoardDetector
from occupancy_tracker import OccupancyTracker
from chess_engine import ChessGame
from arm_kinematics import ArmKinematics

# Global State for Web Dashboard
SHARED_STATE = {
    "status": "Starting system...",
    "fen": "",
    "turn": "White (Player)",
    "last_move": "None",
    "arm_action": "IDLE",
    "arm_waypoints": [],
    "board_calibrated": False,
    "current_frame_jpeg": None,
    "warped_board_jpeg": None,
}

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Autonomous Chess Robot Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
        h1 {{ margin: 0 0 10px 0; color: #38bdf8; font-size: 24px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 20px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
        .feed {{ width: 100%; border-radius: 8px; background: #000; min-height: 280px; object-fit: contain; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 13px; }}
        .badge-green {{ background: #059669; color: #ecfdf5; }}
        .badge-blue {{ background: #0284c7; color: #f0f9ff; }}
        .info-row {{ margin: 8px 0; font-size: 15px; }}
        .label {{ color: #94a3b8; font-weight: 500; }}
        pre {{ background: #090d16; padding: 10px; border-radius: 6px; overflow-x: auto; color: #a5f3fc; font-size: 13px; max-height: 200px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Autonomous Chess Robot</h1>
        <div><span id="turn-badge" class="badge badge-green">Connecting...</span></div>
    </div>
    <div class="grid">
        <div class="card">
            <h3>Camera Feed</h3>
            <img class="feed" src="/camera_stream" alt="Camera Feed">
        </div>
        <div class="card">
            <h3>Rectified 8x8 Board & Differences</h3>
            <img class="feed" src="/warped_stream" alt="Rectified Board">
        </div>
    </div>
    <div style="margin-top: 20px;" class="card">
        <h3>System Telemetry & Arm Decisions</h3>
        <div class="info-row"><span class="label">Status:</span> <span id="status-val">Waiting...</span></div>
        <div class="info-row"><span class="label">Last Move:</span> <span id="move-val">None</span></div>
        <div class="info-row"><span class="label">FEN:</span> <span id="fen-val" style="font-family: monospace;">-</span></div>
        <div class="info-row"><span class="label">Arm Action:</span> <span id="arm-val">IDLE</span></div>
        <h4 style="margin: 12px 0 6px 0; color: #38bdf8;">Current Arm Coordinates & Trajectory:</h4>
        <pre id="waypoints-val">Waiting for robot arm move...</pre>
    </div>
    <script>
        setInterval(() => {{
            fetch('/state')
                .then(r => r.json())
                .then(data => {{
                    document.getElementById('status-val').innerText = data.status;
                    document.getElementById('turn-badge').innerText = data.turn;
                    document.getElementById('move-val').innerText = data.last_move;
                    document.getElementById('fen-val').innerText = data.fen;
                    document.getElementById('arm-val').innerText = data.arm_action;
                    document.getElementById('waypoints-val').innerText = JSON.stringify(data.arm_waypoints, null, 2);
                }});
        }}, 500);
    </script>
</body>
</html>"""
            self.wfile.write(html.encode())

        elif self.path == "/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(SHARED_STATE).encode())

        elif self.path == "/camera_stream":
            self.stream_mjpeg("current_frame_jpeg")

        elif self.path == "/warped_stream":
            self.stream_mjpeg("warped_board_jpeg")

        else:
            self.send_response(404)
            self.end_headers()

    def stream_mjpeg(self, frame_key):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                jpeg = SHARED_STATE.get(frame_key)
                if jpeg is not None:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                time.sleep(0.08)
        except Exception:
            pass

def run_web_server():
    server = HTTPServer(("0.0.0.0", config.WEB_PORT), DashboardHandler)
    print(f"[WebServer] Live dashboard available at http://0.0.0.0:{config.WEB_PORT}")
    server.serve_forever()

def create_synthetic_chessboard():
    """Generates a synthetic starting chessboard image if no camera is connected yet."""
    img = np.zeros((config.WARPED_BOARD_SIZE, config.WARPED_BOARD_SIZE, 3), dtype=np.uint8)
    sq = config.WARPED_BOARD_SIZE // 8
    for r in range(8):
        for c in range(8):
            color = (235, 235, 208) if (r + c) % 2 == 0 else (119, 149, 86)
            cv2.rectangle(img, (c*sq, r*sq), ((c+1)*sq, (r+1)*sq), color, -1)
            # Add square coordinate text
            file_char = chr(ord('a') + c)
            rank_char = str(8 - r)
            cv2.putText(img, f"{file_char}{rank_char}", (c*sq + 10, (r+1)*sq - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 50, 50), 1)
    return img

def main_loop():
    print("[AutonomousChess] Starting autonomous coordinator loop...")
    detector = BoardDetector()
    tracker = OccupancyTracker(detector)
    game = ChessGame()
    arm = ArmKinematics()

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    use_synthetic = False
    if not cap.isOpened():
        print(f"[AutonomousChess] Camera index {config.CAMERA_INDEX} not available. Running in simulated camera mode.")
        use_synthetic = True

    synthetic_board = create_synthetic_chessboard()

    # Capture initial frame and establish baseline
    if not use_synthetic:
        ret, frame = cap.read()
        if ret:
            warped = detector.warp_board(frame)
            tracker.set_baseline(warped)
    else:
        tracker.set_baseline(synthetic_board)

    SHARED_STATE["status"] = "Game ready. Player's turn (White)."
    SHARED_STATE["fen"] = game.board.fen()

    while True:
        if not use_synthetic:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue
            warped = detector.warp_board(frame)
        else:
            frame = synthetic_board.copy()
            warped = synthetic_board.copy()

        # Update Web Dashboard JPEGs
        _, jpeg1 = cv2.imencode(".jpg", frame)
        _, jpeg2 = cv2.imencode(".jpg", warped)
        SHARED_STATE["current_frame_jpeg"] = jpeg1.tobytes()
        SHARED_STATE["warped_board_jpeg"] = jpeg2.tobytes()

        # Check turn
        if game.is_player_turn(chess.WHITE):
            SHARED_STATE["turn"] = "White (Player's turn)"
            if tracker.is_board_stable(warped):
                candidate_move, score = tracker.detect_candidate_move(warped, game.get_legal_moves())
                if candidate_move is not None:
                    print(f"\n[Vision] Detected player move: {candidate_move.uci()} (Confidence: {score:.1f})")
                    ok, san = game.apply_move(candidate_move)
                    if ok:
                        tracker.set_baseline(warped)
                        SHARED_STATE["last_move"] = f"Player: {san} ({candidate_move.uci()})"
                        SHARED_STATE["fen"] = game.board.fen()
                        SHARED_STATE["status"] = f"Player played {san}. Robot calculating response..."
        else:
            # Robot Arm's Turn (Black)
            SHARED_STATE["turn"] = "Black (Robot Arm's turn)"
            SHARED_STATE["status"] = "Robot thinking..."
            time.sleep(0.5)

            engine_move = game.get_best_engine_move()
            if engine_move is not None:
                move_uci = engine_move.uci()
                print(f"\n[Robot] Stockfish selected move: {move_uci}")
                SHARED_STATE["status"] = f"Robot moving piece: {move_uci}"
                SHARED_STATE["arm_action"] = f"MOVING {move_uci}"

                # 1. Generate 3D trajectories
                waypoints = arm.generate_move_trajectory(game.board, engine_move)
                SHARED_STATE["arm_waypoints"] = waypoints

                # 2. Execute on physical arm (or simulation)
                arm.execute_waypoints(waypoints)

                # 3. Apply move to chess logic
                ok, san = game.apply_move(engine_move)
                SHARED_STATE["last_move"] = f"Robot: {san} ({move_uci})"
                SHARED_STATE["fen"] = game.board.fen()
                SHARED_STATE["arm_action"] = "IDLE (Move Complete)"
                SHARED_STATE["status"] = f"Robot played {san}. Waiting for Player move..."

                # Reset baseline after arm finishes moving
                time.sleep(0.5)
                if not use_synthetic:
                    ret, f = cap.read()
                    if ret:
                        tracker.set_baseline(detector.warp_board(f))
                else:
                    tracker.set_baseline(synthetic_board)

        time.sleep(0.05)

if __name__ == "__main__":
    # Start web dashboard in background daemon thread
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()

    # Start main vision and arm controller
    main_loop()
