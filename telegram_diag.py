"""
telegram_diag.py — simulate Telegram updates to diagnose bot
==========================================================
Sends fake update objects through the handler functions to see exactly what
responses the code produces.  Useful when the bot doesn't appear to react in
Telegram.

Usage:
    python telegram_diag.py
"""
import json
from nse_telegram_polling import process_update, handle_command
from datetime import date

# prepare minimal scan results so handler has data
from nse_telegram_handler import save_scan_results
import pandas as pd

save_scan_results(pd.DataFrame([{'symbol':'TEST','score':1}]), date.today())

# fake message update
message_update = {
    'update_id': 10000,
    'message': {
        'message_id': 1,
        'from': {'id': 12345, 'is_bot': False, 'first_name': 'Tester'},
        'chat': {'id': 12345, 'type': 'private'},
        'date': int(date.today().strftime('%s')),
        'text': '/start@nsescanner_bot'
    }
}

# fake callback update
callback_update = {
    'update_id': 10001,
    'callback_query': {
        'id': 'abc123',
        'from': {'id': 12345, 'is_bot': False, 'first_name': 'Tester'},
        'message': {'message_id': 1, 'chat': {'id': 12345, 'type': 'private'}},
        'data': 'next'
    }
}

print("\n--- Processing message update ---")
process_update(message_update)
print("\n--- Processing callback update ---")
process_update(callback_update)
