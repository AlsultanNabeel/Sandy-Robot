
#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoIoTCloud.h>
#include <Arduino_ConnectionHandler.h>
#include "config.h"
#include "secrets.h"
#include "thingProperties.h"

// ===== AI Thinker ESP32-CAM pins =====
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

WebServer server(80);

bool cameraInitialized = false;
unsigned long lastStatusPrintMs = 0;

IPAddress local_IP(CAMERA_LOCAL_IP_1, CAMERA_LOCAL_IP_2, CAMERA_LOCAL_IP_3, CAMERA_LOCAL_IP_4);
IPAddress gateway(CAMERA_GATEWAY_1, CAMERA_GATEWAY_2, CAMERA_GATEWAY_3, CAMERA_GATEWAY_4);
IPAddress subnet(CAMERA_SUBNET_1, CAMERA_SUBNET_2, CAMERA_SUBNET_3, CAMERA_SUBNET_4);
IPAddress primaryDNS(8, 8, 8, 8);
IPAddress secondaryDNS(1, 1, 1, 1);

static bool tokenOk(const char* argName, const char* expected) {
  return expected && strlen(expected) > 0 && server.hasArg(argName) && server.arg(argName) == expected;
}

static bool basicAuthOk() {
  return server.authenticate(CAMERA_HTTP_USER, CAMERA_HTTP_PASS);
}

static bool allowSnapshot() {
  return basicAuthOk() && tokenOk("token", CAMERA_SNAPSHOT_TOKEN);
}

static bool allowControl() {
  return basicAuthOk() && tokenOk("token", CAMERA_CONTROL_TOKEN);
}

void setCameraStatus(const String& value) {
  cameraStatus = value;
  Serial.println("[CAM STATUS] " + value);
}

void setMode(const String& value) {
  cameraMode = value;
}

camera_config_t buildCameraConfig() {
  camera_config_t cfg;
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer = LEDC_TIMER_0;
  cfg.pin_d0 = Y2_GPIO_NUM;
  cfg.pin_d1 = Y3_GPIO_NUM;
  cfg.pin_d2 = Y4_GPIO_NUM;
  cfg.pin_d3 = Y5_GPIO_NUM;
  cfg.pin_d4 = Y6_GPIO_NUM;
  cfg.pin_d5 = Y7_GPIO_NUM;
  cfg.pin_d6 = Y8_GPIO_NUM;
  cfg.pin_d7 = Y9_GPIO_NUM;
  cfg.pin_xclk = XCLK_GPIO_NUM;
  cfg.pin_pclk = PCLK_GPIO_NUM;
  cfg.pin_vsync = VSYNC_GPIO_NUM;
  cfg.pin_href = HREF_GPIO_NUM;
  cfg.pin_sccb_sda = SIOD_GPIO_NUM;
  cfg.pin_sccb_scl = SIOC_GPIO_NUM;
  cfg.pin_pwdn = PWDN_GPIO_NUM;
  cfg.pin_reset = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.frame_size = CAMERA_DEFAULT_FRAME_SIZE;
  cfg.jpeg_quality = CAMERA_DEFAULT_JPEG_QUALITY;
  cfg.fb_count = CAMERA_DEFAULT_FB_COUNT;
  cfg.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  return cfg;
}

bool startCameraHardware() {
  if (cameraInitialized) return true;

  pinMode(PWDN_GPIO_NUM, OUTPUT);
  digitalWrite(PWDN_GPIO_NUM, LOW);
  delay(80);

  camera_config_t cfg = buildCameraConfig();
  esp_err_t err = esp_camera_init(&cfg);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    setCameraStatus("error_init");
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, CAMERA_VERTICAL_FLIP);
  }

  cameraInitialized = true;
  setCameraStatus("ready");
  return true;
}

void stopCameraHardware() {
  if (cameraInitialized) {
    esp_camera_deinit();
    cameraInitialized = false;
  }
  pinMode(PWDN_GPIO_NUM, OUTPUT);
  digitalWrite(PWDN_GPIO_NUM, HIGH);
  setCameraStatus("sleeping");
}

void applyPowerState(bool enabled) {
  Serial.print("[POWER] applyPowerState(");
  Serial.print(enabled ? "true" : "false");
  Serial.println(")");

  cameraPower = enabled;

  if (enabled) {
    Serial.println("[POWER] starting camera hardware...");
    if (startCameraHardware()) {
      if (cameraMode == "idle") setMode("watch");
      setCameraStatus("ready");
      Serial.println("[POWER] camera hardware started");
    } else {
      Serial.println("[POWER] camera hardware failed to start");
    }
  } else {
    Serial.println("[POWER] stopping camera hardware...");
    stopCameraHardware();
    cameraStream = false;
    cameraSnapshot = false;
    if (cameraMode != "full") setMode("idle");
    Serial.println("[POWER] camera hardware stopped");
  }

  Serial.print("[POWER] cameraPower=");
  Serial.println(cameraPower ? "true" : "false");
  Serial.print("[POWER] cameraMode=");
  Serial.println(cameraMode);
  Serial.print("[POWER] cameraStatus=");
  Serial.println(cameraStatus);
}

