#ifndef CONFIG_H
#define CONFIG_H

// =========================================================================
// Network & Backend Configuration
// =========================================================================
// Wi-Fi Credentials (Laptop / Phone Hotspot)
#define WIFI_SSID       ".."
#define WIFI_PASSWORD   "nopenope"

// Backend Server URL (e.g. your laptop's local IP on the hotspot)
// Note: Do NOT include trailing slash. Include the port (default :8000).
#define BACKEND_BASE_URL "http://192.168.43.50:8000"

// Unique Device Identifier and Authentication Key
#define DEVICE_ID        "esp32_keys_01"
#define DEVICE_API_KEY   "super_secret_key_12345"
#define API_KEY          DEVICE_API_KEY

// =========================================================================
// Hardware Pin Configuration (Do NOT change as hardware is pre-wired)
// =========================================================================
#define PIN_SOUND_DO     33   // Sound sensor DO digital input pin
#define PIN_BUZZER       25   // Active buzzer transistor base pin (1k resistor)
#define PIN_BUTTON       27   // Push button to GND (INPUT_PULLUP)

// Sound Sensor Active Level:
// Most LM393 microphone modules output LOW when sound is detected.
// If your specific module outputs HIGH on sound, change this to HIGH.
#define SOUND_ACTIVE_LEVEL LOW

// Serial Monitor Test Mode:
// Set to true to print every sound pulse & duration for potentiometer tuning.
// Can also be toggled live by typing 't' in the Arduino Serial Monitor (115200 baud).
#define SOUND_TEST_MODE   false

// =========================================================================
// Timing Constants (Milliseconds)
// =========================================================================
#define CLAP_DEBOUNCE_MS     80    // Ignore bounce pulses within single clap
#define CLAP_MIN_GAP_MS      150   // Minimum gap between clap 1 and clap 2
#define CLAP_MAX_GAP_MS      900   // Maximum gap allowed for 2nd clap
#define CLAP_MAX_PULSE_MS    400   // Pulses longer than this = noise
#define CLAP_NOISE_CHECK_MS  250   // Window after 2nd clap to check for 3rd sound (noise)
#define CLAP_POST_RING_SILENCE_MS 2000  // Ignore sound during ring + 2s after

#define BTN_DEBOUNCE_MS      50    // Button debounce period
#define BTN_LONG_PRESS_MS    1500  // Hold ≥ 1.5s for "find phone"

#define HEARTBEAT_INTERVAL_MS 3000 // Heartbeat every 3 seconds
#define HTTP_TIMEOUT_MS       1500  // HTTP request timeout

#endif // CONFIG_H
