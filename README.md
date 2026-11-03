# 🔑 Find-My-Keys Beeper — Complete IoT Project

A low-cost, reliable IoT key finder built with an **ESP32 DevKit V1**, an **LM393 Sound Sensor**, an **Active Buzzer**, a **Push Button**, a **FastAPI + SQLite** backend, a long-polling **Telegram Bot**, and a **clean SaaS-style Web Dashboard** with voice control and mobile shortcuts.

---

## 📋 System Architecture

```mermaid
graph TD
    UserClap[Double Clap] -->|DO pin GPIO33| ESP32[ESP32 DevKit V1]
    Button[Push Button] -->|GPIO27| ESP32
    ESP32 -->|GPIO25 + 1k + NPN| Buzzer[Active Buzzer Beeps]

    ESP32 -->|HTTP POST 3s Heartbeat| Backend[FastAPI Server]
    ESP32 -->|HTTP POST Double-Clap Event| Backend
    ESP32 -->|HTTP POST Find Phone| Backend

    Dashboard[Web Dashboard :8000] <-->|REST Polling 2s| Backend
    TelegramApp[Telegram Bot] <-->|Async Long Polling| Backend
    QuickShortcut[/quick?token=] -->|POST /api/ring| Backend
```

---

## 🔌 Hardware & Wiring Summary

> [!IMPORTANT]
> **Pins are fixed and pre-wired.** Do not change the pin numbers in code.

|| Component | Pin / Terminal | ESP32 Pin | Description / Notes |
|| :--- | :--- | :--- | :--- |
|| **LM393 Sound Sensor** | `VCC` | `3.3V` or `VIN (5V)` | Power input |
|| | `GND` | `GND` | Common ground |
|| | `DO` | **`GPIO33`** | Digital Output (Comparator threshold) |
|| **Active Buzzer Circuit** | `Base` | **`GPIO25`** | Connected via **1kΩ resistor** to transistor Base |
|| (NPN BC547) | `Collector` | Buzzer `(-)` pin | Low-side transistor switch |
|| | `Emitter` | `GND` | Ground connection |
|| | Buzzer `(+)` | `VIN (5V)` | Direct 5V supply from USB |
|| **Push Button** | One side | **`GPIO27`** | INPUT_PULLUP (no external resistor) |
|| | Other side | `GND` | Connect to ground |

