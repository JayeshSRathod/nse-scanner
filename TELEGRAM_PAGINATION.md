# Telegram Pagination System — NSE Scanner

## Overview

The NSE Momentum Scanner now supports full pagination through Telegram, allowing users to browse all 25 scanned stocks in groups of 5 using simple commands.

## Setup Instructions

### 1. Install Flask (Required for Webhook Server)

```bash
pip install flask
```

Or install from requirements:
```bash
pip install flask requests
```

### 2. Get Your Telegram Bot Token & Chat ID

Already set in `.env`:
- **TELEGRAM_TOKEN**: `8659199776:AAF2vBF4NadqSM5t4LTv87qpP--3Jk_IgUo`
- **TELEGRAM_CHATID**: `7872191203`

### 3. Set Up Webhook with Telegram

The webhook tells Telegram where to send incoming messages.

#### Option A: Using Setup Script (Recommended)

```bash
# Check your bot info
python setup_telegram_webhook.py --bot-info

# Set webhook to your server
python setup_telegram_webhook.py --set-webhook https://your-domain.com/webhook

# Check webhook status
python setup_telegram_webhook.py --info

# Delete webhook when done
python setup_telegram_webhook.py --delete-webhook
```

#### Option B: Manual Setup

1. Get your domain/URL (e.g., `https://example.com`)
2. Call Telegram API:
   ```
   https://api.telegram.org/bot8659199776:AAF2vBF4NadqSM5t4LTv87qpP--3Jk_IgUo/setWebhook?url=https://your-domain.com/webhook
   ```

#### Option C: Local Testing with ngrok

For local development, use ngrok to tunnel:

```bash
# Install ngrok: https://ngrok.com/download

# Start ngrok (open new terminal)
ngrok http 8080

# You'll see: "Forwarding https://abcd1234.ngrok.io -> http://localhost:8080"
# Use that URL with setup script:
python setup_telegram_webhook.py --set-webhook https://abcd1234.ngrok.io/webhook
```

### 4. Start the Webhook Server

```bash
# Production (port 8080, public)
python nse_telegram_webhook.py --port 8080

# Development (debug mode)
python nse_telegram_webhook.py --port 8080 --debug
```

## Available Telegram Commands

Once the webhook is running and configured:

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Show welcome + Top 5 stocks | `/start` |
| `/next` or `/continue` | Show next 5 stocks | `/next` |
| `/prev` | Show previous 5 stocks | `/prev` |
| `/page N` | Jump to page N | `/page 2` |
| `/list` | Show summary of all stocks | `/list` |
| `/help` | Show available commands | `/help` |

## Usage Examples

### Starting Pagination

Send to @nsescanner_bot on Telegram:
```
/start
```

Response:
```
📈 NSE Momentum Stocks (Showing 1-5 of 25)

#1. STOCK_A
Score: 15.2 | 1M: 8.5% | 3M: 22.1%
Close: ₹2450.50 | Vol: 2,500,000 | Deliv: 45.2%
─────────────────────────────────────────

📄 Page 1/5
👉 Use `/next` to see next 5 stocks
```

### Getting Next Page

Send:
```
/next
```

Response shows stocks 6-10 with `/prev` navigation option.

### Jump to Specific Page

Send:
```
/page 3
```

Shows stocks 11-15.

### View Summary

Send:
```
/list
```

Shows all 25 stocks in summary format with pagination info.

## Architecture

### Files

1. **nse_telegram_webhook.py**
   - Flask-based webhook server
   - Listens for Telegram messages
   - Handles `/start`, `/next`, `/prev`, `/page N` commands
   - Manages per-user pagination state (current page per chat_id)

2. **nse_telegram_handler.py**
   - `save_scan_results(df, date)` - Persists scanner results to `telegram_last_scan.json`
   - `load_scan_results()` - Loads saved results from JSON
   - `format_stock_list(stocks, start_idx, count)` - Formats 5 stocks per page with navigation
   - `format_help()` - Generates help message

3. **setup_telegram_webhook.py**
   - Helper script for webhook configuration
   - `--set-webhook URL` - Set webhook with Telegram API
   - `--info` - Check webhook status
   - `--bot-info` - Check bot details
   - `--test-local` - Test pagination locally

