#!/usr/bin/env python3
"""Tests for webhook management CLI commands."""

import os
import sys
import unittest
from unittest.mock import patch, Mock
import io

# Add parent directory to path to import bridge module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bridge


class TestSetWebhook(unittest.TestCase):
    """Test set_webhook function."""

    def setUp(self):
        """Set up test environment."""
        os.environ['TELEGRAM_BOT_TOKEN'] = 'test_bot_token_123'
        os.environ['WEBHOOK_PATH'] = 'test_webhook_path_abc'
        os.environ['TELEGRAM_WEBHOOK_SECRET'] = 'test_secret_xyz'
        import importlib
        importlib.reload(bridge)

    def tearDown(self):
        """Clean up environment."""
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        os.environ.pop('WEBHOOK_PATH', None)
        os.environ.pop('TELEGRAM_WEBHOOK_SECRET', None)
        import importlib
        importlib.reload(bridge)

    @patch('bridge.telegram_api')
    def test_set_webhook_with_secret(self, mock_api):
        """Test set_webhook includes secret token when configured."""
        mock_api.return_value = {"ok": True, "result": True}

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.set_webhook("coder.luandro.com")

        self.assertTrue(result)
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        self.assertEqual(call_args[0][0], "setWebhook")
        params = call_args[0][1]
        self.assertEqual(params["url"], "https://coder.luandro.com/test_webhook_path_abc")
        self.assertEqual(params["secret_token"], "test_secret_xyz")
        output = mock_stdout.getvalue()
        self.assertIn("Webhook set successfully", output)
        self.assertIn("Secret token: configured", output)

    def test_set_webhook_without_secret(self):
        """Test set_webhook works without secret token."""
        # Save original module state
        original_secret = bridge.TELEGRAM_WEBHOOK_SECRET
        try:
            # Temporarily set secret to empty
            bridge.TELEGRAM_WEBHOOK_SECRET = ''
            with patch('bridge.telegram_api') as mock_api:
                mock_api.return_value = {"ok": True, "result": True}

                with patch('sys.stdout', new_callable=io.StringIO):
                    result = bridge.set_webhook("coder.luandro.com")

                self.assertTrue(result)
                params = mock_api.call_args[0][1]
                self.assertNotIn("secret_token", params)
        finally:
            # Restore original state
            bridge.TELEGRAM_WEBHOOK_SECRET = original_secret

    @patch('bridge.telegram_api')
    def test_set_webhook_failure(self, mock_api):
        """Test set_webhook handles API failure."""
        mock_api.return_value = {"ok": False, "description": "Bad Request: token is invalid"}

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.set_webhook("coder.luandro.com")

        self.assertFalse(result)
        output = mock_stdout.getvalue()
        self.assertIn("Failed to set webhook", output)
        self.assertIn("Bad Request", output)

    @patch('bridge.telegram_api')
    def test_set_webhook_no_response(self, mock_api):
        """Test set_webhook handles no API response."""
        mock_api.return_value = None

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.set_webhook("coder.luandro.com")

        self.assertFalse(result)
        output = mock_stdout.getvalue()
        self.assertIn("Failed to set webhook", output)

    def test_set_webhook_url_format(self):
        """Test that webhook URL is correctly formatted."""
        # Save original module state
        original_path = bridge.WEBHOOK_PATH
        try:
            # Temporarily set webhook path
            bridge.WEBHOOK_PATH = 'abc123'
            with patch('bridge.telegram_api') as mock_api:
                mock_api.return_value = {"ok": True}

                bridge.set_webhook("example.com")
                args = mock_api.call_args[0][1]
                self.assertEqual(args['url'], "https://example.com/abc123")
        finally:
            # Restore original state
            bridge.WEBHOOK_PATH = original_path


class TestGetWebhookInfo(unittest.TestCase):
    """Test get_webhook_info function."""

    @patch('bridge.telegram_api')
    def test_get_webhook_info(self, mock_api):
        """Test getting webhook info."""
        mock_api.return_value = {
            "ok": True,
            "result": {
                "url": "https://coder.luandro.com/test_webhook_path_abc",
                "has_custom_certificate": False,
                "pending_update_count": 0
            }
        }

        info = bridge.get_webhook_info()

        self.assertEqual(info["url"], "https://coder.luandro.com/test_webhook_path_abc")
        self.assertEqual(info["pending_update_count"], 0)
        self.assertFalse(info["has_custom_certificate"])

    @patch('bridge.telegram_api')
    def test_get_webhook_info_failure(self, mock_api):
        """Test get_webhook_info handles API failure."""
        mock_api.return_value = {"ok": False, "description": "Unauthorized"}

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            info = bridge.get_webhook_info()

        self.assertEqual(info, {})
        output = mock_stdout.getvalue()
        self.assertIn("Failed to get webhook info", output)


