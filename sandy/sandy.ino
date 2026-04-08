
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
unsigned long cloudWarmupUntilMs = 0;
bool startupSequenceDone = false;

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
// Base Motion Functions (L298N)
// =========================
// تم نقل الدوال إلى هنا لتكون منظمة

void stopMotors() {
  digitalWrite(MOTOR_LEFT_IN1, LOW);
  digitalWrite(MOTOR_LEFT_IN2, LOW);
  digitalWrite(MOTOR_RIGHT_IN3, LOW);
  digitalWrite(MOTOR_RIGHT_IN4, LOW);
  Serial.println("[MOTOR] Stop");
}

void moveForward() {
  digitalWrite(MOTOR_LEFT_IN1, HIGH);
  digitalWrite(MOTOR_LEFT_IN2, LOW);
  digitalWrite(MOTOR_RIGHT_IN3, HIGH);
  digitalWrite(MOTOR_RIGHT_IN4, LOW);
  Serial.println("[MOTOR] Forward");
}

void moveBackward() {
  digitalWrite(MOTOR_LEFT_IN1, LOW);
  digitalWrite(MOTOR_LEFT_IN2, HIGH);
  digitalWrite(MOTOR_RIGHT_IN3, LOW);
  digitalWrite(MOTOR_RIGHT_IN4, HIGH);
  Serial.println("[MOTOR] Backward");
}

void turnLeft() {
  digitalWrite(MOTOR_LEFT_IN1, LOW);
  digitalWrite(MOTOR_LEFT_IN2, HIGH); // العجلة اليسرى للخلف
  digitalWrite(MOTOR_RIGHT_IN3, HIGH);
  digitalWrite(MOTOR_RIGHT_IN4, LOW);  // العجلة اليمنى للأمام
  Serial.println("[MOTOR] Turn Left");
}

void turnRight() {
  digitalWrite(MOTOR_LEFT_IN1, HIGH);
  digitalWrite(MOTOR_LEFT_IN2, LOW);   // العجلة اليسرى للأمام
  digitalWrite(MOTOR_RIGHT_IN3, LOW);
  digitalWrite(MOTOR_RIGHT_IN4, HIGH); // العجلة اليمنى للخلف
  Serial.println("[MOTOR] Turn Right");
}

// =========================
// Utility
// =========================

const char* moodToString(Mood mood) {
  switch (mood) {
    case MOOD_IDLE: return "idle";
    case MOOD_HAPPY: return "happy";
    case MOOD_BIG_HAPPY: return "big_happy";
    case MOOD_CURIOUS: return "curious";
    case MOOD_THINK: return "think";
    case MOOD_TALK: return "talk";
    case MOOD_ALERT: return "alert";
    case MOOD_SURPRISED: return "surprised";
    case MOOD_SLEEPY: return "sleepy";
    case MOOD_BORED: return "bored";
    case MOOD_YAWN: return "yawn";
    case MOOD_SAD: return "sad";
    case MOOD_ANGRY: return "angry";
    case MOOD_SMIRK: return "smirk";
    case MOOD_CUTE: return "cute";
    case MOOD_EXCITED: return "excited";
    case MOOD_SHY: return "shy";
    case MOOD_CONFUSED: return "confused";
    case MOOD_EMPATHETIC: return "empathetic";
    case MOOD_LOVE: return "love";
    case MOOD_CRY: return "cry";
    case MOOD_WINK: return "wink";
    case MOOD_KISS: return "kiss";
    case MOOD_HEART_EYES: return "heart_eyes";
    case MOOD_CALM: return "calm";
    default: return "idle";
  }
}

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
  if (!ENABLE_BUZZER) {
    Serial.println("Buzzer disabled in config");
    return;
  }

  buzzerReady = ledcAttach(BUZZER_PIN, BUZZER_BASE_FREQ, BUZZER_RESOLUTION);

  Serial.print("BUZZER_PIN = ");
  Serial.println(BUZZER_PIN);
  Serial.print("buzzerReady = ");
  Serial.println(buzzerReady ? "true" : "false");

  if (buzzerReady) {
    ledcWriteTone(BUZZER_PIN, 0);
    ledcWrite(BUZZER_PIN, 0);
  }
}
void stopBuzzer() {
  if (!ENABLE_BUZZER) return;

  ledcWriteTone(BUZZER_PIN, 0);
  ledcWrite(BUZZER_PIN, 0);
  ledcDetach(BUZZER_PIN);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  buzzerReady = false;
}

