#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>
#include <TFT_eSPI.h>
#include "secrets.h"
#include "config.h"
#include <ArduinoIoTCloud.h>
#include <Arduino_ConnectionHandler.h>


const int ledPin   = 2;
const int servoPin = 13;
const int TRIG_PIN = 5;
const int ECHO_PIN = 19;
const int MELODY_BUZZER = 27;
const int BUZZER_RESOLUTION = 8;
const int BUZZER_BASE_FREQ = 1000;
const bool ENABLE_MELODY_BUZZER = true;
const int SERVO_MIN_US = 500;
const int SERVO_MAX_US = 2400;
const int SERVO_SAFE_MIN_ANGLE = 55;
const int SERVO_SAFE_MAX_ANGLE = 125;
const int SERVO_STEP_DEG = 2;
const int SERVO_STEP_DELAY_MS = 10;
const int SERVO_HOLD_MS = 250;
int neck_angle = 90;
String face_mood = "IDLE";
float distance_cm = 0;
String buzzer_cmd = "";

// Motors are on hold until I return to them
// const int IN1 = 32;
// const int IN2 = 33;
// const int IN3 = 25;
// const int IN4 = 26;

TFT_eSPI tft = TFT_eSPI();
WebServer server(80);
Servo neckServo;
int currentNeckAngle = 90;
unsigned long lastServoMoveMs = 0;

#define TFT_W 240
#define TFT_H 240
#define TFT_DC    2
#define TFT_RST   4

// Keeping the motor helpers around but disabled for now
// void motorsStop() {
//   digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
//   digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
// }
// void motorsForward() {
//   digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
//   digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
// }
// void motorsBackward() {
//   digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
//   digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
// }
// void motorsTurnLeft() {
//   digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH);
//   digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
// }
// void motorsTurnRight() {
//   digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
//   digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH);
// }

void ensureServoAttached() {
  if (!neckServo.attached()) {
    neckServo.setPeriodHertz(50);
    neckServo.attach(servoPin, SERVO_MIN_US, SERVO_MAX_US);
    neckServo.write(currentNeckAngle);
    delay(20);
  }
}

void releaseServoIfIdle() {
  // Leaving the servo attached all the time for now
}

void moveNeckTo(int targetAngle) {
  targetAngle = constrain(targetAngle, SERVO_SAFE_MIN_ANGLE, SERVO_SAFE_MAX_ANGLE);
  ensureServoAttached();
  delay(50); // a tiny delay so movement stays smooth
  if (targetAngle == currentNeckAngle) {
    lastServoMoveMs = millis();
    return;
  }
  while (currentNeckAngle != targetAngle) {
    int delta = targetAngle - currentNeckAngle;
    if (abs(delta) <= SERVO_STEP_DEG) {
      currentNeckAngle = targetAngle;
    } else {
      currentNeckAngle += (delta > 0) ? SERVO_STEP_DEG : -SERVO_STEP_DEG;
    }
    neckServo.write(currentNeckAngle);
    delay(SERVO_STEP_DELAY_MS);
  }
  lastServoMoveMs = millis();
}

long measureDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return 0;
  return duration * 0.034 / 2;
}

void playToneNote(int freq, int dur) {
  if (!ENABLE_MELODY_BUZZER) return;
  if (freq > 0) {
    ledcWriteTone(MELODY_BUZZER, freq); 
  } else {
    ledcWriteTone(MELODY_BUZZER, 0); 
  }
  delay(dur);
  ledcWriteTone(MELODY_BUZZER, 0); 
  delay(30); 
}

void playMelody(const int* notes, const int* durations, int length) {
  for (int i = 0; i < length; i++) {
    playToneNote(notes[i], durations[i]);
  }
  ledcWriteTone(MELODY_BUZZER, 0);
}

void melodyBoot() {
  const int notes[]     = {1319, 1568, 2093, 2349, 3136}; 
  const int durations[] = {100, 100, 100, 150, 300};
  playMelody(notes, durations, 5);
}

void melodyWelcome() {
  const int notes[]     = {2093, 2637, 3136}; 
  const int durations[] = {100, 100, 250};
  playMelody(notes, durations, 3);
}

void melodyThink() {
  const int notes[]     = {3136, 0, 3136}; 
  const int durations[] = {50, 30, 50};
  playMelody(notes, durations, 3);
}

void melodyConfirm() {
  const int notes[]     = {2093, 2793}; 
  const int durations[] = {80, 120};
  playMelody(notes, durations, 2);
}

