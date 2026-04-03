#ifndef SANDY_FACES_H
#define SANDY_FACES_H

// Sandy face renderer v5 - Nabil "Ultra-Clean, Giant Face" Edition
// - background is absolute black
// - removed all interior frame clutter
// - single, very thin, soft outer frame at true display edge
// - MAXIMIZED eye, mouth, and nose size to fill the screen
// - retained all emotion rendering logic, just on a larger scale

// --- ألوان نبيل الجديدة (خلفية سوداء مطلقة لإبراز الملامح) ---
#define FACE_BG_OUTER      0x0000  // أسود مطلق خلفي (قاعدة عميقة جداً)
#define FACE_BG_PANEL      0x0000  // أسود مطلق لوحة (نفس الخلفية لتختفي الإطارات)
#define FACE_BG_INNER      0x0000  // أسود مطلق داخلي (لسواد تام يبرز الملامح)
#define FACE_BORDER        0x0841  // ظل عميق جداً (كحدود مخفية للوجه عند الأطراف جداً)
#define FACE_BORDER_SOFT   0x2124  // رمادي كربوني ناعم (كحدود خارجية ناعمة على طرف الشاشة)
#define FACE_WHITE         0xFFFF  // أبيض نقي (لتبرز العيون بقوة)
#define FACE_SOFT          0xAD55  // إضاءة ناعمة بلمسة سماوية
#define FACE_SHADOW        0x0000  // (اختفى الظل على الخلفية السوداء)
#define FACE_BLUSH         0xD1B2  // وردي خافت طبيعي (تم تكبير حبات الورد)
#define FACE_LIP           0xF206  // أحمر حيوي مشرق (للكلام المفعم بالحياة - التم صار عملاق)
#define FACE_LIP_SOFT      0xB26A  // وردي مغبر (للحالات الهادئة)
#define FACE_MOUTH_NEUTRAL 0x4228  // فم بلون كاكاو غامق
#define FACE_MOUTH_EDGE    0x738E  // تحديد ناعم للفم
#define FACE_MOUTH_INNER   0x18C3  // عمق الفم العملاق (أسود مزرق)
#define FACE_HEART         0xF800  // أحمر نقي صارخ❤️ (لعيون الحب العملاقة)
#define FACE_TEAR          0x5DFF  // أزرق كريستالي لامع💧 (لدموع عملاقة)
#define FACE_GOLD          0xFEC0  // ذهبي مشرق🌟 (لمسات الفخامة)
#define FACE_NOSE          0x5ACB  // أنف بلمسة رمادية زرقاء (صار أكبر وواضح)
#define FACE_IRIS          0x03FF  // أزرق كهربائي (Iris) بيخطف العين (أقوى تباين)
#define FACE_IRIS_2        0x87FF  // مركز القزحية مضيء جداً
#define FACE_PUPIL         0x0000  // أسود مطلق للسمت
#define FACE_HAND          0xE73C  // لون يد دافئ
#define FACE_HAND_SHADOW   0xB575  // ظل يد ناعم