void playToneMs(int freq, int dur) {
  if (!ENABLE_BUZZER) return;

  if (!buzzerReady) {
    buzzerReady = ledcAttach(BUZZER_PIN, BUZZER_BASE_FREQ, BUZZER_RESOLUTION);
    if (!buzzerReady) return;
  }

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
  if (!ENABLE_BUZZER) return;

  for (int i = 0; i < len; i++) {
    playToneMs(notes[i], durs[i]);
  }

  stopBuzzer();
}

// --- مكتبة النغمات الجديدة المختارة ---

// Based on #2: Boot - Futuristic
void melodyBoot() {
  const int n[] = {880, 1047, 1319, 1760};
  const int d[] = {70, 70, 70, 200};
  playMelody(n, d, 4);
}

// Based on #6: Success - Item Get
void melodyHappy() {
  const int n[] = {880, 988, 1109, 1319};
  const int d[] = {80, 80, 80, 180};
  playMelody(n, d, 4);
}

// Based on #8: Curious - Hmm?
void melodyCurious() {
  const int n[] = {880, 1109};
  const int d[] = {120, 250};
  playMelody(n, d, 2);
}

// Based on #13: Sad - Slow
void melodySad() {
  const int n[] = {880, 784, 659};
  const int d[] = {250, 200, 400};
  playMelody(n, d, 3);
}

// Based on #11: Alert - Ping (أفضل للتنبيه من #8)
void melodyAlert() {
  const int n[] = {2093, 0, 2093};
  const int d[] = {150, 80, 150};
  playMelody(n, d, 3);
}

// Based on #15: Error - Fail
void melodyError() {
  const int n[] = {523, 494, 466, 440};
  const int d[] = {100, 100, 100, 200};
  playMelody(n, d, 4);
}

// ملاحظة: لم نضف نغمات Shutdown, Love, Urgent Alert بعد لأن ليس لها استدعاء في بايثون حالياً.
// يمكننا إضافتها بسهولة لاحقاً عند الحاجة.
void buzzerSelfTest() {
  Serial.println("BUZZER SELF TEST START");

  // test 1: direct HIGH/LOW -> يفيد إذا كان البازر active
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(400);
  digitalWrite(BUZZER_PIN, LOW);
  delay(300);

  // test 2: tone -> يفيد إذا كان البازر passive
  if (ENABLE_BUZZER && buzzerReady) {
    ledcWriteTone(BUZZER_PIN, 1500);
    delay(400);
    ledcWriteTone(BUZZER_PIN, 0);
    delay(300);

    ledcWriteTone(BUZZER_PIN, 2200);
    delay(400);
    ledcWriteTone(BUZZER_PIN, 0);
    delay(300);
  }

  Serial.print("ENABLE_BUZZER = ");
  Serial.println(ENABLE_BUZZER ? "true" : "false");
  Serial.print("buzzerReady = ");
  Serial.println(buzzerReady ? "true" : "false");
  Serial.println("BUZZER SELF TEST END");
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
  moodState = moodToString(currentMood);

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
    blinkUntilMs = now + 80;
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
      moodState = "idle";
    }

    if (now - lastIdleActionMs > nextIdleActionDelayMs) {
      lastIdleActionMs = now;
      runIdleAction();
    }
  }
  if (currentMood == MOOD_SLEEPY) {
    zzz_phase = (zzz_phase + 1) % 80;
  } else {
    zzz_phase = 0;
  }
  if (currentMood == MOOD_EMPATHETIC) {
    tear_wobble = (millis() / 150) % 2 == 0 ? 1 : -1;
  } else {
    tear_wobble = 0;
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
// Cloud Callbacks
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
  autonomousMode = false;
  statusText = "mood:" + moodState;

  lastIdleActionMs = millis(); // أعد ضبط مؤقت الخمول الآن
  nextIdleActionDelayMs = 30000 + random(0, 30000); 

  drawFace();
}
void onServoAngleChange() {
  if (servoAngle < SERVO_SAFE_MIN_ANGLE) servoAngle = SERVO_SAFE_MIN_ANGLE;
  if (servoAngle > SERVO_SAFE_MAX_ANGLE) servoAngle = SERVO_SAFE_MAX_ANGLE;

  targetNeckAngle = servoAngle;
  autonomousIdle = false;
  autonomousMode = false;
  statusText = "servo";

  lastIdleActionMs = millis(); // أعد ضبط مؤقت الخمول الآن
  nextIdleActionDelayMs = 30000 + random(0, 30000); 
}