void markSnapshotRequest() {
  cameraSnapshot = true;
  if (!cameraPower) applyPowerState(true);
  setMode("snapshot");
  setCameraStatus("snapshot_requested");
}

String buildStatusJson() {
  String json = "{";
  json += "\"cameraPower\":" + String(cameraPower ? "true" : "false");
  json += ",\"cameraStream\":" + String(cameraStream ? "true" : "false");
  json += ",\"cameraSnapshot\":" + String(cameraSnapshot ? "true" : "false");
  json += ",\"cameraMode\":\"" + cameraMode + "\"";
  json += ",\"cameraStatus\":\"" + cameraStatus + "\"";
  json += ",\"secretArmed\":" + String(secretArmed ? "true" : "false");
  json += ",\"fullModeEnabled\":" + String(fullModeEnabled ? "true" : "false");
  json += ",\"cameraInitialized\":" + String(cameraInitialized ? "true" : "false");
  json += ",\"ip\":\"" + WiFi.localIP().toString() + "\"";
  json += "}";
  return json;
}

void sendJson(const String& json, int code = 200) {
  server.send(code, "application/json", json);
}

void handleRoot() {
  sendJson(buildStatusJson());
}

void handleStatus() {
  if (!allowControl()) {
    if (!basicAuthOk()) return server.requestAuthentication();
    sendJson("{\"ok\":false,\"error\":\"unauthorized\"}", 401);
    return;
  }
  sendJson(buildStatusJson());
}

void handleSnapshot() {
  if (!basicAuthOk()) {
    server.requestAuthentication();
    return;
  }
  if (!tokenOk("token", CAMERA_SNAPSHOT_TOKEN)) {
    server.send(401, "text/plain", "Unauthorized");
    return;
  }

  if (!cameraPower) {
    server.send(423, "text/plain", "Camera is sleeping");
    return;
  }
  if (!cameraInitialized && !startCameraHardware()) {
    server.send(500, "text/plain", "Camera init failed");
    return;
  }

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    setCameraStatus("capture_error");
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  server.sendHeader("Content-Disposition", "inline; filename=sandy_snapshot.jpg");
  server.sendHeader("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  server.sendHeader("Pragma", "no-cache");
  server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);

  cameraSnapshot = false;
  if (cameraMode == "snapshot") setMode("watch");
  setCameraStatus("ready");
}

void handleStream() {
  if (!basicAuthOk()) {
    server.requestAuthentication();
    return;
  }
  if (!tokenOk("token", CAMERA_SNAPSHOT_TOKEN)) {
    server.send(401, "text/plain", "Unauthorized");
    return;
  }
  if (!cameraPower) {
    server.send(423, "text/plain", "Camera is sleeping");
    return;
  }
  if (!cameraInitialized && !startCameraHardware()) {
    server.send(500, "text/plain", "Camera init failed");
    return;
  }

  cameraStream = true;
  setMode(fullModeEnabled ? "full" : "watch");
  setCameraStatus("streaming");

  WiFiClient client = server.client();
  String response = "HTTP/1.1 200 OK\r\n";
  response += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n";
  response += "Cache-Control: no-store, no-cache, must-revalidate, max-age=0\r\n";
  response += "Pragma: no-cache\r\n\r\n";
  client.print(response);

  while (client.connected()) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      setCameraStatus("stream_error");
      break;
    }

    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.printf("Content-Length: %u\r\n\r\n", fb->len);
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);

    ArduinoCloud.update();
    delay(CAMERA_STREAM_FRAME_DELAY_MS);

    if (!cameraPower || !cameraStream) break;
  }

  cameraStream = false;
  if (cameraPower) {
    setCameraStatus("ready");
    if (!fullModeEnabled) setMode("watch");
  } else {
    setCameraStatus("sleeping");
    setMode("idle");
  }
}

