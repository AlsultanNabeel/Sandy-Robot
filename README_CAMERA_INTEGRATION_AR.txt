Sandy Camera Integration - النسخة المرتبة

هذا المجلد يحتوي على:
1) esp32cam_secure_cloud/
   - مشروع ESP32-CAM جديد
   - مربوط بـ Arduino IoT Cloud
   - الكاميرا مطفية افتراضياً
   - snapshot محمي بتوكن
   - control endpoint محمي بتوكن مختلف
   - أوامر on / off / arm_secret / disarm_secret / auth_ok / auth_fail

2) sandy_camera.py
   - نسخة Python مرتبة
   - تتحكم بالكاميرا عن طريق /control
   - تلتقط snapshot فقط عند الحاجة
   - تدعم verify_owner
   - تدعم enter_secret_mode_if_owner

الملفات التي تحتاج تعبئتها:
- esp32cam_secure_cloud/secrets.h
- esp32cam_secure_cloud/config.h
- sandy_camera_config.json

أضف إلى sandy_camera_config.json القيم التالية:
{
  "cam_ip": "192.168.8.150",
  "snapshot_token": "ضع نفس CAMERA_SNAPSHOT_TOKEN هنا",
  "control_token": "ضع نفس CAMERA_CONTROL_TOKEN هنا",
  "faces_db": "faces/faces_db.pkl",
  "owner_names": ["Nabeel"]
}

الأوامر المتوفرة من بايثون:
- open_eyes()
- close_eyes()
- verify_owner()
- enter_secret_mode_if_owner()
- get_remote_status()

المسار المقترح:
- ارفع مشروع esp32cam_secure_cloud إلى ESP32-CAM
- عدل sandy_camera.py في مشروعك الرئيسي
- بعدها نربط أوامر الكلام:
  "ساندي افتحي عيونك" -> open_eyes()
  "سكري عيونك" -> close_eyes()
  الجملة السرية -> enter_secret_mode_if_owner()
