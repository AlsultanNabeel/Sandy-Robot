#ifndef SANDY_FACES_H
#define SANDY_FACES_H


// تنفيذ كل التعديلات الفنية المطلوبة لشخصية أنمي معبرة وحيوية.

// --- الألوان ---
#define FACE_BG_INNER      0x0000
#define FACE_WHITE         0xFFFF
#define FACE_SOFT          0xAD55
#define FACE_BLUSH         0xD1B2
#define FACE_LIP           0xF206
#define FACE_LIP_SOFT      0xB26A
#define FACE_MOUTH_NEUTRAL 0x4228
#define FACE_MOUTH_EDGE    0x738E
#define FACE_MOUTH_INNER   0x18C3
#define FACE_HEART         0xF800
#define FACE_TEAR          0x5DFF
#define FACE_IRIS          0x03FF
#define FACE_IRIS_2        0x87FF
#define FACE_PUPIL         0x0000
#define FACE_NOSE          0x5ACB  

// --- متغيرات الحالة العامة ---
static TFT_eSprite faceSprite = TFT_eSprite(&tft);
static bool faceSpriteReady = false;
static bool faceShellReady = false;
static bool faceRendererReady = false;
static Mood lastRenderedMood = MOOD_IDLE;
static unsigned long lastFacePushMs = 0;

// --- متغيرات خاصة بالحركة (Animation) ---
static int zzz_phase = 0;
static int tear_wobble = 0;

// --- دوال مساعدة ---
static inline void ensureFaceSprite() {
  if (faceSpriteReady) return;
  faceSprite.setColorDepth(16);
  faceSprite.createSprite(220, 220);
  faceSprite.setSwapBytes(false);
  faceSpriteReady = true;
}

static inline void drawFaceShellStatic() {
  tft.fillScreen(FACE_BG_INNER);
  tft.drawRoundRect(0, 0, 240, 240, 36, 0x2124);
  faceShellReady = true;
}

template <typename Canvas>
static inline void fillInnerPanel(Canvas &c) {
  c.fillRoundRect(0, 0, 220, 220, 24, FACE_BG_INNER);
}

static inline void clearFace() {
  faceShellReady = false;
  drawFaceShellStatic();
  ensureFaceSprite();
  fillInnerPanel(faceSprite);
}

// --- دوال الرسم المحدثة ---

template <typename Canvas>
static inline void drawNoseSoft(Canvas &c, int cx = 110, int cy = 130) {
  c.drawLine(cx, cy - 12, cx - 3, cy + 3, FACE_NOSE);
  c.drawLine(cx, cy - 12, cx + 3, cy + 3, FACE_NOSE);
  c.drawLine(cx - 3, cy + 3, cx - 8, cy + 8, FACE_NOSE);
  c.drawLine(cx + 3, cy + 3, cx + 8, cy + 8, FACE_NOSE);
}

template <typename Canvas>
static inline void drawEyeCore(Canvas &c, int cx, int cy, int rx, int ry, int pupilX, int pupilY, bool blink, int openness, bool heart_small, bool heart_big) {
  int ex = cx - rx;
  int ey = cy - ry;
  int ew = rx * 2;
  int eh = ry * 2;
  int rr = max(12, ry - 2);

  if (blink) {
    c.fillRoundRect(ex - 3, ey - 2, ew + 6, eh + 6, rr, FACE_BG_INNER);
    c.drawWideLine(ex + 8, cy, ex + ew - 8, cy, 3, FACE_WHITE, FACE_BG_INNER);
    return;
  }

  c.fillRoundRect(ex, ey, ew, eh, rr, FACE_WHITE);
  c.drawRoundRect(ex, ey, ew, eh, rr, FACE_SOFT);

  int irisR = max(10, rx - 6);
  int px = cx + pupilX;
  int py = cy + pupilY;
  c.fillCircle(px, py, irisR, FACE_IRIS);
  c.fillCircle(px, py + 1, irisR - 4, FACE_IRIS_2);
  c.fillCircle(px, py + 1, irisR / 2, FACE_PUPIL);
  c.fillCircle(px - irisR / 3, py - irisR / 3, max(2, irisR / 3), FACE_WHITE);

  if (heart_small) c.fillCircle(px, py, 4, FACE_HEART);
  if (heart_big) c.fillCircle(px, py, 7, FACE_HEART);

  if (openness < 100) {
    int coverH = (ry * 2 * (100 - openness)) / 100;
    c.fillRoundRect(ex - 2, ey - 2, ew + 4, coverH + 2, rr, FACE_BG_INNER);
  }
}

