"""
Telegram Bot for Find-My-Keys Beeper
Uses long-polling via httpx with no webhooks or public URLs required.
"""

import asyncio
import logging
import wave
import struct
import math
import io
from datetime import datetime, timezone
from typing import List, Optional, Set
import httpx

from db import (
    get_device_status,
    set_ring_flag,
    stop_ringing,
    record_event
)

logger = logging.getLogger("telegram_bot")

def generate_siren_audio(duration: float = 4.0, sample_rate: int = 22050) -> bytes:
    """Synthesizes an unmistakable, high-intensity emergency alarm siren in WAV format."""
    num_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(sample_rate)
        
        samples = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            # Fast alternating warble between 1200 Hz and 2400 Hz
            f = 1800.0 + 600.0 * math.sin(2.0 * math.pi * 6.0 * t)
            # Add harmonic overtone
            val1 = 24000.0 * math.sin(2.0 * math.pi * f * t)
            val2 = 8000.0 * math.sin(2.0 * math.pi * (f * 1.5) * t)
            sample_val = int(max(-32767, min(32767, val1 + val2)))
            samples.extend(struct.pack('<h', sample_val))
        wf.writeframes(samples)
    return buf.getvalue()

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🔔 Ring Keys"}, {"text": "⏹️ Stop"}],
        [{"text": "📊 Status"}, {"text": "🕒 Last Seen"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

class TelegramBotService:
    def __init__(self, token: str, allowed_chat_ids: List[int], default_device_id: str):
        self.token = token.strip() if token else ""
        self.allowed_chat_ids: Set[int] = set(allowed_chat_ids)
        self.default_device_id = default_device_id
        self.client: Optional[httpx.AsyncClient] = None
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.siren_audio_bytes: bytes = generate_siren_audio()

    def is_configured(self) -> bool:
        return bool(self.token and not self.token.startswith("your_"))

    async def start(self):
        if not self.is_configured():
            logger.info("[Telegram Bot] No valid TELEGRAM_BOT_TOKEN configured. Bot polling is disabled.")
            return

        self.is_running = True
        self.client = httpx.AsyncClient(timeout=35.0)
        self.task = asyncio.create_task(self._poll_loop())
        logger.info(f"[Telegram Bot] Started long polling for device '{self.default_device_id}'. Allowed chats: {list(self.allowed_chat_ids)}")

        # Proactively send welcome keyboard to all allowed chats on startup
        for cid in self.allowed_chat_ids:
            asyncio.create_task(self.send_message(
                cid,
                "<b>🔑 Key Finder Bot Online!</b>\n\nYour on-screen controller keyboard is active below. Tap any button to command your keys:",
                reply_markup=MAIN_KEYBOARD
            ))

    async def stop(self):
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.client:
            await self.client.aclose()
        logger.info("[Telegram Bot] Stopped long polling.")

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: Optional[dict] = None) -> bool:
        """Sends a message to a specific Telegram chat with optional custom keyboard."""
        if not self.client or not self.is_running:
            return False
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            resp = await self.client.post(url, json=payload, timeout=10.0)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"[Telegram Bot] Failed to send message to {chat_id}: {e}")
            return False

    async def send_audio_alert(self, chat_id: int, audio_bytes: bytes, filename: str = "find_phone_alarm.wav", caption: str = "") -> bool:
        """Sends an urgent alarm audio clip to the chat."""
        if not self.client or not self.is_running:
            return False
        try:
            url = f"{self.base_url}/sendAudio"
            files = {"audio": (filename, audio_bytes, "audio/wav")}
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
                "title": "🚨 FIND PHONE SIREN ALARM",
                "performer": "Key Finder Fob",
                "disable_notification": False
            }
            resp = await self.client.post(url, data=data, files=files, timeout=15.0)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"[Telegram Bot] Failed to send audio alert to {chat_id}: {e}")
            return False

    async def _poll_loop(self):
        offset = 0
        logger.info("[Telegram Bot] Long-poll loop initialized.")
        
        while self.is_running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": offset, "timeout": 25}
                response = await self.client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            offset = max(offset, update["update_id"] + 1)
                            await self._handle_update(update)
                elif response.status_code == 401:
                    logger.error("[Telegram Bot] Unauthorized: Invalid TELEGRAM_BOT_TOKEN. Stopping bot.")
                    self.is_running = False
                    break
                else:
                    logger.warning(f"[Telegram Bot] getUpdates returned HTTP {response.status_code}. Retrying in 5s...")
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Telegram Bot] Connection error during poll: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict):
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()

        # Security requirement: Only respond to chat IDs in ALLOWED_CHAT_IDS; ignore everyone else.
        if not self.allowed_chat_ids or chat_id not in self.allowed_chat_ids:
            logger.warning(f"[Telegram Bot] Ignored message from unauthorized chat ID: {chat_id}")
            return

        # Route commands or quick keyboard text taps
        normalized = text.lower()
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            if "@" in cmd:
                cmd = cmd.split("@")[0]

            logger.info(f"[Telegram Bot] Executing command '{cmd}' from chat {chat_id}")

            if cmd in ("/start", "/help"):
                await self._cmd_help(chat_id)
            elif cmd == "/ring":
                await self._cmd_ring(chat_id)
            elif cmd == "/status":
                await self._cmd_status(chat_id)
            elif cmd == "/lastseen":
                await self._cmd_lastseen(chat_id)
            elif cmd == "/stop":
                await self._cmd_stop(chat_id)
            else:
                await self.send_message(
                    chat_id,
                    "Unknown command. Tap a button below or send /help.",
                    reply_markup=MAIN_KEYBOARD
                )
        else:
            # Match keyboard button labels or quick voice/text inputs
            if "ring" in normalized:
                logger.info(f"[Telegram Bot] Button tap 'Ring' from chat {chat_id}")
                await self._cmd_ring(chat_id)
            elif "stop" in normalized:
                logger.info(f"[Telegram Bot] Button tap 'Stop' from chat {chat_id}")
                await self._cmd_stop(chat_id)
            elif "status" in normalized:
                logger.info(f"[Telegram Bot] Button tap 'Status' from chat {chat_id}")
                await self._cmd_status(chat_id)
            elif "last seen" in normalized or "lastseen" in normalized:
                logger.info(f"[Telegram Bot] Button tap 'Last Seen' from chat {chat_id}")
                await self._cmd_lastseen(chat_id)
            else:
                await self._cmd_help(chat_id)

    async def _cmd_help(self, chat_id: int):
        help_text = (
            "<b>🔑 Key Finder Bot Commands & Controls</b>\n\n"
            "Use the 1-tap buttons below or slash commands:\n"
            "• /ring or 🔔 <b>Ring Keys</b> — Activates the buzzer\n"
            "• /stop or ⏹️ <b>Stop</b> — Silences the buzzer immediately\n"
            "• /status or 📊 <b>Status</b> — Live Wi-Fi signal & connection state\n"
            "• /lastseen or 🕒 <b>Last Seen</b> — Exact last check-in time\n"
            "• /help — Show this command list\n\n"
            "<i>Tip: Press the physical button on your ESP32 anytime to trigger a 'Find Phone' alert here!</i>"
        )
        await self.send_message(chat_id, help_text, reply_markup=MAIN_KEYBOARD)

    async def _cmd_status(self, chat_id: int):
        status = get_device_status(self.default_device_id)
        online_str = "🟢 <b>ONLINE</b>" if status["online"] else "🔴 <b>OFFLINE</b>"
        
        last_seen = status["last_seen"]
        if last_seen:
            sec = status["seconds_since_last_seen"]
            last_seen_str = f"{sec} second{'s' if sec != 1 else ''} ago"
        else:
            last_seen_str = "Never"

        rssi = status["rssi"]
        rssi_str = f"{rssi} dBm ({status['rssi_quality']})" if rssi is not None else "N/A"
        
        uptime_sec = status["uptime"]
        hours = uptime_sec // 3600
        mins = (uptime_sec % 3600) // 60
        secs = uptime_sec % 60
        uptime_str = f"{hours}h {mins}m {secs}s" if hours > 0 else f"{mins}m {secs}s"

        msg = (
            f"<b>Device Status:</b> {online_str}\n"
            f"<b>Device ID:</b> <code>{self.default_device_id}</code>\n"
            f"<b>Last Seen:</b> {last_seen_str}\n"
            f"<b>Wi-Fi Signal:</b> {rssi_str}\n"
            f"<b>Uptime:</b> {uptime_str}\n"
            f"<b>Rings Today:</b> {status['rings_today']}"
        )
        await self.send_message(chat_id, msg, reply_markup=MAIN_KEYBOARD)

    async def _cmd_lastseen(self, chat_id: int):
        status = get_device_status(self.default_device_id)
        if not status["last_seen"]:
            await self.send_message(chat_id, "⚠️ Device has not checked in yet.", reply_markup=MAIN_KEYBOARD)
            return

        dt = datetime.fromisoformat(status["last_seen"])
        readable = dt.strftime("%B %d, %Y at %I:%M:%S %p UTC")
        sec = status["seconds_since_last_seen"]
        await self.send_message(
            chat_id,
            f"🕒 <b>Last Seen:</b> {readable}\n<i>({sec} second{'s' if sec != 1 else ''} ago)</i>",
            reply_markup=MAIN_KEYBOARD
        )

    async def _cmd_ring(self, chat_id: int):
        status_before = get_device_status(self.default_device_id)
        was_offline = not status_before["online"]

        # If offline, report when last seen and issue warning
        if was_offline:
            sec = status_before["seconds_since_last_seen"]
            last_seen_info = f"{sec} seconds ago" if sec is not None else "never"
            await self.send_message(
                chat_id,
                f"⚠️ <b>Warning:</b> Device appears <b>OFFLINE</b> (last seen {last_seen_info}).\n"
                f"Queueing ring command for when it reconnects...",
                reply_markup=MAIN_KEYBOARD
            )

        # Set ring flag
        set_ring_flag(self.default_device_id, source="telegram")
        await self.send_message(chat_id, "🔔 <b>Ringing your keys...</b>", reply_markup=MAIN_KEYBOARD)

        # Asynchronously monitor for device acknowledgment (heartbeat poll response + /api/ack)
        asyncio.create_task(self._wait_for_ring_ack(chat_id))

    async def _wait_for_ring_ack(self, chat_id: int):
        """Polls device state for up to 8 seconds to confirm the device rang."""
        start_time = datetime.now(timezone.utc)
        for _ in range(16): # 16 * 0.5s = 8 seconds
            await asyncio.sleep(0.5)
            status = get_device_status(self.default_device_id)
            if status.get("ring_acked_at"):
                ack_dt = datetime.fromisoformat(status["ring_acked_at"])
                if ack_dt >= start_time:
                    sec = status["seconds_since_last_seen"]
                    await self.send_message(
                        chat_id,
                        f"✅ <b>Keys rang!</b> Device acknowledged buzzer (last seen {sec}s ago).",
                        reply_markup=MAIN_KEYBOARD
                    )
                    return

    async def _cmd_stop(self, chat_id: int):
        stop_ringing(self.default_device_id, source="telegram")
        await self.send_message(chat_id, "⏹️ <b>Ring stopped.</b> Buzzer cancelled.", reply_markup=MAIN_KEYBOARD)

    async def send_find_phone_message(self):
        """Sends an urgent notification and loud alarm siren to all allowed chat IDs."""
        if not self.client or not self.is_running:
            logger.warning("[Telegram Bot] Cannot send find phone message: bot not running")
            return

        message = (
            "🚨🚨 <b>FIND PHONE ALERT!</b> 📱🔊\n\n"
            "The physical button on your <b>Key Finder</b> was pressed!\n"
            "<i>Your keys are looking for this phone!</i>"
        )

        for chat_id in self.allowed_chat_ids:
            try:
                # 1. Send the prominent alert message
                try:
                    await self.send_message(chat_id, message, reply_markup=MAIN_KEYBOARD)
                except TypeError:
                    await self.send_message(chat_id, message)

                # 2. Send the loud siren audio alarm
                if self.siren_audio_bytes:
                    await self.send_audio_alert(
                        chat_id,
                        self.siren_audio_bytes,
                        filename="Find_Phone_Siren.wav",
                        caption="🔊 <b>SIREN ALARM:</b> Play out loud to pinpoint phone location!"
                    )
                logger.info(f"[Telegram Bot] Find phone message + siren alert sent to chat {chat_id}")
            except Exception as e:
                logger.error(f"[Telegram Bot] Failed to send find phone message to {chat_id}: {e}")
