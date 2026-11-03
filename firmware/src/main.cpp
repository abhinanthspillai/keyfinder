/*
 * =========================================================================
 * Find-My-Keys Beeper - ESP32 Firmware
 * =========================================================================
 * Hardware Setup:
 *   - Board: ESP32 DevKit V1 (30-pin)
 *   - Sound Sensor DO (LM393): GPIO33 (Input)
 *   - Active Buzzer (via NPN Transistor & 1k resistor): GPIO25 (Output)
 *   - Push Button: GPIO27 (INPUT_PULLUP)
 * =========================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <esp_wifi.h>
#include "config.h"
#include "pitches.h"
#include "../lib/ClapDetector/ClapDetector.h"
#include "../lib/RingPattern/RingPattern.h"
#include "../lib/ButtonHandler/ButtonHandler.h"

// -------------------------------------------------------------------------
// Global State & Timing Variables
// -------------------------------------------------------------------------

// Wi-Fi & Network
unsigned long lastHeartbeatTime = 0;
unsigned long lastWifiCheckTime = 0;
unsigned long lastWifiAttempt = 0;
bool wifiWasConnected = false;

// Sound sensor
bool lastSoundState = false;
unsigned long soundStateChangeTime = 0;
bool soundTestMode = SOUND_TEST_MODE;

// Clap detector (pure logic)
ClapDetector clapDetector(
    CLAP_DEBOUNCE_MS,
    CLAP_MIN_GAP_MS,
    CLAP_MAX_GAP_MS,
    CLAP_MAX_PULSE_MS,
    CLAP_NOISE_CHECK_MS,
    CLAP_POST_RING_SILENCE_MS
);

// Ring pattern (pure logic)
RingPattern ringPattern;

// Button handler (pure logic)
ButtonHandler buttonHandler(BTN_DEBOUNCE_MS, BTN_LONG_PRESS_MS);

// Event flags
bool pendingClapEvent = false;
bool pendingFindPhoneEvent = false;

// -------------------------------------------------------------------------
// Forward Declarations
// -------------------------------------------------------------------------
void initHardware();
void checkWifiStatus();
void updateSoundSensor();
void updateButton();
void setBuzzerHardware(bool on);
void buzzerTask(void *pvParameters);
void sendHeartbeat();
void sendClapEvent();
void sendFindPhoneEvent();
void sendAck();
void handleSerialCommands();

static TaskHandle_t buzzerTaskHandle = NULL;

// -------------------------------------------------------------------------
// Arduino Setup & Main Loop
// -------------------------------------------------------------------------
void setup() {
    // Safety: immediately ensure buzzer pin is OUTPUT and LOW
    pinMode(PIN_BUZZER, OUTPUT);
    digitalWrite(PIN_BUZZER, LOW);

    // Hardware verification beep at boot (150ms)
    digitalWrite(PIN_BUZZER, HIGH);
    delay(150);
    digitalWrite(PIN_BUZZER, LOW);

    // Sound sensor as INPUT
    pinMode(PIN_SOUND_DO, INPUT);

    // Button as INPUT_PULLUP
    pinMode(PIN_BUTTON, INPUT_PULLUP);

    Serial.begin(115200);
    delay(300);

    Serial.println();
    Serial.println(F("================================================"));
    Serial.println(F("   FIND-MY-KEYS BEEPER - ESP32 FIRMWARE"));
    Serial.println(F("================================================"));
    Serial.printf("Device ID: %s\n", DEVICE_ID);
    Serial.printf("Buzzer Pin: GPIO%d | Sound Pin: GPIO%d | Button Pin: GPIO%d\n",
                 PIN_BUZZER, PIN_SOUND_DO, PIN_BUTTON);
    Serial.printf("Active Level: %s\n", SOUND_ACTIVE_LEVEL == LOW ? "LOW" : "HIGH");
    Serial.println(F("Type 't' + Enter in Serial Monitor to toggle Test Mode."));
    Serial.println(F("================================================"));

    // Clear any stale NVS Wi-Fi cache
    WiFi.disconnect(true);
    delay(200);

    // Register Wi-Fi Event Handler for diagnostic logging
    WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
        if (event == ARDUINO_EVENT_WIFI_STA_START) {
            Serial.println(F("[Wi-Fi] STA started"));
        } else if (event == ARDUINO_EVENT_WIFI_STA_CONNECTED) {
            Serial.println(F("[Wi-Fi] Station connected to AP"));
        } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
            Serial.print(F("[Wi-Fi] Got IP: "));
            Serial.println(IPAddress(info.got_ip.ip_info.ip.addr));
        } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
            Serial.printf("[Wi-Fi] Disconnected, reason: %d\n", info.wifi_sta_disconnected.reason);
        }
    });

    // Start Wi-Fi connection
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    esp_wifi_set_ps(WIFI_PS_NONE);
    WiFi.setAutoReconnect(false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastWifiAttempt = millis();
    Serial.printf("[Wi-Fi] Connecting to SSID: %s ", WIFI_SSID);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(F("."));
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        wifiWasConnected = true;
        Serial.println();
        Serial.println(F("[Wi-Fi] Connected successfully!"));
        Serial.printf("[Wi-Fi] IP Address : %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[Wi-Fi] Signal RSSI: %d dBm\n", WiFi.RSSI());

        // Chirp confirming Wi-Fi connection
        setBuzzerHardware(true);
        delay(80);
        setBuzzerHardware(false);
    } else {
        Serial.println();
        Serial.println(F("[Wi-Fi] Initial connection in progress, continuing to loop..."));
    }

    // Launch dedicated Buzzer Task on Core 0 with priority 3
    // Runs independently of Core 1 network calls, ensuring microsecond-accurate chirps
    xTaskCreatePinnedToCore(
        buzzerTask,
        "BuzzerTask",
        2048,
        NULL,
        3,
        &buzzerTaskHandle,
        0 // Pin to Core 0
    );
}

void loop() {
    unsigned long now = millis();

    // 1. Process clap detection
    updateSoundSensor();

    // 2. Process button
    updateButton();

    // 3. Buzzer is driven with hardware precision by buzzerTask on Core 0

    // 4. Send clap event to backend
    if (pendingClapEvent && WiFi.status() == WL_CONNECTED) {
        pendingClapEvent = false;
        sendClapEvent();
    }

    // 5. Send find phone event
    if (pendingFindPhoneEvent && WiFi.status() == WL_CONNECTED) {
        pendingFindPhoneEvent = false;
        sendFindPhoneEvent();
    }

    // 6. Monitor Wi-Fi state
    checkWifiStatus();

    // 7. Send periodic heartbeat (throttle during ringing to reduce Wi-Fi congestion)
    unsigned long hbInterval = ringPattern.isPlaying() ? 1500 : HEARTBEAT_INTERVAL_MS;
    if (WiFi.status() == WL_CONNECTED && (now - lastHeartbeatTime >= hbInterval)) {
        lastHeartbeatTime = now;
        sendHeartbeat();
    }

    // 8. Handle serial commands
    handleSerialCommands();
}

// -------------------------------------------------------------------------
// Hardware Initialization
// -------------------------------------------------------------------------
void initHardware() {
    pinMode(PIN_BUZZER, OUTPUT);
    digitalWrite(PIN_BUZZER, LOW);
    pinMode(PIN_SOUND_DO, INPUT);
    pinMode(PIN_BUTTON, INPUT_PULLUP);
}

// -------------------------------------------------------------------------
// Sound Sensor Processing
// -------------------------------------------------------------------------
void updateSoundSensor() {
#if !ENABLE_CLAP_DETECTION
    return; // Clap detection disabled in favor of Mobile Shortcuts & Telegram
#else
    unsigned long now = millis();
    bool currentSoundState = (digitalRead(PIN_SOUND_DO) == SOUND_ACTIVE_LEVEL);

    // Check for state change
    if (currentSoundState != lastSoundState) {
        soundStateChangeTime = now;
        lastSoundState = currentSoundState;
    }

    // Process through clap detector
    bool isRinging = ringPattern.isPlaying();
    bool doubleClapDetected = clapDetector.processSound(now, currentSoundState, isRinging);

    if (doubleClapDetected) {
        Serial.println(F(">>> DOUBLE CLAP DETECTED! TRIGGERING RING <<<"));
        ringPattern.start();
        pendingClapEvent = true;
    }
#endif
}

// -------------------------------------------------------------------------
// Button Processing
// -------------------------------------------------------------------------
void updateButton() {
    unsigned long now = millis();
    bool buttonPressed = (digitalRead(PIN_BUTTON) == LOW); // INPUT_PULLUP

    ButtonHandler::Action action = buttonHandler.process(now, buttonPressed);

    if (action == ButtonHandler::SHORT_PRESS) {
        Serial.println(F("[BUTTON] Short press detected"));
        if (ringPattern.isPlaying()) {
            Serial.println(F("[BUTTON] Stopping ring"));
            ringPattern.stop();
            setBuzzerHardware(false);
        } else {
            Serial.println(F("[BUTTON] Triggering Find Phone!"));
            // Play confirmation chirp
            setBuzzerHardware(true);
            delay(80);
            setBuzzerHardware(false);
            pendingFindPhoneEvent = true;
        }
    } else if (action == ButtonHandler::LONG_PRESS) {
        Serial.println(F("[BUTTON] Long press detected - sending find phone"));
        setBuzzerHardware(true);
        delay(120);
        setBuzzerHardware(false);
        pendingFindPhoneEvent = true;
    }
}

// -------------------------------------------------------------------------
// Buzzer Driving (Active Buzzer on GPIO25 via BC547 NPN Transistor)
// -------------------------------------------------------------------------
void setBuzzerHardware(bool on) {
    digitalWrite(PIN_BUZZER, on ? HIGH : LOW);
}

// Dedicated FreeRTOS task running on Core 0
// Unaffected by HTTP requests or network delays on Core 1
void buzzerTask(void *pvParameters) {
    for (;;) {
        if (ringPattern.isPlaying()) {
            unsigned long now = millis();
            bool on = ringPattern.update(now);
            setBuzzerHardware(on);
            vTaskDelay(pdMS_TO_TICKS(5)); // 5ms precision
        } else {
            setBuzzerHardware(false);
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }
}

// -------------------------------------------------------------------------
// Wi-Fi Connection Monitoring
// -------------------------------------------------------------------------
void checkWifiStatus() {
    unsigned long now = millis();
    if (now - lastWifiCheckTime < 1000) return;
    lastWifiCheckTime = now;

    wl_status_t status = WiFi.status();

    if (status == WL_CONNECTED) {
        if (!wifiWasConnected) {
            wifiWasConnected = true;
            Serial.println();
            Serial.println(F("[Wi-Fi] Connected successfully!"));
            Serial.printf("[Wi-Fi] IP Address : %s\n", WiFi.localIP().toString().c_str());
            Serial.printf("[Wi-Fi] Signal RSSI: %d dBm\n", WiFi.RSSI());

            // Chirp confirming Wi-Fi connection
            setBuzzerHardware(true);
            delay(80);
            setBuzzerHardware(false);
        }
    } else {
        if (wifiWasConnected) {
            wifiWasConnected = false;
            Serial.println(F("[Wi-Fi] Connection lost!"));
            lastWifiAttempt = now;
        }

        // Gentle reconnect attempt every 10 seconds (avoids flooding AP)
        if (now - lastWifiAttempt >= 10000) {
            lastWifiAttempt = now;
            Serial.printf("[Wi-Fi] Status: %d. Retrying connection to '%s'...\n", (int)status, WIFI_SSID);
            WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        }
    }
}

// -------------------------------------------------------------------------
// HTTP Client Network Calls (Supports Local HTTP & Cloud HTTPS / Render)
// -------------------------------------------------------------------------
WiFiClient wifiClient;
WiFiClientSecure secureClient;

bool beginHttpRequest(HTTPClient &http, const String &url) {
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.setTimeout(HTTP_TIMEOUT_MS);
    if (url.startsWith("https://")) {
        secureClient.setInsecure(); // Skip certificate validation for cloud platforms like Render
        return http.begin(secureClient, url);
    } else {
        return http.begin(wifiClient, url);
    }
}

void sendHeartbeat() {
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    String url = String(BACKEND_BASE_URL) + "/api/heartbeat";
    if (!beginHttpRequest(http, url)) return;
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);

    StaticJsonDocument<192> reqDoc;
    reqDoc["device_id"] = DEVICE_ID;
    reqDoc["rssi"] = WiFi.RSSI();
    reqDoc["uptime"] = (unsigned long)(millis() / 1000);

    String requestBody;
    serializeJson(reqDoc, requestBody);

    int httpCode = http.POST(requestBody);

    if (httpCode == HTTP_CODE_OK || httpCode == 200) {
        String response = http.getString();
        StaticJsonDocument<256> respDoc;
        DeserializationError err = deserializeJson(respDoc, response);

        if (!err) {
            bool shouldRing = respDoc["ring"] | false;
            bool stopRequested = respDoc["stop"] | false;

            if (stopRequested && ringPattern.isPlaying()) {
                Serial.println(F("[SERVER] Stop command received."));
                ringPattern.stop();
                setBuzzerHardware(false);
            } else if (shouldRing && !ringPattern.isPlaying()) {
                Serial.println(F("[SERVER] Ring command received via heartbeat!"));
                ringPattern.start();
                sendAck();
            }
        }
    } else {
        if (httpCode > 0) {
            Serial.printf("[Heartbeat] HTTP Error: %d\n", httpCode);
        } else {
            Serial.printf("[Heartbeat] Connection failed: %s\n", http.errorToString(httpCode).c_str());
        }
    }
    http.end();
}

void sendAck() {
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    String url = String(BACKEND_BASE_URL) + "/api/ack";
    if (!beginHttpRequest(http, url)) return;
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);

    StaticJsonDocument<128> doc;
    doc["device_id"] = DEVICE_ID;

    String body;
    serializeJson(doc, body);

    int httpCode = http.POST(body);
    if (httpCode == 200) {
        Serial.println(F("[ACK] Ring acknowledged to backend successfully."));
    }
    http.end();
}

void sendClapEvent() {
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    String url = String(BACKEND_BASE_URL) + "/api/event";
    if (!beginHttpRequest(http, url)) return;
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);

    StaticJsonDocument<192> doc;
    doc["device_id"] = DEVICE_ID;
    doc["type"] = "clap_ring";
    doc["source"] = "clap";

    String body;
    serializeJson(doc, body);

    int httpCode = http.POST(body);
    if (httpCode == 200 || httpCode == 201) {
        Serial.println(F("[EVENT] Double-clap event reported to server."));
    } else {
        Serial.printf("[EVENT] Failed to report clap event: HTTP %d\n", httpCode);
    }
    http.end();
}

void sendFindPhoneEvent() {
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    String url = String(BACKEND_BASE_URL) + "/api/find_phone";
    if (!beginHttpRequest(http, url)) return;
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);

    StaticJsonDocument<128> doc;
    doc["device_id"] = DEVICE_ID;

    String body;
    serializeJson(doc, body);

    int httpCode = http.POST(body);
    if (httpCode == 200) {
        Serial.println(F("[FIND_PHONE] Find phone event sent to server."));
    } else {
        Serial.printf("[FIND_PHONE] Failed to send find phone event: HTTP %d\n", httpCode);
    }
    http.end();
}

// -------------------------------------------------------------------------
// Serial Monitor Test & Calibration Commands
// -------------------------------------------------------------------------
void handleSerialCommands() {
    if (Serial.available() > 0) {
        char cmd = Serial.read();
        if (cmd == 'r' || cmd == 'R') {
            Serial.println(F(">>> Manual Test Ring Triggered via Serial <<<"));
            ringPattern.start();
        } else if (cmd == 's' || cmd == 'S') {
            Serial.println(F(">>> Manual Stop Triggered via Serial <<<"));
            ringPattern.stop();
            setBuzzerHardware(false);
        }
    }
}
