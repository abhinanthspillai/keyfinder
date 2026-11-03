"""
Find-My-Keys Beeper - FastAPI Backend Server
Serves REST API for ESP32 device, Web Dashboard, and runs the Telegram Bot.
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, Header, HTTPException, Request, Depends, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Ensure backend directory is in python path
sys.path.insert(0, os.path.dirname(__file__))

import db
from bot import TelegramBotService

# Load environment variables
load_dotenv()

API_KEY = os.getenv("DEVICE_API_KEY") or os.getenv("API_KEY", "super_secret_key_12345")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32_keys_01")
QUICK_TOKEN = os.getenv("QUICK_TOKEN", "")
OFFLINE_THRESHOLD = int(os.getenv("OFFLINE_THRESHOLD_SECONDS", "15"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_IDS_RAW = os.getenv("ALLOWED_CHAT_IDS", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Parse allowed chat IDs
allowed_chat_ids: List[int] = []
if ALLOWED_CHAT_IDS_RAW:
    for cid in ALLOWED_CHAT_IDS_RAW.split(","):
        cid = cid.strip()
        if cid and (cid.isdigit() or (cid.startswith("-") and cid[1:].isdigit())):
            allowed_chat_ids.append(int(cid))

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("key_finder")

# Initialize Telegram Bot instance
bot_service = TelegramBotService(
    token=TELEGRAM_BOT_TOKEN,
    allowed_chat_ids=allowed_chat_ids,
    default_device_id=DEVICE_ID
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    db.init_db()
    logger.info(f"Key Finder Server starting on port {PORT}. Device ID: '{DEVICE_ID}'")
    
    # Start Telegram Bot if configured
    await bot_service.start()
    
    yield
    
    # Shutdown
    logger.info("Stopping Telegram Bot and background tasks...")
    await bot_service.stop()
    logger.info("Shutdown complete.")

app = FastAPI(
    title="Find-My-Keys Beeper API",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files directory
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# -----------------------------------------------------------------------------
# Security Dependency
# -----------------------------------------------------------------------------
def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key or x_api_key != API_KEY:
        logger.warning(f"Unauthorized API access rejected. Header: '{x_api_key}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header"
        )
    return x_api_key

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class HeartbeatPayload(BaseModel):
    device_id: str = Field(default=DEVICE_ID)
    rssi: int
    uptime: int

class EventPayload(BaseModel):
    device_id: str = Field(default=DEVICE_ID)
    type: str = Field(..., description="e.g. clap_ring, button_press")
    source: str = Field(default="device", description="e.g. clap, manual")

class AckPayload(BaseModel):
    device_id: str = Field(default=DEVICE_ID)

class RingPayload(BaseModel):
    device_id: Optional[str] = DEVICE_ID
    source: Optional[str] = "dashboard"

class StopPayload(BaseModel):
    device_id: Optional[str] = DEVICE_ID
    source: Optional[str] = "dashboard"

class FindPhonePayload(BaseModel):
    device_id: str = Field(default=DEVICE_ID)

# -----------------------------------------------------------------------------
# Device API Endpoints (Require X-API-Key)
# -----------------------------------------------------------------------------
@app.post("/api/heartbeat")
def handle_heartbeat(payload: HeartbeatPayload, _auth: str = Depends(verify_api_key)):
    """Device reports in every ~3s. Returns whether buzzer should ring."""
    state = db.record_heartbeat(
        device_id=payload.device_id,
        rssi=payload.rssi,
        uptime=payload.uptime
    )
    should_ring = state.get("pending_ring", False)
    should_stop = state.get("pending_stop", False)
    if should_ring:
        logger.info(f"[HEARTBEAT] Sent RING command to device '{payload.device_id}' (RSSI: {payload.rssi} dBm)")
    if should_stop:
        logger.info(f"[HEARTBEAT] Sent STOP command to device '{payload.device_id}'")
    return {
        "status": "ok",
        "ring": should_ring,
        "ring_seconds": 4,
        "stop": should_stop
    }

@app.post("/api/event")
def handle_event(payload: EventPayload, _auth: str = Depends(verify_api_key)):
    """Logs an event originating from the device (e.g. valid double-clap)."""
    event_id = db.record_event(
        device_id=payload.device_id,
        event_type=payload.type,
        source=payload.source
    )
    logger.info(f"[EVENT] Logged device event #{event_id}: '{payload.type}' from '{payload.source}'")
    return {"status": "recorded", "event_id": event_id}

@app.post("/api/ack")
def handle_ack(payload: AckPayload, _auth: str = Depends(verify_api_key)):
    """Device confirms it received the ring command and has begun ringing."""
    result = db.acknowledge_ring(device_id=payload.device_id)
    logger.info(f"[ACK] Device '{payload.device_id}' acknowledged ring.")
    return result

# -----------------------------------------------------------------------------
# Control & Dashboard Endpoints
# -----------------------------------------------------------------------------
@app.post("/api/ring")
def trigger_ring(payload: RingPayload):
    """Sets the pending ring flag so the device rings on its next heartbeat."""
    target_device = payload.device_id or DEVICE_ID
    status_info = db.get_device_status(target_device, OFFLINE_THRESHOLD)
    result = db.set_ring_flag(device_id=target_device, source=payload.source or "dashboard")
    logger.info(f"[RING] Ring requested for '{target_device}' by '{payload.source}' (Device Online: {status_info['online']})")
    return {
        "status": "ring_scheduled",
        "device_id": target_device,
        "device_online": status_info["online"],
        "seconds_since_last_seen": status_info["seconds_since_last_seen"]
    }

@app.post("/api/stop")
def stop_device_ring(payload: StopPayload):
    """Stops a ringing device early."""
    target_device = payload.device_id or DEVICE_ID
    result = db.stop_ringing(device_id=target_device, source=payload.source or "dashboard")
    logger.info(f"[STOP] Ring stopped for '{target_device}' by '{payload.source}'")
    return result

@app.get("/api/status")
def get_status(device_id: Optional[str] = None):
    """Returns real-time status of the device, RSSI, last seen, and rings today."""
    target = device_id or DEVICE_ID
    return db.get_device_status(target, OFFLINE_THRESHOLD)

@app.get("/api/events")
def get_events(limit: int = 100):
    """Returns the most recent events (newest first)."""
    return db.get_recent_events(limit=limit)

@app.get("/api/chart-data")
def get_chart_data(device_id: Optional[str] = None):
    """Returns historical RSSI and rings-per-hour for dashboard charts."""
    target = device_id or DEVICE_ID
    return db.get_chart_data(target)

@app.post("/api/demo-data")
def load_demo_data(device_id: Optional[str] = None):
    """Inserts mock heartbeats and events so charts and tables look populated."""
    target = device_id or DEVICE_ID
    db.insert_demo_data(target)
    logger.info(f"[DEMO] Sample demo data loaded for '{target}'")
    return {"status": "demo_data_loaded", "device_id": target}

@app.delete("/api/demo-data")
def delete_demo_data(device_id: Optional[str] = None):
    """Removes all demo rows."""
    target = device_id or DEVICE_ID
    db.clear_demo_data(target)
    logger.info(f"[DEMO] Demo data purged for '{target}'")
    return {"status": "demo_data_cleared", "device_id": target}

@app.post("/api/find_phone")
async def handle_find_phone(payload: FindPhonePayload, _auth: str = Depends(verify_api_key)):
    """Device button press - sends immediate Reverse Find Phone alert to Telegram."""
    device_id = payload.device_id
    db.record_event(device_id, "find_phone", "button")
    logger.info(f"[FIND_PHONE] Reverse Find Phone triggered by device '{device_id}' -> Sending Telegram Alert")
    await bot_service.send_find_phone_message()
    return {"status": "find_phone_triggered", "device_id": device_id}

def get_lan_ip():
    env_ip = os.getenv("HOST_LAN_IP")
    if env_ip:
        return env_ip
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@app.get("/api/config-info")
def get_config_info():
    """Returns safe configuration info for dashboard shortcuts."""
    render_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")
    if render_url:
        render_url = render_url.rstrip("/")
        mobile_url = f"{render_url}/quick?token={QUICK_TOKEN}"
        display_host = render_url.replace("https://", "").replace("http://", "")
    else:
        lan_ip = get_lan_ip()
        mobile_url = f"http://{lan_ip}:{PORT}/quick?token={QUICK_TOKEN}"
        display_host = lan_ip

    return {
        "device_id": DEVICE_ID,
        "quick_token": QUICK_TOKEN,
        "telegram_bot_username": "My_keyfinder_bot" if TELEGRAM_BOT_TOKEN else "",
        "lan_ip": display_host,
        "port": PORT,
        "mobile_quick_url": mobile_url
    }

@app.get("/quick")
def serve_quick_page(token: str = None):
    """Serves the quick ring shortcut page for mobile home screen."""
    if not QUICK_TOKEN or not token or token != QUICK_TOKEN:
        return HTMLResponse("<h3>Invalid or missing token. Access denied.</h3>", status_code=403)

    quick_html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Key Finder">
  <meta name="theme-color" content="#090D16">
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="apple-touch-icon" href="/static/favicon.svg">
  <title>Key Finder</title>
  <style>
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }
    :root {
      --bg: #090D16;
      --card-bg: rgba(22, 30, 46, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #6366F1;
      --accent-glow: rgba(99, 102, 241, 0.35);
      --text: #F8FAFC;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
      --online: #10B981;
      --offline: #EF4444;
      --stop: #E11D48;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
      background: radial-gradient(circle at 50% 25%, #171E31 0%, var(--bg) 75%);
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      min-height: 100dvh;
      padding: env(safe-area-inset-top, 24px) 20px env(safe-area-inset-bottom, 24px);
      user-select: none;
      -webkit-user-select: none;
    }
    .widget {
      width: 100%;
      max-width: 360px;
      background: var(--card-bg);
      backdrop-filter: blur(28px);
      -webkit-backdrop-filter: blur(28px);
      border: 1px solid var(--card-border);
      border-radius: 32px;
      padding: 28px 24px 24px;
      box-shadow: 0 24px 50px -12px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.08);
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
    }
    .top-pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.07);
      padding: 5px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-muted);
      letter-spacing: 0.2px;
      margin-bottom: 24px;
    }
    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--text-dim);
      transition: all 0.3s ease;
    }
    .dot.online {
      background: var(--online);
      box-shadow: 0 0 10px var(--online);
    }
    .dot.offline {
      background: var(--offline);
    }
    .icon-halo {
      width: 72px;
      height: 72px;
      border-radius: 22px;
      background: linear-gradient(145deg, rgba(99, 102, 241, 0.14), rgba(99, 102, 241, 0.03));
      border: 1px solid rgba(99, 102, 241, 0.25);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 16px;
      box-shadow: 0 10px 24px -4px var(--accent-glow);
    }
    .icon-halo svg {
      width: 34px;
      height: 34px;
      stroke: var(--accent);
    }
    .title-area {
      margin-bottom: 28px;
    }
    .app-title {
      font-size: 21px;
      font-weight: 700;
      letter-spacing: -0.4px;
      color: #FFFFFF;
      margin-bottom: 3px;
    }
    .app-subtitle {
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 400;
    }
    .action-container {
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    .btn-main {
      width: 100%;
      height: 60px;
      border-radius: 18px;
      border: none;
      font-size: 17px;
      font-weight: 600;
      letter-spacing: -0.2px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      transition: transform 0.12s ease, box-shadow 0.15s ease;
    }
    .btn-main:active {
      transform: scale(0.97);
    }
    .btn-main svg {
      width: 20px;
      height: 20px;
      stroke-width: 2.2;
    }
    .btn-ring {
      background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%);
      color: #FFFFFF;
      box-shadow: 0 10px 24px -4px rgba(79, 70, 229, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.25);
    }
    .btn-stop {
      background: linear-gradient(135deg, #BE123C 0%, #E11D48 100%);
      color: #FFFFFF;
      box-shadow: 0 10px 24px -4px rgba(225, 29, 72, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.2);
    }
    .is-pulsing {
      animation: pulse-ring 1.1s infinite ease-in-out;
    }
    @keyframes pulse-ring {
      0% { transform: scale(1); opacity: 0.95; }
      50% { transform: scale(1.02); opacity: 1; }
      100% { transform: scale(1); opacity: 0.95; }
    }
    .status-toast {
      font-size: 13px;
      font-weight: 500;
      min-height: 22px;
      color: var(--text-dim);
      margin-top: 14px;
      transition: color 0.2s ease;
    }
    .status-toast.active {
      color: #A5B4FC;
    }
    .status-toast.error {
      color: #FDA4AF;
    }
    .footer-nav {
      width: 100%;
      display: flex;
      justify-content: center;
      gap: 12px;
      margin-top: 28px;
      padding-top: 18px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }
    .nav-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-dim);
      text-decoration: none;
      padding: 6px 14px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.06);
      transition: all 0.15s ease;
    }
    .nav-btn:hover, .nav-btn:active {
      color: var(--text);
      background: rgba(255, 255, 255, 0.08);
    }
    .nav-btn svg {
      width: 13px;
      height: 13px;
      fill: currentColor;
    }
  </style>
</head>
<body>
  <div class="widget">
    <div class="top-pill">
      <span id="statusDot" class="dot"></span>
      <span id="statusBadgeText">Checking device...</span>
    </div>

    <div class="icon-halo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="7.5" cy="15.5" r="4.5"/>
        <path d="m21 2-9.6 9.6"/>
        <path d="m15.5 7.5 3 3"/>
        <path d="m18.5 4.5 2 2"/>
      </svg>
    </div>

    <div class="title-area">
      <h1 class="app-title">Key Finder</h1>
      <p class="app-subtitle">1-Tap Instant Ring</p>
    </div>

    <div class="action-container">
      <button id="ringBtn" class="btn-main btn-ring" type="button">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>
        </svg>
        Ring My Keys
      </button>

      <button id="stopBtn" class="btn-main btn-stop is-pulsing" type="button" style="display: none;">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="2"/>
        </svg>
        Stop Buzzer
      </button>

      <div id="statusToast" class="status-toast">Ready</div>
    </div>

    <div class="footer-nav">
      <a href="https://t.me/My_keyfinder_bot" target="_blank" class="nav-btn">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.75-.55 2.92-1.27 4.86-2.11 5.83-2.52 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .37z"/></svg>
        Telegram
      </a>
      <a href="/" class="nav-btn">
        Dashboard
      </a>
    </div>
  </div>

  <script>
    const ringBtn = document.getElementById('ringBtn');
    const stopBtn = document.getElementById('stopBtn');
    const statusToast = document.getElementById('statusToast');
    const statusDot = document.getElementById('statusDot');
    const statusBadgeText = document.getElementById('statusBadgeText');

    let ringCountdownTimer = null;

    function vibrate(pattern = 50) {
      if ('vibrate' in navigator) navigator.vibrate(pattern);
    }

    function showStatus(msg, type = 'normal') {
      statusToast.textContent = msg;
      statusToast.className = 'status-toast' + (type === 'error' ? ' error' : type === 'active' ? ' active' : '');
    }

    async function checkDeviceStatus() {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const data = await res.json();
          if (data.online) {
            statusDot.className = 'dot online';
            statusBadgeText.textContent = 'Device Online · ' + (data.rssi ? data.rssi + ' dBm' : 'Strong');
          } else {
            statusDot.className = 'dot offline';
            statusBadgeText.textContent = 'Device Offline';
          }
        }
      } catch (e) {
        statusBadgeText.textContent = 'Server Connected';
      }
    }

    checkDeviceStatus();
    setInterval(checkDeviceStatus, 5000);

    ringBtn.addEventListener('click', async () => {
      vibrate([60, 40, 60]);
      ringBtn.style.display = 'none';
      stopBtn.style.display = 'flex';
      showStatus('Ringing keys...', 'active');

      try {
        const res = await fetch('/api/ring', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source: 'mobile_shortcut' })
        });
        const data = await res.json();
        if (data.device_online) {
          let secondsLeft = 4;
          showStatus(`Buzzer ringing (${secondsLeft}s)...`, 'active');
          if (ringCountdownTimer) clearInterval(ringCountdownTimer);
          ringCountdownTimer = setInterval(() => {
            secondsLeft -= 1;
            if (secondsLeft <= 0) {
              clearInterval(ringCountdownTimer);
              stopBtn.style.display = 'none';
              ringBtn.style.display = 'flex';
              showStatus('Ready');
            } else {
              showStatus(`Buzzer ringing (${secondsLeft}s)...`, 'active');
            }
          }, 1000);
        } else {
          showStatus('Device offline · Command queued', 'error');
        }
      } catch (err) {
        showStatus('Error: ' + err.message, 'error');
      }
    });

    stopBtn.addEventListener('click', async () => {
      vibrate(40);
      if (ringCountdownTimer) clearInterval(ringCountdownTimer);
      stopBtn.style.display = 'none';
      ringBtn.style.display = 'flex';
      showStatus('Buzzer stopped');

      try {
        await fetch('/api/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source: 'mobile_shortcut' })
        });
      } catch (err) {
        showStatus('Error: ' + err.message, 'error');
      }
    });
  </script>
</body>
</html>
    """
    return HTMLResponse(quick_html)

@app.get("/favicon.ico")
def serve_favicon():
    """Serves the vector favicon."""
    favicon_path = os.path.join(STATIC_DIR, "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return HTMLResponse("", status_code=404)

# -----------------------------------------------------------------------------
# Frontend Dashboard Route
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the single-page dashboard HTML."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h3>Dashboard file not found. Ensure static/index.html exists.</h3>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
