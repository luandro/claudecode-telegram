#!/usr/bin/env python3
"""Tests for webhook secret token validation"""

import json
import os
import sys
import unittest
from http.client import HTTPConnection
from threading import Thread
from time import sleep

# Add parent directory to path to import bridge module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bridge


def start_server(port, host='127.0.0.1'):
    """Start the bridge server in a separate thread."""
    # Override the port and host for testing
    bridge.PORT = port
    bridge.HOST = host
    # Use a fixed webhook path for testing
    bridge.WEBHOOK_PATH = 'test_webhook_path_12345'
    # Set a test secret token
    bridge.TELEGRAM_WEBHOOK_SECRET = 'test_secret_token_abc123'

    server = bridge.HTTPServer((host, port), bridge.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sleep(0.5)  # Give server time to start
    return server


class TestWebhookSecretValidation(unittest.TestCase):
    """Test webhook secret token validation."""

    @classmethod
    def setUpClass(cls):
        """Start test server."""
        cls.test_port = 18081
        cls.server = start_server(cls.test_port)

    @classmethod
    def tearDownClass(cls):
        """Shutdown test server."""
        if hasattr(cls, 'server'):
            cls.server.shutdown()

    def test_valid_secret_token_allows_request(self):
        """Test POST request with valid secret token returns 200."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Bot-Api-Secret-Token': 'test_secret_token_abc123'
        }
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_12345', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_invalid_secret_token_rejects_request(self):
        """Test POST request with invalid secret token returns 401."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Bot-Api-Secret-Token': 'wrong_secret_token'
        }
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_12345', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        self.assertEqual(response.read(), b'Unauthorized')
        conn.close()

    def test_missing_secret_token_rejects_request(self):
        """Test POST request without secret token header returns 401 when secret is configured."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_12345', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        self.assertEqual(response.read(), b'Unauthorized')
        conn.close()

    def test_empty_secret_token_rejects_request(self):
        """Test POST request with empty secret token returns 401."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Bot-Api-Secret-Token': ''
        }
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_12345', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        conn.close()

    def test_secret_token_case_sensitive(self):
        """Test that secret token comparison is case-sensitive."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Bot-Api-Secret-Token': 'Test_Secret_Token_Abc123'  # Different case
        }
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_12345', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        conn.close()


class TestWebhookSecretDisabled(unittest.TestCase):
    """Test behavior when webhook secret is not configured."""

    @classmethod
    def setUpClass(cls):
        """Start test server without secret configured."""
        cls.test_port = 18082
        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        # Use a fixed webhook path for testing
        bridge.WEBHOOK_PATH = 'test_webhook_path_no_secret'
        # No secret token configured
        bridge.TELEGRAM_WEBHOOK_SECRET = ''

        cls.server = bridge.HTTPServer(('127.0.0.1', cls.test_port), bridge.Handler)
        thread = Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        sleep(0.5)  # Give server time to start

    @classmethod
    def tearDownClass(cls):
        """Shutdown test server."""
        if hasattr(cls, 'server'):
            cls.server.shutdown()

    def test_request_without_secret_when_not_configured(self):
        """Test POST request without secret token succeeds when secret is not configured."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_no_secret', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_request_with_secret_when_not_configured(self):
        """Test POST request with secret token succeeds when secret is not configured (backward compatibility)."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Bot-Api-Secret-Token': 'some_secret_token'
        }
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_no_secret', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        # When no secret is configured, validation is skipped for backward compatibility
        self.assertEqual(response.status, 200)
        conn.close()


class TestWebhookSecretEnvironmentVariable(unittest.TestCase):
    """Test webhook secret environment variable configuration."""

    def test_secret_from_environment_variable(self):
        """Test that TELEGRAM_WEBHOOK_SECRET can be set via environment variable."""
        custom_secret = 'my_custom_secret_token_xyz789'
        os.environ['TELEGRAM_WEBHOOK_SECRET'] = custom_secret
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.TELEGRAM_WEBHOOK_SECRET, custom_secret)
        # Clean up
        os.environ.pop('TELEGRAM_WEBHOOK_SECRET', None)

    def test_default_secret_is_empty(self):
        """Test that default secret is empty string (validation disabled)."""
        # Ensure no env var is set
        os.environ.pop('TELEGRAM_WEBHOOK_SECRET', None)
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.TELEGRAM_WEBHOOK_SECRET, '')


if __name__ == '__main__':
    unittest.main()
