import os
import glob
import cv2

print("=== CHECKING CONNECTED CAMERAS & DEVICES ===")
# Check video devices
video_devs = glob.glob("/dev/video*")
print("Detected /dev/video* devices:", video_devs)

# Test opening video capture
working_cams = []
for idx in [0, 1, 2, 4]:
    cap = cv2.VideoCapture(idx)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            working_cams.append((idx, frame.shape))
        cap.release()

print("Active Working OpenCV Cameras (index, resolution):", working_cams)

# Check USB Serial / Robot Arm devices
serial_devs = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/serial/by-id/*")
print("Detected USB Serial / Arm Controllers:", serial_devs)
