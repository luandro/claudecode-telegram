"""
Webhook setup and management.

Handles automatic webhook configuration with Telegram, including
change detection and URL updates when the webhook endpoint changes.
"""

import re
import time
import threading
from dataclasses import dataclass
from typing import Optional

from .telegram import TelegramClient
from .state import StateManager
from .config import BridgeConfig


@dataclass
class WebhookStatusCache:
    """Cache for webhook status to enable fast health checks without API calls.

    Attributes:
        configured: Whether webhook is currently configured
        url: Current webhook URL (None if not configured)
        last_check: Unix timestamp of last status check
        last_error: Last error message (None if no error)
    """
    configured: bool
    url: Optional[str]
    last_check: int
    last_error: Optional[str]


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
        self._status_cache = WebhookStatusCache(
            configured=False,
            url=None,
            last_check=0,
            last_error=None
        )
        self._status_lock = threading.Lock()

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
            print(f"Aborting auto-setup: Could not determine webhook URL for {self.config.deployment_mode} mode", flush=True)
            return False

        print(f"Target webhook URL: {webhook_url}", flush=True)

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
        tunnel_url = self._wait_for_tunnel_url(max_wait_seconds=120, poll_interval=2)

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

    def get_cached_status(self) -> WebhookStatusCache:
        """Get the cached webhook status (thread-safe).

        This provides fast access to webhook status without API calls.
        The cache is updated by the recovery loop.

        Returns:
            WebhookStatusCache with current cached status
        """
        with self._status_lock:
            return WebhookStatusCache(
                configured=self._status_cache.configured,
                url=self._status_cache.url,
                last_check=self._status_cache.last_check,
                last_error=self._status_cache.last_error
            )

    def _update_status_cache(
        self,
        configured: bool,
        url: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """Update the webhook status cache (thread-safe).

        Args:
            configured: Whether webhook is configured
            url: Current webhook URL (optional)
            error: Error message if any (optional)
        """
        with self._status_lock:
            self._status_cache.configured = configured
            self._status_cache.url = url
            self._status_cache.last_check = int(time.time())
            if error:
                self._status_cache.last_error = error
            elif configured:
                self._status_cache.last_error = None

    def _verify_and_update_cache(self) -> bool:
        """Verify webhook status with Telegram and update cache.

        Returns:
            True if webhook is properly configured, False otherwise
        """
        current_url = self.get_current_url()
        if current_url:
            self._update_status_cache(configured=True, url=current_url)
            return True
        else:
            self._update_status_cache(
                configured=False,
                error="No webhook configured in Telegram"
            )
            return False

    def start_recovery_loop(self, startup_delay: int = 5) -> threading.Thread:
        """Start the webhook recovery loop in a background thread.

        The recovery loop:
        1. Performs initial webhook setup after startup delay
        2. Periodically verifies webhook status with Telegram (60s interval)
        3. Re-configures webhook if tunnel URL changes (tunnel mode only)
        4. Automatically recovers from failures with exponential backoff (max 5 min)
        5. Updates the webhook status cache for fast health checks

        Args:
            startup_delay: Seconds to wait before initial setup (default: 5)

        Returns:
            The started daemon thread
        """
        def _recovery_loop():
            """Continuous loop that manages webhook configuration and monitors changes."""
            # Wait for services to initialize
            if startup_delay > 0:
                print(f"Waiting {startup_delay}s for services to initialize...", flush=True)
                time.sleep(startup_delay)

            # Initial setup
            result = self.auto_setup()
            if result is False:
                print("Warning: Webhook auto-setup failed - may need manual configuration", flush=True)
                print("Manual setup: set-webhook --domain <your-domain>", flush=True)
                self._update_status_cache(configured=False, error="Initial auto-setup failed")
            elif result is True:
                self._verify_and_update_cache()

            # Recovery loop settings
            check_interval = 60  # Check every 60 seconds
            max_backoff = 300  # Max 5 minutes between retries on failure
            current_backoff = check_interval
            last_tunnel_url = self.state.get_tunnel_url()

            while True:
                time.sleep(current_backoff)

                try:
                    # Check if tunnel URL changed (tunnel mode only)
                    if self.config.deployment_mode == "tunnel":
                        current_tunnel_url = self.state.get_tunnel_url()
                        if current_tunnel_url and current_tunnel_url != last_tunnel_url:
                            print(f"Tunnel URL changed: {last_tunnel_url} -> {current_tunnel_url}", flush=True)
                            last_tunnel_url = current_tunnel_url
                            # Re-run auto-setup with new URL
                            result = self.auto_setup()
                            if result:
                                self._verify_and_update_cache()
                                current_backoff = check_interval  # Reset backoff on success
                            else:
                                current_backoff = min(current_backoff * 2, max_backoff)
                            continue

                    # Periodic verification (all modes)
                    is_configured = self._verify_and_update_cache()

                    if not is_configured:
                        # Webhook not configured, try to set it up
                        print("Webhook not configured, attempting recovery...", flush=True)
                        result = self.auto_setup()
                        if result:
                            self._verify_and_update_cache()
                            current_backoff = check_interval
                        else:
                            current_backoff = min(current_backoff * 2, max_backoff)
                    else:
                        current_backoff = check_interval  # Reset backoff on success

                except Exception as e:
                    print(f"Error in webhook recovery loop: {e}", flush=True)
                    self._update_status_cache(configured=False, error=str(e))
                    current_backoff = min(current_backoff * 2, max_backoff)

        thread = threading.Thread(target=_recovery_loop, daemon=True)
        thread.start()
        return thread