4. **nse_output.py** (Updated)
   - `generate_report()` now calls `save_scan_results()` after scanning
   - Sends top 5 stocks to Telegram with `/next` hint

5. **telegram_last_scan.json** (Generated)
   ```json
   {
     "scan_date": "2026-03-05",
     "total_stocks": 25,
     "page_size": 5,
     "stocks": [
       {
         "rank": 1,
         "symbol": "RELIANCE",
         "score": 15.2,
         "return_1m_pct": 8.5,
         "return_3m_pct": 22.1,
         "close": 2450.50,
         "volume": 2500000,
         "delivery_pct": 45.2
       },
       ...
     ]
   }
   ```

### Data Flow

```
nse_scanner.py (calculates 25 best stocks)
    ↓
nse_output.py (runs generate_report)
    ├→ save_excel() → XLS file
    └→ send_telegram() 
         ├→ save_scan_results() → telegram_last_scan.json
         └→ sends Top 5 to Telegram
    ↓
User sends /next command
    ↓
nse_telegram_webhook.py (receives via webhook)
    ├→ load_scan_results() from JSON
    ├→ format_stock_list() for page 2
    └→ sends response to Telegram
```

## State Management

User pagination state is stored in memory:

```python
user_state = {
    '7872191203': 1  # chat_id: current_page_number
}
```

- User starts at page 0 (stocks 1-5)
- Pressing `/next` increments to page 1 (stocks 6-10)
- Pressing `/prev` decrements page
- State resets when webhook server restarts

## Troubleshooting

### Webhook Not Working

1. Check webhook status:
   ```bash
   python setup_telegram_webhook.py --info
   ```

2. Verify Flask server is running:
   ```bash
   python nse_telegram_webhook.py --port 8080
   ```

3. Test locally:
   ```bash
   python setup_telegram_webhook.py --test-local
   ```

### Telegram Token Error (401)

1. Check `.env` file has correct token:
   ```bash
   grep TELEGRAM_TOKEN .env
   ```

2. Verify token with bot info:
   ```bash
   python setup_telegram_webhook.py --bot-info
   ```

3. Token should be: `8659199776:AAF2vBF4NadqSM5t4LTv87qpP--3Jk_IgUo`

### No Scan Results (telegram_last_scan.json not found)

1. Run the scanner first:
   ```bash
   python nse_scanner.py
   ```

2. Generate output (which saves pagination data):
   ```bash
   python nse_output.py
   ```

3. Verify JSON file exists:
   ```bash
   ls -la telegram_last_scan.json
   ```

### Commands Not Working

1. Ensure webhook is set:
   ```bash
   python setup_telegram_webhook.py --info
   # Should show your webhook URL
   ```

2. Send `/start` to reset user state

3. Check Flask console for errors

## Integration with Daily Runner

To automatically save pagination results when scanner runs:

```bash
# In nse_daily_runner.py or nse_scanner.py
python nse_output.py --date $(date +%Y-%m-%d)
```

This will:
1. Generate Excel report
2. Send Top 5 to Telegram
3. Save all 25 stocks to `telegram_last_scan.json` for pagination

## Advanced: Custom Domain Setup

For production, you'll need:

1. **Domain**: `example.com`
2. **SSL Certificate**: (Telegram requires HTTPS)
3. **Server**: Flask app running on public IP

```bash
# Set webhook to production domain
python setup_telegram_webhook.py --set-webhook https://example.com/webhook

# Start production server
python nse_telegram_webhook.py --port 8080
```

Then reverse proxy (nginx) to port 8080:

```nginx
server {
    server_name example.com;
    listen 443 ssl http2;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /webhook {
        proxy_pass http://localhost:8080/webhook;
    }
}
```

## Testing Locally

Without setting up a full webhook:

```bash
python setup_telegram_webhook.py --test-local
```

This shows pagination locally using test data, demonstrating format and navigation without needing Telegram connection.

## Summary

The pagination system enables users to:
- ✅ Browse all 25 scanned stocks in groups of 5
- ✅ Navigate forward (`/next`) and backward (`/prev`)
- ✅ Jump to specific pages (`/page 3`)
- ✅ View stock details (score, returns, price, volume, delivery%)
- ✅ Manage pagination state per user (multiple users can browse independently)
- ✅ Works with automated daily scans

All scan results are automatically saved and available for 24 hours (until next scan).
