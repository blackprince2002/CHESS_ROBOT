"""
Ultra-lightweight Camera Streamer for Raspberry Pi.
Streams the USB webcam feed to http://<PI_IP>:8080 directly in your browser.
Zero lag, zero overhead.
"""

import cv2
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

camera = None

def get_camera():
    global camera
    for idx in [0, 1, 2, 4]:
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                print(f"[CamStream] Connected to webcam at /dev/video{idx}")
                return cap
        cap.release()
    return None

class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """<!DOCTYPE html>
<html>
<head>
    <title>Raspberry Pi Live Camera Feed</title>
    <style>
        body { background: #0b0f19; color: #fff; font-family: sans-serif; text-align: center; margin: 0; padding: 20px; }
        h1 { color: #38bdf8; margin-bottom: 8px; }
        p { color: #94a3b8; margin-top: 0; }
        .box { display: inline-block; background: #1e293b; padding: 12px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
        img { max-width: 90vw; max-height: 80vh; border-radius: 8px; border: 2px solid #334155; }
    </style>
</head>
<body>
    <h1>Chessboard Live Camera Feed</h1>
    <p>Live from Raspberry Pi (USB Webcam)</p>
    <div class="box">
        <img src="/stream.mjpg" alt="Live Stream">
    </div>
</body>
</html>"""
            self.wfile.write(html.encode())

        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            
            global camera
            if camera is None or not camera.isOpened():
                camera = get_camera()

            try:
                while True:
                    if camera is not None and camera.isOpened():
                        ret, frame = camera.read()
                        if ret and frame is not None:
                            # Add a subtle timestamp / status overlay
                            ts = time.strftime("%Y-%m-%d %H:%M:%S")
                            cv2.putText(frame, f"LIVE: {ts}", (20, 40),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                            
                            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                            self.wfile.write(b"--frame\r\n")
                            self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                            self.wfile.write(jpeg.tobytes())
                            self.wfile.write(b"\r\n")
                    time.sleep(0.04) # ~25 FPS
            except Exception:
                pass
        else:
            self.send_response(404)
            self.end_headers()

def main():
    global camera
    camera = get_camera()
    server = HTTPServer(("0.0.0.0", 8080), StreamHandler)
    print("\n=======================================================")
    print(" LIVE CAMERA SERVER RUNNING ON PORT 8080")
    print(" Open http://192.168.8.189:8080 in your browser to view")
    print("=======================================================\n")
    server.serve_forever()

if __name__ == "__main__":
    main()
