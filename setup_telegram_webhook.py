"""
setup_telegram_webhook.py — Configure Telegram Webhook
========================================================
Helper script to set up and test Telegram webhook for pagination.

Usage:
    1. Get webhook URL:
       python setup_telegram_webhook.py --get-url
    
    2. Set webhook with Telegram:
       python setup_telegram_webhook.py --set-webhook https://[YOUR_DOMAIN]/webhook
    
    3. Test webhook locally:
       python setup_telegram_webhook.py --test-local
    
    4. Check webhook info:
       python setup_telegram_webhook.py --info
"""

import requests
import json
import argparse
import sys

try:
    import config
except ImportError:
    print("ERROR: config.py not found.")
    sys.exit(1)


def get_bot_info():
    """Get bot info from Telegram."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getMe"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data['ok']:
            return data['result']
        else:
            print(f"Error: {data['description']}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def get_webhook_info():
    """Get webhook info from Telegram."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getWebhookInfo"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data['ok']:
            return data['result']
        else:
            print(f"Error: {data['description']}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def set_webhook(webhook_url):
    """Set webhook URL with Telegram."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/setWebhook"
    data = {'url': webhook_url}
    try:
        response = requests.post(url, json=data, timeout=5)
        result = response.json()
        if result['ok']:
            print(f"✅ Webhook set successfully: {webhook_url}")
            return True
        else:
            print(f"❌ Error: {result['description']}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def delete_webhook():
    """Delete webhook."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/setWebhook"
    data = {'url': ''}
    try:
        response = requests.post(url, json=data, timeout=5)
        result = response.json()
        if result['ok']:
            print("✅ Webhook deleted successfully")
            return True
        else:
            print(f"❌ Error: {result['description']}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_local():
    """Test pagination locally."""
    print("\n📝 Testing Telegram Handler Locally\n")
    
    try:
        from nse_telegram_handler import load_scan_results, format_stock_list, format_help
        
        results = load_scan_results()
        if not results:
            print("❌ No scan results found. Run nse_output.py first.")
            return
        
        stocks = results['stocks']
        page_size = results['page_size']
        total_pages = (len(stocks) + page_size - 1) // page_size
        
        print(f"✅ Loaded {len(stocks)} scanned stocks")
        print(f"   Total pages: {total_pages}")
        print(f"   Page size: {page_size}\n")
        
        # Show page 1
        print("📄 PAGE 1 (Stocks 1-5):")
        print(format_stock_list(stocks, 0, page_size))
        
        # Show page 2
        if total_pages > 1:
            print("\n📄 PAGE 2 (Stocks 6-10):")
            print(format_stock_list(stocks, 1 * page_size, page_size))
        
        # Show help
        print("\n" + "="*50)
        print(format_help())
        
    except ImportError as e:
        print(f"❌ Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Telegram Webhook Setup")
    
    parser.add_argument("--get-url", action="store_true", 
                       help="Show your bot's webhook URL format")
    parser.add_argument("--set-webhook", metavar="URL", 
                       help="Set webhook URL")
    parser.add_argument("--delete-webhook", action="store_true",
                       help="Delete webhook")
    parser.add_argument("--info", action="store_true",
                       help="Show webhook info")
    parser.add_argument("--bot-info", action="store_true",
                       help="Show bot info")
    parser.add_argument("--test-local", action="store_true",
                       help="Test pagination locally")
    
    args = parser.parse_args()
    
    if args.get_url:
        print("\n🔗 Webhook URL Format:")
        print(f"https://[YOUR_DOMAIN]/webhook")
        print("\nExample (for local ngrok tunnel):")
        print("https://abcd1234.ngrok.io/webhook")
        
    elif args.set_webhook:
        print(f"\n🔧 Setting webhook to: {args.set_webhook}")
        set_webhook(args.set_webhook)
        
    elif args.delete_webhook:
        print("\n🔧 Deleting webhook...")
        delete_webhook()
        
    elif args.info:
        print("\n📊 Webhook Info:")
        info = get_webhook_info()
        if info:
            print(json.dumps(info, indent=2))
            
    elif args.bot_info:
        print("\n🤖 Bot Info:")
        info = get_bot_info()
        if info:
            print(json.dumps(info, indent=2))
            
    elif args.test_local:
        test_local()
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
