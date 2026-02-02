"""Tests for webhook management."""

import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from claudecode_telegram.webhook import WebhookManager, WebhookStatusCache, _is_valid_domain
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.state import StateManager
from claudecode_telegram.config import BridgeConfig


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock configuration."""
    config = MagicMock(spec=BridgeConfig)
    config.claude_dir = tmp_path
    config.webhook_path = "test_webhook_path"
    config.telegram_webhook_secret = "test_secret"
    config.webhook_auto_setup = True
    config.deployment_mode = "production"
    config.webhook_domain = "example.com"
    return config


@pytest.fixture
def mock_telegram():
    """Create a mock Telegram client."""
    return MagicMock(spec=TelegramClient)


@pytest.fixture
def state_manager(tmp_path):
    """Create a StateManager with temporary directory."""
    return StateManager(tmp_path)


@pytest.fixture
def webhook_manager(mock_telegram, state_manager, mock_config):
    """Create a WebhookManager instance."""
    return WebhookManager(mock_telegram, state_manager, mock_config)


class TestDomainValidation:
    """Tests for domain validation function."""

    def test_valid_domains(self):
        """Test that valid domains are accepted."""
        assert _is_valid_domain("example.com")
        assert _is_valid_domain("sub.example.com")
        assert _is_valid_domain("my-site.example.org")
        assert _is_valid_domain("a.b.c.d.example.co.uk")
        assert _is_valid_domain("EXAMPLE.COM")  # Uppercase is normalized to lowercase

    def test_invalid_domains(self):
        """Test that invalid domains are rejected."""
        assert not _is_valid_domain("")
        assert not _is_valid_domain("not-a-domain")
        assert not _is_valid_domain("example")
        assert not _is_valid_domain("-example.com")
        assert not _is_valid_domain("example-.com")
        assert not _is_valid_domain("example..com")

    def test_edge_cases(self):
        """Test edge cases for domain validation."""
        # Too long
        assert not _is_valid_domain("a" * 254)
        # Just right
        assert _is_valid_domain("a" * 60 + ".com")


class TestWebhookManager:
    """Tests for WebhookManager class."""

    def test_initialization(self, webhook_manager, mock_telegram, state_manager, mock_config):
        """Test that WebhookManager initializes correctly."""
        assert webhook_manager.telegram is mock_telegram
        assert webhook_manager.state is state_manager
        assert webhook_manager.config is mock_config

    def test_get_current_url_success(self, webhook_manager, mock_telegram):
        """Test getting current webhook URL successfully."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/webhook",
            "pending_update_count": 0
        }

        url = webhook_manager.get_current_url()
        assert url == "https://example.com/webhook"
        mock_telegram.get_webhook_info.assert_called_once()

    def test_get_current_url_no_webhook(self, webhook_manager, mock_telegram):
        """Test getting current URL when no webhook is set."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "",
            "pending_update_count": 0
        }

        url = webhook_manager.get_current_url()
        assert url is None

    def test_get_current_url_with_error(self, webhook_manager, mock_telegram):
        """Test getting current URL with recent error."""
        current_time = int(time.time())
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/webhook",
            "last_error_date": current_time - 1800,  # 30 minutes ago
            "last_error_message": "Connection timeout"
        }

        url = webhook_manager.get_current_url()
        assert url == "https://example.com/webhook"

    def test_get_current_url_api_failure(self, webhook_manager, mock_telegram):
        """Test getting current URL when API fails."""
        mock_telegram.get_webhook_info.return_value = {}

        url = webhook_manager.get_current_url()
        assert url is None

    def test_set_webhook_success(self, webhook_manager, mock_telegram, state_manager):
        """Test setting webhook successfully."""
        mock_telegram.set_webhook.return_value = True

        result = webhook_manager.set_webhook("https://example.com/webhook")

        assert result is True
        mock_telegram.set_webhook.assert_called_once_with(
            url="https://example.com/webhook",
            secret="test_secret",
            max_connections=100
        )
        assert state_manager.get_webhook_url() == "https://example.com/webhook"

    def test_set_webhook_failure(self, webhook_manager, mock_telegram, state_manager):
        """Test setting webhook when it fails."""
        mock_telegram.set_webhook.return_value = False

        result = webhook_manager.set_webhook("https://example.com/webhook")

        assert result is False
        assert state_manager.get_webhook_url() is None

    def test_delete_webhook_success(self, webhook_manager, mock_telegram, state_manager):
        """Test deleting webhook successfully."""
        # Set up state
        state_manager.set_webhook_url("https://example.com/webhook")
        mock_telegram.delete_webhook.return_value = True

        result = webhook_manager.delete_webhook()

        assert result is True
        mock_telegram.delete_webhook.assert_called_once_with(drop_pending=True)
        assert state_manager.get_webhook_url() is None

    def test_delete_webhook_failure(self, webhook_manager, mock_telegram, state_manager):
        """Test deleting webhook when it fails."""
        state_manager.set_webhook_url("https://example.com/webhook")
        mock_telegram.delete_webhook.return_value = False

        result = webhook_manager.delete_webhook()

        assert result is False
        # State should not be cleared on failure
        assert state_manager.get_webhook_url() == "https://example.com/webhook"

    def test_verify_success(self, webhook_manager, mock_telegram):
        """Test verifying webhook successfully."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/webhook",
            "pending_update_count": 0
        }

        result = webhook_manager.verify()
        assert result is True

    def test_verify_no_url(self, webhook_manager, mock_telegram):
        """Test verifying when no webhook URL is set."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "",
            "pending_update_count": 0
        }

        result = webhook_manager.verify()
        assert result is False

    def test_verify_with_pending_updates(self, webhook_manager, mock_telegram):
        """Test verifying with pending updates (still passes)."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/webhook",
            "pending_update_count": 5
        }

        result = webhook_manager.verify()
        assert result is True  # Should still pass but warn

    def test_verify_api_failure(self, webhook_manager, mock_telegram):
        """Test verifying when API call fails."""
        mock_telegram.get_webhook_info.return_value = {}

        result = webhook_manager.verify()
        assert result is False

    def test_is_configured_true(self, webhook_manager, state_manager):
        """Test is_configured when webhook URL is stored."""
        state_manager.set_webhook_url("https://example.com/webhook")

        assert webhook_manager.is_configured() is True

    def test_is_configured_false(self, webhook_manager):
        """Test is_configured when no webhook URL is stored."""
        assert webhook_manager.is_configured() is False

    def test_auto_setup_disabled(self, webhook_manager, mock_config):
        """Test auto_setup when disabled."""
        mock_config.webhook_auto_setup = False

        result = webhook_manager.auto_setup()
        assert result is None

    def test_auto_setup_no_deployment_mode(self, webhook_manager, mock_config):
        """Test auto_setup when deployment mode is not set."""
        mock_config.deployment_mode = ""

        result = webhook_manager.auto_setup()
        assert result is False

    def test_auto_setup_invalid_deployment_mode(self, webhook_manager, mock_config):
        """Test auto_setup with invalid deployment mode."""
        mock_config.deployment_mode = "invalid"

        result = webhook_manager.auto_setup()
        assert result is False

    def test_auto_setup_already_configured(self, webhook_manager, mock_telegram, mock_config):
        """Test auto_setup when webhook is already correctly configured."""
        expected_url = "https://example.com/test_webhook_path"
        mock_telegram.get_webhook_info.return_value = {"url": expected_url}

        result = webhook_manager.auto_setup()

        assert result is True
        # Should not call set_webhook since already configured
        mock_telegram.set_webhook.assert_not_called()

    def test_auto_setup_production_success(self, webhook_manager, mock_telegram, mock_config):
        """Test auto_setup for production mode successfully."""
        mock_telegram.get_webhook_info.return_value = {"url": ""}
        mock_telegram.set_webhook.return_value = True

        result = webhook_manager.auto_setup()

        assert result is True
        mock_telegram.set_webhook.assert_called_once()
        call_args = mock_telegram.set_webhook.call_args
        assert call_args[1]["url"] == "https://example.com/test_webhook_path"

    def test_auto_setup_production_no_domain(self, webhook_manager, mock_config):
        """Test auto_setup for production mode without domain."""
        mock_config.webhook_domain = ""

        result = webhook_manager.auto_setup()
        assert result is False

    def test_auto_setup_production_invalid_domain(self, webhook_manager, mock_config):
        """Test auto_setup for production mode with invalid domain."""
        mock_config.webhook_domain = "not-a-valid-domain"

        result = webhook_manager.auto_setup()
        assert result is False

    def test_auto_setup_tunnel_mode(self, webhook_manager, mock_telegram, mock_config, state_manager):
        """Test auto_setup for tunnel mode."""
        mock_config.deployment_mode = "tunnel"

        # Mock tunnel URL
        state_manager._write_text_file(
            state_manager.tunnel_url_file,
            "https://tunnel.example.com"
        )

        mock_telegram.get_webhook_info.return_value = {"url": ""}
        mock_telegram.set_webhook.return_value = True

        result = webhook_manager.auto_setup()

        assert result is True
        call_args = mock_telegram.set_webhook.call_args
        assert call_args[1]["url"] == "https://tunnel.example.com/test_webhook_path"

    def test_auto_setup_tunnel_mode_no_url(self, webhook_manager, mock_config):
        """Test auto_setup for tunnel mode when tunnel URL is not available."""
        mock_config.deployment_mode = "tunnel"

        # Don't create tunnel URL file, so it will timeout
        with patch('time.sleep'):  # Speed up the test
            result = webhook_manager.auto_setup()

        assert result is False

    def test_auto_setup_url_change(self, webhook_manager, mock_telegram, state_manager, mock_config):
        """Test auto_setup when webhook URL needs to change."""
        # Old webhook is different
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://old.example.com/webhook"
        }
        mock_telegram.set_webhook.return_value = True

        result = webhook_manager.auto_setup()

        assert result is True
        mock_telegram.set_webhook.assert_called_once()
        # Check that new URL is correct
        call_args = mock_telegram.set_webhook.call_args
        assert "example.com" in call_args[1]["url"]

    def test_auto_setup_cleans_stale_state(self, webhook_manager, mock_telegram, state_manager, mock_config):
        """Test that auto_setup cleans up stale state file."""
        # State file exists but webhook not in Telegram
        state_manager.set_webhook_url("https://stale.example.com/webhook")
        mock_telegram.get_webhook_info.return_value = {"url": ""}
        mock_telegram.set_webhook.return_value = True

        result = webhook_manager.auto_setup()

        assert result is True
        # State should be updated with new URL
        assert state_manager.get_webhook_url() == "https://example.com/test_webhook_path"

    def test_wait_for_tunnel_url_timeout(self, webhook_manager):
        """Test _wait_for_tunnel_url when it times out."""
        with patch('time.sleep'):  # Speed up the test
            result = webhook_manager._wait_for_tunnel_url(
                max_wait_seconds=1,
                poll_interval=0.1
            )

        assert result is None

    def test_wait_for_tunnel_url_success(self, webhook_manager, state_manager):
        """Test _wait_for_tunnel_url when URL becomes available."""
        # Write tunnel URL file
        state_manager._write_text_file(
            state_manager.tunnel_url_file,
            "https://tunnel.example.com"
        )

        result = webhook_manager._wait_for_tunnel_url(
            max_wait_seconds=10,
            poll_interval=0.1
        )

        assert result == "https://tunnel.example.com"

    def test_get_production_webhook_url(self, webhook_manager):
        """Test _get_production_webhook_url."""
        url = webhook_manager._get_production_webhook_url()
        assert url == "https://example.com/test_webhook_path"

    def test_get_tunnel_webhook_url(self, webhook_manager, state_manager):
        """Test _get_tunnel_webhook_url."""
        # Write tunnel URL
        state_manager._write_text_file(
            state_manager.tunnel_url_file,
            "https://tunnel.example.com"
        )

        url = webhook_manager._get_tunnel_webhook_url()
        assert url == "https://tunnel.example.com/test_webhook_path"


