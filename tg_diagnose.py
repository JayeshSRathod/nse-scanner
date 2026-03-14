"""
tg_diagnose.py — Telegram Bot Full Diagnostic
==============================================
Run this ONCE to find exactly why /start and inline buttons aren't working.

Usage:
    python tg_diagnose.py

What it does:
    1. Validates your token
    2. Deletes any registered webhook (which blocks polling)
    3. Clears pending updates (old /start taps that piled up)
    4. Checks telegram_last_scan.json exists and is valid
    5. Sends a live test message WITH an inline button to your chat
    6. Polls for 60 seconds — prints every raw update received
    7. Prints a final PASS/FAIL summary for each check

After running this you will know EXACTLY what to fix.
"""

import os
import sys
import json
import time

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

try:
    import config
    TOKEN   = config.TELEGRAM_TOKEN
    CHAT_ID = str(config.TELEGRAM_CHATID)
except Exception as e:
    print(f"ERROR: config.py problem: {e}")
    sys.exit(1)

BASE = f"https://api.telegram.org/bot{TOKEN}"

# ── results accumulator ───────────────────────────────────────
results = {}


def check(label, passed, detail=""):
    mark = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {mark}  {label}")
    if detail:
        print(f"          {detail}")
    results[label] = passed


# ─────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("  TELEGRAM BOT DIAGNOSTIC")
print("="*55)


# ── 1. Token valid? ───────────────────────────────────────────
print("\n[1] Checking token...")
try:
    r    = requests.get(f"{BASE}/getMe", timeout=5)
    data = r.json()
    if data.get("ok"):
        bot = data["result"]
        check("Token valid", True,
              f"@{bot['username']}  id={bot['id']}")
    else:
        check("Token valid", False, data.get("description", "unknown"))
        print("\nFix: Check TELEGRAM_TOKEN in config.py")
        sys.exit(1)
except Exception as e:
    check("Token valid", False, str(e))
    sys.exit(1)


# ── 2. Delete webhook ─────────────────────────────────────────
print("\n[2] Checking / deleting webhook...")
try:
    r    = requests.get(f"{BASE}/getWebhookInfo", timeout=5)
    info = r.json().get("result", {})
    wh   = info.get("url", "")
    if wh:
        print(f"  ⚠️  Webhook registered: {wh}")
        print("  Deleting webhook now...")
        del_r = requests.post(f"{BASE}/setWebhook", json={"url": ""}, timeout=5)
        if del_r.json().get("ok"):
            check("Webhook removed", True, "was blocking all updates — now deleted")
        else:
            check("Webhook removed", False, del_r.text[:100])
    else:
        check("No webhook blocking", True, "polling will work")
except Exception as e:
    check("Webhook check", False, str(e))


# ── 3. Clear pending updates ──────────────────────────────────
print("\n[3] Clearing any pending updates (old taps, old /start)...")
try:
    r = requests.get(f"{BASE}/getUpdates",
                     params={"timeout": 0, "offset": -1}, timeout=5)
    updates = r.json().get("result", [])
    if updates:
        last_id = updates[-1]["update_id"]
        requests.get(f"{BASE}/getUpdates",
                     params={"offset": last_id + 1, "timeout": 0}, timeout=5)
        check("Pending updates cleared", True, f"discarded {len(updates)} old update(s)")
    else:
        check("Pending updates cleared", True, "nothing pending")
except Exception as e:
    check("Clear updates", False, str(e))


# ── 4. Check JSON file ────────────────────────────────────────
print("\n[4] Checking telegram_last_scan.json...")

# Check both possible locations
_here        = os.path.dirname(os.path.abspath(__file__))
json_paths   = [
    os.path.join(_here, "telegram_last_scan.json"),   # same folder as script
    os.path.join(os.getcwd(), "telegram_last_scan.json"),  # cwd
]
json_found   = False
json_path_ok = None

for p in json_paths:
    if os.path.exists(p):
        try:
            with open(p) as f:
                j = json.load(f)
            stocks = j.get("stocks", [])
            sdate  = j.get("scan_date", "?")
            check("JSON file found", True,
                  f"{p}\n          stocks={len(stocks)}  date={sdate}")
            json_found   = True
            json_path_ok = p
            break
        except Exception as e:
            check("JSON file readable", False, f"{p} — {e}")

if not json_found:
    check("JSON file found", False,
          f"Not found in:\n"
          f"          {json_paths[0]}\n"
          f"          {json_paths[1]}\n"
          f"          Fix: run  python nse_output.py --test")


