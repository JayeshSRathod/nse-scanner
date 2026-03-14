#!/usr/bin/env python3
"""Bot that logs to file"""
import sys
import time
import os

log_file = open(r'c:\Users\ratho\nse-scanner\bot_log.txt', 'w', buffering=1)

def log(msg):
    timestamp = time.strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    log_file.write(line + '\n')
    log_file.flush()
    print(line, flush=True)

log("Bot DEBUG starting...")

try:
    import config
    import requests
    import json
    from nse_telegram_handler import load_scan_results
    
    log(f"Config loaded: token={config.TELEGRAM_TOKEN[:20]}..., chat_id={config.TELEGRAM_CHATID}")
    
    results = load_scan_results()
    if not results:
        log("ERROR: No scan results")
        sys.exit(1)
    log(f"Scan results loaded: {len(results['stocks'])} stocks")
    
except Exception as e:
    log(f"ERROR: {e}")
    import traceback
    traceback.print_exc(file=log_file)
    sys.exit(1)

log("Starting polling loop...")
last_update_id = None
poll_count = 0

try:
    while True:
        poll_count += 1
        try:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
            params = {'timeout': 30, 'offset': last_update_id} if last_update_id else {'timeout': 30}
            
            log(f"Poll #{poll_count}: getUpdates...")
            response = requests.get(url, params=params, timeout=35)
            data = response.json()
            
            if data.get('ok'):
                updates = data.get('result', [])
                if updates:
                    log(f"Poll #{poll_count}: Got {len(updates)} updates")
                    for update in updates:
                        chat_id = update['message']['chat']['id'] if 'message' in update else 'unknown'
                        text = update['message'].get('text', '') if 'message' in update else ''
                        log(f"  FROM {chat_id}: {text}")
                        
                        if 'message' in update and text.startswith('/'):
                            log(f"  PROCESSING /start...")
                            send_url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
                            r = requests.post(send_url, data={'chat_id': chat_id, 'text': 'Bot is alive! /start received'}, timeout=5)
                            if r.status_code == 200:
                                log(f"  Message sent OK")
                            else:
                                log(f"  Message FAILED: {r.status_code}")
                        
                        last_update_id = update['update_id'] + 1
            else:
                log(f"getUpdates error: {data}")
                
        except Exception as e:
            log(f"Poll error: {e}")
            time.sleep(5)
        
except KeyboardInterrupt:
    log("User stopped bot")
finally:
    log_file.close()
