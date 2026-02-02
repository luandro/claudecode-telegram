"""
Tests for TmuxController class.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from claudecode_telegram.tmux import TmuxController


class TestTmuxController:
    """Test suite for TmuxController class."""

    def test_init_default_socket(self):
        """Test initialization with default socket path."""
        controller = TmuxController(session="claude")
        assert controller.session == "claude"
        assert controller.socket_path == ""

    def test_init_custom_socket(self):
        """Test initialization with custom socket path."""
        controller = TmuxController(session="claude", socket_path="/tmp/tmux-socket")
        assert controller.session == "claude"
        assert controller.socket_path == "/tmp/tmux-socket"

    def test_build_cmd_no_socket(self):
        """Test command building without socket path."""
        controller = TmuxController(session="claude")
        cmd = controller._build_cmd(["has-session", "-t", "claude"])
        assert cmd == ["tmux", "has-session", "-t", "claude"]

    def test_build_cmd_with_socket(self):
        """Test command building with socket path."""
        controller = TmuxController(session="claude", socket_path="/tmp/tmux-socket")
        cmd = controller._build_cmd(["has-session", "-t", "claude"])
        assert cmd == ["tmux", "-S", "/tmp/tmux-socket", "has-session", "-t", "claude"]

    @patch("subprocess.run")
    def test_exists_true(self, mock_run):
        """Test exists() returns True when session exists."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        assert controller.exists() is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["tmux", "has-session", "-t", "claude"]

    @patch("subprocess.run")
    def test_exists_false(self, mock_run):
        """Test exists() returns False when session doesn't exist."""
        mock_run.return_value = MagicMock(returncode=1)
        controller = TmuxController(session="claude")
        assert controller.exists() is False
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_exists_timeout(self, mock_run):
        """Test exists() returns False on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["tmux"], timeout=5)
        controller = TmuxController(session="claude")
        assert controller.exists() is False

    @patch("subprocess.run")
    def test_exists_file_not_found(self, mock_run):
        """Test exists() returns False when tmux not found."""
        mock_run.side_effect = FileNotFoundError()
        controller = TmuxController(session="claude")
        assert controller.exists() is False

    @patch("subprocess.run")
    def test_exists_generic_error(self, mock_run):
        """Test exists() returns False on generic error."""
        mock_run.side_effect = Exception("Generic error")
        controller = TmuxController(session="claude")
        assert controller.exists() is False

    @patch("subprocess.run")
    def test_send_keys_literal(self, mock_run):
        """Test send_keys() with literal mode."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.send_keys("hello world", literal=True)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["tmux", "send-keys", "-t", "claude", "-l", "hello world"]

    @patch("subprocess.run")
    def test_send_keys_non_literal(self, mock_run):
        """Test send_keys() without literal mode."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.send_keys("C-c", literal=False)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["tmux", "send-keys", "-t", "claude", "C-c"]

    @patch("subprocess.run")
    def test_send_keys_timeout(self, mock_run):
        """Test send_keys() raises RuntimeError on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["tmux"], timeout=5)
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Timeout sending keys"):
            controller.send_keys("hello")

    @patch("subprocess.run")
    def test_send_keys_failed(self, mock_run):
        """Test send_keys() raises RuntimeError on command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["tmux"],
            stderr=b"error message"
        )
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Failed to send keys"):
            controller.send_keys("hello")

    @patch("subprocess.run")
    def test_send_keys_file_not_found(self, mock_run):
        """Test send_keys() raises RuntimeError when tmux not found."""
        mock_run.side_effect = FileNotFoundError()
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="tmux binary not found"):
            controller.send_keys("hello")

    @patch("subprocess.run")
    def test_send_keys_generic_error(self, mock_run):
        """Test send_keys() raises RuntimeError on generic error."""
        mock_run.side_effect = Exception("Generic error")
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Unexpected error"):
            controller.send_keys("hello")

    @patch("subprocess.run")
    def test_send_enter_success(self, mock_run):
        """Test send_enter() succeeds."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.send_enter()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["tmux", "send-keys", "-t", "claude", "Enter"]

    @patch("subprocess.run")
    def test_send_enter_timeout(self, mock_run):
        """Test send_enter() raises RuntimeError on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["tmux"], timeout=5)
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Timeout sending Enter"):
            controller.send_enter()

    @patch("subprocess.run")
    def test_send_enter_failed(self, mock_run):
        """Test send_enter() raises RuntimeError on command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["tmux"],
            stderr=b"error message"
        )
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Failed to send Enter"):
            controller.send_enter()

    @patch("subprocess.run")
    def test_send_escape_success(self, mock_run):
        """Test send_escape() succeeds."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.send_escape()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["tmux", "send-keys", "-t", "claude", "Escape"]

    @patch("subprocess.run")
    def test_send_escape_timeout(self, mock_run):
        """Test send_escape() raises RuntimeError on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["tmux"], timeout=5)
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Timeout sending Escape"):
            controller.send_escape()

    @patch("subprocess.run")
    def test_send_escape_failed(self, mock_run):
        """Test send_escape() raises RuntimeError on command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["tmux"],
            stderr=b"error message"
        )
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Failed to send Escape"):
            controller.send_escape()

    @patch("subprocess.run")
    def test_capture_pane_success(self, mock_run):
        """Test capture_pane() returns content successfully."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="pane content here\nmore lines\n"
        )
        controller = TmuxController(session="claude")
        content = controller.capture_pane(lines=100)
        assert content == "pane content here\nmore lines\n"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["tmux", "capture-pane", "-t", "claude", "-p", "-S", "-100"]

    @patch("subprocess.run")
    def test_capture_pane_custom_lines(self, mock_run):
        """Test capture_pane() with custom line count."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="content"
        )
        controller = TmuxController(session="claude")
        controller.capture_pane(lines=50)
        args = mock_run.call_args[0][0]
        assert "-50" in args

    @patch("subprocess.run")
    def test_capture_pane_timeout(self, mock_run):
        """Test capture_pane() returns None on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["tmux"], timeout=10)
        controller = TmuxController(session="claude")
        assert controller.capture_pane() is None

    @patch("subprocess.run")
    def test_capture_pane_failed(self, mock_run):
        """Test capture_pane() returns None on command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["tmux"],
            stderr=b"error"
        )
        controller = TmuxController(session="claude")
        assert controller.capture_pane() is None

    @patch("subprocess.run")
    def test_capture_pane_file_not_found(self, mock_run):
        """Test capture_pane() returns None when tmux not found."""
        mock_run.side_effect = FileNotFoundError()
        controller = TmuxController(session="claude")
        assert controller.capture_pane() is None

    @patch("subprocess.run")
    def test_capture_pane_generic_error(self, mock_run):
        """Test capture_pane() returns None on generic error."""
        mock_run.side_effect = Exception("Generic error")
        controller = TmuxController(session="claude")
        assert controller.capture_pane() is None

    @patch("subprocess.run")
    def test_with_socket_path_all_methods(self, mock_run):
        """Test all methods work with custom socket path."""
        mock_run.return_value = MagicMock(returncode=0, stdout="content")
        controller = TmuxController(session="claude", socket_path="/tmp/tmux-socket")

        # Test exists
        controller.exists()
        assert mock_run.call_args[0][0][:3] == ["tmux", "-S", "/tmp/tmux-socket"]

        # Test send_keys
        controller.send_keys("hello")
        assert mock_run.call_args[0][0][:3] == ["tmux", "-S", "/tmp/tmux-socket"]

        # Test send_enter
        controller.send_enter()
        assert mock_run.call_args[0][0][:3] == ["tmux", "-S", "/tmp/tmux-socket"]

        # Test send_escape
        controller.send_escape()
        assert mock_run.call_args[0][0][:3] == ["tmux", "-S", "/tmp/tmux-socket"]

        # Test capture_pane
        controller.capture_pane()
        assert mock_run.call_args[0][0][:3] == ["tmux", "-S", "/tmp/tmux-socket"]
