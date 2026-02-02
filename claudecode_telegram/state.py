"""
State file management for claudecode-telegram.

Manages persistent state files in CLAUDE_DIR including:
- telegram_chat_id: Current active chat ID
- telegram_pending: Timestamp flag for Telegram-initiated messages
- telegram_webhook_url: Last configured webhook URL
"""