class TestWebhookStatusCache:
    """Tests for WebhookStatusCache functionality."""

    def test_dataclass_creation(self):
        """Test creating WebhookStatusCache instance."""
        cache = WebhookStatusCache(
            configured=True,
            url="https://example.com/webhook",
            last_check=1234567890,
            last_error=None
        )
        assert cache.configured is True
        assert cache.url == "https://example.com/webhook"
        assert cache.last_check == 1234567890
        assert cache.last_error is None

    def test_get_cached_status_initial(self, webhook_manager):
        """Test get_cached_status returns initial state."""
        cache = webhook_manager.get_cached_status()
        assert isinstance(cache, WebhookStatusCache)
        assert cache.configured is False
        assert cache.url is None
        assert cache.last_check == 0
        assert cache.last_error is None

    def test_get_cached_status_thread_safe(self, webhook_manager):
        """Test that get_cached_status is thread-safe."""
        # Update cache from main thread
        webhook_manager._update_status_cache(
            configured=True,
            url="https://example.com/webhook"
        )

        # Read from another thread
        result = []
        def read_cache():
            cache = webhook_manager.get_cached_status()
            result.append(cache)

        thread = threading.Thread(target=read_cache)
        thread.start()
        thread.join()

        assert len(result) == 1
        assert result[0].configured is True
        assert result[0].url == "https://example.com/webhook"

    def test_update_status_cache_configured(self, webhook_manager):
        """Test updating cache when webhook is configured."""
        webhook_manager._update_status_cache(
            configured=True,
            url="https://example.com/webhook"
        )

        cache = webhook_manager.get_cached_status()
        assert cache.configured is True
        assert cache.url == "https://example.com/webhook"
        assert cache.last_check > 0
        assert cache.last_error is None

    def test_update_status_cache_with_error(self, webhook_manager):
        """Test updating cache with error message."""
        webhook_manager._update_status_cache(
            configured=False,
            error="Connection failed"
        )

        cache = webhook_manager.get_cached_status()
        assert cache.configured is False
        assert cache.last_error == "Connection failed"

    def test_update_status_cache_clears_error_on_success(self, webhook_manager):
        """Test that successful update clears previous error."""
        # First set an error
        webhook_manager._update_status_cache(
            configured=False,
            error="Previous error"
        )

        # Then update successfully
        webhook_manager._update_status_cache(
            configured=True,
            url="https://example.com/webhook"
        )

        cache = webhook_manager.get_cached_status()
        assert cache.configured is True
        assert cache.last_error is None

    def test_verify_and_update_cache_success(self, webhook_manager, mock_telegram):
        """Test _verify_and_update_cache when webhook is configured."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/webhook"
        }

        result = webhook_manager._verify_and_update_cache()

        assert result is True
        cache = webhook_manager.get_cached_status()
        assert cache.configured is True
        assert cache.url == "https://example.com/webhook"
        assert cache.last_error is None

    def test_verify_and_update_cache_failure(self, webhook_manager, mock_telegram):
        """Test _verify_and_update_cache when webhook is not configured."""
        mock_telegram.get_webhook_info.return_value = {"url": ""}

        result = webhook_manager._verify_and_update_cache()

        assert result is False
        cache = webhook_manager.get_cached_status()
        assert cache.configured is False
        assert cache.last_error == "No webhook configured in Telegram"


class TestRecoveryLoop:
    """Tests for webhook recovery loop functionality."""

    def test_start_recovery_loop_returns_thread(self, webhook_manager, mock_telegram):
        """Test that start_recovery_loop returns a daemon thread."""
        # Mock properly to avoid errors in background thread
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/webhook",
            "pending_update_count": 0,
            "last_error_date": 0
        }

        thread = webhook_manager.start_recovery_loop(startup_delay=0)
        # Give thread time to start
        time.sleep(0.1)

        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
        assert thread.is_alive()

    def test_recovery_loop_logic_with_configured_webhook(self, webhook_manager, mock_telegram):
        """Test recovery loop logic when webhook is already configured."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/test_webhook_path",
            "pending_update_count": 0,
            "last_error_date": 0
        }

        # Directly call the verification method that the loop uses
        result = webhook_manager._verify_and_update_cache()

        assert result is True
        cache = webhook_manager.get_cached_status()
        assert cache.configured is True
        assert cache.url == "https://example.com/test_webhook_path"
        assert cache.last_check > 0

    def test_recovery_loop_logic_with_failed_setup(self, webhook_manager, mock_telegram):
        """Test recovery loop logic when setup fails."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "",
            "pending_update_count": 0,
            "last_error_date": 0
        }

        # Directly call the verification method that the loop uses
        result = webhook_manager._verify_and_update_cache()

        assert result is False
        cache = webhook_manager.get_cached_status()
        assert cache.configured is False
        assert cache.last_error == "No webhook configured in Telegram"

    def test_recovery_loop_handles_tunnel_mode(self, webhook_manager, mock_telegram, state_manager, mock_config):
        """Test that recovery loop can handle tunnel mode configuration."""
        mock_config.deployment_mode = "tunnel"

        # Set tunnel URL
        state_manager._write_text_file(
            state_manager.tunnel_url_file,
            "https://tunnel.example.com"
        )

        mock_telegram.get_webhook_info.return_value = {
            "url": "",
            "pending_update_count": 0,
            "last_error_date": 0
        }
        mock_telegram.set_webhook.return_value = True

        # Test that auto_setup works with tunnel mode
        result = webhook_manager.auto_setup()
        assert result is True

    def test_recovery_from_unconfigured_state(self, webhook_manager, mock_telegram):
        """Test logic for recovering from unconfigured state."""
        # Simulate webhook becoming unconfigured
        mock_telegram.get_webhook_info.return_value = {
            "url": "",
            "pending_update_count": 0,
            "last_error_date": 0
        }

        # Verify detection
        is_configured = webhook_manager._verify_and_update_cache()
        assert is_configured is False

        cache = webhook_manager.get_cached_status()
        assert cache.configured is False
        assert cache.last_error == "No webhook configured in Telegram"

    def test_update_cache_with_multiple_threads(self, webhook_manager):
        """Test that cache updates are thread-safe."""
        results = []

        def update_cache(configured, url):
            webhook_manager._update_status_cache(configured=configured, url=url)
            results.append(webhook_manager.get_cached_status())

        threads = [
            threading.Thread(target=update_cache, args=(True, f"https://url{i}.com"))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All updates should have succeeded without errors
        assert len(results) == 5
        # Final cache should have one of the URLs
        final_cache = webhook_manager.get_cached_status()
        assert final_cache.configured is True
        assert "https://url" in final_cache.url

    def test_recovery_loop_respects_startup_delay(self, webhook_manager, mock_telegram):
        """Test that recovery loop includes startup delay."""
        mock_telegram.get_webhook_info.return_value = {
            "url": "https://example.com/webhook",
            "pending_update_count": 0,
            "last_error_date": 0
        }

        # Just verify the method accepts startup_delay parameter
        thread = webhook_manager.start_recovery_loop(startup_delay=5)
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
