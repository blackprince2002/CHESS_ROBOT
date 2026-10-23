/*
 * Arduino Uno Robotic Chess Arm Firmware
 * Receives Cartesian G-code commands over USB Serial from Raspberry Pi:
 *   G1 X{x} Y{y} Z{z} F{feedrate}
 *   M3 (GRIP) / M5 (RELEASE)
 *
 * Drives 4-axis or 3-axis arm servos (Base, Shoulder, Elbow, Gripper).
 */

#include <Servo.h>

// Servo pin definitions (adjust to your shield/wiring)
const int PIN_BASE     = 9;
const int PIN_SHOULDER = 10;
const int PIN_ELBOW    = 11;
const int PIN_GRIPPER  = 6;

Servo servoBase;
Servo servoShoulder;
Servo servoElbow;
Servo servoGripper;

// Physical Arm link lengths in millimeters
const float L1 = 150.0; // Shoulder to Elbow link length (mm)
const float L2 = 160.0; // Elbow to Wrist link length (mm)
const float BASE_HEIGHT = 80.0; // Base rotation pivot to shoulder height (mm)

// Gripper angles
const int GRIP_CLOSED = 45;   // Grasp piece angle
const int GRIP_OPEN   = 110;  // Release piece angle

void setup() {
  Serial.begin(115200);
  servoBase.attach(PIN_BASE);
  servoShoulder.attach(PIN_SHOULDER);
  servoElbow.attach(PIN_ELBOW);
  servoGripper.attach(PIN_GRIPPER);

  // Home parking position
  servoGripper.write(GRIP_OPEN);
  moveToCartesian(0.0, 100.0, 100.0);
  
  Serial.println("ARM_READY");
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;

    if (cmd.startsWith("G1")) {
      float x = parseCoordinate(cmd, 'X');
      float y = parseCoordinate(cmd, 'Y');
      float z = parseCoordinate(cmd, 'Z');
      moveToCartesian(x, y, z);
      Serial.println("OK G1");
    } 
    else if (cmd.indexOf("M3") >= 0) {
      servoGripper.write(GRIP_CLOSED);
      delay(300);
      Serial.println("OK M3");
    } 
    else if (cmd.indexOf("M5") >= 0) {
      servoGripper.write(GRIP_OPEN);
      delay(300);
      Serial.println("OK M5");
    }
  }
}

float parseCoordinate(String str, char axis) {
  int idx = str.indexOf(axis);
  if (idx < 0) return 0.0;
  int endIdx = str.indexOf(' ', idx);
  if (endIdx < 0) endIdx = str.length();
  return str.substring(idx + 1, endIdx).toFloat();
}

// 3-DOF Inverse Kinematics: Converts (X, Y, Z mm) to servo angles
void moveToCartesian(float x, float y, float z) {
  // 1. Base angle (yaw in XY plane)
  float baseRad = atan2(x, y);
  int baseAngle = (int)(baseRad * 180.0 / PI) + 90;
  baseAngle = constrain(baseAngle, 0, 180);

  // 2. Planar projection for shoulder & elbow
  float r = sqrt(x * x + y * y);
  float dz = z - BASE_HEIGHT;
  float d = sqrt(r * r + dz * dz);

  // Law of Cosines for elbow
  float cosElbow = (d * d - L1 * L1 - L2 * L2) / (2.0 * L1 * L2);
  cosElbow = constrain(cosElbow, -1.0, 1.0);
  float elbowRad = acos(cosElbow);
  int elbowAngle = (int)(elbowRad * 180.0 / PI);

  // Shoulder angle
  float alpha = atan2(dz, r);
  float beta = atan2(L2 * sin(elbowRad), L1 + L2 * cos(elbowRad));
  int shoulderAngle = (int)((alpha + beta) * 180.0 / PI);
  shoulderAngle = constrain(shoulderAngle, 0, 180);
  elbowAngle = constrain(elbowAngle, 0, 180);

  servoBase.write(baseAngle);
  servoShoulder.write(shoulderAngle);
  servoElbow.write(elbowAngle);
  delay(150);
}
