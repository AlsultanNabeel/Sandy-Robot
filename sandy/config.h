
#ifndef SANDY_CONFIG_H
#define SANDY_CONFIG_H

// Pins
#define SERVO_PIN 19
#define TRIG_PIN 15
#define ECHO_PIN 1
#define BUZZER_PIN 27

// --- Base Motion (L298N) ---
// تمت إضافة هذه التعريفات هنا
#define MOTOR_LEFT_IN1  32
#define MOTOR_LEFT_IN2  33
#define MOTOR_RIGHT_IN3 25
#define MOTOR_RIGHT_IN4 26
// ملاحظة: بنات السرعة ENA/ENB غير مستخدمة حالياً للتحكم البسيط.
// يتم التحكم بالسرعة عبر الجمبر الموجود على لوحة L298N.


// Servo limits - Professional Smooth & Fast
#define SERVO_CENTER_ANGLE 90
#define SERVO_SAFE_MIN_ANGLE 5   // تجنب الأطراف القاسية للنعومة
#define SERVO_SAFE_MAX_ANGLE 175

#define SERVO_STEP_DEG 3         // لازم تبقى 1 عشان السلاسة
#define SERVO_STEP_DELAY_MS 1    // الغِ التأخير تماماً هنا!

// Servo pulse widths
#define SERVO_MIN_US 500
#define SERVO_MAX_US 2400

// Distance sensor
#define DISTANCE_READ_INTERVAL_MS 500

// Face animation
#define FACE_ANIM_INTERVAL_MS 80

// Buzzer
#define ENABLE_BUZZER true
#define BUZZER_RESOLUTION 8
#define BUZZER_BASE_FREQ 1000

#endif