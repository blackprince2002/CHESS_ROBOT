"""
Test Script: Verifies Arm Decision and Coordinate Kinematics on Raspberry Pi
Demonstrates how moves like 'e7e5' or captures are mapped into real-world (X, Y, Z) mm waypoints.
"""

import chess
from chess_engine import ChessGame
from arm_kinematics import ArmKinematics

def test_pipeline():
    print("==================================================")
    print(" AUTONOMOUS CHESS ROBOT: DECISION & ARM TEST")
    print("==================================================")
    
    game = ChessGame()
    arm = ArmKinematics(square_size_mm=45.0, origin_x=150.0, origin_y=100.0)

    # 1. Player plays e2 -> e4
    player_move = chess.Move.from_uci("e2e4")
    print(f"\n[Test] Player moves: {player_move.uci()}")
    game.apply_move(player_move)

    # 2. Query Stockfish for Robot's response move
    print("\n[Test] Querying Stockfish for Robot's counter-move...")
    robot_move = game.get_best_engine_move(time_limit=1.0)
    print(f"[Test] Robot Decision: {robot_move.uci()} ({game.board.san(robot_move)})")

    # 3. Generate physical (X, Y, Z) coordinates for the robotic arm
    waypoints = arm.generate_move_trajectory(game.board, robot_move)
    
    print("\n[Test] Generated 3D Trajectory for Robot Arm:")
    for i, wp in enumerate(waypoints):
        print(f"  Step {i+1:02d}: X={wp['x']:6.1f} mm | Y={wp['y']:6.1f} mm | Z={wp['z']:5.1f} mm | Gripper={wp['gripper']:7s} | {wp['desc']}")

    # 4. Test a Capture Scenario (e.g. e4 x d5)
    print("\n--------------------------------------------------")
    print(" TESTING PIECE CAPTURE TRAJECTORY (Graveyard Bin)")
    print("--------------------------------------------------")
    test_board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    capture_move = chess.Move.from_uci("e4d5") # White pawn takes black pawn on d5
    cap_waypoints = arm.generate_move_trajectory(test_board, capture_move)
    for i, wp in enumerate(cap_waypoints):
        print(f"  Step {i+1:02d}: X={wp['x']:6.1f} mm | Y={wp['y']:6.1f} mm | Z={wp['z']:5.1f} mm | Gripper={wp['gripper']:7s} | {wp['desc']}")

    game.close()
    print("\n==================================================")
    print(" TEST COMPLETED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    test_pipeline()
