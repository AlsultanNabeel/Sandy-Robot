def prepare_telegram_polling(telegram_bot):
    try:
        telegram_bot.remove_webhook()
        print("[Telegram] Webhook removed for local polling mode.")
    except Exception as e:
        print(f"[Telegram] Failed to remove webhook: {e}")


def set_telegram_webhook(
    telegram_bot,
    telegram_bot_token: str,
    railway_url: str,
    webhook_path: str,
    telegram_secret_token: str = "",
):
    if not telegram_bot_token or not railway_url:
        print("[Webhook] TELEGRAM_BOT_TOKEN or RAILWAY_URL not set!")
        return

    webhook_url = railway_url
    if not webhook_url.startswith("http"):
        webhook_url = "https://" + webhook_url
    webhook_url = webhook_url.rstrip("/") + webhook_path

    print(f"[Webhook] Setting webhook to: {webhook_url}")
    telegram_bot.remove_webhook()
    telegram_bot.set_webhook(
        url=webhook_url,
        secret_token=telegram_secret_token if telegram_secret_token else None,
    )