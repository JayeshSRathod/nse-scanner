#!/usr/bin/env python3
"""
verify_system.py — NSE Scanner System Verification
====================================================
Comprehensive system check to verify all components are working.

Run: python verify_system.py

This script checks:
- Python version and required packages
- Configuration files
- Database connectivity
- Telegram bot configuration
- File structure
- Execution of key functions
"""

import os
import sys
from pathlib import Path
from datetime import date

def print_header(title):
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_check(name, status, detail=""):
    """Print check result."""
    symbol = "✅" if status else "❌"
    print(f"{symbol} {name}")
    if detail:
        print(f"   └─ {detail}")

def check_python():
    """Check Python version."""
    print_header("PYTHON ENVIRONMENT")
    version = sys.version_info
    status = version.major == 3 and version.minor >= 9
    print_check(f"Python {version.major}.{version.minor}.{version.micro}", status)
    return status

def check_packages():
    """Check required packages."""
    print_header("REQUIRED PACKAGES")
    
    packages = {
        'pandas': 'Data processing',
        'requests': 'HTTP requests',
        'openpyxl': 'Excel file creation',
        'flask': 'Webhook server',
        'sqlite3': 'Database (built-in)',
        'dotenv': 'Environment configuration'
    }
    
    all_ok = True
    for pkg, desc in packages.items():
        try:
            if pkg == 'sqlite3':
                import sqlite3
            elif pkg == 'dotenv':
                import dotenv
            else:
                __import__(pkg)
            print_check(f"{pkg:15s} {desc}", True)
        except ImportError:
            print_check(f"{pkg:15s} {desc}", False, "Not installed. Run: pip install " + pkg)
            all_ok = False
    
    return all_ok

def check_config():
    """Check configuration files."""
    print_header("CONFIGURATION")
    
    all_ok = True
    
    # Check .env file
    env_exists = os.path.exists('.env')
    print_check(".env file", env_exists)
    
    if env_exists:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            import os as os_check
            
            token = os_check.getenv('TELEGRAM_TOKEN')
            chat_id = os_check.getenv('TELEGRAM_CHAT_ID')
            
            print_check("TELEGRAM_TOKEN set", bool(token), 
                       f"Token length: {len(token) if token else 0}")
            print_check("TELEGRAM_CHAT_ID set", bool(chat_id), 
                       f"Chat ID: {chat_id if chat_id else 'Not set'}")
        except Exception as e:
            print_check("Load .env", False, str(e))
            all_ok = False
    else:
        all_ok = False
    
    # Check config.py
    config_exists = os.path.exists('config.py')
    print_check("config.py file", config_exists)
    
    if config_exists:
        try:
            import config
            print_check("config.py imports", True, 
                       f"Version: {config.__name__}")
        except Exception as e:
            print_check("config.py imports", False, str(e))
            all_ok = False
    
    return all_ok

def check_database():
    """Check database."""
    print_header("DATABASE")
    
    all_ok = True
    
    # Check database file
    db_exists = os.path.exists('nse_scanner.db')
    print_check("nse_scanner.db exists", db_exists)
    
    if db_exists:
        try:
            import sqlite3
            conn = sqlite3.connect('nse_scanner.db')
            cursor = conn.cursor()
            
            # Check tables
            tables = {
                'daily_prices': 'Stock prices',
                'blacklist': 'Blacklisted stocks',
                'index_perf': 'Index performance'
            }
            
            for table, desc in tables.items():
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print_check(f"{table:20s} {desc}", True, f"{count:,} records")
            
            conn.close()
        except Exception as e:
            print_check("Database connectivity", False, str(e))
            all_ok = False
    
    return db_exists and all_ok

def check_files():
    """Check required files."""
    print_header("PROJECT FILES")
    
    files = {
        'core': [
            'nse_historical_downloader.py',
            'nse_parser.py',
            'nse_loader.py',
            'nse_scanner.py',
            'nse_output.py'
        ],
        'telegram': [
            'nse_telegram_handler.py',
            'nse_telegram_webhook.py',
            'setup_telegram_webhook.py'
        ],
        'demo': [
            'demo_pagination.py'
        ],
        'docs': [
            'DEPLOY.md',
            'TELEGRAM_PAGINATION.md',
            'PROJECT_COMPLETE.md',
            'INDEX.md'
        ]
    }
    
    all_ok = True
    for category, file_list in files.items():
        print(f"\n{category.upper()} FILES:")
        for filename in file_list:
            exists = os.path.exists(filename)
            print_check(filename, exists)
            if not exists:
                all_ok = False
    
    return all_ok

def check_pagination():
    """Check pagination system."""
    print_header("PAGINATION SYSTEM")
    
    all_ok = True
    
    # Check telegram handler
    try:
        from nse_telegram_handler import (
            load_scan_results,
            save_scan_results,
            format_stock_list,
            format_help
        )
        print_check("Pagination functions", True, "All 4 functions importable")
        
        # Check if pagination data exists
        pagination_exists = os.path.exists('telegram_last_scan.json')
        print_check("telegram_last_scan.json", pagination_exists, 
                   "Generated by scanner or --test")
        
    except ImportError as e:
        print_check("Pagination functions", False, str(e))
        all_ok = False
    
    return all_ok

