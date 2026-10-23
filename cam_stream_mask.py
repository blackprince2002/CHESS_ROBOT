"""
Live camera feed with the 12x8 grid mask drawn on top, served to your browser.
Open  http://<PI_IP>:8080

Browser controls let you nudge each of the 4 outer grid corners so the grid
lines up exactly with the printed mat. Changes are saved to grid_corners.json.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

import grid_mask
from grid_mask import GridMask, save_corners, load_corners

PORT = 8080

state = {"frame": None, "jpeg_mask": None, "jpeg_raw": None, "warp": None,
         "fps": 0.0, "camera": "searching..."}
corners = load_corners().copy()
lock = threading.Lock()


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
                state["camera"] = "NO CAMERA FOUND - check USB"
                time.sleep(2)
                continue
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            cap = None
            continue

        with lock:
            g = GridMask(corners)
        overlay = g.draw_overlay(frame)
        warped = g.warp(frame)
        cv2.putText(overlay, time.strftime("%H:%M:%S"), (8, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        state["jpeg_mask"] = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        state["jpeg_raw"] = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        state["warp"] = cv2.imencode(".jpg", cv2.resize(warped, (600, 400)),
                                     [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        n += 1
        if time.time() - t0 >= 2:
            state["fps"] = n / (time.time() - t0)
            n, t0 = 0, time.time()


PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Chess Mat - Live Mask</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#0b0f19;color:#e2e8f0;font-family:Segoe UI,sans-serif;margin:0;padding:16px}
h1{color:#38bdf8;margin:0 0 4px}small{color:#94a3b8}
.row{display:flex;flex-wrap:wrap;gap:16px;margin-top:12px}
.card{background:#1e293b;border-radius:12px;padding:12px}
img{border-radius:8px;display:block;max-width:100%}
.pad{display:grid;grid-template-columns:repeat(3,38px);gap:4px;margin:6px 0}
button{background:#334155;color:#fff;border:0;border-radius:6px;padding:8px;cursor:pointer;font-size:14px}
button:hover{background:#0ea5e9}
.corner{display:inline-block;margin:6px 14px 6px 0;vertical-align:top}
select{background:#334155;color:#fff;border:0;padding:6px;border-radius:6px}
</style></head><body>
<h1>Chess Mat Live Mask</h1>
<small>Green = playable 8x8 (a1..h8) &nbsp;|&nbsp; Orange = 32 capture boxes &nbsp;|&nbsp; Pink dots = grid corners</small>
<div class="row">
  <div class="card"><b>Camera + mask</b><br><img src="/mask.mjpg" width="640"></div>
  <div class="card"><b>Top-down (warped) view</b><br><img src="/warp.mjpg" width="600"></div>
</div>
<div class="row"><div class="card">
  <b>Adjust corners</b> (step <select id="step"><option>1</option><option selected>2</option><option>5</option></select> px)<br>
  <div id="pads"></div>
  <div style="margin-top:8px"><button onclick="rawToggle()">Toggle raw / mask</button>
  <span id="info" style="margin-left:12px;color:#94a3b8"></span></div>
</div></div>
<script>
const names=["Top-Left","Top-Right","Bottom-Right","Bottom-Left"];
const pads=document.getElementById('pads');
names.forEach((n,i)=>{
  pads.insertAdjacentHTML('beforeend',`<div class="corner"><b>${n}</b><div class="pad">
  <span></span><button onclick="mv(${i},0,-1)">&#9650;</button><span></span>
  <button onclick="mv(${i},-1,0)">&#9664;</button><span></span><button onclick="mv(${i},1,0)">&#9654;</button>
  <span></span><button onclick="mv(${i},0,1)">&#9660;</button><span></span></div></div>`);
});
function mv(i,dx,dy){const s=+document.getElementById('step').value;
  fetch(`/move?i=${i}&dx=${dx*s}&dy=${dy*s}`);}
let raw=false;function rawToggle(){raw=!raw;document.querySelector('img').src=raw?'/raw.mjpg':'/mask.mjpg';}
setInterval(()=>fetch('/info').then(r=>r.json()).then(d=>{
  document.getElementById('info').innerText=`camera ${d.camera} | ${d.fps.toFixed(1)} FPS | corners ${JSON.stringify(d.corners)}`;}),1000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, "text/html", PAGE.encode())
        elif u.path == "/info":
            body = json.dumps({"camera": state["camera"], "fps": state["fps"],
                               "corners": [[round(float(x)), round(float(y))] for x, y in corners]})
            self._send(200, "application/json", body.encode())
        elif u.path == "/move":
            q = parse_qs(u.query)
            i, dx, dy = int(q["i"][0]), float(q["dx"][0]), float(q["dy"][0])
            with lock:
                corners[i] = corners[i] + np.array([dx, dy], dtype=np.float32)
                save_corners(corners)
            self._send(200, "text/plain", b"ok")
        elif u.path in ("/mask.mjpg", "/raw.mjpg", "/warp.mjpg"):
            key = {"/mask.mjpg": "jpeg_mask", "/raw.mjpg": "jpeg_raw", "/warp.mjpg": "warp"}[u.path]
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    jpg = state[key]
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
    threading.Thread(target=capture_loop, daemon=True).start()
    print(f"Live mask server on http://0.0.0.0:{PORT}", flush=True)
    ThreadedServer(("0.0.0.0", PORT), Handler).serve_forever()