void melodyAlertSoft() {
  const int notes[]     = {3136, 2637, 2093}; 
  const int durations[] = {100, 100, 200};
  playMelody(notes, durations, 3);
}

void drawConnecting() {
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_YELLOW);
  tft.setTextSize(2);
  tft.setCursor(30, 100);
  tft.print("Connecting...");
}

void drawConnected() {
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE);
  tft.setTextSize(2);
  tft.setCursor(55, 110);
  tft.print("Sandy Ready!");
  tft.setTextSize(1);
  tft.setTextColor(TFT_CYAN);
  tft.setCursor(60, 140);
  tft.print(WiFi.localIP().toString());
  delay(2000);
  setMood(0);
}

// Face animation variables for the TFT emoji
int eyeX = 120, eyeY = 85;
int targetEyeX = 120, targetEyeY = 85;
int currentMood = 0;
unsigned long lastEyeMove  = 0;
unsigned long lastMoodAnim = 0;

void drawEye(int cx, int cy, int pupilX, int pupilY, uint16_t color) {
  tft.fillCircle(cx, cy, 22, TFT_BLACK);
  tft.drawCircle(cx, cy, 22, color);
  tft.fillCircle(pupilX, pupilY, 10, color);
  tft.fillCircle(pupilX - 3, pupilY - 3, 3, TFT_WHITE);
}

void drawMouth(int mood) {
  tft.fillRect(70, 130, 100, 40, TFT_BLACK);
  switch (mood) {
    case 0: tft.drawArc(120, 125, 28, 24, 200, 340, TFT_WHITE, TFT_BLACK); break;
    case 1: tft.drawCircle(120, 148, 12, TFT_CYAN); break;
    case 2: tft.drawLine(100, 148, 130, 144, TFT_YELLOW); tft.drawLine(130, 144, 140, 148, TFT_YELLOW); break;
    case 3: tft.fillRoundRect(100, 138, 40, 18, 6, TFT_GREEN); tft.fillRect(102, 140, 36, 8, TFT_BLACK); break;
    case 4: tft.drawCircle(120, 148, 16, TFT_RED); tft.fillCircle(120, 148, 10, TFT_BLACK); break;
  }
}

void drawEyebrows(int mood) {
  tft.fillRect(60, 45, 120, 20, TFT_BLACK);
  switch (mood) {
    case 0: tft.drawLine(78, 57, 108, 55, TFT_WHITE);  tft.drawLine(132, 55, 162, 57, TFT_WHITE);  break;
    case 1: tft.drawLine(78, 52, 108, 50, TFT_CYAN);   tft.drawLine(132, 50, 162, 52, TFT_CYAN);   break;
    case 2: tft.drawLine(78, 57, 108, 52, TFT_YELLOW); tft.drawLine(132, 55, 162, 57, TFT_YELLOW); break;
    case 3: tft.drawLine(78, 57, 108, 55, TFT_GREEN);  tft.drawLine(132, 55, 162, 57, TFT_GREEN);  break;
    case 4: tft.drawLine(78, 52, 108, 58, TFT_RED);    tft.drawLine(132, 58, 162, 52, TFT_RED);    break;
  }
}

uint16_t moodColor() {
  switch (currentMood) {
    case 1: return TFT_CYAN;
    case 2: return TFT_YELLOW;
    case 3: return TFT_GREEN;
    case 4: return TFT_RED;
    default: return TFT_WHITE;
  }
}

void drawEyesOnly() {
  uint16_t col = moodColor();
  int lPupilX = 88  + (eyeX - 120) / 4;
  int lPupilY = 85  + (eyeY - 85)  / 4;
  int rPupilX = 152 + (eyeX - 120) / 4;
  int rPupilY = 85  + (eyeY - 85)  / 4;
  drawEye(88,  85, lPupilX, lPupilY, col);
  drawEye(152, 85, rPupilX, rPupilY, col);
}

void drawFace() {
  uint16_t col = moodColor();
  tft.drawCircle(120, 110, 100, col);
  drawEyebrows(currentMood);
  int lPupilX = 88  + (eyeX - 120) / 4;
  int lPupilY = 85  + (eyeY - 85)  / 4;
  int rPupilX = 152 + (eyeX - 120) / 4;
  int rPupilY = 85  + (eyeY - 85)  / 4;
  drawEye(88,  85, lPupilX, lPupilY, col);
  drawEye(152, 85, rPupilX, rPupilY, col);
  drawMouth(currentMood);
}