def check_telegram_bot():
    """Check Telegram bot configuration."""
    print_header("TELEGRAM BOT")
    
    all_ok = True
    
    try:
        import config
        import requests
        
        token = config.TELEGRAM_TOKEN
        chat_id = config.TELEGRAM_CHATID
        
        print_check("Bot token configured", bool(token))
        print_check("Chat ID configured", bool(chat_id))
        
        # Test bot connectivity
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    bot_info = data.get('result', {})
                    bot_name = bot_info.get('first_name', 'Unknown')
                    print_check("Bot accessible", True, f"Name: {bot_name}")
                else:
                    print_check("Bot accessible", False, data.get('description', 'Unknown error'))
                    all_ok = False
            else:
                print_check("Bot accessible", False, f"HTTP {response.status_code}")
                all_ok = False
        except requests.exceptions.Timeout:
            print_check("Bot accessible", False, "Connection timeout")
            all_ok = False
        except Exception as e:
            print_check("Bot accessible", False, str(e))
            all_ok = False
            
    except Exception as e:
        all_ok = False
    
    return all_ok

def check_webhooks():
    """Check webhook configuration."""
    print_header("WEBHOOK SERVER")
    
    all_ok = True
    
    try:
        from nse_telegram_webhook import app, send_message, handle_command
        print_check("Webhook server imports", True, "Flask app configured")
        
        # Check Flask routes
        routes = ['/webhook', '/health']
        for route in routes:
            if any(route in str(rule) for rule in app.url_map.iter_rules()):
                print_check(f"Route {route:15s}", True)
            else:
                print_check(f"Route {route:15s}", False)
                all_ok = False
    except ImportError as e:
        print_check("Webhook server imports", False, str(e))
        all_ok = False
    except Exception as e:
        print_check("Webhook setup", False, str(e))
        all_ok = False
    
    return all_ok

def check_directories():
    """Check directory structure."""
    print_header("DIRECTORIES")
    
    dirs = {
        'nse_data': 'Downloaded NSE data',
        'output': 'Generated Excel reports',
        'logs': 'Application logs',
        'tests': 'Test files'
    }
    
    all_ok = True
    for dirname, desc in dirs.items():
        exists = os.path.isdir(dirname)
        print_check(f"{dirname:15s} {desc}", exists)
        if not exists:
            all_ok = False
    
    return all_ok

def check_syntax():
    """Check Python syntax of all files."""
    print_header("PYTHON SYNTAX")
    
    py_files = [
        'config.py',
        'nse_historical_downloader.py',
        'nse_parser.py',
        'nse_loader.py',
        'nse_scanner.py',
        'nse_output.py',
        'nse_telegram_handler.py',
        'nse_telegram_webhook.py',
        'setup_telegram_webhook.py',
        'demo_pagination.py'
    ]
    
    import py_compile
    all_ok = True
    
    for filename in py_files:
        if os.path.exists(filename):
            try:
                py_compile.compile(filename, doraise=True)
                print_check(filename, True)
            except py_compile.PyCompileError as e:
                print_check(filename, False, f"Syntax error: {e}")
                all_ok = False
        else:
            print_check(filename, False, "File not found")
            all_ok = False
    
    return all_ok

def main():
    """Run all checks."""
    print("\n" + "=" * 70)
    print("  NSE MOMENTUM SCANNER — SYSTEM VERIFICATION")
    print("=" * 70)
    print(f"\nDate: {date.today()}")
    print(f"Python: {sys.version}")
    print(f"Working Directory: {os.getcwd()}")
    
    results = {
        'Python Environment': check_python(),
        'Required Packages': check_packages(),
        'Configuration': check_config(),
        'Directories': check_directories(),
        'Project Files': check_files(),
        'Python Syntax': check_syntax(),
        'Database': check_database(),
        'Pagination System': check_pagination(),
        'Telegram Bot': check_telegram_bot(),
        'Webhook Server': check_webhooks(),
    }
    
    # Summary
    print_header("SUMMARY")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed
    
    for check, status in results.items():
        symbol = "✅" if status else "❌"
        print(f"{symbol} {check}")
    
    print("")
    print(f"Result: {passed}/{total} checks passed")
    
    if failed == 0:
        print("\n🎉 ALL SYSTEMS OPERATIONAL!")
        print("\nYou can now:")
        print("  • Run: python nse_scanner.py")
        print("  • Deploy: python nse_telegram_webhook.py --port 8080")
        print("  • Test: python setup_telegram_webhook.py --test-local")
        return 0
    else:
        print(f"\n⚠️  {failed} checks failed. See above for details.")
        print("\nTo resolve:")
        print("  1. Check error messages above")
        print("  2. Review DEPLOY.md for setup instructions")
        print("  3. Run: pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
