#!/usr/bin/env python3
"""Tests for ALLOWED_TELEGRAM_USER_IDS configuration"""

import json
import os
import sys
import unittest
from http.client import HTTPConnection
from threading import Thread
from time import sleep
from unittest.mock import Mock, patch

# Add parent directory to path to import bridge module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bridge


def start_server(port, host='127.0.0.1'):
    """Start the bridge server in a separate thread."""
    # Override the port and host for testing
    bridge.PORT = port
    bridge.HOST = host
    # Use a fixed webhook path for testing
    bridge.WEBHOOK_PATH = 'test_webhook_user_auth'
    # No secret token for these tests
    bridge.TELEGRAM_WEBHOOK_SECRET = ''
    # Set up mock telegram_api to avoid actual API calls
    bridge.telegram_api = Mock()

    server = bridge.HTTPServer((host, port), bridge.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sleep(0.5)  # Give server time to start
    return server


class TestAllowedUserIdsWithRestriction(unittest.TestCase):
    """Test ALLOWED_TELEGRAM_USER_IDS with restriction enabled."""

    @classmethod
    def setUpClass(cls):
        """Start test server with allowed user IDs configured."""
        cls.test_port = 18090
        cls.allowed_user_1 = 123456789
        cls.allowed_user_2 = 987654321
        cls.blocked_user = 111111111

        # Set up allowed user IDs
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = f'{cls.allowed_user_1},{cls.allowed_user_2}'
        import importlib
        importlib.reload(bridge)

        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        bridge.WEBHOOK_PATH = 'test_webhook_user_auth'
        bridge.TELEGRAM_WEBHOOK_SECRET = ''
        bridge.telegram_api = Mock()

        cls.server = bridge.HTTPServer(('127.0.0.1', cls.test_port), bridge.Handler)
        thread = Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        """Shutdown test server and clean up."""
        if hasattr(cls, 'server'):
            cls.server.shutdown()
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

    def test_allowed_user_can_send_message(self):
        """Test that allowed user can send messages."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 1,
            'message': {
                'message_id': 100,
                'from': {'id': self.allowed_user_1, 'first_name': 'Allowed'},
                'chat': {'id': 1, 'type': 'private'},
                'text': 'Hello from allowed user'
            }
        }

        conn.request('POST', '/test_webhook_user_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_blocked_user_cannot_send_message(self):
        """Test that blocked user is silently ignored (200 OK, no action)."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 2,
            'message': {
                'message_id': 101,
                'from': {'id': self.blocked_user, 'first_name': 'Blocked'},
                'chat': {'id': 1, 'type': 'private'},
                'text': 'Hello from blocked user'
            }
        }

        # Reset mock before the request
        bridge.telegram_api.reset_mock()

        conn.request('POST', '/test_webhook_user_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)  # Server responds 200 OK

        # Verify NO telegram_api call was made (silent ignore, no message sent)
        # Only answerCallbackQuery might be called for callback queries, but not for messages
        calls = bridge.telegram_api.call_args_list
        # Check that sendMessage was NOT called
        for call in calls:
            if call[0][0] == 'sendMessage':
                self.fail(f"sendMessage should not be called for blocked users, but was called with: {call[0][1]}")
        conn.close()

    def test_second_allowed_user_can_send_message(self):
        """Test that second allowed user can also send messages."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 3,
            'message': {
                'message_id': 102,
                'from': {'id': self.allowed_user_2, 'first_name': 'Allowed2'},
                'chat': {'id': 2, 'type': 'private'},
                'text': 'Hello from second allowed user'
            }
        }

        conn.request('POST', '/test_webhook_user_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()


class TestAllowedUserIdsWithoutRestriction(unittest.TestCase):
    """Test ALLOWED_TELEGRAM_USER_IDS without restriction (default behavior)."""

    @classmethod
    def setUpClass(cls):
        """Start test server without allowed user IDs configured."""
        cls.test_port = 18091
        cls.test_user = 999999999

        # Ensure no allowed user IDs are set
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        bridge.WEBHOOK_PATH = 'test_webhook_user_auth_no_restriction'
        bridge.TELEGRAM_WEBHOOK_SECRET = ''
        bridge.telegram_api = Mock()

        cls.server = bridge.HTTPServer(('127.0.0.1', cls.test_port), bridge.Handler)
        thread = Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        """Shutdown test server."""
        if hasattr(cls, 'server'):
            cls.server.shutdown()

    def test_any_user_can_send_message_when_not_configured(self):
        """Test that any user can send messages when restriction is not configured."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 4,
            'message': {
                'message_id': 103,
                'from': {'id': self.test_user, 'first_name': 'AnyUser'},
                'chat': {'id': 3, 'type': 'private'},
                'text': 'Hello from any user'
            }
        }

        conn.request('POST', '/test_webhook_user_auth_no_restriction', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()


class TestAllowedUserIdsCallback(unittest.TestCase):
    """Test ALLOWED_TELEGRAM_USER_IDS with callback queries."""

    @classmethod
    def setUpClass(cls):
        """Start test server with allowed user IDs configured."""
        cls.test_port = 18092
        cls.allowed_user = 123456789
        cls.blocked_user = 111111111

        # Set up allowed user IDs
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = str(cls.allowed_user)
        import importlib
        importlib.reload(bridge)

        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        bridge.WEBHOOK_PATH = 'test_webhook_callback_auth'
        bridge.TELEGRAM_WEBHOOK_SECRET = ''
        bridge.telegram_api = Mock()

        cls.server = bridge.HTTPServer(('127.0.0.1', cls.test_port), bridge.Handler)
        thread = Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        """Shutdown test server and clean up."""
        if hasattr(cls, 'server'):
            cls.server.shutdown()
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

    def test_allowed_user_can_trigger_callback(self):
        """Test that allowed user can trigger callback queries."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 5,
            'callback_query': {
                'id': 'callback_1',
                'from': {'id': self.allowed_user, 'first_name': 'Allowed'},
                'message': {'message_id': 200, 'chat': {'id': 1, 'type': 'private'}},
                'data': 'continue_recent'
            }
        }

        conn.request('POST', '/test_webhook_callback_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_blocked_user_cannot_trigger_callback(self):
        """Test that blocked user callback is silently ignored (200 OK, no action)."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 6,
            'callback_query': {
                'id': 'callback_2',
                'from': {'id': self.blocked_user, 'first_name': 'Blocked'},
                'message': {'message_id': 201, 'chat': {'id': 1, 'type': 'private'}},
                'data': 'continue_recent'
            }
        }

        # Reset mock before the request
        bridge.telegram_api.reset_mock()

        conn.request('POST', '/test_webhook_callback_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)  # Server responds 200 OK

        # Verify answerCallbackQuery was called (required by Telegram)
        # But NO other telegram_api calls were made (silent ignore, no error message)
        calls = bridge.telegram_api.call_args_list
        # Only answerCallbackQuery should be called, no sendMessage
        for call in calls:
            if call[0][0] == 'sendMessage':
                self.fail(f"sendMessage should not be called for blocked users, but was called with: {call[0][1]}")
        # answerCallbackQuery should have been called (required by Telegram API)
        callback_answered = any(call[0][0] == 'answerCallbackQuery' for call in calls)
        self.assertTrue(callback_answered, "answerCallbackQuery should be called even for blocked users")
        conn.close()


class TestAllowedUserIdsEnvironmentVariable(unittest.TestCase):
    """Test ALLOWED_TELEGRAM_USER_IDS environment variable configuration."""

    def setUp(self):
        """Clean environment before each test."""
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)

    def tearDown(self):
        """Clean environment after each test."""
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)

    def test_allowed_user_ids_from_environment_variable(self):
        """Test that ALLOWED_TELEGRAM_USER_IDS can be set via environment variable."""
        custom_ids = '123456789,987654321,555555555'
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = custom_ids
        import importlib
        importlib.reload(bridge)

        expected_ids = {123456789, 987654321, 555555555}
        self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, expected_ids)

    def test_allowed_user_ids_with_spaces(self):
        """Test that spaces in ALLOWED_TELEGRAM_USER_IDS are handled correctly."""
        custom_ids = '123456789, 987654321 , 555555555'
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = custom_ids
        import importlib
        importlib.reload(bridge)

        expected_ids = {123456789, 987654321, 555555555}
        self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, expected_ids)

    def test_allowed_user_ids_single_value(self):
        """Test that single user ID in ALLOWED_TELEGRAM_USER_IDS works."""
        custom_ids = '123456789'
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = custom_ids
        import importlib
        importlib.reload(bridge)

        expected_ids = {123456789}
        self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, expected_ids)

    def test_allowed_user_ids_empty_string(self):
        """Test that empty string results in no restriction."""
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = ''
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, set())

    def test_allowed_user_ids_not_set(self):
        """Test that not setting the variable results in no restriction."""
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, set())

    def test_allowed_user_ids_invalid_format(self):
        """Test that invalid format is handled gracefully."""
        # This should print a warning but not crash
        with patch('builtins.print') as mock_print:
            os.environ['ALLOWED_TELEGRAM_USER_IDS'] = 'invalid,123,abc'
            import importlib
            importlib.reload(bridge)

            # Should still work, just skip invalid values
            self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, set())
            # Should have printed a warning
            mock_print.assert_called()
            warning_calls = [str(call) for call in mock_print.call_args_list]
            self.assertTrue(any('Invalid ALLOWED_TELEGRAM_USER_IDS' in str(call) for call in warning_calls))


