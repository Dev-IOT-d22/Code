#include "WifiCam.hpp"
#include <WiFi.h>

static const char* WIFI_SSID = "HuyNQ";
static const char* WIFI_PASS = "huyandwho";

// ==========================
// GPIO ESP32-CAM
// ==========================
#define LED_BUILTIN 4
#define RELAY_PIN 2

// ===========================
// Biến logic
// ===========================
boolean activeRelay = false;
unsigned long prevMillis = 0;
int interval = 5000; // mở cửa 5 giây

esp32cam::Resolution initialResolution;
WebServer server(80);

// ===========================
// Hàm xử lý unlock
// ===========================
void handleUnlock() {
  if (!activeRelay) {
    activeRelay = true;
    digitalWrite(RELAY_PIN, HIGH);
    digitalWrite(LED_BUILTIN, HIGH);
    
    prevMillis = millis();
    
    Serial.println("✔ UNLOCK DOOR!");
    
    server.send(200, "text/plain", "Door unlocked");
  } else {
    server.send(200, "text/plain", "Already unlocked");
  }
}

// ===========================
// Hàm xử lý lock thủ công
// ===========================
void handleLock() {
  if (activeRelay) {
    activeRelay = false;
    digitalWrite(RELAY_PIN, LOW);
    digitalWrite(LED_BUILTIN, LOW);
    
    Serial.println("✖ LOCK DOOR");
    
    server.send(200, "text/plain", "Door locked");
  } else {
    server.send(200, "text/plain", "Already locked");
  }
}

// ===========================
// Hàm kiểm tra trạng thái
// ===========================
void handleStatus() {
  String status = activeRelay ? "unlocked" : "locked";
  server.send(200, "text/plain", status);
}

// ===========================
// SETUP
// ===========================
void setup() {
  Serial.begin(115200);
  Serial.println();
  esp32cam::setLogger(Serial);
  delay(1000);

  // --- GPIO ---
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);
  
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // --- WIFI ---
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  
  if (WiFi.waitForConnectResult() != WL_CONNECTED) {
    Serial.printf("WiFi failure %d\n", WiFi.status());
    delay(5000);
    ESP.restart();
  }
  
  Serial.println("WiFi connected");
  delay(1000);

  // --- CAMERA ---
  {
    using namespace esp32cam;

    initialResolution = Resolution::find(1024, 768);

    Config cfg;
    cfg.setPins(pins::AiThinker);
    cfg.setResolution(initialResolution);
    cfg.setJpeg(80);

    bool ok = Camera.begin(cfg);
    if (!ok) {
      Serial.println("camera initialize failure");
      delay(5000);
      ESP.restart();
    }
    Serial.println("camera initialize success");
  }

  Serial.println("camera starting");
  Serial.print("http://");
  Serial.println(WiFi.localIP());

  // --- WEB SERVER ---
  addRequestHandlers();  // Handlers từ WifiCam library
  
  // Thêm các endpoint mới cho relay
  server.on("/unlock", HTTP_GET, handleUnlock);
  server.on("/lock", HTTP_GET, handleLock);
  server.on("/status", HTTP_GET, handleStatus);
  
  server.begin();
  
  Serial.println("Server started!");
  Serial.println("Endpoints:");
  Serial.println("  GET /unlock - Mở khóa cửa");
  Serial.println("  GET /lock   - Khóa cửa thủ công");
  Serial.println("  GET /status - Kiểm tra trạng thái");
}

// ===========================
// LOOP
// ===========================
void loop() {
  server.handleClient();
  
  // Tự động đóng cửa sau interval
  if (activeRelay && millis() - prevMillis > interval) {
    activeRelay = false;
    
    digitalWrite(RELAY_PIN, LOW);
    digitalWrite(LED_BUILTIN, LOW);
    
    Serial.println("✖ AUTO LOCK DOOR");
  }
}