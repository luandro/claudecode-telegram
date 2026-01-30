#!/usr/bin/env python3
"""Tests for DM_ALLOWED_USER_ID configuration (DM-only restriction)"""

import json
import os
import sys
import unittest
from http.client import HTTPConnection
from threading import Thread
from time import sleep
from unittest.mock import Mock

# Add parent directory to path to import bridge module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bridge


def start_server(port, host='127.0.0.1'):
    """Start the bridge server in a separate thread."""
    # Override the port and host for testing
    bridge.PORT = port
    bridge.HOST = host
    # Use a fixed webhook path for testing
    bridge.WEBHOOK_PATH = 'test_webhook_dm_auth'
    # No secret token for these tests
    bridge.TELEGRAM_WEBHOOK_SECRET = ''
    # Set up mock telegram_api to avoid actual API calls
    bridge.telegram_api = Mock()

    server = bridge.HTTPServer((host, port), bridge.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sleep(0.5)  # Give server time to start
    return server


class TestDMAllowedUserIdWithRestriction(unittest.TestCase):
    """Test DM_ALLOWED_USER_ID with restriction enabled."""

    @classmethod
    def setUpClass(cls):
        """Start test server with DM allowed user ID configured."""
        cls.test_port = 18093
        cls.dm_allowed_user = 244055394  # The user from the task
        cls.blocked_user = 111111111

        # Set up DM allowed user ID
        os.environ['DM_ALLOWED_USER_ID'] = str(cls.dm_allowed_user)
        # Ensure ALLOWED_TELEGRAM_USER_IDS is empty for DM-only test
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        bridge.WEBHOOK_PATH = 'test_webhook_dm_auth'
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
        os.environ.pop('DM_ALLOWED_USER_ID', None)
        import importlib
        importlib.reload(bridge)

    def test_allowed_user_can_send_dm(self):
        """Test that allowed user can send DM messages."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 1,
            'message': {
                'message_id': 100,
                'from': {'id': self.dm_allowed_user, 'first_name': 'AllowedDM'},
                'chat': {'id': 1, 'type': 'private'},
                'text': 'Hello from allowed DM user'
            }
        }

        conn.request('POST', '/test_webhook_dm_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_blocked_user_cannot_send_dm(self):
        """Test that blocked user is silently ignored (200 OK, no action)."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 2,
            'message': {
                'message_id': 101,
                'from': {'id': self.blocked_user, 'first_name': 'Blocked'},
                'chat': {'id': 2, 'type': 'private'},
                'text': 'Hello from blocked DM user'
            }
        }

        # Reset mock before the request
        bridge.telegram_api.reset_mock()

        conn.request('POST', '/test_webhook_dm_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)  # Server responds 200 OK

        # Verify NO telegram_api call was made (silent ignore, no message sent)
        calls = bridge.telegram_api.call_args_list
        # Check that sendMessage was NOT called
        for call in calls:
            if call[0][0] == 'sendMessage':
                self.fail(f"sendMessage should not be called for blocked users, but was called with: {call[0][1]}")
        conn.close()

    def test_any_user_can_send_to_group(self):
        """Test that any user can send to groups when only DM is restricted."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 3,
            'message': {
                'message_id': 102,
                'from': {'id': 999999999, 'first_name': 'GroupUser'},
                'chat': {'id': -100123456789, 'type': 'supergroup'},
                'text': 'Hello from group user'
            }
        }

        conn.request('POST', '/test_webhook_dm_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_any_user_can_send_to_channel(self):
        """Test that any user can send to channels when only DM is restricted."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 4,
            'message': {
                'message_id': 103,
                'from': {'id': 888888888, 'first_name': 'ChannelUser'},
                'chat': {'id': -100987654321, 'type': 'channel'},
                'text': 'Hello from channel user'
            }
        }

        conn.request('POST', '/test_webhook_dm_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()


class TestDMAllowedUserIdWithoutRestriction(unittest.TestCase):
    """Test DM_ALLOWED_USER_ID without restriction (DMs blocked)."""

    @classmethod
    def setUpClass(cls):
        """Start test server without DM allowed user ID configured."""
        cls.test_port = 18094
        cls.test_user = 777777777

        # Ensure no DM allowed user ID is set
        os.environ.pop('DM_ALLOWED_USER_ID', None)
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        bridge.WEBHOOK_PATH = 'test_webhook_dm_no_auth'
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

    def test_dm_blocked_when_not_configured(self):
        """Test that DMs are silently blocked when DM_ALLOWED_USER_ID is not configured."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 5,
            'message': {
                'message_id': 104,
                'from': {'id': self.test_user, 'first_name': 'AnyUser'},
                'chat': {'id': 5, 'type': 'private'},
                'text': 'Hello from any user'
            }
        }

        # Reset mock before the request
        bridge.telegram_api.reset_mock()

        conn.request('POST', '/test_webhook_dm_no_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)

        # Verify NO telegram_api call was made (silent ignore, no message sent)
        calls = bridge.telegram_api.call_args_list
        # Check that sendMessage was NOT called
        for call in calls:
            if call[0][0] == 'sendMessage':
                self.fail(f"sendMessage should not be called for blocked users, but was called with: {call[0][1]}")
        conn.close()


class TestDMAllowedUserIdCallback(unittest.TestCase):
    """Test DM_ALLOWED_USER_ID with callback queries."""

    @classmethod
    def setUpClass(cls):
        """Start test server with DM allowed user ID configured."""
        cls.test_port = 18095
        cls.dm_allowed_user = 244055394
        cls.blocked_user = 111111111

        # Set up DM allowed user ID
        os.environ['DM_ALLOWED_USER_ID'] = str(cls.dm_allowed_user)
        import importlib
        importlib.reload(bridge)

        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        bridge.WEBHOOK_PATH = 'test_webhook_dm_callback_auth'
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
        os.environ.pop('DM_ALLOWED_USER_ID', None)
        import importlib
        importlib.reload(bridge)

    def test_allowed_user_can_trigger_dm_callback(self):
        """Test that allowed user can trigger callback queries in DM."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 6,
            'callback_query': {
                'id': 'callback_1',
                'from': {'id': self.dm_allowed_user, 'first_name': 'AllowedDM'},
                'message': {'message_id': 200, 'chat': {'id': 1, 'type': 'private'}},
                'data': 'continue_recent'
            }
        }

        conn.request('POST', '/test_webhook_dm_callback_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_blocked_user_cannot_trigger_dm_callback(self):
        """Test that blocked user callback is silently ignored (200 OK, no action)."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 7,
            'callback_query': {
                'id': 'callback_2',
                'from': {'id': self.blocked_user, 'first_name': 'Blocked'},
                'message': {'message_id': 201, 'chat': {'id': 2, 'type': 'private'}},
                'data': 'continue_recent'
            }
        }

        # Reset mock before the request
        bridge.telegram_api.reset_mock()

        conn.request('POST', '/test_webhook_dm_callback_auth', body=json.dumps(test_data).encode(), headers=headers)
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


class TestDMAllowedUserIdEnvironmentVariable(unittest.TestCase):
    """Test DM_ALLOWED_USER_ID environment variable configuration."""

    def setUp(self):
        """Clean environment before each test."""
        os.environ.pop('DM_ALLOWED_USER_ID', None)

    def tearDown(self):
        """Clean environment after each test."""
        os.environ.pop('DM_ALLOWED_USER_ID', None)

    def test_dm_allowed_user_id_from_environment_variable(self):
        """Test that DM_ALLOWED_USER_ID can be set via environment variable."""
        custom_id = '244055394'
        os.environ['DM_ALLOWED_USER_ID'] = custom_id
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.DM_ALLOWED_USER_ID, 244055394)

    def test_dm_allowed_user_id_with_spaces(self):
        """Test that spaces around DM_ALLOWED_USER_ID are handled correctly."""
        custom_id = '  244055394  '
        os.environ['DM_ALLOWED_USER_ID'] = custom_id
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.DM_ALLOWED_USER_ID, 244055394)

    def test_dm_allowed_user_id_empty_string(self):
        """Test that empty string results in 0 (no DM access)."""
        os.environ['DM_ALLOWED_USER_ID'] = ''
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.DM_ALLOWED_USER_ID, 0)

    def test_dm_allowed_user_id_not_set(self):
        """Test that not setting the variable results in 0 (no DM access)."""
        import importlib
        importlib.reload(bridge)

        self.assertEqual(bridge.DM_ALLOWED_USER_ID, 0)

    def test_dm_allowed_user_id_invalid_format(self):
        """Test that invalid format is handled gracefully."""
        from unittest.mock import patch
        # This should print a warning but not crash
        with patch('builtins.print') as mock_print:
            os.environ['DM_ALLOWED_USER_ID'] = 'invalid'
            import importlib
            importlib.reload(bridge)

            # Should default to 0
            self.assertEqual(bridge.DM_ALLOWED_USER_ID, 0)
            # Should have printed a warning
            mock_print.assert_called()
            warning_calls = [str(call) for call in mock_print.call_args_list]
            self.assertTrue(any('Invalid DM_ALLOWED_USER_ID' in str(call) for call in warning_calls))


class TestCombinedRestrictions(unittest.TestCase):
    """Test combined DM_ALLOWED_USER_ID and ALLOWED_TELEGRAM_USER_IDS."""

    @classmethod
    def setUpClass(cls):
        """Start test server with both restrictions configured."""
        cls.test_port = 18096
        cls.dm_allowed_user = 244055394
        cls.allowed_group_users = {123456789, 987654321}

        # Set up both restrictions
        os.environ['DM_ALLOWED_USER_ID'] = str(cls.dm_allowed_user)
        os.environ['ALLOWED_TELEGRAM_USER_IDS'] = '123456789,987654321'
        import importlib
        importlib.reload(bridge)

        # Override the port and host for testing
        bridge.PORT = cls.test_port
        bridge.HOST = '127.0.0.1'
        bridge.WEBHOOK_PATH = 'test_webhook_combined_auth'
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
        os.environ.pop('DM_ALLOWED_USER_ID', None)
        os.environ.pop('ALLOWED_TELEGRAM_USER_IDS', None)
        import importlib
        importlib.reload(bridge)

    def test_dm_allowed_user_can_send_dm(self):
        """Test that DM allowed user can send DMs."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 8,
            'message': {
                'message_id': 105,
                'from': {'id': self.dm_allowed_user, 'first_name': 'DMUser'},
                'chat': {'id': 1, 'type': 'private'},
                'text': 'Hello from DM allowed user'
            }
        }

        conn.request('POST', '/test_webhook_combined_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_group_allowed_user_can_send_to_group(self):
        """Test that group allowed user can send to groups."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 9,
            'message': {
                'message_id': 106,
                'from': {'id': 123456789, 'first_name': 'GroupUser'},
                'chat': {'id': -100123456789, 'type': 'supergroup'},
                'text': 'Hello from group allowed user'
            }
        }

        conn.request('POST', '/test_webhook_combined_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        conn.close()

    def test_non_group_user_cannot_send_to_group(self):
        """Test that non-allowed user is silently ignored for groups (200 OK, no action)."""
        conn = HTTPConnection('127.0.0.1', self.test_port)
        headers = {'Content-Type': 'application/json'}

        test_data = {
            'update_id': 10,
            'message': {
                'message_id': 107,
                'from': {'id': 555555555, 'first_name': 'NotGroupUser'},
                'chat': {'id': -100123456789, 'type': 'supergroup'},
                'text': 'Hello from non-allowed group user'
            }
        }

        # Reset mock before the request
        bridge.telegram_api.reset_mock()

        conn.request('POST', '/test_webhook_combined_auth', body=json.dumps(test_data).encode(), headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)

        # Verify NO telegram_api call was made (silent ignore, no message sent)
        calls = bridge.telegram_api.call_args_list
        # Check that sendMessage was NOT called
        for call in calls:
            if call[0][0] == 'sendMessage':
                self.fail(f"sendMessage should not be called for blocked users, but was called with: {call[0][1]}")
        conn.close()


if __name__ == '__main__':
    unittest.main()
