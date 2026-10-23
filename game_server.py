"""
Chess Game Server v2 - Button-Confirm Mode
============================================
Human presses "I moved" on the dashboard after making their move on the board.
This eliminates false detections from camera noise/wobble.

Run on Raspberry Pi:
    python3 game_server.py

Open browser:
    http://<PI_IP>:8080
"""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np
import chess

from grid_mask import GridMask, save_corners, load_corners, CELL_PX, BOARD_COLS, ROWS
from piece_tracker import PieceTracker
from chess_engine import ChessGame
from arm_kinematics import ArmKinematics

PORT = 8080

# Force unbuffered stdout
sys.stdout.reconfigure(line_buffering=True)

# ───── Shared state ─────
state = {
    "jpeg_mask": None,
    "jpeg_raw": None,
    "warp": None,
    "heatmap": None,
    "fps": 0.0,
    "camera": "searching...",
    "phase": "INIT",
    "status_text": "Initializing...",
    "move_log": [],
    "engine_move": None,
    "arm_waypoints": [],
    "detected_uci": "",
    "top_candidates": [],   # top-3 move candidates from diff analysis
}

# Signal: human pressed "I moved" button
human_moved_event = threading.Event()
# Signal: human pressed "Confirm move X" button
confirmed_move_uci = [None]

corners = load_corners().copy()
lock = threading.Lock()

grid = GridMask(corners)
tracker = PieceTracker(grid)
engine = None
arm = None
latest_warped = [None]

# ───── Camera ─────
def open_camera():
    for idx in [0, 1, 2, 3, 4]:
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                state["camera"] = f"/dev/video{idx}"
                return cap
        cap.release()
    return None