void setMood(int mood) {
  currentMood = mood;
  tft.fillRect(0, 0, 240, 240, TFT_BLACK);
  drawFace();
}

void updateFaceAnimation() {
  unsigned long now = millis();
  if (now - lastEyeMove > 3000 + random(2000)) {
    targetEyeX  = 100 + random(40);
    targetEyeY  = 75  + random(20);
    lastEyeMove = now;
  }
  if (abs(eyeX - targetEyeX) > 1 || abs(eyeY - targetEyeY) > 1) {
    eyeX += (targetEyeX - eyeX) / 3;
    eyeY += (targetEyeY - eyeY) / 3;
    drawEyesOnly();
  }
  if (currentMood == 3 && now - lastMoodAnim > 250) {
    lastMoodAnim = now;
    tft.fillRect(70, 130, 100, 40, TFT_BLACK);
    drawMouth(3);
  }
}

void handleShowText() {
  // Expect 240x240 data from the client
  const int W = 240;
  const int H = 240;
  int expectedBytes = W * H * 2; 

  // Read raw data from the HTTP client
  WiFiClient client = server.client();
  uint8_t* buf = (uint8_t*)malloc(expectedBytes);

  if (!buf) {
    server.send(500, "text/plain", "No Memory");
    return;
  }

  int received = 0;
  unsigned long startTime = millis();
  
  // Wait for the full image (5-second timeout)
  while (received < expectedBytes && (millis() - startTime < 5000)) {
    while (client.available() && received < expectedBytes) {
      buf[received++] = client.read();
    }
    yield();
  }

  if (received == expectedBytes) {
    // Push the full image to the TFT
    tft.pushImage(0, 0, W, H, (uint16_t*)buf);
    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Incomplete Data");
  }

  free(buf); // never skip cleaning up RAM
}

String executeCommand(String command) {
  command.trim();
  if      (command == "LED_ON")       { digitalWrite(ledPin, HIGH); return "OK_LED_ON"; }
  else if (command == "LED_OFF")      { digitalWrite(ledPin, LOW);  return "OK_LED_OFF"; }
  else if (command == "LOOK_LEFT")    { moveNeckTo(55);  return "OK_LEFT"; }
  else if (command == "LOOK_RIGHT")   { moveNeckTo(125); return "OK_RIGHT"; }
  else if (command == "LOOK_CENTER")  { moveNeckTo(90);  return "OK_CENTER"; }
  else if (command == "SCAN_POS_1")   { moveNeckTo(55);  return "OK_SCAN1"; }
  else if (command == "SCAN_POS_2")   { moveNeckTo(90);  return "OK_SCAN2"; }
  else if (command == "SCAN_POS_3")   { moveNeckTo(125); return "OK_SCAN3"; }
  // Movement commands still parked
  // else if (command == "MOVE_FORWARD")  { motorsForward();  return "OK_FORWARD"; }
  // else if (command == "MOVE_BACKWARD") { motorsBackward(); return "OK_BACKWARD"; }
  // else if (command == "MOVE_LEFT")     { motorsTurnLeft(); return "OK_TURN_LEFT"; }
  // else if (command == "MOVE_RIGHT")    { motorsTurnRight();return "OK_TURN_RIGHT"; }
  // else if (command == "MOVE_STOP")     { motorsStop();     return "OK_STOP"; }
  // Quick tunes for different moods
  else if (command == "BUZZ_WELCOME" || command == "MELODY_WELCOME") {
    if (!ENABLE_MELODY_BUZZER) return "MELODY_DISABLED";
    melodyWelcome(); return "OK_MELODY_WELCOME";
  }
  else if (command == "BUZZ_THINK" || command == "MELODY_THINK") {
    if (!ENABLE_MELODY_BUZZER) return "MELODY_DISABLED";
    melodyThink(); return "OK_MELODY_THINK";
  }
  else if (command == "BUZZ_CONFIRM" || command == "MELODY_CONFIRM") {
    if (!ENABLE_MELODY_BUZZER) return "MELODY_DISABLED";
    melodyConfirm(); return "OK_MELODY_CONFIRM";
  }
  else if (command == "MELODY_ALERT") {
    if (!ENABLE_MELODY_BUZZER) return "MELODY_DISABLED";
    melodyAlertSoft(); return "OK_MELODY_ALERT";
  }
  else if (command == "MELODY_BOOT") {
    if (!ENABLE_MELODY_BUZZER) return "MELODY_DISABLED";
    melodyBoot(); return "OK_MELODY_BOOT";
  }
  else if (command == "BUZZ_ALERT")  { return "ALERT_BUZZER_DISABLED"; }
  else if (command == "FACE_IDLE")   { setMood(0); return "OK_IDLE"; }
  else if (command == "FACE_LISTEN") { setMood(1); return "OK_LISTEN"; }
  else if (command == "FACE_THINK")  { setMood(2); return "OK_THINK"; }
  else if (command == "FACE_SPEAK")  { setMood(3); return "OK_SPEAK"; }
  else if (command == "FACE_ALERT")  { setMood(4); return "OK_ALERT"; }
  else return "UNKNOWN_CMD";
}

