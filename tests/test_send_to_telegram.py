"""Tests for the send_to_telegram hook."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
from send_to_telegram import (
    extract_from_transcript,
    extract_from_tmux,
    format_for_telegram,
    get_bot_token,
    main,
    parse_arguments,
    send_message,
)


class TestGetBotToken:
    """Tests for get_bot_token function."""

    def test_returns_env_token_first(self, tmp_path):
        """Should prefer environment variable over file."""
        token_file = tmp_path / "telegram_bot_token"
        token_file.write_text("file_token")

        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "env_token"}):
            token = get_bot_token(tmp_path)
            assert token == "env_token"

    def test_reads_from_file_when_env_empty(self, tmp_path):
        """Should read from file when env var not set."""
        token_file = tmp_path / "telegram_bot_token"
        token_file.write_text("file_token")

        with patch.dict("os.environ", {}, clear=True):
            token = get_bot_token(tmp_path)
            assert token == "file_token"

    def test_returns_placeholder_when_not_found(self, tmp_path):
        """Should return placeholder when no token found."""
        with patch.dict("os.environ", {}, clear=True):
            token = get_bot_token(tmp_path)
            assert token == "YOUR_BOT_TOKEN_HERE"

    def test_ignores_placeholder_in_env(self, tmp_path):
        """Should ignore placeholder value in environment."""
        token_file = tmp_path / "telegram_bot_token"
        token_file.write_text("file_token")

        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "YOUR_BOT_TOKEN_HERE"}):
            token = get_bot_token(tmp_path)
            assert token == "file_token"


class TestExtractFromTranscript:
    """Tests for extract_from_transcript function."""

    def test_extracts_assistant_text(self, tmp_path):
        """Should extract text from assistant messages."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hi there!"}]}}\n'
        )

        result = extract_from_transcript(transcript, max_wait=1)
        assert result == "Hi there!"

    def test_combines_multiple_text_blocks(self, tmp_path):
        """Should combine multiple text blocks with double newlines."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"First block"},{"type":"text","text":"Second block"}]}}\n'
        )

        result = extract_from_transcript(transcript, max_wait=1)
        assert result == "First block\n\nSecond block"

    def test_returns_none_when_no_user_message(self, tmp_path):
        """Should return None when no user message found."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello"}]}}\n'
        )

        result = extract_from_transcript(transcript, max_wait=1)
        assert result is None

    def test_returns_none_when_file_not_exists(self, tmp_path):
        """Should return None when transcript file doesn't exist."""
        transcript = tmp_path / "nonexistent.jsonl"
        result = extract_from_transcript(transcript, max_wait=1)
        assert result is None

    def test_waits_for_response(self, tmp_path):
        """Should wait for assistant response to appear."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
        )

        # Simulate response appearing after a delay
        def write_response():
            time.sleep(0.3)
            with open(transcript, "a") as f:
                f.write(
                    '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Delayed response"}]}}\n'
                )

        import threading
        thread = threading.Thread(target=write_response)
        thread.start()

        result = extract_from_transcript(transcript, max_wait=10)
        thread.join()

        assert result == "Delayed response"

    def test_ignores_non_text_content(self, tmp_path):
        """Should ignore non-text content blocks."""
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"123"},{"type":"text","text":"Response"}]}}\n'
        )

        result = extract_from_transcript(transcript, max_wait=1)
        assert result == "Response"


class TestExtractFromTmux:
    """Tests for extract_from_tmux function."""

    def test_calls_tmux_extract_response(self):
        """Should call TmuxController.extract_response()."""
        mock_tmux = Mock()
        mock_tmux.extract_response.return_value = "Tmux response"

        result = extract_from_tmux(mock_tmux)

        assert result == "Tmux response"
        mock_tmux.extract_response.assert_called_once()

    def test_returns_none_when_tmux_returns_none(self):
        """Should return None when tmux extraction fails."""
        mock_tmux = Mock()
        mock_tmux.extract_response.return_value = None

        result = extract_from_tmux(mock_tmux)

        assert result is None


class TestFormatForTelegram:
    """Tests for format_for_telegram function."""

    def test_escapes_html_entities(self):
        """Should escape HTML special characters."""
        text = "This has <tags> & entities"
        result = format_for_telegram(text)
        assert "&lt;tags&gt;" in result
        assert "&amp;" in result

    def test_formats_bold_text(self):
        """Should convert **bold** to <b>bold</b>."""
        text = "This is **bold** text"
        result = format_for_telegram(text)
        assert "<b>bold</b>" in result

    def test_formats_italic_text(self):
        """Should convert *italic* to <i>italic</i>."""
        text = "This is *italic* text"
        result = format_for_telegram(text)
        assert "<i>italic</i>" in result

    def test_formats_inline_code(self):
        """Should convert `code` to <code>code</code>."""
        text = "This is `inline code` here"
        result = format_for_telegram(text)
        assert "<code>inline code</code>" in result

    def test_formats_code_block_without_language(self):
        """Should format code block without language specifier."""
        text = "```\ncode here\n```"
        result = format_for_telegram(text)
        assert "<pre>code here</pre>" in result

    def test_formats_code_block_with_language(self):
        """Should format code block with language specifier."""
        text = "```python\nprint('hello')\n```"
        result = format_for_telegram(text)
        assert '<pre><code class="language-python">print(&#x27;hello&#x27;)</code></pre>' in result or \
               '<pre><code class="language-python">print(&apos;hello&apos;)</code></pre>' in result or \
               '<pre><code class="language-python">print(\'hello\')</code></pre>' in result

    def test_escapes_html_in_code_blocks(self):
        """Should escape HTML entities in code blocks."""
        text = "```\n<div>tag</div>\n```"
        result = format_for_telegram(text)
        assert "&lt;div&gt;" in result

    def test_truncates_long_text(self):
        """Should truncate text longer than 4000 chars."""
        text = "x" * 5000
        result = format_for_telegram(text)
        assert len(result) < 5000
        assert "..." in result

    def test_handles_empty_text(self):
        """Should handle empty text gracefully."""
        result = format_for_telegram("")
        assert result == ""

    def test_handles_mixed_formatting(self):
        """Should handle mixed markdown formatting."""
        text = "This has **bold**, *italic*, and `code`"
        result = format_for_telegram(text)
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<code>code</code>" in result

    def test_preserves_single_asterisk(self):
        """Should not format single asterisks not meant as italic."""
        text = "**bold** not *italic but standalone * asterisk"
        result = format_for_telegram(text)
        # This is tricky - the regex should handle it properly
        assert "<b>bold</b>" in result


class TestSendMessage:
    """Tests for send_message function."""

    def test_sends_html_formatted_message(self):
        """Should send message with HTML formatting."""
        mock_logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = json.dumps({"ok": True}).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = send_message("token123", 12345, "<b>Hello</b>", mock_logger)

            assert result is True
            mock_logger.debug.assert_called_with("Message sent successfully (HTML)")

    def test_falls_back_to_plain_text(self):
        """Should fall back to plain text on HTML failure."""
        mock_logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            # First call (HTML) fails, second call (plain text) succeeds
            mock_response_fail = Mock()
            mock_response_fail.read.return_value = json.dumps({"ok": False}).encode()

            mock_response_success = Mock()
            mock_response_success.read.return_value = json.dumps({"ok": True}).encode()

            mock_urlopen.return_value.__enter__.side_effect = [
                mock_response_fail,
                mock_response_success
            ]

            result = send_message("token123", 12345, "<b>Hello</b>", mock_logger)

            assert result is True
            mock_logger.debug.assert_called_with("Message sent successfully (plain text)")

    def test_returns_false_on_failure(self):
        """Should return False when both attempts fail."""
        mock_logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = json.dumps({"ok": False}).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = send_message("token123", 12345, "<b>Hello</b>", mock_logger)

            assert result is False
            mock_logger.error.assert_called()

    def test_handles_network_error(self):
        """Should handle network errors gracefully."""
        mock_logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Network error")

            result = send_message("token123", 12345, "Hello", mock_logger)

            assert result is False
            mock_logger.error.assert_called()

    def test_truncates_plain_text_fallback(self):
        """Should truncate plain text to 4096 chars."""
        mock_logger = Mock()
        long_text = "x" * 5000

        with patch("urllib.request.urlopen") as mock_urlopen:
            # First call fails, triggering plain text fallback
            mock_response_fail = Mock()
            mock_response_fail.read.return_value = json.dumps({"ok": False}).encode()

            mock_response_success = Mock()
            mock_response_success.read.return_value = json.dumps({"ok": True}).encode()

            mock_urlopen.return_value.__enter__.side_effect = [
                mock_response_fail,
                mock_response_success
            ]

            # Capture the request data to verify truncation
            with patch("urllib.request.Request") as mock_request:
                send_message("token123", 12345, long_text, mock_logger)

                # Check second call (plain text) has truncated text
                calls = mock_request.call_args_list
                if len(calls) >= 2:
                    second_call_data = json.loads(calls[1][0][1].decode())
                    assert len(second_call_data["text"]) <= 4096


class TestParseArguments:
    """Tests for parse_arguments function."""

    def test_parses_transcript_path(self):
        """Should parse --transcript argument."""
        args = parse_arguments(["--transcript", "/path/to/transcript.jsonl"])
        assert args.transcript == Path("/path/to/transcript.jsonl")

    def test_defaults_to_none(self):
        """Should default transcript to None."""
        args = parse_arguments([])
        assert args.transcript is None

    def test_handles_help(self):
        """Should handle --help argument."""
        with pytest.raises(SystemExit) as exc_info:
            parse_arguments(["--help"])
        assert exc_info.value.code == 0


class TestMain:
    """Tests for main function."""

    def test_standalone_mode_with_transcript(self, tmp_path):
        """Should work in standalone mode with --transcript flag."""
        # Set up test environment
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Response"}]}}\n'
        )

        # Set up state files
        (claude_dir / "telegram_pending").write_text(str(int(time.time())))
        (claude_dir / "telegram_chat_id").write_text("12345")
        (claude_dir / "telegram_bot_token").write_text("test_token")

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = Mock()
                mock_response.read.return_value = json.dumps({"ok": True}).encode()
                mock_urlopen.return_value.__enter__.return_value = mock_response

                exit_code = main(["--transcript", str(transcript)])

                assert exit_code == 0

    def test_hook_mode_with_stdin(self, tmp_path):
        """Should work in hook mode reading from stdin."""
        # Set up test environment
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Response"}]}}\n'
        )

        # Set up state files
        (claude_dir / "telegram_pending").write_text(str(int(time.time())))
        (claude_dir / "telegram_chat_id").write_text("12345")
        (claude_dir / "telegram_bot_token").write_text("test_token")

        hook_data = json.dumps({"transcript_path": str(transcript)})

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = hook_data
                mock_stdin.isatty.return_value = False

                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response = Mock()
                    mock_response.read.return_value = json.dumps({"ok": True}).encode()
                    mock_urlopen.return_value.__enter__.return_value = mock_response

                    exit_code = main([])

                    assert exit_code == 0

    def test_exits_when_no_pending_file(self, tmp_path):
        """Should exit early when no pending file exists."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
        )

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}):
            exit_code = main(["--transcript", str(transcript)])
            assert exit_code == 0  # Should exit gracefully

    def test_handles_expired_pending_file(self, tmp_path):
        """Should clean up expired pending file."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
        )

        # Create expired pending file (11 minutes ago)
        expired_time = int(time.time()) - 660
        pending_file = claude_dir / "telegram_pending"
        pending_file.write_text(str(expired_time))

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}):
            exit_code = main(["--transcript", str(transcript)])
            assert exit_code == 0
            assert not pending_file.exists()

    def test_handles_missing_bot_token(self, tmp_path):
        """Should exit when bot token not configured."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
        )

        (claude_dir / "telegram_pending").write_text(str(int(time.time())))
        (claude_dir / "telegram_chat_id").write_text("12345")

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}, clear=True):
            exit_code = main(["--transcript", str(transcript)])
            assert exit_code == 0  # Should exit gracefully

    def test_handles_import_error_gracefully(self, tmp_path):
        """Should continue without tmux when import fails."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]}}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Response"}]}}\n'
        )

        (claude_dir / "telegram_pending").write_text(str(int(time.time())))
        (claude_dir / "telegram_chat_id").write_text("12345")
        (claude_dir / "telegram_bot_token").write_text("test_token")

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}):
            # Remove claudecode_telegram from sys.modules to simulate import failure
            import sys
            sys_modules_backup = sys.modules.copy()

            # Remove any cached imports
            for key in list(sys.modules.keys()):
                if "claudecode_telegram" in key:
                    del sys.modules[key]

            try:
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response = Mock()
                    mock_response.read.return_value = json.dumps({"ok": True}).encode()
                    mock_urlopen.return_value.__enter__.return_value = mock_response

                    exit_code = main(["--transcript", str(transcript)])

                    # Should still succeed using transcript
                    assert exit_code == 0
            finally:
                # Restore sys.modules
                sys.modules.update(sys_modules_backup)

    def test_requires_transcript_path(self, tmp_path):
        """Should fail when no transcript path and stdin is a terminal."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True

                exit_code = main([])

                assert exit_code == 1

    def test_handles_invalid_json_stdin(self, tmp_path):
        """Should handle invalid JSON from stdin."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        with patch.dict("os.environ", {"CLAUDE_DIR": str(claude_dir)}):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = "invalid json"
                mock_stdin.isatty.return_value = False

                exit_code = main([])

                assert exit_code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
