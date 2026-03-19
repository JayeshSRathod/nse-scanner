# main_bot.py

from nse_telegram_webhook import app

if __name__ == "__main__":
    print("🤖 Starting Telegram Webhook Bot...")
    app.run(host="0.0.0.0", port=8080)