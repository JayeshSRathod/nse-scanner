#!/usr/bin/env python3
"""
Minimal debug version of polling bot.
Prints everything to console including timestamps.
"""
import sys
import time
import requests
import json
import os

# Set output to unbuffered
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)

print(f"[{time.strftime('%H:%M:%S')}] Bot DEBUG starting...")
sys.stdout.flush()

try:
    import config
    print(f"[{time.strftime('%H:%M:%S')}] Config loaded")
    print(f"[{time.strftime('%H:%M:%S')}]   Token: {config.TELEGRAM_TOKEN[:20]}...")
    print(f"[{time.strftime('%H:%M:%S')}]   Chat ID: {config.TELEGRAM_CHATID}")
    sys.stdout.flush()
except Exception as e:
    print(f"[ERROR] Failed to load config: {e}")
    sys.stdout.flush()
    sys.exit(1)

try:
    from nse_telegram_handler import load_scan_results
    print(f"[{time.strftime('%H:%M:%S')}] Handler imported")
    results = load_scan_results()
    if results:
        print(f"[{time.strftime('%H:%M:%S')}] Scan results loaded: {len(results['stocks'])} stocks")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] ERROR: No scan results!")
    sys.stdout.flush()
except Exception as e:
    print(f"[ERROR] Handler load failed: {e}")
    sys.stdout.flush()
    sys.exit(1)

print(f"[{time.strftime('%H:%M:%S')}] Starting polling loop...")
sys.stdout.flush()

last_update_id = None
poll_count = 0

while True:
    poll_count += 1
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
        params = {'timeout': 30}
        if last_update_id:
            params['offset'] = last_update_id
        
        print(f"[{time.strftime('%H:%M:%S')}] Poll #{poll_count}: Calling getUpdates...", flush=True)
        
        response = requests.get(url, params=params, timeout=35)
        data = response.json()
        
        if data.get('ok'):
            updates = data.get('result', [])
            print(f"[{time.strftime('%H:%M:%S')}] Poll #{poll_count}: Got {len(updates)} updates", flush=True)
            
            if updates:
                for update in updates:
                    update_id = update.get('update_id')
                    print(f"[{time.strftime('%H:%M:%S')}] Update ID {update_id}:", flush=True)
                    
                    if 'message' in update:
                        msg = update['message']
                        chat_id = msg['chat']['id']
                        text = msg.get('text', '')
                        print(f"[{time.strftime('%H:%M:%S')}]   MESSAGE from {chat_id}: {text}", flush=True)
                        
                        # Send echo response
                        if text.startswith('/'):
                            print(f"[{time.strftime('%H:%M:%S')}]   COMMAND detected, sending response...", flush=True)
                            
                            if text == '/start' or text.startswith('/start@'):
                                send_url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
                                response = requests.post(send_url, data={
                                    'chat_id': chat_id,
                                    'text': 'Welcome! /start command received by bot.',
                                }, timeout=5)
                                if response.status_code == 200:
                                    print(f"[{time.strftime('%H:%M:%S')}]   Response sent OK", flush=True)
                                else:
                                    print(f"[{time.strftime('%H:%M:%S')}]   Response FAILED: {response.status_code}", flush=True)
                    
                    elif 'callback_query' in update:
                        cb = update['callback_query']
                        print(f"[{time.strftime('%H:%M:%S')}]   CALLBACK: {cb.get('data')}", flush=True)
                    
                    last_update_id = update_id + 1
        else:
            print(f"[{time.strftime('%H:%M:%S')}] Poll failed: {data}", flush=True)
        
    except KeyboardInterrupt:
        print(f"\n[{time.strftime('%H:%M:%S')}] Bot stopped by user", flush=True)
        break
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ERROR: {e}", flush=True)
        time.sleep(5)
