"""
Configuration settings for Chessboard Computer Vision & Robot Arm Controller
Designed for Raspberry Pi 4 Model B (Headless Server)
"""

import os

# ==================== CAMERA CONFIGURATION ====================
CAMERA_INDEX = 0             # 0 for default USB camera, or path to test image/video
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
WARPED_BOARD_SIZE = 800      # Rectified board size in pixels (each square is 100x100)

# ==================== PHYSICAL CHESSBOARD DIMENSIONS ====================
# Total area: 40 cm x 61 cm (400 mm x 610 mm)
# 8x8 Playable Chessboard: 400 mm x 400 mm
SQUARE_SIZE_MM = 50.0        # Exactly 50.0 mm per square (400 mm / 8 squares)

# Robot Arm Base is positioned along the 61 cm axis (210 mm extension area)
BOARD_ORIGIN_X_MM = 100.0    # Distance in mm from Robot Arm base to square a1 center
BOARD_ORIGIN_Y_MM = 80.0     # Distance in mm from Robot Arm base to square a1 center

# ==================== ROBOT ARM KINEMATICS & HEIGHTS ====================
ARM_SAFE_HOVER_Z = 90.0      # Safe Z height in mm while moving above pieces
ARM_PICKUP_Z = 24.0          # Gripper Z height in mm when grasping a piece
ARM_PLACE_Z = 26.0           # Gripper Z height in mm when releasing a piece
ARM_REST_POSITION = (0.0, 100.0, 100.0)  # Safe parking coordinate (X, Y, Z)

# Graveyard bins located in the 21 cm extension area outside the 8x8 board
GRAVEYARD_WHITE_PIECES = (50.0, 480.0, ARM_PLACE_Z)
GRAVEYARD_BLACK_PIECES = (350.0, 480.0, ARM_PLACE_Z)

# Serial port for Arduino Uno (Auto-detected if None)
SERIAL_PORT = None           # Auto-detects /dev/ttyACM0 or /dev/ttyUSB0
SERIAL_BAUDRATE = 115200     # Standard Arduino baud rate (or 9600)

# ==================== STOCKFISH ENGINE CONFIG ====================
STOCKFISH_PATH = "/usr/games/stockfish"
ENGINE_SKILL_LEVEL = 10      # 0 (easy) to 20 (grandmaster)
ENGINE_THINK_TIME = 1.0      # Seconds to think per move

# ==================== WEB DASHBOARD CONFIG ====================
WEB_PORT = 5000
