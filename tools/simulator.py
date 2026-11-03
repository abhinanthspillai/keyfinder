"""
ESP32 Simulator for Find-My-Keys Beeper
Mimics the ESP32 device behavior for testing without hardware.
Sends heartbeats, responds to ring commands, and provides keyboard commands.
"""

import time
import json
import requests
import random
import threading
from datetime import datetime

# Configuration (load from environment or use defaults)
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend/.env'))

BACKEND_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "super_secret_key_12345")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32_keys_01")

class ESP32Simulator:
    def __init__(self):
        self.is_ringing = False
        self.is_online = True
        self.uptime = 0
        self.last_heartbeat = 0
        self.heartbeat_interval = 3  # seconds

    def get_rssi(self):
        """Simulate Wi-Fi RSSI between -65 and -45 dBm"""
        return random.randint(-65, -45)

    def send_heartbeat(self):
        """Send heartbeat to backend and check for ring command"""
        if not self.is_online:
            print("[SIM] Device offline - skipping heartbeat")
            return

        try:
            url = f"{BACKEND_URL}/api/heartbeat"
            payload = {
                "device_id": DEVICE_ID,
                "rssi": self.get_rssi(),
                "uptime": self.uptime
            }
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }

            response = requests.post(url, json=payload, headers=headers, timeout=2)
            data = response.json()

            if response.status_code == 200:
                should_ring = data.get("ring", False)
                should_stop = data.get("stop", False)

                if should_stop and self.is_ringing:
                    print("[SIM] >>> BUZZER STOPPED <<<")
                    self.is_ringing = False

                if should_ring and not self.is_ringing:
                    print("[SIM] >>> BUZZER PATTERN STARTED (3 SECONDS) <<<")
                    self.is_ringing = True
                    self.send_ack()
                    # Buzzer automatically completes its pattern after 3 seconds
                    threading.Timer(3.0, self._auto_finish_ring).start()

                print(f"[SIM] Heartbeat OK | RSSI: {payload['rssi']} dBm | Ring: {should_ring}")
            else:
                print(f"[SIM] Heartbeat failed: {response.status_code}")

        except Exception as e:
            print(f"[SIM] Heartbeat error: {e}")

    def send_ack(self):
        """Acknowledge ring command"""
        try:
            url = f"{BACKEND_URL}/api/ack"
            payload = {"device_id": DEVICE_ID}
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }
            requests.post(url, json=payload, headers=headers, timeout=2)
            print("[SIM] Ring acknowledged")
        except Exception as e:
            print(f"[SIM] Ack error: {e}")

    def _auto_finish_ring(self):
        """Called 3 seconds after ring start to finish the buzzer pattern"""
        if self.is_ringing:
            self.is_ringing = False
            print("[SIM] Buzzer pattern finished")
            try:
                requests.post(f"{BACKEND_URL}/api/stop", json={"device_id": DEVICE_ID, "source": "device"}, timeout=2)
            except Exception:
                pass

    def send_clap_event(self):
        """Send double-clap event"""
        try:
            url = f"{BACKEND_URL}/api/event"
            payload = {
                "device_id": DEVICE_ID,
                "type": "clap_ring",
                "source": "clap"
            }
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }
            requests.post(url, json=payload, headers=headers, timeout=2)
            print("[SIM] >>> DOUBLE CLAP EVENT SENT <<<")
        except Exception as e:
            print(f"[SIM] Clap event error: {e}")

    def send_find_phone(self):
        """Send find phone event (button long press)"""
        try:
            url = f"{BACKEND_URL}/api/find_phone"
            payload = {"device_id": DEVICE_ID}
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }
            requests.post(url, json=payload, headers=headers, timeout=2)
            print("[SIM] >>> FIND PHONE EVENT SENT <<<")
        except Exception as e:
            print(f"[SIM] Find phone error: {e}")

    def stop(self):
        """Stop ringing manually"""
        if self.is_ringing:
            print("[SIM] >>> BUZZER STOPPED MANUALLY <<<")
            self.is_ringing = False

    def go_offline(self):
        """Go offline"""
        self.is_online = False
        print("[SIM] Device went OFFLINE")

    def go_online(self):
        """Come back online"""
        self.is_online = True
        print("[SIM] Device came ONLINE")

    def run(self):
        """Main loop with keyboard commands"""
        print("=" * 60)
        print("  ESP32 SIMULATOR - Find-My-Keys Beeper")
        print("=" * 60)
        print(f"Backend: {BACKEND_URL}")
        print(f"Device ID: {DEVICE_ID}")
        print(f"API Key: {API_KEY[:8]}...")
        print("=" * 60)
        print("Keyboard Commands:")
        print("  c - Simulate double clap")
        print("  s - Stop buzzer")
        print("  b - Simulate button long press (find phone)")
        print("  o - Go offline")
        print("  n - Go online")
        print("  q - Quit")
        print("=" * 60)
        print("Running heartbeats every 3 seconds...")
        print()

        import threading

        def heartbeat_loop():
            while True:
                self.send_heartbeat()
                self.uptime += 3
                time.sleep(self.heartbeat_interval)

        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        # Handle keyboard input
        try:
            while True:
                cmd = input().strip().lower()

                if cmd == 'c':
                    self.send_clap_event()
                elif cmd == 's':
                    self.stop()
                elif cmd == 'b':
                    self.send_find_phone()
                elif cmd == 'o':
                    self.go_offline()
                elif cmd == 'n':
                    self.go_online()
                elif cmd == 'q':
                    print("[SIM] Shutting down...")
                    break
                else:
                    print("[SIM] Unknown command. Use: c, s, b, o, n, q")

        except KeyboardInterrupt:
            print("\n[SIM] Interrupted, shutting down...")

if __name__ == "__main__":
    simulator = ESP32Simulator()
    simulator.run()