### Active Level Configuration
Different LM393 sensor breakout boards pull the digital output (`DO`) LOW or HIGH when sound exceeds the threshold.
- In `firmware/include/config.h`, set:
  ```cpp
  #define SOUND_ACTIVE_LEVEL LOW   // Default for most LM393 modules
  ```
  *(If your module's DO LED turns off on sound or triggers inverted, switch this to `HIGH`)*.

---

## 📁 Project Structure

```
Key Finder/
├── firmware/
│   ├── include/
│   │   ├── config.example.h   # Template configuration file
│   │   └── config.h           # Active configuration (gitignored)
│   ├── src/
│   │   └── main.cpp           # ESP32 Arduino sketch
│   ├── lib/
│   │   ├── ClapDetector/      # Pure logic clap detection (unit-testable)
│   │   ├── RingPattern/       # Pure logic ring pattern (unit-testable)
│   │   └── ButtonHandler/     # Pure logic button handling (unit-testable)
│   ├── test/                  # Native Unity unit tests
│   └── platformio.ini         # PlatformIO project file
├── backend/
│   ├── main.py                # FastAPI server application
│   ├── db.py                  # SQLite database models
│   ├── bot.py                 # Telegram bot client
│   ├── requirements.txt       # Python dependencies
│   ├── .env.example           # Template environment file
│   ├── .env                   # Active credentials (gitignored)
│   ├── test_backend.py        # Backend test suite
│   ├── test_bot.py            # Bot test suite
│   └── static/
│       ├── index.html         # Dashboard with voice control
│       ├── style.css          # Dark mode support
│       └── app.js             # Chart.js + Web Speech API
├── tools/
│   └── simulator.py           # ESP32 simulator for testing
├── .gitignore
└── README.md
```

---

## 🚀 Step-by-Step Setup Guide

### 1. Backend Setup (Python 3.11+)

1. Open a terminal and navigate to the project directory:
   ```bash
   cd "Key Finder"
   ```
2. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Create your `.env` configuration file:
   ```bash
   # On Windows PowerShell:
   Copy-Item backend/.env.example backend/.env
   ```
4. Edit `backend/.env` and set your values:
   ```ini
   API_KEY=super_secret_key_12345
   QUICK_TOKEN=your_random_token_here
   DEVICE_ID=esp32_keys_01
   PORT=8000
   HOST=0.0.0.0
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   ALLOWED_CHAT_IDS=123456789
   ```

---

### 2. Telegram Bot Setup (Free & Fast)

1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot` and follow the prompts to choose a name and username.
3. BotFather will provide an **API Token** (format: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
4. Find your **Telegram Chat ID**:
   - Message **[@userinfobot](https://t.me/userinfobot)** or **[@RawDataBot](https://t.me/RawDataBot)**.
   - It will reply with your numeric `Id` (e.g., `987654321`).
5. Update `backend/.env`:
   ```ini
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   ALLOWED_CHAT_IDS=987654321
   ```

---

### 3. Network Setup (Phone Hotspot & Finding Laptop IP)

Connect **both your laptop and your ESP32 to your phone's Wi-Fi hotspot**.

1. Turn on your mobile hotspot.
2. Connect your laptop to the hotspot Wi-Fi.
3. Find your laptop's local IPv4 address:
   ```powershell
   ipconfig
   ```
   Look for **Wireless LAN adapter Wi-Fi**:
   ```text
   IPv4 Address. . . . . . . . . . . : 192.168.43.50
   ```
4. Configure `firmware/include/config.h`:
   ```cpp
   #define WIFI_SSID        "Your_Hotspot_SSID"
   #define WIFI_PASSWORD    "Your_Hotspot_Password"
   #define BACKEND_BASE_URL "http://192.168.43.50:8000"
   #define API_KEY          "super_secret_key_12345"
   #define DEVICE_ID        "esp32_keys_01"
   ```

#### 🛡️ Windows Firewall Note
Windows Firewall may block incoming connections:
- When prompted, check **both Private and Public networks** and click **Allow access**.
- Or run in Administrator PowerShell:
  ```powershell
  New-NetFirewallRule -DisplayName "Key Finder Backend" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
  ```

---

### 4. Flashing the Firmware

#### Using PlatformIO (Recommended)
1. Open the `firmware/` folder in VS Code with PlatformIO installed.
2. Build the firmware:
   ```bash
   cd firmware
   pio run
   ```
3. Connect ESP32 via USB and upload:
   ```bash
   pio run -t upload
   ```
   If it hangs at "Connecting......", hold the **BOOT button** until it starts.

#### Using Arduino IDE
1. Install ESP32 Board Package and ArduinoJson library.
2. Select board: `DOIT ESP32 DEVKIT V1`.
3. Open `firmware/src/main.cpp` and click **Upload**.

---

### 5. Running the Backend Server

Start the FastAPI backend:
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Output:
```text
[INFO] key_finder: Initializing database...
[INFO] key_finder: Key Finder Server starting on port 8000. Device ID: 'esp32_keys_01'
[INFO] telegram_bot: [Telegram Bot] Started long polling for device 'esp32_keys_01'.
```

Visit: **`http://localhost:8000`** or **`http://192.168.43.50:8000`** from your phone.

---

## 🧪 Testing Without Hardware

### Using the Simulator

Run the ESP32 simulator to test the backend without hardware:
```bash
cd tools
python simulator.py
```

Keyboard commands:
- `c` - Simulate double clap
- `s` - Stop buzzer
- `b` - Simulate button long press (find phone)
- `o` - Go offline
- `n` - Go online
- `q` - Quit

### Using curl

```bash
# Send heartbeat
curl -X POST http://localhost:8000/api/heartbeat ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: super_secret_key_12345" ^
  -d "{\"device_id\":\"esp32_keys_01\",\"rssi\":-62,\"uptime\":120}"

# Trigger ring
curl -X POST http://localhost:8000/api/ring ^
  -H "Content-Type: application/json" ^
  -d "{\"device_id\":\"esp32_keys_01\",\"source\":\"dashboard\"}"

# Stop ring
curl -X POST http://localhost:8000/api/stop ^
  -H "Content-Type: application/json" ^
  -d "{\"device_id\":\"esp32_keys_01\",\"source\":\"dashboard\"}"

# Check status
curl http://localhost:8000/api/status
```

---

## 🎯 Features

### Double-Clap Detection
- Clap twice rhythmically (150-900ms gap) to trigger the buzzer
- Ignores single claps, continuous noise, and 3+ rapid sounds
- Works even when Wi-Fi is offline (local buzzer still rings)

### Push Button
- **Short press** (< 1s): Stop ringing or play confirmation chirp
- **Long press** (≥ 1.5s): Send "find phone" message via Telegram

### Telegram Bot Commands
- `/ring` - Ring your keys
- `/stop` - Stop the buzzer
- `/status` - View device status, RSSI, uptime
- `/lastseen` - Last heartbeat timestamp
- `/help` - List commands

### Web Dashboard
- Real-time device status (Online/Offline, RSSI, rings today)
- "Ring my keys" button with voice control
- Wi-Fi signal and rings-per-hour charts
- Event log with source tracking
- Dark mode support (automatic)
- Demo data loading for testing

### Voice Control
- Click microphone button and say: "keys", "find my keys", "ring" to ring
- Say "stop" to stop ringing
- Falls back to text input if microphone unavailable

### Mobile Quick Shortcut
- Add `/quick?token=YOUR_TOKEN` to phone home screen
- One-tap ring without opening full dashboard
- Token required for security

---

## 🤖 Telegram Bot Commands

|| Command | Action |
|| :--- | :--- |
|| `/ring` | Ring buzzer |
|| `/stop` | Stop buzzer |
|| `/status` | View health |
|| `/lastseen` | Last heartbeat time |
|| `/help` | Command list |

---

## 🎯 Hardware Test Checklist

Use this checklist during demonstration:

- [ ] **Single clap ignored**: Clap once, buzzer stays silent
- [ ] **Double clap rings**: Clap twice (400ms apart), buzzer plays pattern
- [ ] **Noise rejection**: Continuous noise or 3 rapid claps ignored
- [ ] **Button short press**: Stop ringing or play chirp
- [ ] **Button long press**: Telegram receives "find phone" message
- [ ] **Telegram /ring**: Bot responds, device rings
- [ ] **Dashboard ring**: Button works, status updates
- [ ] **Voice control**: "ring" command triggers buzzer
- [ ] **Offline detection**: Unplug ESP32, dashboard shows offline in 15s
- [ ] **Dark mode**: Toggle OS theme, dashboard adapts

---

## 🔍 Troubleshooting

### Sound Sensor Issues
- **Symptom**: Buzzer never beeps or beeps continuously
- **Solution**:
  1. Open Serial Monitor at 115200 baud
  2. Turn blue potentiometer until DO LED is OFF when quiet
  3. Test with claps - LED should flash on each clap
  4. If inverted, change `SOUND_ACTIVE_LEVEL` in config.h

### Device Cannot Reach Server
- **Symptom**: Serial shows "Connection failed"
- **Solution**:
  1. Verify ESP32 and laptop on same Wi-Fi
  2. Check laptop IP with `ipconfig`
  3. Ensure backend is running
  4. Test from phone browser: `http://<LAPTOP_IP>:8000`
  5. Check Windows Firewall (allow port 8000)

### Telegram Bot Not Responding
- **Symptom**: Commands receive no reply
- **Solution**:
  1. Check backend logs for "Unauthorized chat ID" warning
  2. Add that ID to `ALLOWED_CHAT_IDS` in .env
  3. Verify `TELEGRAM_BOT_TOKEN` is correct
  4. Send `/start` to the bot first

### Voice Button Not Working
- **Symptom**: Microphone button missing or not responding
- **Solution**:
  1. Browser may not support Web Speech API - text input appears instead
  2. Check microphone permissions in browser settings
  3. Use HTTPS or localhost (required for microphone access)

### /quick Shortcut Not Working
- **Symptom**: "Invalid or missing token" error
- **Solution**:
  1. Set `QUICK_TOKEN` in backend/.env
  2. Restart backend server
  3. Use full URL: `http://<IP>:8000/quick?token=YOUR_TOKEN`

---

## 📄 License
Built as an open-source, zero-cost MCA project template. Free to modify, extend, and demo.
