"""
Webhook setup and management.

Handles automatic webhook configuration with Telegram, including
change detection and URL updates when the webhook endpoint changes.
"""

import re
import time
from typing import Optional

from .telegram import TelegramClient
from .state import StateManager
from .config import BridgeConfig


def _is_valid_domain(domain: str) -> bool:
    """Basic domain name validation.

    Args:
        domain: Domain name to validate (e.g., 'example.com', 'sub.example.com')

    Returns:
        True if domain format is valid, False otherwise
    """
    if not domain or len(domain) > 253:
        return False
    # Basic pattern: alphanumeric + hyphens + dots, proper TLD
    pattern = r'^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$'
    return bool(re.match(pattern, domain.lower()))


class WebhookManager:
    """Manages webhook setup and verification with Telegram.

    Handles automatic webhook configuration, URL change detection,
    and verification of webhook status.
    """

    def __init__(
        self,
        telegram: TelegramClient,
        state: StateManager,
        config: BridgeConfig
    ):
        """Initialize the webhook manager.

        Args:
            telegram: TelegramClient instance for API calls
            state: StateManager instance for file-based state
            config: BridgeConfig instance with deployment settings
        """
        self.telegram = telegram
        self.state = state
        self.config = config

    def get_current_url(self) -> Optional[str]:
        """Get currently configured webhook URL from Telegram.

        Returns:
            Current webhook URL string, or None if no webhook is set or on error
        """
        info = self.telegram.get_webhook_info()
        if not info:
            print("Warning: Failed to query Telegram webhook status", flush=True)
            return None

        url = info.get("url", "").strip()

        # Check for webhook errors
        if info.get("last_error_date"):
            last_error_msg = info.get("last_error_message", "Unknown error")
            error_age = int(time.time()) - info.get("last_error_date", 0)
            if error_age < 3600:  # Recent error (within last hour)
                print(f"Warning: Recent webhook error ({error_age}s ago): {last_error_msg}", flush=True)

        return url if url else None

    def set_webhook(self, url: str) -> bool:
        """Set the Telegram webhook URL.

        Args:
            url: Full webhook URL to register (must be HTTPS)

        Returns:
            True if successful, False otherwise
        """
        success = self.telegram.set_webhook(
            url=url,
            secret=self.config.telegram_webhook_secret or None,
            max_connections=100
        )

        if success:
            self.state.set_webhook_url(url)

        return success

    def delete_webhook(self) -> bool:
        """Delete the current webhook.

        Returns:
            True if successful, False otherwise
        """
        success = self.telegram.delete_webhook(drop_pending=True)

        if success:
            self.state.clear_webhook_url()

        return success

    def verify(self) -> bool:
        """Verify that the webhook is properly configured and reports OK status.

        Returns:
            True if webhook is properly configured, False otherwise
        """
        info = self.telegram.get_webhook_info()
        if not info:
            print("Failed to get webhook info: No response from Telegram API")
            return False

        url = info.get("url", "")
        pending_count = info.get("pending_update_count", 0)
        last_error = info.get("last_error_date", 0)

        # Check if webhook URL is set
        if not url:
            print("Webhook not configured: No URL set")
            return False

        # Check for pending updates (may indicate delivery issues)
        if pending_count > 0:
            print(f"Warning: {pending_count} pending updates")

        # Check for recent errors
        if last_error:
            error_age = int(time.time()) - last_error
            if error_age < 3600:  # Error in the last hour
                print(f"Warning: Recent webhook error ({error_age} seconds ago)")

        print(f"Webhook OK: {url}")
        return True

    def is_configured(self) -> bool:
        """Check if webhook appears to be configured.

        This is a quick local check that doesn't hit the Telegram API.
        For verification with Telegram, use verify() instead.

        Returns:
            True if webhook URL is stored locally, False otherwise
        """
        return self.state.get_webhook_url() is not None

    def auto_setup(self) -> Optional[bool]:
        """Auto-configure Telegram webhook based on deployment mode.

        This function:
        1. Checks if auto-setup is enabled
        2. Validates deployment mode
        3. Determines webhook URL based on mode (tunnel vs production)
        4. Validates against actual Telegram webhook status
        5. Only re-registers if URL has changed in Telegram

        Returns:
            True if configured successfully
            False if attempted but failed
            None if auto-setup is disabled
        """
        # Check if auto-setup is enabled
        if not self.config.webhook_auto_setup:
            print("Webhook auto-setup disabled via WEBHOOK_AUTO_SETUP", flush=True)
            return None

        # Validate deployment mode
        if not self.config.deployment_mode:
            print("ERROR: DEPLOYMENT_MODE not set", flush=True)
            print("Please set DEPLOYMENT_MODE to 'tunnel' or 'production' in your .env file", flush=True)
            print("See .env.example for configuration instructions", flush=True)
            return False

        if self.config.deployment_mode not in ("tunnel", "production"):
            print(f"ERROR: Invalid DEPLOYMENT_MODE='{self.config.deployment_mode}'", flush=True)
            print("Valid options: 'tunnel' or 'production'", flush=True)
            return False

        print(f"Auto-setup webhook for deployment mode: {self.config.deployment_mode}", flush=True)

        # Get local state
        last_webhook_url = self.state.get_webhook_url()

        # Determine webhook URL based on deployment mode
        webhook_url = self._get_webhook_url_for_mode()
        if not webhook_url:
            return False

        # Query actual Telegram webhook status
        current_telegram_webhook = self.get_current_url()

        # Clean up stale state file if it doesn't match Telegram reality
        if last_webhook_url and not current_telegram_webhook:
            print("Warning: State file exists but webhook not in Telegram (cleaning stale state)", flush=True)
            self.state.clear_webhook_url()

        # Check if webhook is already correctly configured in Telegram
        if current_telegram_webhook == webhook_url:
            print(f"Webhook already configured in Telegram: {webhook_url}", flush=True)
            # Update state file to match reality
            self.state.set_webhook_url(webhook_url)
            return True

        # Webhook needs to be set/updated
        if current_telegram_webhook:
            print(f"Webhook URL change detected:", flush=True)
            print(f"  Current: {current_telegram_webhook}", flush=True)
            print(f"  New:     {webhook_url}", flush=True)
        else:
            print(f"No webhook configured in Telegram, setting: {webhook_url}", flush=True)

        # Set webhook
        return self.set_webhook(webhook_url)

    def _get_webhook_url_for_mode(self) -> Optional[str]:
        """Get webhook URL based on deployment mode.

        Returns:
            Webhook URL string, or None if unable to determine
        """
        if self.config.deployment_mode == "tunnel":
            return self._get_tunnel_webhook_url()
        else:  # production
            return self._get_production_webhook_url()

    def _get_tunnel_webhook_url(self) -> Optional[str]:
        """Get webhook URL for tunnel mode.

        Waits for cloudflared tunnel URL to be available.

        Returns:
            Webhook URL string, or None if tunnel not available
        """
        print("Waiting for cloudflared tunnel URL...", flush=True)
        tunnel_url = self._wait_for_tunnel_url(max_wait_seconds=60, poll_interval=2)

        if not tunnel_url:
            print("Failed to get tunnel URL - webhook not configured", flush=True)
            print("You can manually set webhook with: docker compose exec bridge python bridge.py set-webhook --domain <your-domain>", flush=True)
            return None

        return f"{tunnel_url}/{self.config.webhook_path}"

    def _get_production_webhook_url(self) -> Optional[str]:
        """Get webhook URL for production mode.

        Returns:
            Webhook URL string, or None if domain not configured or invalid
        """
        domain = self.config.webhook_domain

        if not domain:
            print("ERROR: WEBHOOK_DOMAIN not set for production mode", flush=True)
            print("Production mode requires a valid domain name", flush=True)
            print("Example: WEBHOOK_DOMAIN=coder.luandro.com", flush=True)
            print("Alternatively, use DEPLOYMENT_MODE=tunnel for local development", flush=True)
            return None

        # Validate domain format
        if not _is_valid_domain(domain):
            print(f"ERROR: Invalid WEBHOOK_DOMAIN format: {domain}", flush=True)
            print("Domain should be in format: example.com or subdomain.example.com", flush=True)
            return None

        return f"https://{domain}/{self.config.webhook_path}"

    def _wait_for_tunnel_url(
        self,
        max_wait_seconds: int = 60,
        poll_interval: int = 2
    ) -> Optional[str]:
        """Wait for cloudflared tunnel URL to be available.

        Args:
            max_wait_seconds: Maximum time to wait for tunnel URL
            poll_interval: Seconds between file checks

        Returns:
            Tunnel URL string or None if not found within timeout
        """
        deadline = time.time() + max_wait_seconds

        while time.time() < deadline:
            tunnel_url = self.state.get_tunnel_url()
            if tunnel_url:
                return tunnel_url
            time.sleep(poll_interval)

        return None