def capture_loop():
    cap = None
    n, t0 = 0, time.time()
    while True:
        if cap is None:
            cap = open_camera()
            if cap is None:
                state["camera"] = "NO CAMERA - check USB"
                time.sleep(2)
                continue
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release(); cap = None
            continue

        with lock:
            g = GridMask(corners)

        warped = g.warp(frame)
        latest_warped[0] = warped

        overlay = g.draw_overlay(frame)
        phase = state["phase"]
        status = state["status_text"]
        cv2.putText(overlay, f"{phase}: {status}", (8, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)

        state["jpeg_mask"] = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        state["jpeg_raw"]  = cv2.imencode(".jpg", frame,   [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        state["warp"]      = cv2.imencode(".jpg", cv2.resize(warped, (600, 400)),
                                          [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()

        if tracker.baseline is not None:
            hm = tracker.diff_heatmap(warped)
            state["heatmap"] = cv2.imencode(".jpg", hm, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()

        n += 1
        if time.time() - t0 >= 2:
            state["fps"] = n / (time.time() - t0)
            n, t0 = 0, time.time()


# ───── Game Loop ─────
def game_loop():
    global engine, arm

    while latest_warped[0] is None:
        time.sleep(0.3)

    state["status_text"] = "Loading Stockfish engine..."
    state["phase"] = "INIT"
    print("[Game] Initializing engine and arm...")
    engine = ChessGame()
    arm = ArmKinematics()

    # Baseline
    state["phase"] = "BASELINE"
    state["status_text"] = "Press '📸 Capture Baseline' when pieces are in starting position."
    print("[Game] Waiting for baseline capture button...")

    # Wait for the human to press the baseline button
    while state["phase"] == "BASELINE":
        time.sleep(0.5)

    # Main game loop
    while not engine.is_game_over():
        if engine.is_player_turn(chess.WHITE):
            # === HUMAN TURN ===
            state["phase"] = "WAITING_HUMAN"
            state["status_text"] = engine.get_status_text() + " Move a piece, then press '✅ I Moved'."
            state["top_candidates"] = []
            human_moved_event.clear()
            confirmed_move_uci[0] = None
            print("[Game] Waiting for human move button...")

            # Block until "I moved" is pressed
            human_moved_event.wait()

            # Analyse the board change
            state["phase"] = "DETECTING"
            state["status_text"] = "Analyzing board changes..."
            time.sleep(1.5)  # let the board fully stabilize

            warp = latest_warped[0]
            legal_moves = engine.get_legal_moves()
            scores = tracker.compute_diff_scores(warp)

            # Score each legal move and find top candidates
            candidates = []
            for move in legal_moves:
                from_sq = move.from_square
                to_sq = move.to_square
                from_col = chess.square_rank(from_sq)
                from_row = chess.square_file(from_sq)
                to_col = chess.square_rank(to_sq)
                to_row = chess.square_file(to_sq)
                score = scores[from_row, from_col] + scores[to_row, to_col]
                candidates.append((score, move))

            candidates.sort(key=lambda x: -x[0])
            top3 = candidates[:5]

            state["top_candidates"] = [
                {"uci": m.uci(), "san": engine.board.san(m), "score": round(s, 1)}
                for s, m in top3
            ]

            best_score, best_move = top3[0]
            uci = best_move.uci()
            san = engine.board.san(best_move)
            state["detected_uci"] = uci
            state["status_text"] = f"Best guess: {san} ({uci}) score={best_score:.1f}. Confirm or pick another."
            print(f"[Game] Top candidates: {[(m.uci(), round(s,1)) for s,m in top3]}")

            # Wait for user to confirm a move (they can pick from top candidates or type UCI)
            state["phase"] = "CONFIRM"
            confirmed_move_uci[0] = None

            while confirmed_move_uci[0] is None:
                time.sleep(0.2)

            # Apply the confirmed move
            chosen_uci = confirmed_move_uci[0]
            try:
                chosen_move = chess.Move.from_uci(chosen_uci)
                if chosen_move in engine.board.legal_moves:
                    san_applied = engine.board.san(chosen_move)
                    engine.board.push(chosen_move)
                    state["move_log"].append({
                        "turn": len(state["move_log"]) + 1,
                        "uci": chosen_uci, "san": san_applied, "side": "White"
                    })
                    print(f"[Game] Human confirmed: {san_applied} ({chosen_uci})")
                    # Update baseline
                    warp = latest_warped[0]
                    if warp is not None:
                        tracker.set_baseline(warp)
                else:
                    state["status_text"] = f"Move {chosen_uci} is illegal! Retrying..."
                    print(f"[Game] Illegal move: {chosen_uci}")
                    continue
            except Exception as e:
                state["status_text"] = f"Invalid UCI: {chosen_uci} ({e})"
                print(f"[Game] Invalid UCI: {chosen_uci}: {e}")
                continue

        else:
            # === ENGINE TURN (Black) ===
            state["phase"] = "ENGINE_THINKING"
            state["status_text"] = "Stockfish is thinking..."
            print("[Game] Engine thinking...")

            best_move = engine.get_best_engine_move()
            if best_move is None:
                break

            uci = best_move.uci()
            san = engine.board.san(best_move)
            state["engine_move"] = uci
            state["status_text"] = f"Engine plays: {san} ({uci})"
            print(f"[Game] Engine move: {san} ({uci})")

            waypoints = arm.generate_move_trajectory(engine.board, best_move)
            state["arm_waypoints"] = waypoints

            ok, san_applied = engine.apply_move(best_move)
            if ok:
                state["move_log"].append({
                    "turn": len(state["move_log"]) + 1,
                    "uci": uci, "san": san_applied, "side": "Black"
                })

            state["phase"] = "ARM_MOVING"
            state["status_text"] = f"Arm executing {san}... (move the piece manually if no arm connected)"
            arm.execute_waypoints(waypoints)

            # Wait and re-baseline
            time.sleep(2)
            state["status_text"] = f"Engine played {san}. Press '📸 Re-Baseline' then your turn!"

            # Wait for re-baseline after engine move
            state["phase"] = "WAIT_REBASELINE"
            while state["phase"] == "WAIT_REBASELINE":
                time.sleep(0.3)

    # Game over
    state["phase"] = "GAME_OVER"
    state["status_text"] = engine.get_status_text()
    print(f"[Game] GAME OVER: {state['status_text']}")


# ───── Web Dashboard ─────
PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Chess Robot - Live Game</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0e1a;color:#e2e8f0;font-family:Inter,Segoe UI,sans-serif;padding:16px}
h1{color:#38bdf8;font-size:1.8rem;margin-bottom:2px}
.subtitle{color:#64748b;font-size:0.85rem;margin-bottom:14px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.card{background:linear-gradient(135deg,#151b2e 0%,#1e293b 100%);border:1px solid #1e3a5f;
      border-radius:14px;padding:14px;box-shadow:0 4px 20px rgba(0,0,0,0.4)}
.card h2{font-size:1rem;color:#38bdf8;margin-bottom:8px}
img{border-radius:10px;display:block;width:100%}
.status-bar{background:linear-gradient(90deg,#0f172a,#1e293b);border:1px solid #334155;
            border-radius:12px;padding:12px 18px;margin:10px 0;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.phase{font-weight:700;padding:4px 12px;border-radius:8px;font-size:0.8rem;min-width:120px;text-align:center}
.phase-WAITING_HUMAN{background:#22c55e;color:#000}
.phase-DETECTING{background:#eab308;color:#000}
.phase-CONFIRM{background:#f97316;color:#000}
.phase-ENGINE_THINKING{background:#8b5cf6;color:#fff}
.phase-ARM_MOVING{background:#ef4444;color:#fff}
.phase-GAME_OVER{background:#dc2626;color:#fff}
.phase-BASELINE,.phase-INIT,.phase-WAIT_REBASELINE{background:#0ea5e9;color:#000}
.status-text{flex:1;font-size:0.95rem}
.log-table{width:100%;border-collapse:collapse;font-size:0.82rem}
.log-table th{background:#0f172a;color:#94a3b8;padding:6px;text-align:left;border-bottom:1px solid #334155}
.log-table td{padding:5px 6px;border-bottom:1px solid #1e293b}
.log-table tr:hover{background:#172033}
.white-move{color:#f8fafc}.black-move{color:#fb923c}
.btn{background:#334155;color:#fff;border:0;border-radius:8px;padding:10px 16px;cursor:pointer;
     font-size:0.9rem;transition:all 0.2s;margin:4px}
.btn:hover{background:#475569;transform:translateY(-1px)}
.btn-primary{background:linear-gradient(135deg,#22c55e,#16a34a);font-weight:700;font-size:1rem;padding:14px 28px}
.btn-primary:hover{filter:brightness(1.15)}
.btn-confirm{background:linear-gradient(135deg,#f97316,#ea580c);font-weight:600}
.btn-confirm:hover{filter:brightness(1.15)}
.btn-baseline{background:linear-gradient(135deg,#0ea5e9,#0284c7);font-weight:600}
.btn-baseline:hover{filter:brightness(1.15)}
.btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626)}
.candidates{margin-top:8px}
.candidate-btn{background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:8px 14px;
               border-radius:8px;cursor:pointer;margin:3px;font-size:0.85rem;transition:all 0.2s}
.candidate-btn:hover{background:#334155;border-color:#0ea5e9}
.fen{font-family:monospace;font-size:0.72rem;color:#64748b;word-break:break-all;margin-top:6px}
.actions{padding:12px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.pad{display:grid;grid-template-columns:repeat(3,38px);gap:4px;margin:6px 0}
.corner{display:inline-block;margin:6px 14px 6px 0;vertical-align:top}
select,input[type=text]{background:#334155;color:#fff;border:1px solid #475569;padding:6px 10px;border-radius:6px}
input[type=text]{width:80px}
</style></head><body>
<h1>♟ Chess Robot</h1>
<p class="subtitle">Vision · Stockfish · Robotic Arm · Live Dashboard</p>

<div class="status-bar">
  <span class="phase" id="phase">INIT</span>
  <span class="status-text" id="status">Initializing...</span>
  <span style="color:#64748b;font-size:0.8rem" id="fps"></span>
</div>

<div class="actions" id="action-bar">
  <!-- Buttons rendered dynamically based on phase -->
</div>

<div class="grid">
  <div class="card"><h2>📷 Camera + Grid Overlay</h2><img id="cam" src="/mask.mjpg"></div>
  <div class="card"><h2>🔍 Top-Down Warped View</h2><img src="/warp.mjpg"></div>
  <div class="card"><h2>🌡 Change Heatmap</h2><img src="/heatmap.mjpg"></div>
  <div class="card">
    <h2>📋 Move Log</h2>
    <table class="log-table"><thead><tr><th>#</th><th>Side</th><th>Move</th><th>UCI</th></tr></thead>
    <tbody id="log"></tbody></table>
    <div class="fen" id="fen"></div>
    <div id="candidates" class="candidates"></div>
  </div>
</div>

<div class="card" style="margin-top:14px">
  <h2>⚙ Adjust Grid Corners</h2>
  <span>Step <select id="step"><option>1</option><option selected>2</option><option>5</option></select> px</span>
  <div id="pads"></div>
  <div style="margin-top:8px">
    <button class="btn" onclick="rawToggle()">Toggle raw / mask</button>
  </div>
</div>

<script>
const names=["Top-Left","Top-Right","Bottom-Right","Bottom-Left"];
const pads=document.getElementById('pads');
names.forEach((n,i)=>{
  pads.insertAdjacentHTML('beforeend',`<div class="corner"><b>${n}</b><div class="pad">
  <span></span><button class="btn" onclick="mv(${i},0,-1)">&#9650;</button><span></span>
  <button class="btn" onclick="mv(${i},-1,0)">&#9664;</button><span></span><button class="btn" onclick="mv(${i},1,0)">&#9654;</button>
  <span></span><button class="btn" onclick="mv(${i},0,1)">&#9660;</button><span></span></div></div>`);
});
function mv(i,dx,dy){const s=+document.getElementById('step').value;fetch(`/move?i=${i}&dx=${dx*s}&dy=${dy*s}`);}
let raw=false;function rawToggle(){raw=!raw;document.getElementById('cam').src=raw?'/raw.mjpg':'/mask.mjpg';}

// === API calls ===
function captureBaseline(){fetch('/api/capture_baseline');}
function humanMoved(){fetch('/api/human_moved');}
function confirmMove(uci){fetch('/api/confirm_move?uci='+uci);}
function confirmManual(){
  const v=document.getElementById('manual_uci').value.trim();
  if(v.length>=4) confirmMove(v);
}
function newGame(){fetch('/api/new_game').then(()=>location.reload());}

// === Polling ===
let lastPhase='';
setInterval(()=>fetch('/api/state').then(r=>r.json()).then(d=>{
  const pe=document.getElementById('phase');
  pe.textContent=d.phase;
  pe.className='phase phase-'+d.phase;
  document.getElementById('status').textContent=d.status;
  document.getElementById('fps').textContent=d.fps.toFixed(1)+' FPS | '+d.camera;
  document.getElementById('fen').textContent='FEN: '+d.fen;

  // Move log
  const tb=document.getElementById('log');
  let html='';
  d.moves.forEach(m=>{
    const cls=m.side==='White'?'white-move':'black-move';
    html+=`<tr class="${cls}"><td>${m.turn}</td><td>${m.side}</td><td><b>${m.san}</b></td><td>${m.uci}</td></tr>`;
  });
  tb.innerHTML=html;

  // Action buttons based on phase
  const bar=document.getElementById('action-bar');
  if(d.phase !== lastPhase){
    lastPhase=d.phase;
    if(d.phase==='BASELINE' || d.phase==='WAIT_REBASELINE'){
      bar.innerHTML='<button class="btn btn-baseline" onclick="captureBaseline()">📸 Capture Baseline</button>';
    } else if(d.phase==='WAITING_HUMAN'){
      bar.innerHTML='<button class="btn btn-primary" onclick="humanMoved()">✅ I Moved!</button>';
    } else if(d.phase==='CONFIRM'){
      bar.innerHTML='';  // candidates rendered below
    } else {
      bar.innerHTML='';
    }
    bar.innerHTML+=' <button class="btn btn-danger" onclick="newGame()">🔄 New Game</button>';
  }

  // Candidates (during CONFIRM phase)
  const cdiv=document.getElementById('candidates');
  if(d.phase==='CONFIRM' && d.candidates && d.candidates.length>0){
    let ch='<b>Pick the correct move:</b><br>';
    d.candidates.forEach(c=>{
      ch+=`<button class="candidate-btn" onclick="confirmMove('${c.uci}')">${c.san} (${c.uci}) [${c.score}]</button> `;
    });
    ch+=`<br><input type="text" id="manual_uci" placeholder="e2e4" style="margin-top:6px">
         <button class="btn btn-confirm" onclick="confirmManual()">Confirm UCI</button>`;
    cdiv.innerHTML=ch;
  } else {
    cdiv.innerHTML='';
  }
}),700);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)

        if u.path in ("/", "/index.html"):
            self._send(200, "text/html", PAGE.encode())

        elif u.path == "/api/state":
            fen = engine.board.fen() if engine else "starting..."
            body = json.dumps({
                "phase": state["phase"],
                "status": state["status_text"],
                "fps": state["fps"],
                "camera": state["camera"],
                "fen": fen,
                "moves": state["move_log"],
                "detected": state["detected_uci"],
                "engine_move": state["engine_move"],
                "candidates": state["top_candidates"],
            })
            self._send(200, "application/json", body.encode())

        elif u.path == "/api/capture_baseline":
            warp = latest_warped[0]
            if warp is not None:
                tracker.set_baseline(warp)
                print("[API] Baseline captured!")
                state["status_text"] = "Baseline captured! White to move."
                if state["phase"] in ("BASELINE", "WAIT_REBASELINE"):
                    state["phase"] = "WAITING_HUMAN"
            self._send(200, "text/plain", b"ok")

        elif u.path == "/api/human_moved":
            print("[API] Human says: I moved!")
            human_moved_event.set()
            self._send(200, "text/plain", b"ok")

        elif u.path == "/api/confirm_move":
            q = parse_qs(u.query)
            uci = q.get("uci", [None])[0]
            if uci:
                confirmed_move_uci[0] = uci
                print(f"[API] Move confirmed: {uci}")
            self._send(200, "text/plain", b"ok")

        elif u.path == "/api/new_game":
            if engine:
                engine.board.reset()
                state["move_log"].clear()
                state["engine_move"] = None
                state["detected_uci"] = ""
                state["top_candidates"] = []
                state["phase"] = "BASELINE"
                state["status_text"] = "New game! Press 📸 Capture Baseline."
                human_moved_event.clear()
                confirmed_move_uci[0] = None
            self._send(200, "text/plain", b"ok")

        elif u.path == "/move":
            q = parse_qs(u.query)
            i, dx, dy = int(q["i"][0]), float(q["dx"][0]), float(q["dy"][0])
            with lock:
                corners[i] = corners[i] + np.array([dx, dy], dtype=np.float32)
                save_corners(corners)
            self._send(200, "text/plain", b"ok")

        elif u.path in ("/mask.mjpg", "/raw.mjpg", "/warp.mjpg", "/heatmap.mjpg"):
            key = {
                "/mask.mjpg": "jpeg_mask", "/raw.mjpg": "jpeg_raw",
                "/warp.mjpg": "warp", "/heatmap.mjpg": "heatmap",
            }[u.path]
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    jpg = state.get(key)
                    if jpg is not None:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                    time.sleep(0.07)
            except Exception:
                pass

        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    print("=" * 50)
    print("  CHESS ROBOT - Game Server v2")
    print("=" * 50)
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=game_loop, daemon=True).start()
    print(f"Dashboard: http://0.0.0.0:{PORT}", flush=True)
    ThreadedServer(("0.0.0.0", PORT), Handler).serve_forever()
