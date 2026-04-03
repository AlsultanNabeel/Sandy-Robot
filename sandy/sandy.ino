#include <Arduino.h>
#include <TFT_eSPI.h>
#include <ESP32Servo.h>
#include "config.h"
#include "secrets.h"
#include "thingProperties.h"


TFT_eSPI tft = TFT_eSPI();
Servo neckServo;

bool cloudBuzzerActive = false;
unsigned long cloudBuzzerUntilMs = 0;
String pendingBuzzerEvent = "";
bool pendingBuzzerPlay = false;

// =========================
// Mood System
// =========================
enum Mood {
  MOOD_IDLE = 0,
  MOOD_HAPPY,
  MOOD_BIG_HAPPY,
  MOOD_CURIOUS,
  MOOD_THINK,
  MOOD_TALK,
  MOOD_ALERT,
  MOOD_SURPRISED,
  MOOD_SLEEPY,
  MOOD_BORED,
  MOOD_YAWN,
  MOOD_SAD,
  MOOD_ANGRY,
  MOOD_SMIRK,
  MOOD_CUTE,
  MOOD_EXCITED,
  MOOD_SHY,
  MOOD_CONFUSED,
  MOOD_EMPATHETIC,
  MOOD_LOVE,
  MOOD_CRY,
  MOOD_WINK,
  MOOD_KISS,
  MOOD_HEART_EYES,
  MOOD_CALM
};

Mood currentMood = MOOD_IDLE;

unsigned long lastAnimMs = 0;
unsigned long lastBlinkMs = 0;
unsigned long blinkUntilMs = 0;
unsigned long moodUntilMs = 0;
unsigned long lastIdleActionMs = 0;
unsigned long nextIdleActionDelayMs = 180000 + random(0, 120000);
unsigned long lastServoStepMs = 0;
unsigned long lastTalkToneMs = 0;
unsigned long lastEyeTargetMs = 0;

bool autonomousIdle = true;
bool talkingPulse = false;
uint8_t talkFrame = 0;
unsigned long lastTalkFrameMs = 0;
unsigned long fxStartMs = 0;

// =========================
// Eyes
// =========================
int eyeOffsetX = 0;
int eyeOffsetY = 0;
int targetEyeOffsetX = 0;
int targetEyeOffsetY = 0;

#include "sandy_faces.h"

// =========================
// Servo
// =========================
int currentNeckAngle = SERVO_CENTER_ANGLE;
int targetNeckAngle  = SERVO_CENTER_ANGLE;

// =========================
// Buzzer
// =========================
bool buzzerReady = false;

// =========================
// Utility
// =========================
int clampAngle(int angle) {
  if (angle < SERVO_SAFE_MIN_ANGLE) return SERVO_SAFE_MIN_ANGLE;
  if (angle > SERVO_SAFE_MAX_ANGLE) return SERVO_SAFE_MAX_ANGLE;
  return angle;
}

void ensureServoAttached() {
  if (!neckServo.attached()) {
    neckServo.setPeriodHertz(50);
    neckServo.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
    delay(20);
  }
}

void moveNeckTo(int angle) {
  targetNeckAngle = clampAngle(angle);
}

void updateServoMotion() {
  unsigned long now = millis();
  if (now - lastServoStepMs < SERVO_STEP_DELAY_MS) return;
  lastServoStepMs = now;

  if (currentNeckAngle == targetNeckAngle) return;

  if (currentNeckAngle < targetNeckAngle) {
    currentNeckAngle += SERVO_STEP_DEG;
    if (currentNeckAngle > targetNeckAngle) currentNeckAngle = targetNeckAngle;
  } else {
    currentNeckAngle -= SERVO_STEP_DEG;
    if (currentNeckAngle < targetNeckAngle) currentNeckAngle = targetNeckAngle;
  }

  neckServo.write(currentNeckAngle);
}

// =========================
// Buzzer
// =========================
void setupBuzzer() {
  if (!ENABLE_BUZZER) return;
  buzzerReady = ledcAttach(BUZZER_PIN, BUZZER_BASE_FREQ, BUZZER_RESOLUTION);
  if (buzzerReady) ledcWriteTone(BUZZER_PIN, 0);
}
void stopBuzzer() {
  if (!ENABLE_BUZZER || !buzzerReady) return;
  ledcWriteTone(BUZZER_PIN, 0);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
}

void playToneMs(int freq, int dur) {
  if (!ENABLE_BUZZER || !buzzerReady) return;

  if (freq <= 0) {
    stopBuzzer();
    delay(dur);
    return;
  }

  ledcWriteTone(BUZZER_PIN, freq);
  delay(dur);
  stopBuzzer();
  delay(20);
}

