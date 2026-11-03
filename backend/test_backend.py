"""
Automated backend verification script for Find-My-Keys Beeper
Tests all REST endpoints, headers, database operations, and static file serving.
"""

import sys
import os
import json
from fastapi.testclient import TestClient

# Ensure backend folder is in path
sys.path.insert(0, os.path.dirname(__file__))

from main import app, API_KEY, DEVICE_ID, QUICK_TOKEN
import db

def run_tests():
    print(">>> Starting Automated Backend Verification Tests <<<")
    with TestClient(app) as client:
        # 1. Test Static & Dashboard route
        print("[1] Testing GET / (Dashboard HTML)...")
        res = client.get("/")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert "Key Finder" in res.text
        print("    PASSED: Dashboard serves index.html")

        # 2. Test Static CSS & JS
        print("[2] Testing GET /static/style.css and /static/app.js...")
        res_css = client.get("/static/style.css")
        assert res_css.status_code == 200
        res_js = client.get("/static/app.js")
        assert res_js.status_code == 200
        print("    PASSED: Static assets served successfully")

        # 3. Test Initial Status (should be offline initially)
        print("[3] Testing GET /api/status...")
        res = client.get("/api/status")
        assert res.status_code == 200
        status_data = res.json()
        assert "online" in status_data
        assert "device_id" in status_data
        print(f"    PASSED: Device initial online status: {status_data['online']}")

        # 4. Test Heartbeat Authentication (Unauthorized without header)
        print("[4] Testing POST /api/heartbeat (Security & Auth)...")
        bad_res = client.post(
            "/api/heartbeat",
            json={"device_id": DEVICE_ID, "rssi": -65, "uptime": 100}
        )
        assert bad_res.status_code == 401, f"Expected 401 without API key, got {bad_res.status_code}"
        print("    PASSED: Blocked unauthenticated heartbeat (401)")

        # 5. Test Valid Heartbeat
        print("[5] Testing POST /api/heartbeat (Valid Heartbeat)...")
        hb_res = client.post(
            "/api/heartbeat",
            headers={"X-API-Key": API_KEY},
            json={"device_id": DEVICE_ID, "rssi": -62, "uptime": 120}
        )
        assert hb_res.status_code == 200
        hb_data = hb_res.json()
        assert hb_data["status"] == "ok"
        assert "ring" in hb_data
        print(f"    PASSED: Heartbeat registered. Response: {hb_data}")

        # 6. Verify Status is now Online
        print("[6] Checking device status after heartbeat...")
        res = client.get("/api/status")
        data = res.json()
        assert data["online"] is True
        assert data["rssi"] == -62
        assert data["rssi_quality"] == "Strong"
        print(f"    PASSED: Device is ONLINE with signal {data['rssi']} dBm ({data['rssi_quality']})")

        # 7. Test Double-Clap Event Reporting from Device
        print("[7] Testing POST /api/event (Clap Ring)...")
        ev_res = client.post(
            "/api/event",
            headers={"X-API-Key": API_KEY},
            json={"device_id": DEVICE_ID, "type": "clap_ring", "source": "clap"}
        )
        assert ev_res.status_code == 200
        print("    PASSED: Event recorded")

        # 8. Test Ring Trigger from Dashboard / Telegram
        print("[8] Testing POST /api/ring (Trigger buzzer)...")
        ring_res = client.post(
            "/api/ring",
            json={"device_id": DEVICE_ID, "source": "dashboard"}
        )
        assert ring_res.status_code == 200
        ring_data = ring_res.json()
        assert ring_data["status"] == "ring_scheduled"
        print("    PASSED: Ring flag scheduled")

        # 9. Verify next heartbeat receives ring: true
        print("[9] Testing heartbeat ring flag pickup...")
        hb2_res = client.post(
            "/api/heartbeat",
            headers={"X-API-Key": API_KEY},
            json={"device_id": DEVICE_ID, "rssi": -60, "uptime": 123}
        )
        assert hb2_res.status_code == 200
        assert hb2_res.json()["ring"] is True
        print("    PASSED: Device received ring: true in heartbeat response")

        # 10. Test Device Acknowledgment (/api/ack)
        print("[10] Testing POST /api/ack (Device buzzer confirmation)...")
        ack_res = client.post(
            "/api/ack",
            headers={"X-API-Key": API_KEY},
            json={"device_id": DEVICE_ID}
        )
        assert ack_res.status_code == 200
        print("    PASSED: Ring acknowledged and flag cleared")

        # 11. Verify next heartbeat has ring: false
        hb3_res = client.post(
            "/api/heartbeat",
            headers={"X-API-Key": API_KEY},
            json={"device_id": DEVICE_ID, "rssi": -60, "uptime": 126}
        )
        assert hb3_res.json()["ring"] is False
        print("    PASSED: Pending ring cleared after ack")

        # 12. Test Stop Ring
        print("[12] Testing POST /api/stop...")
        stop_res = client.post(
            "/api/stop",
            json={"device_id": DEVICE_ID, "source": "dashboard"}
        )
        assert stop_res.status_code == 200
        print("    PASSED: Stop ring succeeded")

        # 13. Test GET /api/events
        print("[13] Testing GET /api/events...")
        events_res = client.get("/api/events")
        assert events_res.status_code == 200
        events = events_res.json()
        assert len(events) >= 3
        print(f"    PASSED: Retrieved {len(events)} events")

        # 14. Test Demo Data Load & Purge
        print("[14] Testing POST and DELETE /api/demo-data...")
        demo_res = client.post("/api/demo-data")
        assert demo_res.status_code == 200
        events_after_demo = client.get("/api/events").json()
        demo_count = sum(1 for e in events_after_demo if e.get("is_demo") == 1)
        assert demo_count > 0, "Demo data should have been added"
        print(f"    PASSED: Demo data loaded ({demo_count} sample events)")

        purge_res = client.delete("/api/demo-data")
        assert purge_res.status_code == 200
        events_after_purge = client.get("/api/events").json()
        demo_count_after = sum(1 for e in events_after_purge if e.get("is_demo") == 1)
        assert demo_count_after == 0, "Demo data should have been removed"
        print("    PASSED: Demo data successfully purged")

        # 15. Test Chart Data
        print("[15] Testing GET /api/chart-data...")
        chart_res = client.get("/api/chart-data")
        assert chart_res.status_code == 200
        cd = chart_res.json()
        assert "rssi_history" in cd
        assert "rings_per_hour" in cd
        print("    PASSED: Chart data endpoint returns valid time series structures")

        # 16. Test /api/find_phone
        print("[16] Testing POST /api/find_phone...")
        find_phone_res = client.post(
            "/api/find_phone",
            headers={"X-API-Key": API_KEY},
            json={"device_id": DEVICE_ID}
        )
        assert find_phone_res.status_code == 200
        print("    PASSED: Find phone endpoint accepts requests")

        # 17. Test /quick without token
        print("[17] Testing GET /quick without token...")
        quick_res = client.get("/quick")
        assert quick_res.status_code == 403
        print("    PASSED: /quick rejects requests without token")

        # 18. Test /quick with invalid token
        print("[18] Testing GET /quick with invalid token...")
        quick_res = client.get("/quick?token=wrong_token")
        assert quick_res.status_code == 403
        print("    PASSED: /quick rejects requests with invalid token")

        # 19. Test /quick with valid token (if QUICK_TOKEN is set)
        if QUICK_TOKEN:
            print("[19] Testing GET /quick with valid token...")
            quick_res = client.get(f"/quick?token={QUICK_TOKEN}")
            assert quick_res.status_code == 200
            assert "Key Finder" in quick_res.text
            print("    PASSED: /quick serves page with valid token")


    print("\n=======================================================")
    print("   ALL BACKEND TESTS PASSED FLAWLESSLY!               ")
    print("=======================================================")

if __name__ == "__main__":
    run_tests()