// هذه هي الدالة التي تستجيب لأوامر الحركة من Cloud
// تم تفعيلها وربطها بالدوال الفعالة
void onBaseActionChange() {
  statusText = "base:" + baseAction;
  Serial.print("[CLOUD] Base Action: ");
  Serial.println(baseAction);
  
  if (baseAction == "forward") {
    moveForward();
  } else if (baseAction == "backward") {
    moveBackward();
  } else if (baseAction == "left") {
    turnLeft();
  } else if (baseAction == "right") {
    turnRight();
  } else if (baseAction == "stop") {
    stopMotors();
  }
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
  else if (eventName == "error") melodyError();
  else if (eventName == "stop") stopBuzzer();
}

void onBuzzerCommandChange() {
  Serial.print("Buzzer command received: ");
  Serial.println(buzzerCommand);

  // نخزن الأمر ونرفع علماً لتشغيله في الـ loop الرئيسي
  // هذا يمنع تجميد الاتصال بالـ Cloud
  pendingBuzzerEvent = buzzerCommand;
  pendingBuzzerPlay = true;
  
  // نضبط مؤقتاً لإيقاف البازر إذا استمر بالخطأ
  cloudBuzzerActive = true;
  cloudBuzzerUntilMs = millis() + 2000; 
  statusText = "buzzer:" + buzzerCommand;

  // إعادة تعيين المتغير السحابي فوراً
  buzzerCommand = "none"; 
}

 // =========================
//  Distance Sensor
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
  tft.setRotation(0);
  clearFace();

  setupBuzzer();
  stopBuzzer();

  // --- تهيئة بنات المواتير ---
  // تم تفعيل هذا الجزء
  pinMode(MOTOR_LEFT_IN1, OUTPUT);
  pinMode(MOTOR_LEFT_IN2, OUTPUT);
  pinMode(MOTOR_RIGHT_IN3, OUTPUT);
  pinMode(MOTOR_RIGHT_IN4, OUTPUT);
  stopMotors(); // التأكد من أن المواتير متوقفة عند البدء

  initProperties();
  ArduinoCloud.begin(ArduinoIoTPreferredConnection);
  
  // تهيئة القيم الافتراضية للمتغيرات السحابية
  moodState = "idle";
  buzzerCommand = "none";
  baseAction = "stop"; // تهيئة متغير الحركة
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

  cloudWarmupUntilMs = millis() + 3000;
  startupSequenceDone = false;

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

  // معالجة نغمات البازر المجدولة
  if (pendingBuzzerPlay) {
    pendingBuzzerPlay = false; // نلغي العلم
    playEventSound(pendingBuzzerEvent);
    pendingBuzzerEvent = ""; // نفرغ اسم الحدث
  }

  // تسلسل بدء التشغيل
  if (!startupSequenceDone && now >= cloudWarmupUntilMs) {
    startupSequence();
    startupSequenceDone = true;
    currentMood = MOOD_IDLE;
    moodState = "idle";
    fxStartMs = millis();
    drawFace();
  }

  // تحديث تحريك الوجه
  if (now - lastAnimMs > FACE_ANIM_INTERVAL_MS) {
    lastAnimMs = now;
    updateFaceAnimation();
  }

  // معالجة حالة الكلام (الحركة والرقبة)
  if (currentMood == MOOD_TALK) {
    maybeTalkTone();
    applyMoodMotion(MOOD_TALK);
  }

  // إيقاف البازر السحابي بعد انتهاء الوقت
  if (cloudBuzzerActive && now >= cloudBuzzerUntilMs) {
    stopBuzzer();
    cloudBuzzerActive = false;
  }

  // تحديث حركة السيرفو (الرقبة)
  updateServoMotion();

  // قراءة مستشعر المسافة وتحديث القيمة السحابية
  static unsigned long lastDistanceReadMs = 0;
  if (now - lastDistanceReadMs >= DISTANCE_READ_INTERVAL_MS) {
    lastDistanceReadMs = now;

    float d = readDistanceCm();
    if (d > 0) {
      distanceCm = d; // تحديث المتغير السحابي
    }
  }

}