void playMelody(const int *notes, const int *durs, int len) {
  if (!ENABLE_BUZZER || !buzzerReady) return;

  for (int i = 0; i < len; i++) {
    playToneMs(notes[i], durs[i]);
  }

  stopBuzzer();
}

void melodyBoot() {
  const int n[] = {1319, 1760, 2093};
  const int d[] = {70,   90,   140};
  playMelody(n, d, 3);
}

void melodyHappy() {
  const int n[] = {1568, 2093, 2637};
  const int d[] = {70,   90,   180};
  playMelody(n, d, 3);
}

void melodyCurious() {
  const int n[] = {1319, 1568, 1319};
  const int d[] = {70,   90,   140};
  playMelody(n, d, 3);
}

void melodySad() {
  const int n[] = {1175, 1047};
  const int d[] = {110,  220};
  playMelody(n, d, 2);
}

void melodyAlert() {
  const int n[] = {2200, 1800, 2200};
  const int d[] = {55,   55,   120};
  playMelody(n, d, 3);
}

void maybeTalkTone() {
  return;
}

// =========================
// Mood -> Servo
// =========================
void applyMoodMotion(Mood mood) {
  switch (mood) {
    case MOOD_IDLE:       moveNeckTo(SERVO_CENTER_ANGLE); break;
    case MOOD_CALM:       moveNeckTo(SERVO_CENTER_ANGLE - 2); break;
    case MOOD_HAPPY:      moveNeckTo(SERVO_CENTER_ANGLE + 6); break;
    case MOOD_BIG_HAPPY:  moveNeckTo(SERVO_CENTER_ANGLE - 8); break;
    case MOOD_CURIOUS:    moveNeckTo(SERVO_CENTER_ANGLE + 16); break;
    case MOOD_THINK:      moveNeckTo(SERVO_CENTER_ANGLE - 12); break;
    case MOOD_TALK:       moveNeckTo(SERVO_CENTER_ANGLE + (talkingPulse ? 4 : -4)); break;
    case MOOD_SURPRISED:  moveNeckTo(SERVO_CENTER_ANGLE + 2); break;
    case MOOD_SLEEPY:     moveNeckTo(SERVO_CENTER_ANGLE - 8); break;
    case MOOD_BORED:      moveNeckTo(SERVO_CENTER_ANGLE + 3); break;
    case MOOD_YAWN:       moveNeckTo(SERVO_CENTER_ANGLE - 10); break;
    case MOOD_SAD:        moveNeckTo(SERVO_CENTER_ANGLE - 12); break;
    case MOOD_ANGRY:      moveNeckTo(SERVO_CENTER_ANGLE + 18); break;
    case MOOD_SMIRK:      moveNeckTo(SERVO_CENTER_ANGLE + 10); break;
    case MOOD_CUTE:       moveNeckTo(SERVO_CENTER_ANGLE - 5); break;
    case MOOD_EXCITED:    moveNeckTo(SERVO_CENTER_ANGLE + random(-12, 13)); break;
    case MOOD_SHY:        moveNeckTo(SERVO_CENTER_ANGLE - 10); break;
    case MOOD_CONFUSED:   moveNeckTo(SERVO_CENTER_ANGLE + 8); break;
    case MOOD_EMPATHETIC: moveNeckTo(SERVO_CENTER_ANGLE - 8); break;
    case MOOD_LOVE:       moveNeckTo(SERVO_CENTER_ANGLE - 4); break;
    case MOOD_CRY:        moveNeckTo(SERVO_CENTER_ANGLE - 16); break;
    case MOOD_WINK:       moveNeckTo(SERVO_CENTER_ANGLE + 4); break;
    case MOOD_KISS:       moveNeckTo(SERVO_CENTER_ANGLE - 6); break;
    case MOOD_HEART_EYES: moveNeckTo(SERVO_CENTER_ANGLE - 2); break;
    case MOOD_ALERT:      moveNeckTo(SERVO_CENTER_ANGLE + 14); break;
  }
}

// =========================
// Idle behavior
// =========================
void chooseNewEyeTarget() {
  switch (currentMood) {
    case MOOD_SLEEPY:
    case MOOD_YAWN:
      targetEyeOffsetX = random(-1, 2);
      targetEyeOffsetY = random(1, 3);
      break;
    case MOOD_CURIOUS:
    case MOOD_CONFUSED:
      targetEyeOffsetX = random(-7, 8);
      targetEyeOffsetY = random(-2, 3);
      break;
    default:
      targetEyeOffsetX = random(-5, 6);
      targetEyeOffsetY = random(-3, 4);
      break;
  }
}

