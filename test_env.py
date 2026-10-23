import cv2
import chess
import numpy as np
import shutil

print("=== PI HARDWARE & ENVIRONMENT STATUS ===")
print("OpenCV Version   :", cv2.__version__)
print("Chess Version    :", chess.__version__)
print("NumPy Version    :", np.__version__)
print("Stockfish Path   :", shutil.which("stockfish"))
