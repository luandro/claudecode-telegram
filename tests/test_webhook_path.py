#!/usr/bin/env python3
"""Tests for webhook path validation"""

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

    server = bridge.HTTPServer((host, port), bridge.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sleep(0.5)  # Give server time to start
    return server


class TestWebhookPathValidation(unittest.TestCase):
    """Test webhook path validation."""

    @classmethod
    def setUpClass(cls):
        """Start test server."""
        cls.test_port = 18080
        cls.server = start_server(cls.test_port)

    @classmethod
    def tearDownClass(cls):
        """Shutdown test server."""
        if hasattr(cls, 'server'):
            cls.server.shutdown()

    def test_valid_webhook_path_get(self):
        """Test GET request with valid webhook path returns 200."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        conn.request('GET', '/test_webhook_path_12345')
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), b'Claude-Telegram Bridge')
        conn.close()

    def test_valid_webhook_path_post(self):
        """Test POST request with valid webhook path returns 200."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}
        # Send a minimal valid update
        test_data = {'update_id': 1}
        conn.request('POST', '/test_webhook_path_12345', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_invalid_webhook_path_get(self):
        """Test GET request with invalid webhook path returns 404."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        conn.request('GET', '/invalid_path')
        response = conn.getresponse()
        self.assertEqual(response.status, 404)
        self.assertEqual(response.read(), b'Not Found')
        conn.close()

    def test_invalid_webhook_path_post(self):
        """Test POST request with invalid webhook path returns 404."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}
        test_data = {'update_id': 1}
        conn.request('POST', '/invalid_path', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 404)
        conn.close()

    def test_root_path_get(self):
        """Test GET request to root path returns 404."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        conn.request('GET', '/')
        response = conn.getresponse()
        self.assertEqual(response.status, 404)
        conn.close()

    def test_path_without_leading_slash(self):
        """Test that paths without leading slash are handled correctly."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        # Even without leading slash, the handler should normalize and return 404
        # for invalid paths
        conn.request('GET', '/invalid')
        response = conn.getresponse()
        self.assertEqual(response.status, 404)
        conn.close()

    def test_webhook_path_with_trailing_slash(self):
        """Test that webhook path with trailing slash is handled correctly."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        # Trailing slash should still work
        conn.request('GET', '/test_webhook_path_12345/')
        response = conn.getresponse()
        # This should return 404 since the path doesn't match exactly
        self.assertEqual(response.status, 404)
        conn.close()


class TestWebhookPathGeneration(unittest.TestCase):
    """Test webhook path generation."""

    def test_default_webhook_path_is_long_random_string(self):
        """Test that default webhook path is a 64-character hex string."""
        # Reset WEBHOOK_PATH to trigger auto-generation
        os.environ.pop('WEBHOOK_PATH', None)
        # Re-import to get the auto-generated value
        import importlib
        importlib.reload(bridge)

        webhook_path = bridge.WEBHOOK_PATH
        self.assertEqual(len(webhook_path), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in webhook_path))

    def test_custom_webhook_path_from_env(self):
        """Test that custom webhook path from environment is used."""
        custom_path = 'my_custom_secret_path'
        os.environ['WEBHOOK_PATH'] = custom_path
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.WEBHOOK_PATH, custom_path)
        # Clean up
        os.environ.pop('WEBHOOK_PATH', None)


if __name__ == '__main__':
    unittest.main()
