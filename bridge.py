#!/usr/bin/env python3
"""Claude Code <-> Telegram Bridge - CLI entry point.

This is a thin wrapper that provides CLI interface to the bridge server.
All implementation logic lives in the claudecode_telegram package.
"""

import argparse
import json
import sys

from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.server import run_server
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.webhook import WebhookManager
from claudecode_telegram.state import StateManager


def main() -> int:
    """Main CLI entry point with subcommands for webhook management."""
    # Default webhook domain from environment or fallback
    import os
    default_domain = os.environ.get("WEBHOOK_DOMAIN", "coder.luandro.com")

    parser = argparse.ArgumentParser(description="Claude Code <-> Telegram Bridge")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Set webhook command
    webhook_parser = subparsers.add_parser("set-webhook", help="Set Telegram webhook")
    webhook_parser.add_argument(
        "--domain",
        default=default_domain,
        help=f"Webhook domain (default: {default_domain})"
    )

    # Get webhook info command
    subparsers.add_parser("get-webhook-info", help="Get current webhook info")

    # Verify webhook command
    subparsers.add_parser("verify-webhook", help="Verify webhook is properly configured")

    # Delete webhook command
    subparsers.add_parser("delete-webhook", help="Delete webhook")

    args = parser.parse_args()

    # Load configuration from environment
    config = BridgeConfig.from_env()

    # Validate bot token exists for all commands
    if not config.bot_token:
        print("Error: TELEGRAM_BOT_TOKEN not set", flush=True)
        return 1

    # Execute command
    if args.command == "set-webhook":
        # Create minimal instances for webhook management
        telegram = TelegramClient(config.bot_token)
        state = StateManager(config.claude_dir)
        webhook = WebhookManager(telegram, state, config)

        # Build webhook URL and set it
        webhook_url = f"https://{args.domain}/{config.webhook_path}"
        return 0 if webhook.set_webhook(webhook_url) else 1

    elif args.command == "get-webhook-info":
        # Get webhook info
        telegram = TelegramClient(config.bot_token)
        info = telegram.get_webhook_info()
        print(json.dumps(info, indent=2), flush=True)
        return 0

    elif args.command == "verify-webhook":
        # Verify webhook
        telegram = TelegramClient(config.bot_token)
        state = StateManager(config.claude_dir)
        webhook = WebhookManager(telegram, state, config)
        return 0 if webhook.verify() else 1

    elif args.command == "delete-webhook":
        # Delete webhook
        telegram = TelegramClient(config.bot_token)
        state = StateManager(config.claude_dir)
        webhook = WebhookManager(telegram, state, config)
        return 0 if webhook.delete_webhook() else 1

    else:
        # Default: run server (backward compatible, no subcommand)
        return run_server(config)


if __name__ == "__main__":
    sys.exit(main())
