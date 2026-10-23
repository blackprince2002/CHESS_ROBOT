# ♟️ Autonomous Chess Robot (CHESS_ROBOT)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.6%2B-green.svg)](https://opencv.org/)
[![Stockfish](https://img.shields.io/badge/Stockfish-16%2B-orange.svg)](https://stockfishchess.org/)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%204%20%7C%20Arduino%20Uno-red.svg)](https://www.raspberrypi.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An end-to-end autonomous robotic chess system combining **Computer Vision**, **Stockfish AI**, and a **4-DOF Robotic Arm**. An overhead USB camera monitors an extended physical chess mat, detects human moves in real time using per-square image differencing, validates positions with `python-chess`, queries Stockfish for the optimal counter-move, and commands an Arduino-powered robotic arm to pick and place pieces across the board.

---

## 📸 System Overview

```
                          ┌──────────────────────────┐
                          │   Overhead USB Camera    │
                          └─────────────┬────────────┘
                                        │ (Video Stream /dev/video0)
                                        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 4 (Brain / Server)                       │
│                                                                           │
│   ┌────────────────────┐   ┌─────────────────────┐   ┌────────────────┐   │
│   │ Perspective Warp   │──▶│ Piece Tracker       │──▶│ python-chess   │   │
│   │ (12x8 Mat Rectify) │   │ (Gaussian Diff)     │   │ Move Validator │   │
│   └────────────────────┘   └─────────────────────┘   └───────┬────────┘   │
│                                                              │            │
│   ┌────────────────────┐   ┌─────────────────────┐           ▼            │
│   │ Web Dashboard      │◀──│ 3D Kinematics       │◀──┌────────────────┐   │
│   │ (HTTP Port 8080)   │   │ Trajectory Planner  │   │ Stockfish AI   │   │
│   └────────────────────┘   └──────────┬──────────┘   └────────────────┘   │
└───────────────────────────────────────┼───────────────────────────────────┘
                                        │ USB Serial (G-code / Baud 115200)
                                        ▼
                          ┌──────────────────────────┐
                          │    Arduino Uno + CNC     │
                          │   Robotic Arm & Servos   │
                          └──────────────────────────┘
```

---

## 📐 Physical Board Dimensions & Layout

The system is calibrated for a **$61\text{ cm} \times 40\text{ cm}$ ($610\text{ mm} \times 400\text{ mm}$)** mat consisting of a **$12 \times 8$ grid**:

* **Playable Chessboard ($8 \times 8$):** Columns $0 \dots 7$ ($40\text{ cm} \times 40\text{ cm}$), each square is exactly **$50\text{ mm} \times 50\text{ mm}$**.
* **Graveyard / Captured Slots ($4 \times 8 = 32$ boxes):** Columns $8 \dots 11$ ($21\text{ cm} \times 40\text{ cm}$) reserved for placing captured pieces.
* **Orientation:**
  * **White (Human):** Starts on the **LEFT** (columns 0 & 1 $\rightarrow$ Ranks 1 & 2).
  * **Black (Robot):** Starts on the **RIGHT** (columns 6 & 7 $\rightarrow$ Ranks 7 & 8).
  * **Files $a \dots h$:** Run vertically from top (File $a$) to bottom (File $h$).

```
            Row 0 (File a) ────▶ [ a1 ][ a2 ][ a3 ][ a4 ][ a5 ][ a6 ][ a7 ][ a8 ]  [ 0 ][ 8 ][16][24]
            Row 1 (File b) ────▶ [ b1 ][ b2 ][ b3 ][ b4 ][ b5 ][ b6 ][ b7 ][ b8 ]  [ 1 ][ 9 ][17][25]
            Row 2 (File c) ────▶ [ c1 ][ c2 ][ c3 ][ c4 ][ c5 ][ c6 ][ c7 ][ c8 ]  [ 2 ][10 ][18][26]
            Row 3 (File d) ────▶ [ d1 ][ d2 ][ d3 ][ d4 ][ d5 ][ d6 ][ d7 ][ d8 ]  [ 3 ][11 ][19][27]
            Row 4 (File e) ────▶ [ e1 ][ e2 ][ e3 ][ e4 ][ e5 ][ e6 ][ e7 ][ e8 ]  [ 4 ][12 ][20][28]
            Row 5 (File f) ────▶ [ f1 ][ f2 ][ f3 ][ f4 ][ f5 ][ f6 ][ f7 ][ f8 ]  [ 5 ][13 ][21][29]
            Row 6 (File g) ────▶ [ g1 ][ g2 ][ g3 ][ g4 ][ g5 ][ g6 ][ g7 ][ g8 ]  [ 6 ][14 ][22][30]
            Row 7 (File h) ────▶ [ h1 ][ h2 ][ h3 ][ h4 ][ h5 ][ h6 ][ h7 ][ h8 ]  [ 7 ][15 ][23][31]
                                 ▲                        ▲                         ▲
                                 │                        │                         │
                               Rank 1                   Rank 8                   32 Captured
                            (White Side)             (Black Side)               Piece Graveyard
```

---

## 🧰 Hardware Requirements

1. **Raspberry Pi 4 Model B** (2GB / 4GB / 8GB) running Ubuntu 24.04 or Raspberry Pi OS.
2. **Standard USB UVC Webcam** (640x480 / 1280x720) mounted directly above the mat.
3. **Arduino Uno R3** connected to Raspberry Pi via USB cable.
4. **4-DOF Robotic Arm** with MG996R / SG90 servos and a mechanical claw/gripper.
5. **External 5V / 6V 3A+ Power Supply** for the servo motors (do not power servos directly from Arduino 5V pin!).
6. **$61 \times 40\text{ cm}$ Chess Mat** & standard chess pieces.

---

## 🚀 Quick Start & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/blackprince2002/CHESS_ROBOT.git
cd CHESS_ROBOT
```

### 2. Raspberry Pi Setup (Headless or Desktop)

Run these commands on the Raspberry Pi:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required system packages and Stockfish
sudo apt install -y python3-pip python3-opencv python3-numpy stockfish v4l-utils git

# Install Python libraries
pip3 install python-chess pyserial --break-system-packages

# Set USB webcam permissions
sudo chmod 666 /dev/video*
sudo usermod -a -G video $USER
```

### 3. Flash the Arduino Firmware

1. Open `chess_arm_controller.ino` in the [Arduino IDE](https://www.arduino.cc/en/software).
2. Connect your Arduino Uno via USB.
3. Select board **Arduino Uno** and your serial port.
4. Click **Upload**.

---

## 🎮 Running the Game Server

On the Raspberry Pi, launch the game server:

```bash
cd CHESS_ROBOT
python3 game_server.py
```

Or run in background with persistent logging:
```bash
nohup python3 -u game_server.py > server.log 2>&1 &
```

Now open any web browser on your PC, tablet, or phone on the same Wi-Fi:

👉 **`http://<RASPBERRY_PI_IP>:8080`**  *(e.g., `http://192.168.8.189:8080`)*

---

## 🕹️ Gameplay Flow

1. **Setup:** Place all pieces in their starting positions.
2. **Capture Baseline:** On the web dashboard, click **`📸 Capture Baseline`**.
3. **Make Your Move:** Physically move your White piece (e.g., move your Knight from `b1` to `a3`).
4. **Click "I Moved":** Click **`✅ I Moved!`**. The computer vision will:
   * Perform Gaussian differencing against the baseline.
   * Rank all legal candidate moves with confidence scores.
   * Highlight the top match (e.g., `Na3 (b1a3) [137.3]`).
5. **Confirm Move:** Click the matching candidate button (or enter custom UCI like `e2e4` if needed).
6. **Stockfish & Robot Turn:**
   * Stockfish evaluates the position and selects Black's counter-move (e.g., `e5 (e7e5)`).
   * The 3D trajectory planner generates collision-safe coordinates ($Z=90\text{mm}$ transit hop).
   * G-code commands are transmitted over USB serial to the Arduino Uno to actuate the arm.
7. **Next Move:** Manually mirror Black's move if testing without the arm, click **`📸 Capture Baseline`**, and continue playing!

---

## ⚙️ Calibration & Corner Adjustment

If the green grid overlay does not align perfectly with the physical squares on your mat:
1. Open the dashboard at `http://<PI_IP>:8080`.
2. Scroll to the **Adjust Grid Corners** section.
3. Select step size (`1`, `2`, or `5` pixels) and use the directional arrows to nudge each corner:
   * **Top-Left Corner**
   * **Top-Right Corner**
   * **Bottom-Right Corner**
   * **Bottom-Left Corner**
4. The coordinates are saved automatically to `grid_corners.json`.

---

## 📁 Repository Structure

```
CHESS_ROBOT/
├── arm_kinematics.py       # 3D Cartesian millimeter waypoints & G-code generator
├── chess_arm_controller.ino # Arduino Uno firmware for 4-axis servo control
├── chess_engine.py         # python-chess & Stockfish wrapper
├── config.py               # Hardware dimensions, heights, and engine settings
├── game_server.py          # Unified game server, state machine & web dashboard
├── grid_corners.json       # Calibrated camera corner coordinates
├── grid_mask.py            # 12x8 perspective warp & cell polygon projection
├── occupancy_tracker.py    # Per-square frame differencing engine
├── piece_tracker.py        # Move detection & change heatmap generator
├── requirements.txt        # Python dependency manifest
└── README.md               # Project documentation
```

---

## 🌐 API & Video Stream Endpoints

| Endpoint | Type | Description |
| :--- | :---: | :--- |
| `http://<PI_IP>:8080/` | Web | Interactive glassmorphic live game dashboard |
| `http://<PI_IP>:8080/mask.mjpg` | Stream | Live camera feed with $12 \times 8$ grid overlay and square labels |
| `http://<PI_IP>:8080/warp.mjpg` | Stream | Top-down $1200 \times 800$ rectified perspective feed |
| `http://<PI_IP>:8080/heatmap.mjpg`| Stream | Square-by-square visual difference heatmap |
| `http://<PI_IP>:8080/raw.mjpg` | Stream | Unprocessed camera video feed |
| `http://<PI_IP>:8080/api/state` | GET JSON | Current game phase, FEN, move log, FPS, and candidates |
| `http://<PI_IP>:8080/api/capture_baseline` | GET | Captures reference board state |
| `http://<PI_IP>:8080/api/human_moved` | GET | Signals human has finished physical move |
| `http://<PI_IP>:8080/api/confirm_move?uci=e2e4` | GET | Confirms human move and triggers Stockfish |
| `http://<PI_IP>:8080/api/new_game` | GET | Resets board and starts a new match |

---

## 🦾 G-Code Arm Protocol

The Raspberry Pi communicates with the Arduino over USB serial (`115200 baud`) using standard G-code formatting:

```gcode
G1 X150.0 Y100.0 Z90.0 M5    ; Move to safe transit height above square, gripper OPEN
G1 X150.0 Y100.0 Z24.0 M3    ; Lower to grasp piece, gripper CLOSED
G1 X150.0 Y100.0 Z90.0 M3    ; Lift piece to safe travel height
G1 X250.0 Y100.0 Z90.0 M3    ; Move over destination square
G1 X250.0 Y100.0 Z26.0 M5    ; Place piece down, gripper OPEN
G1 X0.0   Y100.0 Z100.0 M5   ; Return to safe rest/parking position
```

---

## 🛠️ Troubleshooting

* **Camera not detected:** Run `v4l2-ctl --list-devices` on the Pi. Ensure the webcam is connected and run `sudo chmod 666 /dev/video*`.
* **Stockfish binary missing:** Install with `sudo apt install stockfish`. The binary is located at `/usr/games/stockfish`.
* **Serial port permission denied:** Add the user to the dialout group: `sudo usermod -a -G dialout $USER`, then log out and log back in.
* **Port 8080 already in use:** Kill any background instances with `pkill -9 -f game_server`.

---

## 📜 License
This project is open-source under the [MIT License](LICENSE).
Contributions, issues, and pull requests are welcome!