class TestHandlerIsUserAllowed(unittest.TestCase):
    """Test Handler._is_user_allowed method."""

    def setUp(self):
        """Set up test environment."""
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

    def tearDown(self):
        """Clean environment after each test."""
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

    def test_is_user_allowed_without_restriction(self):
        """Test that any user is allowed when restriction is not configured."""
        # Test the method logic directly by checking the ALLOWED_TELEGRAM_USER_IDS
        self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, set())
        # When the set is empty, all users should be allowed
        self.assertTrue(not bridge.ALLOWED_TELEGRAM_USER_IDS)  # Empty set = no restriction

    def test_is_user_allowed_with_restriction(self):
        """Test that only allowed users are permitted when restriction is configured."""
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = '123456789,987654321'
        import importlib
        importlib.reload(bridge)

        expected_ids = {123456789, 987654321}
        self.assertEqual(bridge.ALLOWED_TELEGRAM_USER_IDS, expected_ids)
        # Verify the logic: user_id in set
        self.assertTrue(123456789 in bridge.ALLOWED_TELEGRAM_USER_IDS)
        self.assertTrue(987654321 in bridge.ALLOWED_TELEGRAM_USER_IDS)
        self.assertFalse(111111111 in bridge.ALLOWED_TELEGRAM_USER_IDS)
        self.assertFalse(0 in bridge.ALLOWED_TELEGRAM_USER_IDS)


if __name__ == '__main__':
    unittest.main()