void handleControl() {
  if (!basicAuthOk()) {
    server.requestAuthentication();
    return;
  }
  if (!tokenOk("token", CAMERA_CONTROL_TOKEN)) {
    sendJson("{\"ok\":false,\"error\":\"unauthorized\"}", 401);
    return;
  }

  String action = server.hasArg("action") ? server.arg("action") : "";
  action.trim();

  if (action == "wake") {
    applyPowerState(true);
    cameraStream = true;
    if (!fullModeEnabled) setMode("watch");
  } else if (action == "sleep") {
    fullModeEnabled = false;
    secretArmed = false;
    applyPowerState(false);
  } else if (action == "capture_once") {
    markSnapshotRequest();
  } else if (action == "arm_secret") {
    secretArmed = true;
    setMode("secret");
    if (!cameraPower) applyPowerState(true);
  } else if (action == "disarm_secret") {
    secretArmed = false;
    if (!fullModeEnabled) setMode(cameraPower ? "watch" : "idle");
  } else if (action == "full_mode_on") {
    fullModeEnabled = true;
    secretArmed = false;
    applyPowerState(true);
    cameraStream = true;
    setMode("full");
  } else if (action == "full_mode_off") {
    fullModeEnabled = false;
    cameraStream = false;
    setMode(cameraPower ? "watch" : "idle");
  } else if (action == "auth_ok") {
    cameraStatus = "owner_verified";
  } else if (action == "auth_fail") {
    cameraStatus = "not_owner";
  } else {
    sendJson("{\"ok\":false,\"error\":\"unknown_action\"}", 400);
    return;
  }

  sendJson("{\"ok\":true,\"action\":\"" + action + "\",\"status\":" + buildStatusJson() + "}");
}

void configureNetwork() {
#if CAMERA_USE_STATIC_IP
  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS, secondaryDNS)) {
    Serial.println("Failed to configure static IP");
  }
#endif
}

void connectWiFi() {
  configureNetwork();
  WiFi.begin(SECRET_SSID, SECRET_OPTIONAL_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi IP: ");
  Serial.println(WiFi.localIP());
}

void configureRoutes() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/snapshot", HTTP_GET, handleSnapshot);
  server.on("/stream", HTTP_GET, handleStream);
  server.on("/control", HTTP_GET, handleControl);
  server.begin();
}

void onCameraPowerChange() {
  Serial.print("[CLOUD] onCameraPowerChange -> ");
  Serial.println(cameraPower ? "true" : "false");
  applyPowerState(cameraPower);
}

void onCameraStreamChange() {
  Serial.print("[CLOUD] onCameraStreamChange -> ");
  Serial.println(cameraStream ? "true" : "false");

  if (!cameraPower && cameraStream) {
    applyPowerState(true);
  }

  if (cameraPower && cameraStream) {
    setMode(fullModeEnabled ? "full" : "watch");
    setCameraStatus("ready");
  }

  if (!cameraStream && cameraMode == "watch") {
    setCameraStatus(cameraPower ? "ready" : "sleeping");
  }

  Serial.print("[STREAM] cameraPower=");
  Serial.println(cameraPower ? "true" : "false");
  Serial.print("[STREAM] cameraMode=");
  Serial.println(cameraMode);
  Serial.print("[STREAM] cameraStatus=");
  Serial.println(cameraStatus);
}

void onCameraSnapshotChange() {
  if (cameraSnapshot) {
    markSnapshotRequest();
  }
}

void onCameraModeChange() {
  if (cameraMode == "idle") {
    fullModeEnabled = false;
    secretArmed = false;
    applyPowerState(false);
  } else if (cameraMode == "watch") {
    fullModeEnabled = false;
    if (!cameraPower) applyPowerState(true);
    cameraStream = true;
  } else if (cameraMode == "snapshot") {
    markSnapshotRequest();
  } else if (cameraMode == "secret") {
    secretArmed = true;
    if (!cameraPower) applyPowerState(true);
  } else if (cameraMode == "full") {
    fullModeEnabled = true;
    secretArmed = false;
    applyPowerState(true);
    cameraStream = true;
  }
}

void onSecretArmedChange() {
  if (secretArmed) {
    setMode("secret");
    if (!cameraPower) applyPowerState(true);
  }
}

void onFullModeEnabledChange() {
  if (fullModeEnabled) {
    setMode("full");
    applyPowerState(true);
    cameraStream = true;
  } else if (cameraMode == "full") {
    setMode(cameraPower ? "watch" : "idle");
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(PWDN_GPIO_NUM, OUTPUT);
  digitalWrite(PWDN_GPIO_NUM, HIGH);

  cameraPower = CAMERA_DEFAULT_ENABLED;
  cameraStream = false;
  cameraSnapshot = false;
  cameraMode = CAMERA_DEFAULT_ENABLED ? "watch" : "idle";
  cameraStatus = "booting";
  secretArmed = false;
  fullModeEnabled = false;

  connectWiFi();
  initProperties();
  ArduinoCloud.begin(ArduinoIoTPreferredConnection);
  setDebugMessageLevel(0);

  if (cameraPower) applyPowerState(true);
  else stopCameraHardware();

  configureRoutes();
  setCameraStatus(cameraPower ? "ready" : "sleeping");
  Serial.println("ESP32-CAM secure cloud controller ready.");
}

void loop() {
  ArduinoCloud.update();
  server.handleClient();

  if (millis() - lastStatusPrintMs >= 15000) {
    lastStatusPrintMs = millis();
    Serial.println(buildStatusJson());
  }
}
