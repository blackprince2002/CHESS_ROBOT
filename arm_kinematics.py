"""
Arm Kinematics & Coordinate Solver Module
Translates chess moves (e.g. 'e2 to e4') into physical (X, Y, Z) millimeter trajectories
and waypoint commands for the robotic arm.
"""

import chess
import config
import time

class ArmKinematics:
    def __init__(self,
                 square_size_mm=config.SQUARE_SIZE_MM,
                 origin_x=config.BOARD_ORIGIN_X_MM,
                 origin_y=config.BOARD_ORIGIN_Y_MM):
        self.square_size_mm = square_size_mm
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.serial_conn = None
        self.init_serial()

    def init_serial(self):
        """Initializes serial connection to Arduino Uno if available."""
        import glob
        port = config.SERIAL_PORT
        if port is None:
            # Check for Arduino Uno standard ports
            candidates = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
            if candidates:
                port = candidates[0]
                print(f"[ArmKinematics] Auto-detected Arduino Uno on: {port}")

        if port:
            try:
                import serial
                self.serial_conn = serial.Serial(port, config.SERIAL_BAUDRATE, timeout=1)
                time.sleep(2.0)  # Allow Arduino bootloader to initialize
                print(f"[ArmKinematics] Serial connection established with Arduino Uno on {port}")
            except Exception as e:
                print(f"[ArmKinematics] Serial port {port} unavailable ({e}). Running in simulation mode.")
                self.serial_conn = None
        else:
            print("[ArmKinematics] Arduino Uno not currently plugged into USB. Running in simulation mode.")

    def square_to_cartesian(self, square_name_or_int, z_mm=config.ARM_SAFE_HOVER_Z):
        """
        Converts a chess square (e.g. 'e2' or chess.E2) to physical Cartesian (X, Y, Z) in mm.
        Base origin (0, 0) is at the robot arm base.
        Square a1 is located at (origin_x, origin_y).
        """
        if isinstance(square_name_or_int, str):
            sq = chess.parse_square(square_name_or_int)
        else:
            sq = square_name_or_int

        file_idx = chess.square_file(sq)  # 0 (a) to 7 (h)
        rank_idx = chess.square_rank(sq)  # 0 (1) to 7 (8)

        # Calculate millimeter center of the square
        x_mm = self.origin_x + (file_idx * self.square_size_mm)
        y_mm = self.origin_y + (rank_idx * self.square_size_mm)

        return round(x_mm, 2), round(y_mm, 2), round(z_mm, 2)

    def generate_move_trajectory(self, board, move):
        """
        Generates the complete sequence of physical 3D waypoints and gripper actions.
        Ensures the arm lifts high enough so it never knocks over other pieces!
        
        Returns a list of structured action dictionaries:
        [
            {"action": "MOVE", "x": 150.0, "y": 100.0, "z": 90.0, "gripper": "OPEN", "note": "..."},
            ...
        ]
        """
        waypoints = []
        is_capture = board.is_capture(move)
        is_castling = board.is_castling(move)
        is_en_passant = board.is_en_passant(move)

        from_sq = move.from_square
        to_sq = move.to_square

        from_name = chess.square_name(from_sq)
        to_name = chess.square_name(to_sq)

        print(f"\n[ArmKinematics] Generating trajectory for move: {from_name} -> {to_name}")

        # -------------------------------------------------------------
        # STEP 1: Handle Enemy Piece Capture (Remove to Graveyard)
        # -------------------------------------------------------------
        if is_capture:
            # For en passant, captured pawn is on the same file as to_sq, but previous rank
            if is_en_passant:
                cap_file = chess.square_file(to_sq)
                cap_rank = chess.square_rank(from_sq)
                cap_sq = chess.square(cap_file, cap_rank)
            else:
                cap_sq = to_sq

            cap_x, cap_y, _ = self.square_to_cartesian(cap_sq)
            victim = board.piece_at(cap_sq)
            graveyard = config.GRAVEYARD_WHITE_PIECES if victim and victim.color == chess.WHITE else config.GRAVEYARD_BLACK_PIECES

            # 1a. Hover above captured piece
            waypoints.append({
                "action": "MOVE", "x": cap_x, "y": cap_y, "z": config.ARM_SAFE_HOVER_Z,
                "gripper": "OPEN", "desc": f"Hover above captured piece at {chess.square_name(cap_sq)}"
            })
            # 1b. Lower to grasp
            waypoints.append({
                "action": "MOVE", "x": cap_x, "y": cap_y, "z": config.ARM_PICKUP_Z,
                "gripper": "GRIP", "desc": "Lower and GRIP captured piece"
            })
            # 1c. Lift to safe height
            waypoints.append({
                "action": "MOVE", "x": cap_x, "y": cap_y, "z": config.ARM_SAFE_HOVER_Z,
                "gripper": "GRIP", "desc": "Lift captured piece"
            })
            # 1d. Move to graveyard bin
            waypoints.append({
                "action": "MOVE", "x": graveyard[0], "y": graveyard[1], "z": config.ARM_SAFE_HOVER_Z,
                "gripper": "GRIP", "desc": "Transport to graveyard bin"
            })
            # 1e. Lower and release
            waypoints.append({
                "action": "MOVE", "x": graveyard[0], "y": graveyard[1], "z": graveyard[2],
                "gripper": "OPEN", "desc": "Release in graveyard"
            })
            # 1f. Lift back to safe height
            waypoints.append({
                "action": "MOVE", "x": graveyard[0], "y": graveyard[1], "z": config.ARM_SAFE_HOVER_Z,
                "gripper": "OPEN", "desc": "Lift arm"
            })

        # -------------------------------------------------------------
        # STEP 2: Pick Up Moving Piece
        # -------------------------------------------------------------
        x1, y1, _ = self.square_to_cartesian(from_sq)
        x2, y2, _ = self.square_to_cartesian(to_sq)

        # 2a. Hover above source square
        waypoints.append({
            "action": "MOVE", "x": x1, "y": y1, "z": config.ARM_SAFE_HOVER_Z,
            "gripper": "OPEN", "desc": f"Hover above {from_name}"
        })
        # 2b. Lower and grip
        waypoints.append({
            "action": "MOVE", "x": x1, "y": y1, "z": config.ARM_PICKUP_Z,
            "gripper": "GRIP", "desc": f"Lower and GRIP piece at {from_name}"
        })
        # 2c. Lift to safe travel height
        waypoints.append({
            "action": "MOVE", "x": x1, "y": y1, "z": config.ARM_SAFE_HOVER_Z,
            "gripper": "GRIP", "desc": "Lift piece to safe transit height"
        })

        # -------------------------------------------------------------
        # STEP 3: Transit and Place at Destination
        # -------------------------------------------------------------
        # 3a. Transit above destination
        waypoints.append({
            "action": "MOVE", "x": x2, "y": y2, "z": config.ARM_SAFE_HOVER_Z,
            "gripper": "GRIP", "desc": f"Transit above {to_name}"
        })
        # 3b. Lower and release
        waypoints.append({
            "action": "MOVE", "x": x2, "y": y2, "z": config.ARM_PLACE_Z,
            "gripper": "OPEN", "desc": f"Place and RELEASE piece at {to_name}"
        })
        # 3c. Lift arm to safe height
        waypoints.append({
            "action": "MOVE", "x": x2, "y": y2, "z": config.ARM_SAFE_HOVER_Z,
            "gripper": "OPEN", "desc": "Clear piece"
        })

        # -------------------------------------------------------------
        # STEP 4: Handle Castling (Move the Rook as well)
        # -------------------------------------------------------------
        if is_castling:
            if to_sq == chess.G1:   # White kingside
                rook_from, rook_to = chess.H1, chess.F1
            elif to_sq == chess.C1: # White queenside
                rook_from, rook_to = chess.A1, chess.D1
            elif to_sq == chess.G8: # Black kingside
                rook_from, rook_to = chess.H8, chess.F8
            elif to_sq == chess.C8: # Black queenside
                rook_from, rook_to = chess.A8, chess.D8

            rx1, ry1, _ = self.square_to_cartesian(rook_from)
            rx2, ry2, _ = self.square_to_cartesian(rook_to)
            rook_move_pts = [
                {"action": "MOVE", "x": rx1, "y": ry1, "z": config.ARM_SAFE_HOVER_Z, "gripper": "OPEN", "desc": "Hover Rook"},
                {"action": "MOVE", "x": rx1, "y": ry1, "z": config.ARM_PICKUP_Z, "gripper": "GRIP", "desc": "Grip Rook"},
                {"action": "MOVE", "x": rx1, "y": ry1, "z": config.ARM_SAFE_HOVER_Z, "gripper": "GRIP", "desc": "Lift Rook"},
                {"action": "MOVE", "x": rx2, "y": ry2, "z": config.ARM_SAFE_HOVER_Z, "gripper": "GRIP", "desc": "Transit Rook"},
                {"action": "MOVE", "x": rx2, "y": ry2, "z": config.ARM_PLACE_Z, "gripper": "OPEN", "desc": "Place Rook"},
                {"action": "MOVE", "x": rx2, "y": ry2, "z": config.ARM_SAFE_HOVER_Z, "gripper": "OPEN", "desc": "Clear Rook"},
            ]
            waypoints.extend(rook_move_pts)

        # -------------------------------------------------------------
        # STEP 5: Return to Rest / Parking Position
        # -------------------------------------------------------------
        rx, ry, rz = config.ARM_REST_POSITION
        waypoints.append({
            "action": "MOVE", "x": rx, "y": ry, "z": rz,
            "gripper": "OPEN", "desc": "Return to parking home position"
        })

        return waypoints

    def execute_waypoints(self, waypoints):
        """
        Sends the waypoint list as G-code or Serial commands to the arm controller.
        Format: G1 X{x} Y{y} Z{z} F3000
                M3 (Grip) / M5 (Release)
        """
        for i, pt in enumerate(waypoints):
            gcode = f"G1 X{pt['x']:.1f} Y{pt['y']:.1f} Z{pt['z']:.1f}"
            grip_cmd = "M3 (GRIP)" if pt["gripper"] == "GRIP" else "M5 (RELEASE)"
            full_cmd = f"{gcode} {grip_cmd}"
            
            print(f"  [{i+1}/{len(waypoints)}] {pt['desc']} -> {full_cmd}")

            if self.serial_conn is not None:
                self.serial_conn.write(f"{full_cmd}\n".encode())
                # Wait for OK from controller
                line = self.serial_conn.readline().decode().strip()
            else:
                time.sleep(0.05)  # Fast simulated execution