void handleCmd() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (!server.hasArg("cmd")) {
    server.send(400, "text/plain", "NO_CMD");
    return;
  }
  String cmd    = server.arg("cmd");
  String result = executeCommand(cmd);
  Serial.println("Servo attached: " + String(neckServo.attached()));
  Serial.println("Result: " + result);
  server.send(200, "text/plain", result);
}

void handleDistance() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "text/plain", String(measureDistance()));
}

void handleRoot() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "text/plain", "Sandy ESP32 Online!");
}

void handleNotFound() {
  server.send(404, "text/plain", "Not Found");
}

void onNeckAngleChange();
void onFaceMoodChange();
void onBuzzerCmdChange();

WiFiConnectionHandler ArduinoIoTPreferredConnection(WIFI_SSID, WIFI_PASSWORD);


void setup() {
  
  // 1. Initialize fast to avoid any boot buzz
  pinMode(MELODY_BUZZER, OUTPUT);
  digitalWrite(MELODY_BUZZER, LOW); 

  Serial.begin(115200);
  ArduinoCloud.setBoardId(DEVICE_LOGIN_NAME);
  ArduinoCloud.setSecretDeviceKey(SENSITIVE_DEVICE_KEY);
  ArduinoCloud.addProperty(neck_angle, READWRITE, ON_CHANGE, onNeckAngleChange);
  ArduinoCloud.addProperty(face_mood, READWRITE, ON_CHANGE, onFaceMoodChange);
  ArduinoCloud.addProperty(distance_cm, READ, 5 * SECONDS);
  ArduinoCloud.addProperty(buzzer_cmd, READWRITE, ON_CHANGE, onBuzzerCmdChange);
  ArduinoCloud.begin(ArduinoIoTPreferredConnection);

  pinMode(ledPin,   OUTPUT); digitalWrite(ledPin, LOW);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // 2. Configure PWM for the passive buzzer
  if (ENABLE_MELODY_BUZZER) {
    ledcAttach(MELODY_BUZZER, BUZZER_BASE_FREQ, BUZZER_RESOLUTION);
    ledcWriteTone(MELODY_BUZZER, 0); // mute just in case
  }

  ensureServoAttached();
  moveNeckTo(90);
  delay(SERVO_HOLD_MS);

  // Prepare the TFT screen
  tft.init();
  tft.setRotation(0);
  tft.fillScreen(TFT_BLACK);
  drawConnecting();

  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    tries++;
    if (tries > 40) {
      Serial.println("\n❌ WiFi failed! Restarting...");
      ESP.restart();
    }
  }

  Serial.println("\n✅ WiFi connected!");
  drawConnected();

  server.on("/",          handleRoot);
  server.on("/cmd",       handleCmd);
  server.on("/distance",  handleDistance);
  server.on("/show_text", HTTP_POST, handleShowText); // double-check the handler name
  server.onNotFound(handleNotFound);
  const char* headers[] = {"Content-Length"};
  server.collectHeaders(headers, 1);
  server.begin();

  // 3. Play the boot melody now that buzzer works
  if (ENABLE_MELODY_BUZZER) melodyBoot();
  
  Serial.println("Sandy Ready! 🤖");
}



void loop() {
  ArduinoCloud.update();
  distance_cm = measureDistance();
  releaseServoIfIdle();
  server.handleClient();
  
  static unsigned long lastAnim = 0;
  if (millis() - lastAnim > 50) {
    lastAnim = millis();
    updateFaceAnimation();
  }
}

void onNeckAngleChange() { moveNeckTo(neck_angle); }
void onFaceMoodChange()  { executeCommand("FACE_" + face_mood); }
void onBuzzerCmdChange() { 
  Serial.println("Buzzer CMD: " + buzzer_cmd);
  executeCommand(buzzer_cmd); 
}