void runIdleAction() {
  int r = random(0, 100);

  if      (r < 16) currentMood = MOOD_CURIOUS;
  else if (r < 28) currentMood = MOOD_BORED;
  else if (r < 38) currentMood = MOOD_SLEEPY;
  else if (r < 50) currentMood = MOOD_HAPPY;
  else if (r < 58) currentMood = MOOD_SMIRK;
  else if (r < 66) currentMood = MOOD_SHY;
  else if (r < 74) currentMood = MOOD_CONFUSED;
  else if (r < 82) currentMood = MOOD_CUTE;
  else if (r < 88) currentMood = MOOD_CALM;
  else if (r < 93) currentMood = MOOD_WINK;
  else if (r < 97) currentMood = MOOD_BIG_HAPPY;
  else             currentMood = MOOD_IDLE;

  moodUntilMs = millis() + 1200 + random(0, 1200);
  fxStartMs = millis();
  applyMoodMotion(currentMood);

  nextIdleActionDelayMs = 180000 + random(0, 120000);
}

void updateFaceAnimation() {
  unsigned long now = millis();

  if (currentMood == MOOD_TALK || currentMood == MOOD_EXCITED || currentMood == MOOD_CRY || currentMood == MOOD_LOVE) {
    if (now - lastTalkFrameMs > 75) {
      lastTalkFrameMs = now;
      talkFrame = (talkFrame + 1) % 6;
      talkingPulse = !talkingPulse;
    }
  }

  if (now - lastBlinkMs > 1800 + random(0, 2200)) {
    blinkUntilMs = now + 120;
    lastBlinkMs = now;
  }

  if (now - lastEyeTargetMs > 520) {
    lastEyeTargetMs = now;
    chooseNewEyeTarget();
  }

  if (eyeOffsetX < targetEyeOffsetX) eyeOffsetX++;
  else if (eyeOffsetX > targetEyeOffsetX) eyeOffsetX--;

  if (eyeOffsetY < targetEyeOffsetY) eyeOffsetY++;
  else if (eyeOffsetY > targetEyeOffsetY) eyeOffsetY--;

  if (autonomousIdle) {
    if (moodUntilMs > 0 && now > moodUntilMs) {
      currentMood = MOOD_IDLE;
      moodUntilMs = 0;
      applyMoodMotion(currentMood);
    }

    if (now - lastIdleActionMs > nextIdleActionDelayMs) {
      lastIdleActionMs = now;
      runIdleAction();
    }
  }

  drawFace();
}

// =========================
// Demo actions
// =========================
void startupSequence() {
  fxStartMs = millis();
  currentMood = MOOD_HAPPY;
  drawFace();
  melodyBoot();
  stopBuzzer();
  moveNeckTo(SERVO_CENTER_ANGLE + 6);
  delay(250);

  currentMood = MOOD_BIG_HAPPY;
  drawFace();
  moveNeckTo(SERVO_CENTER_ANGLE - 6);
  delay(250);

  currentMood = MOOD_IDLE;
  drawFace();
  moveNeckTo(SERVO_CENTER_ANGLE);
}

void demoTalkShort() {
  fxStartMs = millis();
  currentMood = MOOD_TALK;
  for (int i = 0; i < 8; i++) {
    talkingPulse = !talkingPulse;
    drawFace();
    maybeTalkTone();
    applyMoodMotion(MOOD_TALK);
    delay(120);
  }
  currentMood = MOOD_IDLE;
}


// =========================
// moodState
// =========================

void onMoodStateChange() {
  if (moodState == "idle") currentMood = MOOD_IDLE;
  else if (moodState == "happy") currentMood = MOOD_HAPPY;
  else if (moodState == "big_happy") currentMood = MOOD_BIG_HAPPY;
  else if (moodState == "curious") currentMood = MOOD_CURIOUS;
  else if (moodState == "think") currentMood = MOOD_THINK;
  else if (moodState == "talk") currentMood = MOOD_TALK;
  else if (moodState == "alert") currentMood = MOOD_ALERT;
  else if (moodState == "surprised") currentMood = MOOD_SURPRISED;
  else if (moodState == "sleepy") currentMood = MOOD_SLEEPY;
  else if (moodState == "bored") currentMood = MOOD_BORED;
  else if (moodState == "yawn") currentMood = MOOD_YAWN;
  else if (moodState == "sad") currentMood = MOOD_SAD;
  else if (moodState == "angry") currentMood = MOOD_ANGRY;
  else if (moodState == "smirk") currentMood = MOOD_SMIRK;
  else if (moodState == "cute") currentMood = MOOD_CUTE;
  else if (moodState == "excited") currentMood = MOOD_EXCITED;
  else if (moodState == "shy") currentMood = MOOD_SHY;
  else if (moodState == "confused") currentMood = MOOD_CONFUSED;
  else if (moodState == "empathetic") currentMood = MOOD_EMPATHETIC;
  else if (moodState == "love") currentMood = MOOD_LOVE;
  else if (moodState == "cry") currentMood = MOOD_CRY;
  else if (moodState == "wink") currentMood = MOOD_WINK;
  else if (moodState == "kiss") currentMood = MOOD_KISS;
  else if (moodState == "heart_eyes") currentMood = MOOD_HEART_EYES;
  else if (moodState == "calm") currentMood = MOOD_CALM;
  else return;

  fxStartMs = millis();
  autonomousIdle = false;
  statusText = "mood:" + moodState;
  drawFace();
}