# ── 5. Send live test message with inline button ──────────────
print("\n[5] Sending test message with inline button to your chat...")
test_msg_id  = None
try:
    kb = {"inline_keyboard": [[
        {"text": "✅ TAP ME to test callbacks", "callback_data": "diag_test"},
    ]]}
    r = requests.post(f"{BASE}/sendMessage", data={
        "chat_id":      CHAT_ID,
        "text":         "🔧 DIAGNOSTIC TEST\n\nPlease tap the button below within 60 seconds:",
        "reply_markup": json.dumps(kb),
    }, timeout=10)
    if r.status_code == 200:
        test_msg_id = r.json()["result"]["message_id"]
        check("Test message sent", True,
              f"msg_id={test_msg_id}  chat={CHAT_ID}")
    else:
        check("Test message sent", False,
              f"HTTP {r.status_code}: {r.text[:200]}")
        print("\n  Fix options:")
        print("  • Wrong TELEGRAM_CHATID in config.py")
        print("  • You haven't started a conversation with your bot yet")
        print("  • Open Telegram, find your bot, send /start manually once")
except Exception as e:
    check("Test message sent", False, str(e))


# ── 6. Poll for 60 seconds ────────────────────────────────────
print("\n[6] Polling for 60 seconds — TAP THE BUTTON IN TELEGRAM NOW...")
print("    (watching for messages AND callback_queries)\n")

callback_received = False
message_received  = False
offset            = None
deadline          = time.time() + 60

while time.time() < deadline:
    remaining = int(deadline - time.time())
    try:
        r = requests.get(f"{BASE}/getUpdates", params={
            "timeout":         10,
            "offset":          offset,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }, timeout=15)
        data = r.json()

        if not data.get("ok"):
            print(f"  getUpdates error: {data}")
            time.sleep(2)
            continue

        updates = data.get("result", [])
        if not updates:
            print(f"  ... waiting ({remaining}s left)", end="\r")
            continue

        for upd in updates:
            offset = upd["update_id"] + 1
            print(f"\n  RAW UPDATE RECEIVED:")
            print(f"  {json.dumps(upd, indent=4)}")

            if "callback_query" in upd:
                cq   = upd["callback_query"]
                data_val = cq.get("data", "")
                from_id  = cq.get("from", {}).get("id")
                print(f"\n  🎉 CALLBACK QUERY received!")
                print(f"     data     = {data_val!r}")
                print(f"     from     = {from_id}")
                # Acknowledge it
                requests.post(f"{BASE}/answerCallbackQuery",
                              data={"callback_query_id": cq["id"],
                                    "text": "Diagnostic received! ✅"},
                              timeout=5)
                callback_received = True

            elif "message" in upd:
                txt = upd["message"].get("text", "")
                print(f"\n  📨 MESSAGE received: {txt!r}")
                message_received = True

    except Exception as e:
        print(f"\n  Poll error: {e}")
        time.sleep(2)

print("\n")
check("Callback query received", callback_received,
      "Button tap was received by polling" if callback_received
      else "No button tap received in 60s — see fixes below")
check("Message received", message_received,
      "Text message was received" if message_received
      else "No text message received (send /start in Telegram to test)")


# ── 7. Final summary ──────────────────────────────────────────
print("\n" + "="*55)
print("  DIAGNOSTIC SUMMARY")
print("="*55)
all_pass = True
for label, passed in results.items():
    mark     = "✅" if passed else "❌"
    all_pass = all_pass and passed
    print(f"  {mark}  {label}")

print("="*55)

if all_pass:
    print("\n  ALL CHECKS PASSED")
    print("  Your bot should work. Run: python nse_telegram_polling.py")
else:
    print("\n  FIX GUIDE:")
    if not results.get("Token valid"):
        print("  • Token wrong → check TELEGRAM_TOKEN in config.py")
    if not results.get("JSON file found"):
        print("  • No JSON → run:  python nse_output.py --test")
        print("                    then re-run this diagnostic")
    if not results.get("Test message sent"):
        print("  • Bot can't reach your chat → open Telegram, find your")
        print("    bot and send /start ONCE to initiate the conversation")
    if not results.get("Callback query received"):
        print("  • Callbacks not arriving:")
        print("    1. Did you tap the button in Telegram within 60s?")
        print("    2. Webhook may need more time to delete — wait 1 min")
        print("       then run: python tg_diagnose.py  again")
        print("    3. Only ONE instance of polling can run at a time")
        print("       Kill any other python processes running the bot")

print()