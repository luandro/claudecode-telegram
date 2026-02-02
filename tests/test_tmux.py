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

    # Tests for high-level convenience methods

    @patch("subprocess.run")
    def test_send_text_with_enter(self, mock_run):
        """Test send_text() sends text and presses Enter by default."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.send_text("hello world")

        # Should call subprocess.run twice: once for send_keys, once for send_enter
        assert mock_run.call_count == 2

        # First call should be send_keys with literal flag
        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args == ["tmux", "send-keys", "-t", "claude", "-l", "hello world"]

        # Second call should be send_enter
        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args == ["tmux", "send-keys", "-t", "claude", "Enter"]

    @patch("subprocess.run")
    def test_send_text_without_enter(self, mock_run):
        """Test send_text() without pressing Enter."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.send_text("hello world", press_enter=False)

        # Should only call subprocess.run once for send_keys
        assert mock_run.call_count == 1

        # Call should be send_keys with literal flag, no Enter
        call_args = mock_run.call_args[0][0]
        assert call_args == ["tmux", "send-keys", "-t", "claude", "-l", "hello world"]

    @patch("subprocess.run")
    def test_interrupt(self, mock_run):
        """Test interrupt() sends Escape."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.interrupt()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["tmux", "send-keys", "-t", "claude", "Escape"]

    @patch("subprocess.run")
    @patch("time.sleep")
    def test_interrupt_and_send(self, mock_sleep, mock_run):
        """Test interrupt_and_send() with default delay."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.interrupt_and_send("new command")

        # Should call subprocess.run three times: escape, send_keys, send_enter
        assert mock_run.call_count == 3

        # First call should be Escape
        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args == ["tmux", "send-keys", "-t", "claude", "Escape"]

        # Should sleep with default delay
        mock_sleep.assert_called_once_with(0.2)

        # Second call should be send_keys
        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args == ["tmux", "send-keys", "-t", "claude", "-l", "new command"]

        # Third call should be Enter
        third_call_args = mock_run.call_args_list[2][0][0]
        assert third_call_args == ["tmux", "send-keys", "-t", "claude", "Enter"]

    @patch("subprocess.run")
    @patch("time.sleep")
    def test_interrupt_and_send_custom_delay(self, mock_sleep, mock_run):
        """Test interrupt_and_send() with custom delay."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.interrupt_and_send("new command", delay=0.5)

        # Should sleep with custom delay
        mock_sleep.assert_called_once_with(0.5)
        assert mock_run.call_count == 3

    @patch("subprocess.run")
    @patch("time.sleep")
    def test_exit_and_run(self, mock_sleep, mock_run):
        """Test exit_and_run() with default delay."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.exit_and_run("claude --continue --dangerously-skip-permissions")

        # Should call subprocess.run five times: escape, /exit send, enter, command send, enter
        assert mock_run.call_count == 5

        # First call should be Escape
        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args == ["tmux", "send-keys", "-t", "claude", "Escape"]

        # Should sleep twice: 0.2s after escape, then custom delay after /exit
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 0.2
        assert mock_sleep.call_args_list[1][0][0] == 0.5  # default delay

        # Second call should be /exit
        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args == ["tmux", "send-keys", "-t", "claude", "-l", "/exit"]

        # Third call should be Enter
        third_call_args = mock_run.call_args_list[2][0][0]
        assert third_call_args == ["tmux", "send-keys", "-t", "claude", "Enter"]

        # Fourth call should be the command
        fourth_call_args = mock_run.call_args_list[3][0][0]
        assert fourth_call_args == ["tmux", "send-keys", "-t", "claude", "-l", "claude --continue --dangerously-skip-permissions"]

        # Fifth call should be Enter
        fifth_call_args = mock_run.call_args_list[4][0][0]
        assert fifth_call_args == ["tmux", "send-keys", "-t", "claude", "Enter"]

    @patch("subprocess.run")
    @patch("time.sleep")
    def test_exit_and_run_custom_delay(self, mock_sleep, mock_run):
        """Test exit_and_run() with custom delay."""
        mock_run.return_value = MagicMock(returncode=0)
        controller = TmuxController(session="claude")
        controller.exit_and_run("claude --resume abc123", delay=1.0)

        # Should sleep twice with correct delays
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 0.2  # fixed delay after escape
        assert mock_sleep.call_args_list[1][0][0] == 1.0  # custom delay after /exit
        assert mock_run.call_count == 5

    @patch("subprocess.run")
    def test_send_text_raises_on_failure(self, mock_run):
        """Test send_text() propagates RuntimeError on failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["tmux"],
            stderr=b"error message"
        )
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Failed to send keys"):
            controller.send_text("hello")

    @patch("subprocess.run")
    def test_interrupt_and_send_raises_on_failure(self, mock_run):
        """Test interrupt_and_send() propagates RuntimeError on failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["tmux"],
            stderr=b"error message"
        )
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Failed to send Escape"):
            controller.interrupt_and_send("hello")

    @patch("subprocess.run")
    def test_exit_and_run_raises_on_failure(self, mock_run):
        """Test exit_and_run() propagates RuntimeError on failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["tmux"],
            stderr=b"error message"
        )
        controller = TmuxController(session="claude")
        with pytest.raises(RuntimeError, match="Failed to send Escape"):
            controller.exit_and_run("claude --continue")

    # Tests for extract_response method

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_no_output(self, mock_capture):
        """Test extract_response() returns None when no output captured."""
        mock_capture.return_value = None
        controller = TmuxController(session="claude")
        assert controller.extract_response() is None

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_no_prompt(self, mock_capture):
        """Test extract_response() returns None when no user prompt found."""
        mock_capture.return_value = "some output\nwithout prompt\nmore output"
        controller = TmuxController(session="claude")
        assert controller.extract_response() is None

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_basic(self, mock_capture):
        """Test extract_response() extracts response after user prompt."""
        mock_capture.return_value = "> user message\nClaude's response here\nmore response"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response here\nmore response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_with_arrow_prompt(self, mock_capture):
        """Test extract_response() works with arrow prompt (❯)."""
        mock_capture.return_value = "❯ user message\nClaude's response"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_with_dollar_prompt(self, mock_capture):
        """Test extract_response() works with dollar prompt ($)."""
        mock_capture.return_value = "$ user message\nClaude's response"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_stops_at_next_prompt(self, mock_capture):
        """Test extract_response() stops at next user prompt."""
        mock_capture.return_value = "> first message\nfirst response\n> second message\nsecond response"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        # Should only get response to second message (last prompt)
        assert response == "second response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_filters_spinner_lines(self, mock_capture):
        """Test extract_response() filters out spinner characters."""
        mock_capture.return_value = "> user message\n  ⠋ Loading\nClaude's response\n  ⠙ Processing"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_filters_tree_lines(self, mock_capture):
        """Test extract_response() filters out tree characters."""
        mock_capture.return_value = "> user message\n├ branch\n│ Tool: Read\nClaude's response\n└ end"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_filters_tool_lines(self, mock_capture):
        """Test extract_response() filters out tool status lines."""
        mock_capture.return_value = (
            "> user message\n"
            "│ Tool: Read file.py\n"
            "│ Read completed\n"
            "Claude's response\n"
            "│ Tool: Write output.txt\n"
            "│ Edit running\n"
            "│ Bash completed"
        )
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_skips_leading_empty_lines(self, mock_capture):
        """Test extract_response() skips empty lines at start of response."""
        mock_capture.return_value = "> user message\n\n\nClaude's response"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_removes_ansi_codes(self, mock_capture):
        """Test extract_response() removes ANSI escape codes."""
        mock_capture.return_value = "> user message\n\x1b[32mGreen text\x1b[0m normal text"
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Green text normal text"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_strips_whitespace(self, mock_capture):
        """Test extract_response() strips leading/trailing whitespace."""
        mock_capture.return_value = "> user message\n   Claude's response   \n  "
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Claude's response"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_empty_after_cleanup(self, mock_capture):
        """Test extract_response() returns None if response is empty after cleanup."""
        mock_capture.return_value = "> user message\n   \n  \n"
        controller = TmuxController(session="claude")
        assert controller.extract_response() is None

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_complex_scenario(self, mock_capture):
        """Test extract_response() with complex realistic scenario."""
        mock_capture.return_value = (
            "Previous output\n"
            "> old message\n"
            "old response\n"
            "> current message\n"
            "\n"
            "  ⠋ Thinking\n"
            "├ Tools\n"
            "│ Tool: Read\n"
            "│ Read completed\n"
            "\x1b[32mFormatted response\x1b[0m\n"
            "More response text\n"
            "  │ running analysis\n"
            "Final response line\n"
            "└ end\n"
        )
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Formatted response\nMore response text\nFinal response line"

    @patch.object(TmuxController, 'capture_pane')
    def test_extract_response_multiline_with_preserving_content(self, mock_capture):
        """Test extract_response() preserves meaningful content across multiple lines."""
        mock_capture.return_value = (
            "> user message\n"
            "Line 1 of response\n"
            "Line 2 of response\n"
            "\n"
            "Line 4 after blank\n"
            "Line 5"
        )
        controller = TmuxController(session="claude")
        response = controller.extract_response()
        assert response == "Line 1 of response\nLine 2 of response\n\nLine 4 after blank\nLine 5"
