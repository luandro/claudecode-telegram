"""
Pytest configuration and shared fixtures.

Provides common test fixtures for mocking external dependencies
(Telegram API, tmux, file system) and setting up test environments.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.tmux import TmuxController
from claudecode_telegram.state import StateManager


@pytest.fixture
def config():
    """Return a test BridgeConfig with safe defaults.

    Returns:
        BridgeConfig: Configuration suitable for testing with:
            - Test bot token
            - Temporary directory for state files
            - Disabled auto-setup to prevent external calls
            - Safe defaults for all other settings
    """
    return BridgeConfig(
        # Core paths and session
        tmux_session="test-session",
        claude_dir=Path("/tmp/test-claude"),
        tmux_socket_path="",

        # Telegram API
        bot_token="test_bot_token_123",
        telegram_webhook_secret="test_secret",
        reaction_emoji="👍",

        # Server configuration
        port=8080,
        host="127.0.0.1",
        webhook_path="test-webhook-path",

        # Deployment configuration
        deployment_mode="tunnel",
        webhook_domain="test.example.com",
        webhook_auto_setup=False,
        webhook_startup_delay=0,

        # Access control
        allowed_user_ids={123456789, 987654321},
        dm_allowed_user_id=123456789,
    )


@pytest.fixture
def mock_telegram():
    """Return a mock TelegramClient for testing.

    Returns:
        Mock: Mock TelegramClient with common methods stubbed:
            - api_call: Returns success response by default
            - send_message: Returns success response
            - set_reaction: Returns True
            - send_typing: Returns True
            - answer_callback: Returns True
            - set_webhook: Returns True
            - get_webhook_info: Returns empty webhook info
            - delete_webhook: Returns True
            - set_commands: Returns True
            - start_typing_loop: Returns a mock thread
    """
    mock = Mock(spec=TelegramClient)

    # Mock successful API call by default
    mock.api_call.return_value = {
        "ok": True,
        "result": {}
    }

    # Mock successful send_message
    mock.send_message.return_value = {
        "ok": True,
        "result": {
            "message_id": 1,
            "chat": {"id": 123456789},
            "text": "test message"
        }
    }

    # Mock successful reactions and actions
    mock.set_reaction.return_value = True
    mock.send_typing.return_value = True
    mock.answer_callback.return_value = True

    # Mock successful webhook operations
    mock.set_webhook.return_value = True
    mock.get_webhook_info.return_value = {
        "url": "",
        "has_custom_certificate": False,
        "pending_update_count": 0
    }
    mock.delete_webhook.return_value = True
    mock.set_commands.return_value = True

    # Mock typing loop thread
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    mock.start_typing_loop.return_value = mock_thread

    return mock


@pytest.fixture
def mock_tmux():
    """Return a mock TmuxController for testing.

    Returns:
        Mock: Mock TmuxController with common methods stubbed:
            - exists: Returns True by default
            - send_keys: No-op
            - send_enter: No-op
            - send_escape: No-op
            - send_text: No-op
            - interrupt: No-op
            - interrupt_and_send: No-op
            - exit_and_run: No-op
            - capture_pane: Returns empty string
            - extract_response: Returns None
    """
    mock = Mock(spec=TmuxController)

    # Mock session exists by default
    mock.exists.return_value = True

    # Mock all send operations as no-ops (no return value)
    mock.send_keys.return_value = None
    mock.send_enter.return_value = None
    mock.send_escape.return_value = None
    mock.send_text.return_value = None
    mock.interrupt.return_value = None
    mock.interrupt_and_send.return_value = None
    mock.exit_and_run.return_value = None

    # Mock capture operations
    mock.capture_pane.return_value = ""
    mock.extract_response.return_value = None

    return mock


@pytest.fixture
def temp_state_dir(tmp_path):
    """Return a StateManager with a temporary directory.

    Args:
        tmp_path: Pytest fixture providing temporary directory path

    Returns:
        StateManager: StateManager instance using tmp_path as claude_dir.
            All state files will be created in the temporary directory
            and automatically cleaned up after the test.
    """
    return StateManager(tmp_path)


@pytest.fixture
def sample_update():
    """Return a sample Telegram update dictionary.

    Returns:
        dict: A typical Telegram message update with:
            - update_id: Unique update identifier
            - message: Message object containing:
                - message_id: Message identifier
                - from: User who sent the message
                - chat: Chat where message was sent
                - text: Message text content
                - date: Unix timestamp
    """
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "from": {
                "id": 123456789,
                "is_bot": False,
                "first_name": "Test",
                "username": "testuser"
            },
            "chat": {
                "id": 123456789,
                "first_name": "Test",
                "username": "testuser",
                "type": "private"
            },
            "date": 1234567890,
            "text": "Hello, Claude!"
        }
    }


@pytest.fixture
def sample_callback():
    """Return a sample Telegram callback query dictionary.

    Returns:
        dict: A typical Telegram callback query with:
            - update_id: Unique update identifier
            - callback_query: Callback query object containing:
                - id: Callback query identifier
                - from: User who triggered the callback
                - message: Original message with inline keyboard
                - data: Callback data payload
                - chat_instance: Chat instance identifier
    """
    return {
        "update_id": 123456790,
        "callback_query": {
            "id": "callback_id_123",
            "from": {
                "id": 123456789,
                "is_bot": False,
                "first_name": "Test",
                "username": "testuser"
            },
            "message": {
                "message_id": 2,
                "from": {
                    "id": 987654321,
                    "is_bot": True,
                    "first_name": "TestBot",
                    "username": "test_bot"
                },
                "chat": {
                    "id": 123456789,
                    "first_name": "Test",
                    "username": "testuser",
                    "type": "private"
                },
                "date": 1234567890,
                "text": "Choose an option:",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Option 1", "callback_data": "option_1"}]
                    ]
                }
            },
            "chat_instance": "chat_instance_123",
            "data": "option_1"
        }
    }