template <typename Canvas>
static inline void drawWinkEye(Canvas &c, int cx, int cy) {
    c.drawWideLine(cx - 20, cy - 3, cx + 20, cy - 3, 3, FACE_WHITE, FACE_BG_INNER);
    c.drawWideLine(cx - 20, cy + 3, cx + 20, cy + 3, 3, FACE_WHITE, FACE_BG_INNER);
    c.drawPixel(cx - 15, cy, FACE_WHITE);
    c.drawPixel(cx + 15, cy, FACE_WHITE);
}

template <typename Canvas>
static inline void drawFoldedArms(Canvas &c, int cx, int cy) {
    c.drawWideLine(cx - 30, cy, cx + 30, cy, 5, FACE_WHITE, FACE_BG_INNER);
    c.drawWideLine(cx - 25, cy + 8, cx + 25, cy + 8, 4, FACE_SOFT, FACE_BG_INNER);
}

template <typename Canvas>
static inline void drawMouthKiss(Canvas &c) {
  c.fillCircle(110, 180, 8, FACE_WHITE);
  c.fillCircle(110, 180, 4, FACE_BG_INNER);
}

template <typename Canvas>
static inline void drawMouthTalkFrame(Canvas &c, bool playful = false) {
  // هذا هو الكود الأصلي لرسم الفم أثناء الكلام
  int randomW = 40 + random(0, 25);
  int randomH = 18 + random(0, 12);

  switch (talkFrame % 4) {
    case 0: 
      c.fillEllipse(110, 185, randomW / 2, randomH / 2, FACE_WHITE);
      c.fillEllipse(110, 185, (randomW / 2) - 4, (randomH / 2) - 4, FACE_BG_INNER);
      break;
    case 1: 
      c.fillEllipse(110, 185, (randomW - 5) / 2, (randomH + 5) / 2, FACE_WHITE);
      c.fillEllipse(110, 185, ((randomW - 5) / 2) - 4, ((randomH + 5) / 2) - 4, FACE_BG_INNER);
      break;
    case 2: 
      c.fillEllipse(110, 185, (randomW + 5) / 2, (randomH - 3) / 2, FACE_WHITE);
      c.fillEllipse(110, 185, ((randomW + 5) / 2) - 4, ((randomH - 3) / 2) - 4, FACE_BG_INNER);
      break;
    default: 
      c.fillEllipse(110, 185, (randomW - 10) / 2, randomH / 2, FACE_WHITE);
      c.fillEllipse(110, 185, ((randomW - 10) / 2) - 4, (randomH / 2) - 4, FACE_BG_INNER);
      break;
  }
}

template <typename Canvas>
static inline void drawZzzAnimation(Canvas &c, int phase) {
    int x = 180 - (phase / 2);
    int y = 40 + (phase / 2);
    c.setTextColor(FACE_SOFT);
    c.setTextSize(2);
    c.drawString("Z", x, y);
    c.drawString("z", x + 15, y - 15);
    c.drawString("z", x + 25, y - 5);
}

template <typename Canvas>
static inline void drawTearAnimation(Canvas &c, int wobble) {
    c.fillCircle(45, 135 + wobble, 10, FACE_TEAR);
    c.fillCircle(175, 135 - wobble, 10, FACE_TEAR);
}