static inline int faceClamp(int v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static TFT_eSprite faceSprite = TFT_eSprite(&tft);
static bool faceSpriteReady = false;
static bool faceShellReady = false;
static bool faceRendererReady = false;
static Mood lastRenderedMood = MOOD_IDLE;
static bool lastRenderedBlink = false;
static int lastRenderedEyeX = 999;
static int lastRenderedEyeY = 999;
static uint8_t lastRenderedTalkFrame = 255;
static int lastRenderedOverlayPhase = -999;
static unsigned long lastFacePushMs = 0;

static inline void ensureFaceSprite() {
  if (faceSpriteReady) return;
  faceSprite.setColorDepth(16);
  // تكبير الرشاش الداخلي ليغطي مساحة الوجه الحقيقية، تم تقليل الهامش ليكون 10 بيكسل فقط عن الحافة
  faceSprite.createSprite(220, 220); 
  faceSprite.setSwapBytes(false);
  faceSpriteReady = true;
}

static inline void drawFaceShellStatic() {
  // 1. ملء الشاشة بالأسود المطلق
  tft.fillScreen(FACE_BG_OUTER);
  
  // 2. رسم حد واحد فقط، خفيف، على الأطراف القصوى للشاشة، بالكاد يظهر
  tft.drawRoundRect(0, 0, 240, 240, 36, FACE_BORDER_SOFT);
  
  faceShellReady = true;
}

template <typename Canvas>
static inline void fillInnerPanel(Canvas &c) {
  c.fillRoundRect(0, 0, 220, 220, 24, FACE_BG_INNER);
}

static inline void faceClearPanel(bool forceFull = false) {
  if (!faceShellReady || forceFull) drawFaceShellStatic();
  ensureFaceSprite();
  fillInnerPanel(faceSprite);
  faceRendererReady = true;
}

static inline void clearFace() {
  faceShellReady = false;
  drawFaceShellStatic();
  ensureFaceSprite();
  fillInnerPanel(faceSprite);
}

template <typename Canvas>
static inline void drawPanelGlow(Canvas &c) {
  // (تم تعطيل تأثيرات الـ Glow ليكون أنظف على الخلفية السوداء)
}

// --- تكبير أحجام الملامح --
template <typename Canvas>
static inline void drawHeartTiny(Canvas &c, int x, int y, int size, uint16_t color) {
  int realSize = size * 2; 
  int r = max(4, realSize / 3);
  c.fillCircle(x - r, y, r, color);
  c.fillCircle(x + r, y, r, color);
  c.fillTriangle(x - realSize, y + 2, x + realSize, y + 2, x, y + realSize + r + 2, color);
}

template <typename Canvas>
static inline void drawDroplet(Canvas &c, int x, int y, int size, uint16_t color) {
  int realSize = size * 2;
  int r = max(4, realSize / 2);
  c.fillCircle(x, y, r, color);
  c.fillTriangle(x, y - realSize, x - r, y - 2, x + r, y - 2, color);
}

template <typename Canvas>
static inline void drawSpark(Canvas &c, int x, int y, int s, uint16_t color) {
  int realS = s * 2;
  c.drawLine(x, y - realS, x, y + realS, color);
  c.drawLine(x - realS, y, x + realS, y, color);
}

template <typename Canvas>
static inline void drawNoseSoft(Canvas &c, int cx = 110, int cy = 130, bool warm = false) {
  uint16_t c1 = warm ? FACE_LIP : FACE_NOSE;
  c.drawLine(cx, cy - 12, cx - 3, cy + 3, c1);
  c.drawLine(cx, cy - 12, cx + 3, cy + 3, c1);
  c.drawLine(cx - 3, cy + 3, cx - 8, cy + 8, c1);
  c.drawLine(cx + 3, cy + 3, cx + 8, cy + 8, c1);
  c.drawPixel(cx - 6, cy + 6, c1);
  c.drawPixel(cx + 6, cy + 6, c1);
}

template <typename Canvas>
static inline void drawBlushSoft(Canvas &c, int y = 160) {
  c.fillCircle(24, y, 18, FACE_BLUSH);
  c.fillCircle(196, y, 18, FACE_BLUSH);
  c.drawCircle(24, y, 18, FACE_SOFT);
  c.drawCircle(196, y, 18, FACE_SOFT);
}

template <typename Canvas>
static inline void drawCheekDots(Canvas &c) {
  c.fillCircle(18, 162, 4, FACE_BLUSH);
  c.fillCircle(30, 165, 4, FACE_BLUSH);
  c.fillCircle(202, 162, 4, FACE_BLUSH);
  c.fillCircle(190, 165, 4, FACE_BLUSH);
}

template <typename Canvas>
static inline void drawBrowLine(Canvas &c, int x1, int y1, int x2, int y2, uint16_t color = FACE_WHITE) {
  c.drawLine(x1, y1, x2, y2, color);
  c.drawLine(x1, y1 + 1, x2, y2 + 1, color);
  c.drawLine(x1, y1 + 2, x2, y2 + 2, color);
}

template <typename Canvas> static inline void drawBrowsNeutral(Canvas &c)     { drawBrowLine(c, 10, 48, 62, 46); drawBrowLine(c, 158, 46, 210, 48); }
template <typename Canvas> static inline void drawBrowsHappy(Canvas &c)       { drawBrowLine(c, 12, 49, 62, 40); drawBrowLine(c, 158, 40, 208, 49); }
template <typename Canvas> static inline void drawBrowsBigHappy(Canvas &c)    { drawBrowLine(c, 12, 47, 62, 37); drawBrowLine(c, 158, 37, 208, 47); }
template <typename Canvas> static inline void drawBrowsCurious(Canvas &c)     { drawBrowLine(c, 10, 50, 62, 38); drawBrowLine(c, 158, 44, 208, 44); }
template <typename Canvas> static inline void drawBrowsThink(Canvas &c)       { drawBrowLine(c, 12, 50, 62, 41); drawBrowLine(c, 158, 42, 208, 47); }
template <typename Canvas> static inline void drawBrowsSurprised(Canvas &c)   { drawBrowLine(c, 14, 35, 62, 31); drawBrowLine(c, 158, 31, 206, 35); }
template <typename Canvas> static inline void drawBrowsSleepy(Canvas &c)      { drawBrowLine(c, 10, 58, 62, 61); drawBrowLine(c, 158, 61, 210, 58); }
template <typename Canvas> static inline void drawBrowsShy(Canvas &c)         { drawBrowLine(c, 12, 48, 62, 43); drawBrowLine(c, 158, 43, 208, 48); }
template <typename Canvas> static inline void drawBrowsSadInnocent(Canvas &c) { drawBrowLine(c, 14, 43, 60, 50); drawBrowLine(c, 160, 50, 206, 43); }
template <typename Canvas> static inline void drawBrowsEmpathetic(Canvas &c)  { drawBrowLine(c, 14, 43, 60, 49); drawBrowLine(c, 160, 49, 206, 43); }
template <typename Canvas> static inline void drawBrowsAngry(Canvas &c)       { drawBrowLine(c, 10, 56, 62, 38); drawBrowLine(c, 158, 38, 210, 56); }
template <typename Canvas> static inline void drawBrowsCalm(Canvas &c)        { drawBrowLine(c, 12, 46, 62, 45); drawBrowLine(c, 158, 45, 208, 46); }

template <typename Canvas>
static inline void drawEyelidCover(Canvas &c, int cx, int cy, int rx, int ry, int coverPct, bool sleepy = false) {
  int ex = cx - rx;
  int ew = rx * 2;
  int top = cy - ry - 2;
  int coverH = faceClamp((ry * 2 * coverPct) / 100, 0, ry * 2 + 4);
  c.fillRoundRect(ex - 3, top - 2, ew + 6, coverH + 4, max(12, ry), FACE_BG_INNER);
  int lidY = top + coverH - 1;
  c.drawLine(ex + 6, lidY, ex + ew - 6, lidY - (sleepy ? 0 : 1), FACE_WHITE);
  c.drawLine(ex + 4, lidY + 1, ex + ew - 4, lidY, FACE_WHITE);
  c.drawLine(ex + 10, lidY + 2, ex + ew - 10, lidY + 1, FACE_SOFT);
}

template <typename Canvas>
static inline void drawClosedEyeLid(Canvas &c, int cx, int cy, int rx, int ry, bool wink = false) {
  int ex = cx - rx;
  int ew = rx * 2;
  int top = cy - ry - 2;
  c.fillRoundRect(ex - 3, top - 2, ew + 6, ry * 2 + 6, max(12, ry), FACE_BG_INNER);
  int lidY = cy + (wink ? -2 : 1);
  c.fillTriangle(ex + 4, lidY - 8, ex + ew - 4, lidY - 4, cx, lidY + 4, FACE_BG_INNER);
  c.drawLine(ex + 8, lidY, ex + ew - 8, lidY - (wink ? 2 : 1), FACE_WHITE);
  c.drawLine(ex + 6, lidY + 1, ex + ew - 6, lidY, FACE_WHITE);
  c.drawLine(ex + 12, lidY + 2, ex + ew - 12, lidY + 1, FACE_SOFT);
  if (wink) {
    c.drawLine(ex + 18, lidY + 5, ex + ew - 18, lidY + 3, FACE_BLUSH);
  }
}

template <typename Canvas>
static inline void drawEyeCore(Canvas &c, int cx, int cy, int rx, int ry, int pupilX, int pupilY, bool blink = false, int openness = 100, bool lowerLid = false, bool sleepy = false, bool heartEye = false) {
  int ex = cx - rx;
  int ey = cy - ry;
  int ew = rx * 2;
  int eh = ry * 2;
  int rr = max(12, ry - 2);

  c.fillRoundRect(ex, ey, ew, eh, rr, FACE_WHITE);
  c.drawRoundRect(ex, ey, ew, eh, rr, FACE_SOFT);
  c.drawRoundRect(ex - 1, ey - 1, ew + 2, eh + 2, rr + 1, FACE_SOFT);

  c.drawLine(ex + 2, ey + 1, ex + ew - 2, ey + 1, FACE_PUPIL);
  c.drawLine(ex + 1, ey + 2, ex + ew - 1, ey + 2, FACE_PUPIL);
  c.drawLine(ex + 3, ey + 3, ex + ew - 3, ey + 3, FACE_PUPIL);
  c.drawLine(ex + 5, ey + 4, ex + ew - 5, ey + 4, FACE_PUPIL);
  c.drawLine(ex + 7, ey + 5, ex + ew - 7, ey + 5, FACE_PUPIL);

  if (heartEye) {
    drawHeartTiny(c, cx, cy + 2, 14, FACE_HEART);
  } else {
    int irisR = max(10, rx - 6);
    int irisR2 = max(6, irisR - 5);
    int pupilR = max(4, irisR / 2);
    int px = faceClamp(cx + pupilX, cx - rx / 2 + 5, cx + rx / 2 - 5);
    int py = faceClamp(cy + pupilY, cy - ry / 4 + 2, cy + ry / 4 + 2);
    c.fillCircle(px, py, irisR, FACE_IRIS);
    c.fillCircle(px, py + 1, irisR2, FACE_IRIS_2);
    c.fillCircle(px, py + 1, pupilR, FACE_PUPIL);
    c.fillCircle(px - irisR / 3, py - irisR / 3, max(2, irisR / 3), FACE_WHITE);
    c.fillCircle(px - irisR / 2, py + irisR / 3, max(1, irisR / 6), FACE_WHITE);
  }

  if (lowerLid) {
    c.drawLine(ex + 12, ey + eh - 4, ex + ew - 12, ey + eh - 4, FACE_BLUSH);
    c.drawLine(ex + 18, ey + eh - 3, ex + ew - 18, ey + eh - 3, FACE_SOFT);
  }

  if (blink) {
    drawClosedEyeLid(c, cx, cy, rx, ry, false);
    return;
  }

  if (openness < 98 || sleepy) {
    int coverPct = sleepy ? 72 : faceClamp((100 - openness) * 2, 0, 86);
    if (coverPct > 0) drawEyelidCover(c, cx, cy, rx, ry, coverPct, sleepy);
  }
}

template <typename Canvas>
static inline void drawEyesPair(Canvas &c, int leftPX, int leftPY, int rightPX, int rightPY, bool blink = false, int openness = 100, bool lowerLid = false, bool sleepy = false, bool heartEyes = false) {
  drawEyeCore(c, 52, 90, 48, 40, leftPX, leftPY, blink, openness, lowerLid, sleepy, heartEyes);
  drawEyeCore(c, 168, 90, 48, 40, rightPX, rightPY, blink, openness, lowerLid, sleepy, heartEyes);
}

template <typename Canvas>
static inline void drawOneEyeWinkPair(Canvas &c, int leftPX, int leftPY, int rightPX, int rightPY, bool leftWink) {
  if (leftWink) {
    drawClosedEyeLid(c, 52, 90, 48, 40, true);
    drawEyeCore(c, 168, 90, 48, 40, rightPX, rightPY, false, 100, false, false, false);
  } else {
    drawEyeCore(c, 52, 90, 48, 40, leftPX, leftPY, false, 100, false, false, false);
    drawClosedEyeLid(c, 168, 90, 48, 40, true);
  }
}

// --- تعديل التم ليكون حقيقي، بسيط، وديناميكي ---

template <typename Canvas>
static inline void drawMouthRealistic(Canvas &c, int cx, int cy, int w, int h, uint16_t lipColor, bool showTeeth = false, bool showTongue = false) {
  int halfW = w / 2;
  
  // حالة الفم المغلق
  if (h <= 6) {
    c.fillRoundRect(cx - halfW, cy - 3, w, 6, 3, lipColor); // الشفاه مدمجة
    c.drawLine(cx - halfW + 2, cy, cx + halfW - 2, cy, FACE_MOUTH_INNER); // خط المنتصف
    return;
  }

  // 1. عمق الفم (الداخل المظلم)
  c.fillRoundRect(cx - halfW, cy - h/2, w, h, max(4, h/4), FACE_MOUTH_INNER);

  // 2. الأسنان (في الجزء العلوي من الفم المفتوح)
  if (showTeeth) {
    int teethH = max(3, h / 4);
    c.fillRoundRect(cx - halfW + 4, cy - h/2 + 1, w - 8, teethH, 2, FACE_WHITE);
    c.drawLine(cx, cy - h/2 + 1, cx, cy - h/2 + teethH, FACE_SOFT); // خط تفصيل الأسنان
  }

  // 3. اللسان (في الجزء السفلي من الفم المفتوح)
  if (showTongue) {
    int tongueW = w - 12;
    int tongueH = max(4, h / 2);
    int tongueY = cy + h/2 - tongueH;
    c.fillRoundRect(cx - tongueW/2, tongueY, tongueW, tongueH, tongueH/2, FACE_BLUSH);
    c.drawLine(cx, tongueY + 2, cx, cy + h/2 - 1, FACE_LIP_SOFT); // خط اللسان
  }

  // 4. الشفة العليا (مستطيل دائري مع تحديد قوس كيوبيد)
  c.fillRoundRect(cx - halfW, cy - h/2 - 4, w, 6, 3, lipColor);
  c.fillCircle(cx, cy - h/2 - 5, 3, FACE_BG_INNER); // دمج لتشكيل قوس الشفة العليا

  // 5. الشفة السفلى
  c.fillRoundRect(cx - halfW + 4, cy + h/2 - 2, w - 8, 6, 3, lipColor);
}

template <typename Canvas> static inline void drawMouthClosedSoft(Canvas &c, uint16_t fill = FACE_MOUTH_NEUTRAL) { drawMouthRealistic(c, 110, 178, 44, 4, fill); }
template <typename Canvas> static inline void drawMouthSmileSoft(Canvas &c, uint16_t fill = FACE_LIP) { drawMouthRealistic(c, 110, 175, 56, 6, fill); c.drawLine(81, 173, 84, 176, fill); c.drawLine(139, 173, 136, 176, fill); }
template <typename Canvas> static inline void drawMouthSmile(Canvas &c, uint16_t fill = FACE_LIP) { drawMouthRealistic(c, 110, 173, 64, 12, fill, true, false); }
template <typename Canvas> static inline void drawMouthBigSmile(Canvas &c, uint16_t fill = FACE_LIP) { drawMouthRealistic(c, 110, 172, 72, 24, fill, true, true); }
template <typename Canvas> static inline void drawMouthSadSoft(Canvas &c, uint16_t fill = FACE_LIP_SOFT) { drawMouthRealistic(c, 110, 181, 46, 4, fill); c.drawLine(85, 184, 88, 181, fill); c.drawLine(135, 184, 132, 181, fill); }
template <typename Canvas> static inline void drawMouthEmpathetic(Canvas &c, uint16_t fill = FACE_LIP_SOFT) { drawMouthRealistic(c, 110, 179, 52, 4, fill); }
template <typename Canvas> static inline void drawMouthSmirk(Canvas &c, uint16_t fill = FACE_MOUTH_NEUTRAL) { drawMouthRealistic(c, 108, 176, 42, 4, fill); c.fillCircle(131, 173, 4, fill); }
template <typename Canvas> static inline void drawMouthOpen(Canvas &c, int w, int h, uint16_t lip = FACE_LIP) { drawMouthRealistic(c, 110, 172, w * 2, h * 2, lip, true, true); }

template <typename Canvas>
static inline void drawMouthTalkFrame(Canvas &c, bool playful = false) {
  // دورة الكلام: يفتح ويسكر بشكل ديناميكي وواقعي
  switch (talkFrame % 6) {
    case 0: drawMouthRealistic(c, 110, 174, 40, 4, FACE_LIP, false, false); break; // مغلق تماماً (استراحة)
    case 1: drawMouthRealistic(c, 110, 174, 46, 14, FACE_LIP, true, false); break; // فتحة متوسطة، تظهر الأسنان
    case 2: drawMouthRealistic(c, 110, 172, 50, 24, FACE_LIP, true, true); break;  // فتحة واسعة، أسنان ولسان
    case 3: drawMouthRealistic(c, 110, 174, 44, 10, FACE_LIP, false, true); break; // شبه مفتوح، يظهر اللسان
    case 4: if (playful) drawMouthRealistic(c, 110, 173, 56, 16, FACE_LIP, true, true); 
            else drawMouthRealistic(c, 110, 174, 38, 6, FACE_LIP, false, false); break; // مغلق تقريباً
    default: drawMouthRealistic(c, 110, 173, 42, 18, FACE_LIP, true, false); break; // نطق حرف العلة (O/U)
  }
}

template <typename Canvas> static inline void drawMouthTongue(Canvas &c) { drawMouthRealistic(c, 110, 174, 52, 16, FACE_LIP, false, true); c.fillRoundRect(102, 180, 16, 12, 6, FACE_BLUSH); }
template <typename Canvas> static inline void drawMouthYawn(Canvas &c) { drawMouthRealistic(c, 110, 172, 40, 36, FACE_LIP_SOFT, false, true); }
template <typename Canvas> static inline void drawMouthKiss(Canvas &c) { c.fillCircle(110, 174, 8, FACE_LIP); c.fillCircle(110, 174, 3, FACE_MOUTH_INNER); }

template <typename Canvas>
static inline void drawSoftHand(Canvas &c, int x, int y) {
  c.fillRoundRect(x + 2, y + 10, 34, 20, 10, FACE_HAND);
  c.drawRoundRect(x + 2, y + 10, 34, 20, 10, FACE_HAND_SHADOW);
  const int fx[4] = {x + 2, x + 11, x + 20, x + 29};
  const int fh[4] = {16, 22, 21, 15};
  const int fy[4] = {y - 6, y - 13, y - 12, y - 5};
  for (int i = 0; i < 4; ++i) {
    c.fillRoundRect(fx[i], fy[i], 8, fh[i], 4, FACE_HAND);
    c.fillCircle(fx[i] + 4, fy[i] + 2, 4, FACE_HAND);
    c.drawRoundRect(fx[i], fy[i], 8, fh[i], 4, FACE_HAND_SHADOW);
  }
  c.fillRoundRect(x - 8, y + 16, 16, 10, 5, FACE_HAND);
  c.drawRoundRect(x - 8, y + 16, 16, 10, 5, FACE_HAND_SHADOW);
}

template <typename Canvas>
static inline void drawHandYawn(Canvas &c) {
  int phase = ((int)(millis() - fxStartMs) / 110) % 6;
  int bob = (phase < 3) ? phase : (6 - phase);
  int handX = 138 - bob;
  int handY = 150 + bob * 2;
  c.fillCircle(156, 184, 18, FACE_BG_INNER);
  drawSoftHand(c, handX, handY);
}

// تم تكبير تأثيرات الأوفيرلاي (القلوب والدموع) لتناسب حجم الوجه العملاق
template <typename Canvas>
static inline void drawLoveHeartsOverlay(Canvas &c) {
  int phase = ((int)(millis() - fxStartMs) / 90) % 30;
  // تم مضاعفة أحجام القلوب وتوسيع مداها
  drawHeartTiny(c, 52, 26 - phase, 9, FACE_HEART); // من فوق العيون
  drawHeartTiny(c, 110, 18 - ((phase + 8) % 30), 10, FACE_HEART); // في الوسط
  drawHeartTiny(c, 168, 30 - ((phase + 16) % 30), 8, FACE_BLUSH); // من فوق العيون الأخرى
}

template <typename Canvas>
static inline void drawCryOverlay(Canvas &c, bool strong) {
  int phase = ((int)(millis() - fxStartMs) / 45) % 76;
  // تم تكبير الدموع وتوسيع مداها
  drawDroplet(c, 42, 130 + phase, 10, FACE_TEAR);
  drawDroplet(c, 178, 132 + ((phase + 9) % 76), 10, FACE_TEAR);
  if (strong) {
    drawDroplet(c, 52, 148 + ((phase + 16) % 60), 9, FACE_TEAR);
    drawDroplet(c, 168, 150 + ((phase + 24) % 60), 9, FACE_TEAR);
    drawDroplet(c, 40, 172 + ((phase + 6) % 42), 8, FACE_TEAR);
    drawDroplet(c, 180, 174 + ((phase + 18) % 42), 8, FACE_TEAR);
  }
}

template <typename Canvas>
static inline void drawWaterline(Canvas &c) {
  // تم جعل خط الماء تحت العيون العملاقة أكثر سمكاً
  c.drawLine(24, 132, 80, 132, FACE_TEAR);
  c.drawLine(24, 133, 80, 133, FACE_TEAR);
  c.drawLine(140, 132, 196, 132, FACE_TEAR);
  c.drawLine(140, 133, 196, 133, FACE_TEAR);
}

template <typename Canvas>
static inline void drawAlertMarks(Canvas &c) {
  // تم تكبير علامات التنبيه العملاقة على الأطراف
  drawSpark(c, 15, 30, 8, FACE_GOLD);
  drawSpark(c, 205, 30, 8, FACE_GOLD);
}

// تم تعديل cy لتكون العيون العملاقة في الأعلى وcy للتم لتكون في الأسفل
template <typename Canvas>
static inline void drawFaceBase(Canvas &c, bool blink = false, int openness = 100, bool lowerLid = false, bool sleepy = false, bool heartEyes = false, int leftPX = 0, int leftPY = 0, int rightPX = 0, int rightPY = 0) {
  fillInnerPanel(c);
  drawPanelGlow(c);
  // العيون العملاقة في الأعلى
  drawEyesPair(c, leftPX, leftPY, rightPX, rightPY, blink, openness, lowerLid, sleepy, heartEyes);

  // الأنف العملاق في الوسط
  drawNoseSoft(c, 110, 130, false);
}

template <typename Canvas>
static inline void renderMood(Canvas &c, Mood mood) {
  bool blink = millis() < blinkUntilMs;
  switch (mood) {
    case MOOD_IDLE:
      drawFaceBase(c, blink, 98, false, false, false, eyeOffsetX, eyeOffsetY, eyeOffsetX, eyeOffsetY);
      drawBrowsNeutral(c);
      drawMouthClosedSoft(c, FACE_MOUTH_NEUTRAL);
      break;
    case MOOD_CALM:
      drawFaceBase(c, blink, 94, false, false, false, eyeOffsetX, eyeOffsetY, eyeOffsetX, eyeOffsetY);
      drawBrowsCalm(c);
      drawMouthSmileSoft(c, FACE_LIP);
      break;
    case MOOD_HAPPY:
      drawFaceBase(c, blink, 98, true, false, false, eyeOffsetX, eyeOffsetY, eyeOffsetX, eyeOffsetY);
      drawBrowsHappy(c);
      drawMouthSmile(c, FACE_LIP);
      break;
    case MOOD_BIG_HAPPY:
      drawFaceBase(c, blink, 100, true, false, false, eyeOffsetX, eyeOffsetY, eyeOffsetX, eyeOffsetY);
      drawBrowsBigHappy(c);
      drawMouthBigSmile(c, FACE_LIP);
      drawBlushSoft(c);
      drawSpark(c, 15, 30, 8, FACE_GOLD); // تكبير الشرر
      drawSpark(c, 205, 30, 8, FACE_GOLD);
      break;
    case MOOD_CURIOUS:
      drawFaceBase(c, blink, 96, false, false, false, eyeOffsetX + 2, eyeOffsetY, eyeOffsetX + 4, eyeOffsetY - 1);
      drawBrowsCurious(c);
      drawMouthClosedSoft(c, FACE_MOUTH_NEUTRAL);
      break;
    case MOOD_THINK:
      drawFaceBase(c, blink, 90, false, false, false, eyeOffsetX - 2, eyeOffsetY + 1, eyeOffsetX - 1, eyeOffsetY + 1);
      drawBrowsThink(c);
      drawMouthSmirk(c, FACE_MOUTH_NEUTRAL);
      break;
    case MOOD_TALK:
      drawFaceBase(c, blink, 96, false, false, false, eyeOffsetX, eyeOffsetY, eyeOffsetX, eyeOffsetY);
      drawBrowsNeutral(c);
      drawMouthTalkFrame(c, false);
      break;
    case MOOD_ALERT:
      drawFaceBase(c, false, 100, false, false, false, 0, 0, 0, 0);
      drawBrowsAngry(c);
      drawMouthOpen(c, 24, 24, FACE_LIP_SOFT);
      drawAlertMarks(c);
      break;
    case MOOD_SURPRISED:
      drawFaceBase(c, false, 100, false, false, false, 0, 0, 0, 0);
      drawBrowsSurprised(c);
      drawMouthOpen(c, 28, 28, FACE_LIP_SOFT);
      drawAlertMarks(c);
      break;
    case MOOD_SLEEPY:
      drawFaceBase(c, true, 18, false, true, false, 0, 1, 0, 1);
      drawBrowsSleepy(c);
      drawMouthClosedSoft(c, FACE_MOUTH_NEUTRAL);
      break;
    case MOOD_BORED:
      drawFaceBase(c, blink, 62, false, true, false, -2, 1, -2, 1);
      drawBrowsSleepy(c);
      drawMouthClosedSoft(c, FACE_MOUTH_NEUTRAL);
      break;
    case MOOD_YAWN:
      drawFaceBase(c, false, 54, false, true, false, 0, 2, 0, 2);
      drawBrowsSleepy(c);
      drawMouthYawn(c);
      drawHandYawn(c);
      break;
    case MOOD_SAD:
      drawFaceBase(c, blink, 88, true, false, false, eyeOffsetX, eyeOffsetY + 3, eyeOffsetX, eyeOffsetY + 3);
      drawBrowsSadInnocent(c);
      drawMouthSadSoft(c, FACE_LIP_SOFT);
      drawWaterline(c);
      break;
    case MOOD_ANGRY:
      drawFaceBase(c, false, 84, false, false, false, eyeOffsetX, eyeOffsetY, eyeOffsetX, eyeOffsetY);
      drawBrowsAngry(c);
      drawMouthOpen(c, 36, 18, 0xC208); // تم تكبير تمدد التم المفتوح
      break;
    case MOOD_SMIRK:
      drawFaceBase(c, blink, 96, false, false, false, 2, 0, 2, 0);
      drawBrowsNeutral(c);
      drawMouthSmirk(c, FACE_MOUTH_NEUTRAL);
      break;
    case MOOD_CUTE:
      drawFaceBase(c, blink, 96, true, false, false, -2, 1, -2, 1);
      drawBrowsHappy(c);
      drawMouthTongue(c);
      drawBlushSoft(c);
      drawCheekDots(c);
      break;
    case MOOD_EXCITED:
      drawFaceBase(c, false, 98, true, false, false, 0, 0, 0, 0);
      drawBrowsBigHappy(c);
      drawMouthTalkFrame(c, true);
      drawBlushSoft(c);
      drawSpark(c, 15, 32, 8, FACE_GOLD); // تكبير الشرر
      drawSpark(c, 205, 32, 8, FACE_GOLD);
      break;
    case MOOD_SHY:
      drawFaceBase(c, blink, 90, true, false, false, -3, 2, -3, 2);
      drawBrowsShy(c);
      drawMouthSmileSoft(c, FACE_LIP);
      drawBlushSoft(c);
      break;
    case MOOD_CONFUSED:
      drawFaceBase(c, blink, 92, false, false, false, 3, -1, -3, 1);
      drawBrowsCurious(c);
      drawMouthSmirk(c, FACE_MOUTH_NEUTRAL);
      break;
    case MOOD_EMPATHETIC:
      drawFaceBase(c, blink, 90, true, false, false, eyeOffsetX, eyeOffsetY + 2, eyeOffsetX, eyeOffsetY + 2);
      drawBrowsEmpathetic(c);
      drawMouthEmpathetic(c, FACE_LIP_SOFT);
      drawBlushSoft(c, 163); // تنزيل قليلاً
      break;
    case MOOD_LOVE:
      drawFaceBase(c, blink, 94, true, false, false, 0, 0, 0, 0);
      drawBrowsHappy(c);
      drawMouthSmileSoft(c, FACE_LIP);
      drawBlushSoft(c);
      drawLoveHeartsOverlay(c);
      break;
    case MOOD_CRY:
      drawFaceBase(c, false, 84, true, false, false, eyeOffsetX, eyeOffsetY + 4, eyeOffsetX, eyeOffsetY + 4);
      drawBrowsSadInnocent(c);
      drawMouthSadSoft(c, FACE_LIP_SOFT);
      drawCryOverlay(c, true);
      break;
    case MOOD_WINK:
      fillInnerPanel(c);
      drawPanelGlow(c);
      drawOneEyeWinkPair(c, eyeOffsetX, eyeOffsetY, eyeOffsetX, eyeOffsetY, true);
      drawBrowsHappy(c);
      drawNoseSoft(c, 110, 130, false);
      drawMouthSmileSoft(c, FACE_LIP);
      break;
    case MOOD_KISS:
      drawFaceBase(c, blink, 90, true, false, false, -1, 1, -1, 1);
      drawBrowsShy(c);
      drawMouthKiss(c);
      drawBlushSoft(c);
      // قلب قبلة عملاق
      drawHeartTiny(c, 150, 130, 9, FACE_HEART); 
      break;
    case MOOD_HEART_EYES:
      drawFaceBase(c, false, 96, true, false, true, 0, 0, 0, 0);
      drawBrowsHappy(c);
      drawMouthSmile(c, FACE_LIP);
      drawBlushSoft(c);
      drawLoveHeartsOverlay(c);
      break;
  }
}

static inline int currentOverlayPhaseForMood(Mood mood) {
  switch (mood) {
    case MOOD_LOVE:
    case MOOD_HEART_EYES:
      return ((int)(millis() - fxStartMs) / 90) % 30;
    case MOOD_CRY:
      return ((int)(millis() - fxStartMs) / 45) % 76;
    case MOOD_YAWN:
      return ((int)(millis() - fxStartMs) / 110) % 6;
    default:
      return 0;
  }
}

static inline bool faceNeedsRedraw() {
  bool blink = millis() < blinkUntilMs;
  int overlayPhase = currentOverlayPhaseForMood(currentMood);
  if (!faceRendererReady) return true;
  if (currentMood != lastRenderedMood) return true;
  if (blink != lastRenderedBlink) return true;
  if (eyeOffsetX != lastRenderedEyeX || eyeOffsetY != lastRenderedEyeY) return true;
  if ((currentMood == MOOD_TALK || currentMood == MOOD_EXCITED) && talkFrame != lastRenderedTalkFrame) return true;
  if (overlayPhase != lastRenderedOverlayPhase) return true;
  return false;
}

static inline void markFaceRendered() {
  lastRenderedMood = currentMood;
  lastRenderedBlink = millis() < blinkUntilMs;
  lastRenderedEyeX = eyeOffsetX;
  lastRenderedEyeY = eyeOffsetY;
  lastRenderedTalkFrame = talkFrame;
  lastRenderedOverlayPhase = currentOverlayPhaseForMood(currentMood);
  lastFacePushMs = millis();
}

static inline void invalidateFaceRenderer() {
  faceRendererReady = false;
  faceShellReady = false;
  lastRenderedTalkFrame = 255;
  lastRenderedOverlayPhase = -999;
}

static inline void drawFace() {
  ensureFaceSprite();
  if (!faceShellReady) drawFaceShellStatic();
  if (!faceNeedsRedraw()) return;
  // small frame cap to keep pushes stable and avoid tearing/jitter
  if (millis() - lastFacePushMs < 20 && currentMood == lastRenderedMood) return;
  renderMood(faceSprite, currentMood);
  // تم تعديل إحداثيات الدفع لتكون أقرب للأطراف جداً (10, 10)
  faceSprite.pushSprite(10, 10);
  faceRendererReady = true;
  markFaceRendered();
}

#endif