void onServoAngleChange() {
  if (servoAngle < SERVO_SAFE_MIN_ANGLE) servoAngle = SERVO_SAFE_MIN_ANGLE;
  if (servoAngle > SERVO_SAFE_MAX_ANGLE) servoAngle = SERVO_SAFE_MAX_ANGLE;

  targetNeckAngle = servoAngle;
  autonomousIdle = false;
  statusText = "servo";
}

void onAutonomousModeChange() {
  autonomousIdle = autonomousMode;
  statusText = autonomousIdle ? "autonomous on" : "autonomous off";
}

void playEventSound(const String& eventName) {
  if (eventName == "startup") melodyBoot();
  else if (eventName == "wake") melodyHappy();
  else if (eventName == "sleep") melodyCurious();
  else if (eventName == "alert") melodyAlert();
  else if (eventName == "sad") melodySad();
  else if (eventName == "error") melodyAlert();
  else if (eventName == "stop") stopBuzzer();
}

void onBuzzerCommandChange() {
  Serial.print("buzzerCommand = ");
  Serial.println(buzzerCommand);

  if (buzzerCommand == "startup" ||
      buzzerCommand == "wake" ||
      buzzerCommand == "sleep" ||
      buzzerCommand == "sad" ||
      buzzerCommand == "alert" ||
      buzzerCommand == "error") {

    pendingBuzzerEvent = buzzerCommand;
    pendingBuzzerPlay = true;
    cloudBuzzerActive = true;
    cloudBuzzerUntilMs = millis() + 2000;
    statusText = "buzzer:" + buzzerCommand;
  }
  else if (buzzerCommand == "stop") {
    stopBuzzer();
    pendingBuzzerEvent = "";
    pendingBuzzerPlay = false;
    cloudBuzzerActive = false;
    statusText = "buzzer:stop";
  }
  else {
    return;
  }

  buzzerCommand = "none";
}
 
 // =========================
//  DistanceCm
// =========================

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000UL);

  if (duration == 0) return -1.0;

  float cm = duration * 0.0343f / 2.0f;
  return cm;
}
// =========================
// Setup / Loop
// =========================

void setup() {
  Serial.begin(115200);
  delay(200);
  randomSeed(esp_random());

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
    tft.init();
  tft.writecommand(0x26);   // GAMSET
  tft.writedata(0x04);      // Gamma Curve 3
  tft.setRotation(0);
  clearFace();

  setupBuzzer();
  stopBuzzer();

  initProperties();
  ArduinoCloud.begin(ArduinoIoTPreferredConnection);
  moodState = "idle";
  buzzerCommand = "none";
  statusText = "booted";
  servoAngle = SERVO_CENTER_ANGLE;
  autonomousMode = true;
  distanceCm = 0;
  setDebugMessageLevel(0);
  // ArduinoCloud.printDebugInfo();

  ensureServoAttached();
  currentNeckAngle = SERVO_CENTER_ANGLE;
  targetNeckAngle = SERVO_CENTER_ANGLE;
  neckServo.write(currentNeckAngle);

  startupSequence();

  autonomousIdle = true;
  currentMood = MOOD_IDLE;
  fxStartMs = millis();
  lastIdleActionMs = millis();
  nextIdleActionDelayMs = 180000 + random(0, 120000);
  drawFace();
}


void loop() {
  unsigned long now = millis();

  ArduinoCloud.update();
  if (pendingBuzzerPlay) {
  pendingBuzzerPlay = false;
  playEventSound(pendingBuzzerEvent);
  pendingBuzzerEvent = "";
  }

  if (now - lastAnimMs > FACE_ANIM_INTERVAL_MS) {
    lastAnimMs = now;
    updateFaceAnimation();
  }

  if (currentMood == MOOD_TALK) {
    maybeTalkTone();
    applyMoodMotion(MOOD_TALK);
  }

  if (cloudBuzzerActive && now >= cloudBuzzerUntilMs) {
    stopBuzzer();
    cloudBuzzerActive = false;
  }

  updateServoMotion();

  static unsigned long lastDistanceReadMs = 0;
  if (now - lastDistanceReadMs >= DISTANCE_READ_INTERVAL_MS) {
    lastDistanceReadMs = now;

    float d = readDistanceCm();
    if (d > 0) {
      distanceCm = d;
    }
  }

}