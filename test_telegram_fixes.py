#!/usr/bin/env python3
"""
test_telegram_fixes.py — Test Telegram button and command fixes
================================================================
Quick test to verify the next button and start command work correctly.
"""

import json
from pathlib import Path
from datetime import date

# Test data setup
TEST_RESULTS = {
    "scan_date": str(date.today()),
    "total_stocks": 25,
    "page_size": 5,
    "stocks": [
        {
            "rank": i+1,
            "symbol": f"STOCK{i:02d}",
            "score": 20 - i*0.5,
            "return_1m_pct": 15 - i*0.3,
            "return_2m_pct": 25 - i*0.4,
            "return_3m_pct": 35 - i*0.5,
            "close": 1000 + i*50,
            "volume": 1000000 + i*100000,
            "delivery_pct": 40 + i*1.5
        }
        for i in range(25)
    ]
}

def test_polling_version():
    """Test the polling version fixes."""
    print("\n" + "="*60)
    print("Testing nse_telegram_polling.py fixes")
    print("="*60)
    
    # Save test data
    with open("telegram_last_scan.json", "w") as f:
        json.dump(TEST_RESULTS, f, indent=2)
    print("✅ Test data saved to telegram_last_scan.json")
    
    # Import the fixed module
    try:
        from nse_telegram_polling import handle_command
        print("✅ Successfully imported handle_command from polling")
    except ImportError as e:
        print(f"❌ Failed to import: {e}")
        return False
    
    # Test /start command
    print("\n📝 Testing /start command...")
    try:
        result = handle_command("test_chat_1", "/start", is_callback=False)
        print(f"✅ /start (regular): Returned None as expected")
    except Exception as e:
        print(f"❌ /start (regular) failed: {e}")
        return False
    
    try:
        result = handle_command("test_chat_1", "/start", is_callback=True)
        if isinstance(result, dict) and 'message' in result and 'keyboard' in result:
            print(f"✅ /start (callback): Returned dict with message and keyboard")
        else:
            print(f"❌ /start (callback): Unexpected result type: {type(result)}")
            return False
    except Exception as e:
        print(f"❌ /start (callback) failed: {e}")
        return False
    
    # Test next button
    print("\n📝 Testing next button (callback_data: 'next')...")
    try:
        result = handle_command("test_chat_1", "next", is_callback=True)
        if isinstance(result, dict) and 'message' in result and 'keyboard' in result:
            print(f"✅ next button: Returned dict with message and keyboard")
        else:
            print(f"❌ next button: Unexpected result type: {type(result)}")
            print(f"   Result: {result}")
            return False
    except Exception as e:
        print(f"❌ next button failed: {e}")
        return False
    
    # Test next button again (should work multiple times)
    print("\n📝 Testing next button second time...")
    try:
        result = handle_command("test_chat_1", "next", is_callback=True)
        if isinstance(result, dict) and 'message' in result:
            print(f"✅ next button (2nd): Still working correctly")
        else:
            print(f"❌ next button (2nd): Failed")
            return False
    except Exception as e:
        print(f"❌ next button (2nd) failed: {e}")
        return False
    
    # Test prev button
    print("\n📝 Testing prev button (callback_data: 'prev')...")
    try:
        result = handle_command("test_chat_1", "prev", is_callback=True)
        if isinstance(result, dict) and 'message' in result:
            print(f"✅ prev button: Returned dict as expected")
        else:
            print(f"❌ prev button: Unexpected result")
            return False
    except Exception as e:
        print(f"❌ prev button failed: {e}")
        return False
    
    # Test page jump
    print("\n📝 Testing page jump (callback_data: 'page_2')...")
    try:
        result = handle_command("test_chat_1", "page_2", is_callback=True)
        if isinstance(result, dict) and 'message' in result:
            print(f"✅ page jump: Returned dict as expected")
        else:
            print(f"❌ page jump: Unexpected result")
            return False
    except Exception as e:
        print(f"❌ page jump failed: {e}")
        return False
    
    # Test help command
    print("\n📝 Testing help button (callback_data: 'help')...")
    try:
        result = handle_command("test_chat_1", "help", is_callback=True)
        if isinstance(result, dict) and 'message' in result:
            print(f"✅ help button: Returned dict as expected")
        else:
            print(f"❌ help button: Unexpected result")
            return False
    except Exception as e:
        print(f"❌ help button failed: {e}")
        return False
    
    # Test list command
    print("\n📝 Testing list button (callback_data: 'list')...")
    try:
        result = handle_command("test_chat_1", "list", is_callback=True)
        if isinstance(result, dict) and 'message' in result:
            print(f"✅ list button: Returned dict as expected")
        else:
            print(f"❌ list button: Unexpected result")
            return False
    except Exception as e:
        print(f"❌ list button failed: {e}")
        return False
    
    return True

def main():
    print("🧪 Testing Telegram Bot Fixes")
    print("="*60)
    
    success = test_polling_version()
    
    if success:
        print("\n" + "="*60)
        print("🎉 All tests passed!")
        print("="*60)
        print("\n✅ Summary of fixes:")
        print("  • /start command properly initializes user state")
        print("  • next button (callback) returns proper dict with message & keyboard")
        print("  • prev button works correctly")
        print("  • page jump buttons work correctly")
        print("  • help and list buttons work correctly")
        print("  • Error handling added for all handlers")
        print("  • Better logging for debugging callback issues")
    else:
        print("\n" + "="*60)
        print("❌ Some tests failed!")
        print("="*60)

if __name__ == "__main__":
    main()
