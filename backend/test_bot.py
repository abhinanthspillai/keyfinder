"""
Unit tests for the Telegram bot command parser and authorization logic.
"""

import sys
import os
import asyncio
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(__file__))

from bot import TelegramBotService
import db

async def run_bot_tests():
    print(">>> Testing Telegram Bot Service <<<")
    bot = TelegramBotService(
        token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        allowed_chat_ids=[999111],
        default_device_id="esp32_keys_01"
    )
    bot.client = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)
    bot.is_running = True

    # Test 1: Unauthorized Chat ID should be completely ignored
    print("[1] Testing Unauthorized Chat...")
    unauth_update = {
        "update_id": 101,
        "message": {
            "chat": {"id": 888222},
            "text": "/ring"
        }
    }
    await bot._handle_update(unauth_update)
    assert bot.send_message.call_count == 0, "Unauthorized chat must NOT trigger messages"
    print("    PASSED: Unauthorized chat ignored")

    # Test 2: Help command
    print("[2] Testing /help command...")
    help_update = {
        "update_id": 102,
        "message": {
            "chat": {"id": 999111},
            "text": "/help"
        }
    }
    await bot._handle_update(help_update)
    assert bot.send_message.call_count == 1
    assert "Key Finder Bot Commands" in bot.send_message.call_args[0][1]
    print("    PASSED: /help replied with commands")

    # Test 3: /status command
    print("[3] Testing /status command...")
    bot.send_message.reset_mock()
    status_update = {
        "update_id": 103,
        "message": {
            "chat": {"id": 999111},
            "text": "/status"
        }
    }
    await bot._handle_update(status_update)
    assert bot.send_message.call_count == 1
    assert "Device Status" in bot.send_message.call_args[0][1]
    print("    PASSED: /status returned formatted device status")

    # Test 4: /ring command
    print("[4] Testing /ring command...")
    bot.send_message.reset_mock()
    ring_update = {
        "update_id": 104,
        "message": {
            "chat": {"id": 999111},
            "text": "/ring"
        }
    }
    await bot._handle_update(ring_update)
    # Checks device status, sends ring message
    assert bot.send_message.call_count >= 1
    state = db.get_device_status("esp32_keys_01")
    assert state["pending_ring"] is True
    print("    PASSED: /ring scheduled ring flag in database")

    # Test 5: /stop command
    print("[5] Testing /stop command...")
    bot.send_message.reset_mock()
    stop_update = {
        "update_id": 105,
        "message": {
            "chat": {"id": 999111},
            "text": "/stop"
        }
    }
    await bot._handle_update(stop_update)
    assert bot.send_message.call_count == 1
    assert "stopped" in bot.send_message.call_args[0][1].lower()
    state = db.get_device_status("esp32_keys_01")
    assert state["pending_ring"] is False
    print("    PASSED: /stop cleared ring flag")

    # Test 6: send_find_phone_message
    print("[6] Testing send_find_phone_message...")
    bot.send_message.reset_mock()
    # Mock the send_message calls within send_find_phone_message
    original_send = bot.send_message
    call_count = 0

    async def counting_send(chat_id, text, parse_mode="HTML"):
        nonlocal call_count
        call_count += 1
        return True

    bot.send_message = counting_send
    await bot.send_find_phone_message()
    assert call_count == 1  # Should send to 1 chat ID
    bot.send_message = original_send
    print("    PASSED: send_find_phone_message sends to all allowed chats")

    print("\n=======================================================")
    print("   ALL TELEGRAM BOT TESTS PASSED FLAWLESSLY!          ")
    print("=======================================================")

if __name__ == "__main__":
    asyncio.run(run_bot_tests())
