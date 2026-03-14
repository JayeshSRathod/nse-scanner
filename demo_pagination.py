"""
demo_pagination.py — Interactive Pagination Demo
=================================================
Shows how pagination would work with all 25 stocks.

Run: python demo_pagination.py

This creates test data and lets you navigate through pages
exactly as users would via Telegram.
"""

import json
from nse_telegram_handler import format_stock_list, RESULTS_FILE


def demo():
    """Interactive pagination demo."""
    
    # Create demo data with 25 stocks
    demo_stocks = []
    for i in range(1, 26):
        demo_stocks.append({
            'rank': i,
            'symbol': f'STOCK{i:02d}',
            'score': round(25 - i * 0.5, 2),
            'return_1m_pct': round(20 - i * 0.3, 1),
            'return_2m_pct': round(30 - i * 0.4, 1),
            'return_3m_pct': round(35 - i * 0.5, 1),
            'close': round(500 + i * 10.5, 2),
            'volume': int(1000000 + i * 50000),
            'delivery_pct': round(40 + i * 0.3, 1)
        })
    
    # Save to JSON
    demo_data = {
        'scan_date': '2026-03-10',
        'total_stocks': 25,
        'page_size': 5,
        'stocks': demo_stocks
    }
    
    with open(RESULTS_FILE, 'w') as f:
        json.dump(demo_data, f, indent=2)
    
    # Demo navigation
    print("=" * 70)
    print("  🤖 NSE TELEGRAM PAGINATION DEMO")
    print("=" * 70)
    print(f"\n💾 Created {RESULTS_FILE} with 25 demo stocks\n")
    
    total_stocks = 25
    page_size = 5
    total_pages = (total_stocks + page_size - 1) // page_size
    
    current_page = 0
    
    while True:
        print("\n" + "=" * 70)
        print(f"  PAGE {current_page + 1} / {total_pages}")
        print("=" * 70)
        
        # Show current page
        message = format_stock_list(demo_stocks, current_page * page_size, page_size)
        print("\n" + message)
        
        # Navigation options
        print("=" * 70)
        print("📱 Available commands:")
        if current_page > 0:
            print("  [1] /prev     - Go to previous page")
        if current_page < total_pages - 1:
            print("  [2] /next     - Go to next page")
        print("  [3] /page N   - Go to specific page (1-{})".format(total_pages))
        print("  [4] /quit     - Exit demo")
        print("=" * 70)
        
        command = input("\nEnter command (or full command like '/next'): ").strip().lower()
        
        if command == '/quit' or command == '4':
            print("\n👋 Thanks for trying the pagination demo!")
            break
        elif command == '/next' or command == '2':
            if current_page < total_pages - 1:
                current_page += 1
                print(f"→ Moving to page {current_page + 1}")
            else:
                print("❌ Already on last page!")
        elif command == '/prev' or command == '1':
            if current_page > 0:
                current_page -= 1
                print(f"← Moving to page {current_page + 1}")
            else:
                print("❌ Already on first page!")
        elif command.startswith('/page ') or command.startswith('3'):
            try:
                if command.startswith('/page '):
                    page_num = int(command.split()[1]) - 1
                else:
                    page_num = int(input("Enter page number (1-{}): ".format(total_pages))) - 1
                
                if 0 <= page_num < total_pages:
                    current_page = page_num
                    print(f"→ Moving to page {current_page + 1}")
                else:
                    print(f"❌ Invalid page! Valid: 1-{total_pages}")
            except (ValueError, IndexError):
                print("❌ Invalid command")
        elif command in ['/start', 'start']:
            current_page = 0
            print("→ Moving to first page")
        elif command == '/help':
            print("""
📄 Available Commands:
  /start      - Go to first page
  /next       - Next 5 stocks
  /prev       - Previous 5 stocks
  /page N     - Jump to page N
  /list       - Show summary
  /quit       - Exit demo
            """)
        elif command == '/list':
            print(f"\n📊 Summary: {total_stocks} stocks scanned")
            print(f"Total pages: {total_pages}")
            print("\nBy rank:")
            for stock in demo_stocks:
                print(f"  #{stock['rank']:2d}. {stock['symbol']:10s} Score: {stock['score']:6.2f}")
        elif command == '':
            continue
        else:
            print(f"❌ Unknown command: '{command}'. Try /help")


if __name__ == "__main__":
    demo()