class TestDeleteWebhook(unittest.TestCase):
    """Test delete_webhook function."""

    @patch('bridge.telegram_api')
    def test_delete_webhook(self, mock_api):
        """Test deleting webhook."""
        mock_api.return_value = {"ok": True, "result": True}

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.delete_webhook()

        self.assertTrue(result)
        mock_api.assert_called_once_with("deleteWebhook", {"drop_pending_updates": True})
        output = mock_stdout.getvalue()
        self.assertIn("Webhook deleted successfully", output)

    @patch('bridge.telegram_api')
    def test_delete_webhook_failure(self, mock_api):
        """Test delete_webhook handles API failure."""
        mock_api.return_value = {"ok": False, "description": "Conflict"}

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.delete_webhook()

        self.assertFalse(result)
        output = mock_stdout.getvalue()
        self.assertIn("Failed to delete webhook", output)


class TestVerifyWebhook(unittest.TestCase):
    """Test verify_webhook function."""

    @patch('bridge.telegram_api')
    def test_verify_webhook_ok(self, mock_api):
        """Test verify_webhook reports OK for properly configured webhook."""
        mock_api.return_value = {
            "ok": True,
            "result": {
                "url": "https://coder.luandro.com/test_webhook_path_abc",
                "has_custom_certificate": False,
                "pending_update_count": 0
            }
        }

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.verify_webhook()

        self.assertTrue(result)
        output = mock_stdout.getvalue()
        self.assertIn("Webhook OK", output)
        self.assertIn("https://coder.luandro.com/test_webhook_path_abc", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_no_url(self, mock_api):
        """Test verify_webhook fails when webhook URL is not set."""
        mock_api.return_value = {
            "ok": True,
            "result": {
                "url": "",
                "has_custom_certificate": False,
                "pending_update_count": 0
            }
        }

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.verify_webhook()

        self.assertFalse(result)
        output = mock_stdout.getvalue()
        self.assertIn("Webhook not configured", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_pending_updates(self, mock_api):
        """Test verify_webhook warns about pending updates."""
        mock_api.return_value = {
            "ok": True,
            "result": {
                "url": "https://coder.luandro.com/test_webhook_path_abc",
                "has_custom_certificate": False,
                "pending_update_count": 5
            }
        }

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.verify_webhook()

        self.assertTrue(result)  # Still returns True
        output = mock_stdout.getvalue()
        self.assertIn("Warning: 5 pending updates", output)
        self.assertIn("Webhook OK", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_recent_error(self, mock_api):
        """Test verify_webhook warns about recent errors."""
        import time
        recent_timestamp = int(time.time()) - 300  # 5 minutes ago

        mock_api.return_value = {
            "ok": True,
            "result": {
                "url": "https://coder.luandro.com/test_webhook_path_abc",
                "has_custom_certificate": False,
                "pending_update_count": 0,
                "last_error_date": recent_timestamp
            }
        }

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.verify_webhook()

        self.assertTrue(result)  # Still returns True
        output = mock_stdout.getvalue()
        self.assertIn("Warning: Recent webhook error", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_old_error(self, mock_api):
        """Test verify_webhook ignores old errors."""
        import time
        old_timestamp = int(time.time()) - 7200  # 2 hours ago

        mock_api.return_value = {
            "ok": True,
            "result": {
                "url": "https://coder.luandro.com/test_webhook_path_abc",
                "has_custom_certificate": False,
                "pending_update_count": 0,
                "last_error_date": old_timestamp
            }
        }

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.verify_webhook()

        self.assertTrue(result)
        output = mock_stdout.getvalue()
        self.assertNotIn("Warning: Recent webhook error", output)
        self.assertIn("Webhook OK", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_no_response(self, mock_api):
        """Test verify_webhook handles no API response."""
        mock_api.return_value = None

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.verify_webhook()

        self.assertFalse(result)
        output = mock_stdout.getvalue()
        self.assertIn("Failed to get webhook info", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_api_error(self, mock_api):
        """Test verify_webhook handles API error response."""
        mock_api.return_value = {
            "ok": False,
            "description": "Unauthorized"
        }

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            result = bridge.verify_webhook()

        self.assertFalse(result)
        output = mock_stdout.getvalue()
        self.assertIn("Failed to get webhook info", output)


class TestCLIArgumentParsing(unittest.TestCase):
    """Test CLI argument parsing."""

    def setUp(self):
        """Set up test environment."""
        os.environ['TELEGRAM_BOT_TOKEN'] = 'test_bot_token_123'
        import importlib
        importlib.reload(bridge)

    def tearDown(self):
        """Clean up environment."""
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        import importlib
        importlib.reload(bridge)

    @patch('bridge.telegram_api')
    def test_set_webhook_command_parsing(self, mock_api):
        """Test set-webhook command argument parsing."""
        mock_api.return_value = {"ok": True}

        # Save original webhook path and set to known value for test
        original_path = bridge.WEBHOOK_PATH
        try:
            bridge.WEBHOOK_PATH = 'test_webhook_path_abc'

            with patch('sys.argv', ['bridge.py', 'set-webhook', '--domain', 'example.com']):
                with patch('sys.stdout', new_callable=io.StringIO):
                    result = bridge.main()

            self.assertEqual(result, 0)
            call_args = mock_api.call_args[0][1]
            self.assertEqual(call_args['url'], 'https://example.com/test_webhook_path_abc')
        finally:
            bridge.WEBHOOK_PATH = original_path

    @patch('bridge.telegram_api')
    def test_set_webhook_default_domain(self, mock_api):
        """Test set-webhook command uses default domain."""
        # Save original state
        original_domain = os.environ.get('WEBHOOK_DOMAIN')
        original_path = bridge.WEBHOOK_PATH
        try:
            os.environ['WEBHOOK_DOMAIN'] = 'custom.domain.com'
            bridge.WEBHOOK_PATH = 'test_webhook_path_abc'

            mock_api.return_value = {"ok": True}

            with patch('sys.argv', ['bridge.py', 'set-webhook']):
                with patch('sys.stdout', new_callable=io.StringIO):
                    result = bridge.main()

            self.assertEqual(result, 0)
            call_args = mock_api.call_args[0][1]
            self.assertEqual(call_args['url'], 'https://custom.domain.com/test_webhook_path_abc')
        finally:
            # Restore original state
            if original_domain is None:
                os.environ.pop('WEBHOOK_DOMAIN', None)
            else:
                os.environ['WEBHOOK_DOMAIN'] = original_domain
            bridge.WEBHOOK_PATH = original_path

    @patch('bridge.telegram_api')
    def test_get_webhook_info_command(self, mock_api):
        """Test get-webhook-info command."""
        mock_api.return_value = {
            "ok": True,
            "result": {"url": "https://example.com/webhook"}
        }

        with patch('sys.argv', ['bridge.py', 'get-webhook-info']):
            with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
                result = bridge.main()

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("https://example.com/webhook", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_command(self, mock_api):
        """Test verify-webhook command."""
        mock_api.return_value = {
            "ok": True,
            "result": {
                "url": "https://example.com/webhook",
                "pending_update_count": 0
            }
        }

        with patch('sys.argv', ['bridge.py', 'verify-webhook']):
            with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
                result = bridge.main()

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Webhook OK", output)

    @patch('bridge.telegram_api')
    def test_verify_webhook_command_failure(self, mock_api):
        """Test verify-webhook command with webhook not configured."""
        mock_api.return_value = {
            "ok": True,
            "result": {"url": "", "pending_update_count": 0}
        }

        with patch('sys.argv', ['bridge.py', 'verify-webhook']):
            with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
                result = bridge.main()

        self.assertEqual(result, 1)
        output = mock_stdout.getvalue()
        self.assertIn("Webhook not configured", output)

    @patch('bridge.telegram_api')
    def test_delete_webhook_command(self, mock_api):
        """Test delete-webhook command."""
        mock_api.return_value = {"ok": True}

        with patch('sys.argv', ['bridge.py', 'delete-webhook']):
            with patch('sys.stdout', new_callable=io.StringIO):
                result = bridge.main()

        self.assertEqual(result, 0)
        mock_api.assert_called_once_with("deleteWebhook", {"drop_pending_updates": True})

    def test_missing_bot_token_exits_with_error(self):
        """Test that missing BOT_TOKEN causes early exit."""
        os.environ.pop('TELEGRAM_BOT_TOKEN', None)
        import importlib
        importlib.reload(bridge)

        with patch('sys.argv', ['bridge.py', 'set-webhook']):
            with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
                result = bridge.main()

        self.assertEqual(result, 1)
        output = mock_stdout.getvalue()
        self.assertIn("TELEGRAM_BOT_TOKEN not set", output)


class TestWebhookDomainEnvironmentVariable(unittest.TestCase):
    """Test webhook domain environment variable configuration."""

    def test_domain_from_environment_variable(self):
        """Test that WEBHOOK_DOMAIN can be set via environment variable."""
        custom_domain = 'my.custom.domain.com'
        os.environ['WEBHOOK_DOMAIN'] = custom_domain

        import importlib
        importlib.reload(bridge)

        # Check that the default_domain in main() uses the env var
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--domain", default=custom_domain)
        args = parser.parse_args([])
        self.assertEqual(args.domain, custom_domain)

        # Clean up
        os.environ.pop('WEBHOOK_DOMAIN', None)

    def test_default_domain_is_coder_domain(self):
        """Test that default domain is coder.luandro.com when env var not set."""
        os.environ.pop('WEBHOOK_DOMAIN', None)

        import importlib
        importlib.reload(bridge)

        default_domain = os.environ.get("WEBHOOK_DOMAIN", "coder.luandro.com")
        self.assertEqual(default_domain, "coder.luandro.com")


if __name__ == '__main__':
    unittest.main()
