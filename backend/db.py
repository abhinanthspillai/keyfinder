"""
Database layer for Find-My-Keys Beeper
Uses SQLite to store heartbeats, event history, and real-time device state.
"""

import sqlite3
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

DB_PATH = os.getenv("DATABASE_PATH") or os.path.join(os.path.dirname(__file__), "key_finder.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables and indexes if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Heartbeats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                rssi INTEGER NOT NULL,
                uptime INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                is_demo INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_heartbeats_device_ts ON heartbeats(device_id, timestamp)")

        # 2. Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                is_demo INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_device_ts ON events(device_id, timestamp)")

        # 3. Device state table (single-source of truth for current device state)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_state (
                device_id TEXT PRIMARY KEY,
                last_seen TEXT,
                rssi INTEGER,
                uptime INTEGER,
                pending_ring INTEGER DEFAULT 0,
                is_ringing INTEGER DEFAULT 0,
                pending_stop INTEGER DEFAULT 0,
                ring_requested_at TEXT,
                ring_acked_at TEXT
            )
        """)
        try:
            cursor.execute("ALTER TABLE device_state ADD COLUMN pending_stop INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()

def record_heartbeat(device_id: str, rssi: int, uptime: int) -> Dict[str, Any]:
    """Records a heartbeat from the device and updates device state."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Insert heartbeat log
        cursor.execute(
            "INSERT INTO heartbeats (device_id, rssi, uptime, timestamp, is_demo) VALUES (?, ?, ?, ?, 0)",
            (device_id, rssi, uptime, now_iso)
        )
        
        # Fetch current device state if exists
        cursor.execute("SELECT * FROM device_state WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        
        if row:
            pending_ring = bool(row["pending_ring"])
            is_ringing = bool(row["is_ringing"])
            pending_stop = bool(row["pending_stop"]) if "pending_stop" in row.keys() else False
            if pending_stop:
                cursor.execute("""
                    UPDATE device_state 
                    SET last_seen = ?, rssi = ?, uptime = ?, pending_stop = 0
                    WHERE device_id = ?
                """, (now_iso, rssi, uptime, device_id))
            else:
                cursor.execute("""
                    UPDATE device_state 
                    SET last_seen = ?, rssi = ?, uptime = ?
                    WHERE device_id = ?
                """, (now_iso, rssi, uptime, device_id))
        else:
            cursor.execute("""
                INSERT INTO device_state (device_id, last_seen, rssi, uptime, pending_ring, is_ringing, pending_stop)
                VALUES (?, ?, ?, ?, 0, 0, 0)
            """, (device_id, now_iso, rssi, uptime))
            pending_ring = False
            is_ringing = False
            pending_stop = False
            
        conn.commit()
        return {
            "device_id": device_id,
            "pending_ring": pending_ring,
            "is_ringing": is_ringing,
            "pending_stop": pending_stop,
            "last_seen": now_iso
        }

def record_event(device_id: str, event_type: str, source: str, is_demo: int = 0, timestamp: Optional[str] = None) -> int:
    """Logs an event (e.g. clap_ring, ring_requested, ring_acknowledged, ring_stopped)."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (device_id, type, source, timestamp, is_demo) VALUES (?, ?, ?, ?, ?)",
            (device_id, event_type, source, ts, is_demo)
        )
        event_id = cursor.lastrowid
        conn.commit()
        return event_id

def set_ring_flag(device_id: str, source: str = "dashboard") -> Dict[str, Any]:
    """Flags a pending ring for the device so next heartbeat triggers buzzer."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM device_state WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE device_state 
                SET pending_ring = 1, is_ringing = 1, ring_requested_at = ?
                WHERE device_id = ?
            """, (now_iso, device_id))
        else:
            cursor.execute("""
                INSERT INTO device_state (device_id, pending_ring, is_ringing, ring_requested_at)
                VALUES (?, 1, 1, ?)
            """, (device_id, now_iso))
            
        cursor.execute(
            "INSERT INTO events (device_id, type, source, timestamp, is_demo) VALUES (?, 'ring_requested', ?, ?, 0)",
            (device_id, source, now_iso)
        )
        conn.commit()
    return {"status": "ring_scheduled", "device_id": device_id, "timestamp": now_iso}

def acknowledge_ring(device_id: str) -> Dict[str, Any]:
    """Called by device when it receives the ring command and starts buzzer."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE device_state 
            SET pending_ring = 0, ring_acked_at = ?
            WHERE device_id = ?
        """, (now_iso, device_id))
        
        cursor.execute(
            "INSERT INTO events (device_id, type, source, timestamp, is_demo) VALUES (?, 'ring_acknowledged', 'device', ?, 0)",
            (device_id, now_iso)
        )
        conn.commit()
    return {"status": "acknowledged", "device_id": device_id, "timestamp": now_iso}

def stop_ringing(device_id: str, source: str = "user") -> Dict[str, Any]:
    """Stops a ringing device early."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE device_state 
            SET pending_ring = 0, is_ringing = 0, pending_stop = 1
            WHERE device_id = ?
        """, (device_id,))
        
        cursor.execute(
            "INSERT INTO events (device_id, type, source, timestamp, is_demo) VALUES (?, 'ring_stopped', ?, ?, 0)",
            (device_id, source, now_iso)
        )
        conn.commit()
    return {"status": "stopped", "device_id": device_id, "timestamp": now_iso}

def get_device_status(device_id: str, offline_threshold_seconds: int = 15) -> Dict[str, Any]:
    """Calculates online/offline status, RSSI rating, rings today, and last seen."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM device_state WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()

        # Count rings today
        today_start_iso = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        cursor.execute("""
            SELECT COUNT(*) AS count FROM events 
            WHERE device_id = ? AND type IN ('ring_requested', 'clap_ring') AND timestamp >= ?
        """, (device_id, today_start_iso))
        rings_today = cursor.fetchone()["count"]

    if not row or not row["last_seen"]:
        return {
            "device_id": device_id,
            "online": False,
            "last_seen": None,
            "seconds_since_last_seen": None,
            "rssi": None,
            "rssi_quality": "Unknown",
            "uptime": 0,
            "is_ringing": False,
            "pending_ring": False,
            "ring_requested_at": None,
            "ring_acked_at": None,
            "rings_today": rings_today
        }

    last_seen_dt = datetime.fromisoformat(row["last_seen"])
    now_dt = datetime.now(timezone.utc)
    seconds_ago = max(0, int((now_dt - last_seen_dt).total_seconds()))
    is_online = seconds_ago <= offline_threshold_seconds

    # If is_ringing was set more than 15 seconds ago and hasn't been cleared, auto-reset is_ringing
    is_ringing = bool(row["is_ringing"])
    if is_ringing and row["ring_requested_at"]:
        req_dt = datetime.fromisoformat(row["ring_requested_at"])
        if (now_dt - req_dt).total_seconds() > 15:
            is_ringing = False
            # Update state in background
            with get_connection() as conn:
                conn.cursor().execute("UPDATE device_state SET is_ringing = 0, pending_ring = 0 WHERE device_id = ?", (device_id,))
                conn.commit()

    rssi = row["rssi"]
    if rssi is None:
        quality = "Unknown"
    elif rssi >= -67:
        quality = "Strong"
    elif rssi >= -80:
        quality = "Fair"
    else:
        quality = "Weak"

    return {
        "device_id": device_id,
        "online": is_online,
        "last_seen": row["last_seen"],
        "seconds_since_last_seen": seconds_ago,
        "rssi": rssi,
        "rssi_quality": quality,
        "uptime": row["uptime"] or 0,
        "is_ringing": is_ringing,
        "pending_ring": bool(row["pending_ring"]),
        "ring_requested_at": row["ring_requested_at"],
        "ring_acked_at": row["ring_acked_at"],
        "rings_today": rings_today
    }

def get_recent_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves recent events sorted by newest first."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, device_id, type, source, timestamp, is_demo 
            FROM events 
            ORDER BY timestamp DESC, id DESC 
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_chart_data(device_id: str) -> Dict[str, Any]:
    """Provides time-series data for RSSI over time and rings per hour."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Wi-Fi RSSI over time (last 30 readings)
        cursor.execute("""
            SELECT rssi, timestamp FROM heartbeats 
            WHERE device_id = ? 
            ORDER BY timestamp DESC, id DESC 
            LIMIT 30
        """, (device_id,))
        recent_hb = [dict(r) for r in cursor.fetchall()]
        recent_hb.reverse() # chronological order for line chart

        # 2. Rings per hour (last 24 hours)
        now_dt = datetime.now(timezone.utc)
        since_dt = now_dt - timedelta(hours=24)
        since_iso = since_dt.isoformat()

        cursor.execute("""
            SELECT timestamp FROM events 
            WHERE device_id = ? AND type IN ('ring_requested', 'clap_ring') AND timestamp >= ?
        """, (device_id, since_iso))
        ring_rows = cursor.fetchall()

    # Bucket rings by 3-hour blocks or hourly over last 24h
    # To keep the bar chart clean and readable: 8 buckets of 3-hour intervals or past 12-24 hours
    hourly_counts: Dict[str, int] = {}
    for i in range(12, -1, -1):
        bucket_time = now_dt - timedelta(hours=i * 2)
        label = bucket_time.strftime("%H:%M")
        hourly_counts[label] = 0

    # Fill in counts
    for r in ring_rows:
        try:
            r_dt = datetime.fromisoformat(r["timestamp"])
            # Match closest bucket
            closest_label = min(
                hourly_counts.keys(),
                key=lambda l: abs((r_dt.hour - int(l.split(":")[0])) % 24)
            )
            hourly_counts[closest_label] += 1
        except Exception:
            pass

    return {
        "rssi_history": {
            "timestamps": [h["timestamp"] for h in recent_hb],
            "values": [h["rssi"] for h in recent_hb]
        },
        "rings_per_hour": {
            "labels": list(hourly_counts.keys()),
            "values": list(hourly_counts.values())
        }
    }

def insert_demo_data(device_id: str):
    """Inserts realistic mock heartbeats and events so charts and tables look populated."""
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        cursor = conn.cursor()

        # Insert 25 sample heartbeats over the past 30 minutes
        sample_rssi = [-64, -65, -63, -62, -66, -65, -61, -63, -68, -69, -67, -64, -63, -62, -60, -61, -63, -65, -66, -64, -62, -61, -63, -64, -62]
        for idx, rssi in enumerate(sample_rssi):
            ts = (now - timedelta(seconds=(25 - idx) * 72)).isoformat()
            cursor.execute(
                "INSERT INTO heartbeats (device_id, rssi, uptime, timestamp, is_demo) VALUES (?, ?, ?, ?, 1)",
                (device_id, rssi, 1000 + idx * 72, ts)
            )

        # Insert sample events
        events_to_add = [
            ("clap_ring", "clap", timedelta(minutes=14)),
            ("ring_requested", "telegram", timedelta(minutes=45)),
            ("ring_acknowledged", "device", timedelta(minutes=44, seconds=58)),
            ("ring_requested", "dashboard", timedelta(hours=2, minutes=10)),
            ("ring_acknowledged", "device", timedelta(hours=2, minutes=9, seconds=57)),
            ("clap_ring", "clap", timedelta(hours=4, minutes=30)),
            ("ring_requested", "telegram", timedelta(hours=7, minutes=15)),
            ("ring_stopped", "telegram", timedelta(hours=7, minutes=14, seconds=55)),
            ("clap_ring", "clap", timedelta(hours=11, minutes=5)),
            ("ring_requested", "dashboard", timedelta(hours=16, minutes=20)),
            ("ring_acknowledged", "device", timedelta(hours=16, minutes=19, seconds=58)),
        ]

        for ev_type, source, offset in events_to_add:
            ev_ts = (now - offset).isoformat()
            cursor.execute(
                "INSERT INTO events (device_id, type, source, timestamp, is_demo) VALUES (?, ?, ?, ?, 1)",
                (device_id, ev_type, source, ev_ts)
            )

        # Update current device state with fresh sample if no device has connected yet
        cursor.execute("SELECT last_seen FROM device_state WHERE device_id = ?", (device_id,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO device_state (device_id, last_seen, rssi, uptime, pending_ring, is_ringing)
                VALUES (?, ?, -62, 2800, 0, 0)
            """, (device_id, now.isoformat()))

        conn.commit()

def clear_demo_data(device_id: str):
    """Removes all rows flagged with is_demo = 1."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM heartbeats WHERE is_demo = 1 AND device_id = ?", (device_id,))
        cursor.execute("DELETE FROM events WHERE is_demo = 1 AND device_id = ?", (device_id,))
        conn.commit()

# Ensure database tables are created on module import
init_db()