// --- دالة الرسم الرئيسية المحدثة بالكامل ---
template <typename Canvas>
static inline void renderMood(Canvas &c, Mood mood) {
  bool blink = millis() < blinkUntilMs;
  fillInnerPanel(c);

  // القيم الافتراضية
  int openness = 100;
  int pupilY = 0;
  bool heart_s = false, heart_b = false;

  // تحديد حالة العيون
  switch(mood) {
    case MOOD_THINK: openness = 80; break;
    case MOOD_BORED: openness = 60; break;
    case MOOD_SLEEPY: openness = 85; break;
    case MOOD_SAD: case MOOD_EMPATHETIC: case MOOD_CRY: pupilY = 8; break;
    case MOOD_LOVE: heart_s = true; break;
    case MOOD_HEART_EYES: heart_b = true; break;
    default: break;
  }
  
  // رسم العيون
  if (mood == MOOD_WINK) {
      drawEyeCore(c, 52, 90, 48, 40, eyeOffsetX, eyeOffsetY, false, 100, false, false);
      drawWinkEye(c, 168, 90);
  } else {
      drawEyeCore(c, 52, 90, 48, 40, eyeOffsetX, pupilY, blink, openness, heart_s, heart_b);
      drawEyeCore(c, 168, 90, 48, 40, eyeOffsetX, pupilY, blink, openness, heart_s, heart_b);
  }

  // رسم الأنف
  drawNoseSoft(c);

  // رسم الفم والعناصر الإضافية
  switch(mood) {
    case MOOD_IDLE:
        c.drawWideLine(90, 180, 130, 180, 4, FACE_WHITE, FACE_BG_INNER);
        break;
    case MOOD_BIG_HAPPY:
        c.fillRoundRect(70, 170, 80, 25, 10, FACE_WHITE);
        c.fillRect(70, 170, 80, 12, FACE_BG_INNER);
        break;
    case MOOD_SMIRK:
        c.drawWideLine(85, 182, 135, 178, 4, FACE_WHITE, FACE_BG_INNER);
        break;
    case MOOD_CUTE:
    case MOOD_HAPPY:
        c.fillRoundRect(80, 170, 60, 20, 10, FACE_WHITE);
        c.fillTriangle(78, 180, 142, 180, 110, 165, FACE_BG_INNER);
        break;
    case MOOD_EXCITED:
        c.fillRoundRect(75, 168, 70, 25, 12, FACE_WHITE);
        c.fillTriangle(73, 178, 147, 178, 110, 160, FACE_BG_INNER);
        break;
    case MOOD_SHY:
        c.drawWideLine(95, 180, 125, 180, 4, FACE_WHITE, FACE_BG_INNER);
        c.drawWideLine(30, 120, 60, 125, 8, FACE_BLUSH, FACE_BG_INNER);
        c.drawWideLine(160, 125, 190, 120, 8, FACE_BLUSH, FACE_BG_INNER);
        break;
    case MOOD_KISS:
        drawMouthKiss(c);
        break;
    case MOOD_LOVE:
    case MOOD_HEART_EYES:
        c.drawWideLine(90, 180, 130, 180, 4, FACE_WHITE, FACE_BG_INNER);
        break;
    case MOOD_CALM:
        c.drawWideLine(90, 180, 130, 180, 4, FACE_WHITE, FACE_BG_INNER);
        drawFoldedArms(c, 110, 205);
        break;
    case MOOD_YAWN:
        c.fillEllipse(110, 185, 35, 25, FACE_WHITE);
        c.fillEllipse(110, 185, 31, 21, FACE_BG_INNER);
        break;
    case MOOD_CONFUSED:
        c.drawWideLine(90, 182, 105, 178, 4, FACE_WHITE, FACE_BG_INNER);
        c.drawWideLine(105, 178, 120, 182, 4, FACE_WHITE, FACE_BG_INNER);
        break;
    case MOOD_ANGRY:
        c.drawWideLine(85, 185, 135, 185, 5, FACE_WHITE, FACE_BG_INNER);
        c.drawWideLine(85, 185, 95, 178, 5, FACE_WHITE, FACE_BG_INNER);
        c.drawWideLine(135, 185, 125, 178, 5, FACE_WHITE, FACE_BG_INNER);
        break;
    case MOOD_EMPATHETIC:
        drawTearAnimation(c, tear_wobble);
        // fall through to sad mouth
    case MOOD_SAD:
    case MOOD_CRY:
        c.fillRoundRect(80, 180, 60, 15, 8, FACE_WHITE);
        c.fillRect(80, 188, 60, 8, FACE_BG_INNER);
        break;
    case MOOD_TALK: // <<<<< تمت إعادة هذه الحالة
        drawMouthTalkFrame(c);
        break;
    default: // ALERT, CURIOUS, etc. will now show a neutral mouth
        c.drawWideLine(90, 180, 130, 180, 4, FACE_WHITE, FACE_BG_INNER);
        break;
  }

  // رسم الحركات الإضافية
  if (mood == MOOD_SLEEPY) drawZzzAnimation(c, zzz_phase);
}

// --- دوال التحكم ---
static inline bool faceNeedsRedraw() {
  return (millis() - lastFacePushMs > 25);
}

static inline void markFaceRendered() {
  lastRenderedMood = currentMood;
  lastFacePushMs = millis();
}

static inline void drawFace() {
  ensureFaceSprite();
  if (!faceShellReady) drawFaceShellStatic();
  if (!faceNeedsRedraw()) return;
  renderMood(faceSprite, currentMood);
  faceSprite.pushSprite(10, 10);
  faceRendererReady = true;
  markFaceRendered();
}

#endif