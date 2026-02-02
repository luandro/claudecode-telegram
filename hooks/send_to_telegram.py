#!/usr/bin/env python3
"""Claude Code Stop hook - sends response back to Telegram.

This Python script replaces the bash hook, combining transcript parsing
with tmux capture fallback for reliable message delivery.

Usage:
    As a hook (stdin):    cat hook_data.json | ./send_to_telegram.py
    Standalone mode:      ./send_to_telegram.py [options]

Arguments:
    --transcript PATH     Path to transcript file
    --help               Show this help message
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional


# Set up logging
def setup_logging(claude_dir: Path) -> logging.Logger:
    """Configure logging to telegram_hook_debug.log."""
    log_file = claude_dir / "telegram_hook_debug.log"
    logging.basicConfig(
        filename=str(log_file),
        level=logging.DEBUG,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def get_bot_token(claude_dir: Path) -> str:
    """
    Get bot token from environment or token file.

    Args:
        claude_dir: Path to Claude configuration directory

    Returns:
        Bot token string, or "YOUR_BOT_TOKEN_HERE" if not found
    """
    # Check environment variable first
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if token and token != "YOUR_BOT_TOKEN_HERE":
        return token

    # Fall back to token file
    token_file = claude_dir / "telegram_bot_token"
    if token_file.exists():
        return token_file.read_text().strip()

    return "YOUR_BOT_TOKEN_HERE"


def extract_from_transcript(transcript_path: Path, max_wait: int = 15) -> Optional[str]:
    """
    Extract response from transcript file.

    Waits up to max_wait attempts (0.5s each) for meaningful content.

    Args:
        transcript_path: Path to the transcript JSONL file
        max_wait: Maximum number of 0.5s wait attempts

    Returns:
        Extracted text response, or None if not found
    """
    if not transcript_path.exists():
        return None

    # Find the last user message line number
    try:
        with open(transcript_path, "r") as f:
            lines = f.readlines()

        last_user_line = None
        for i, line in enumerate(lines):
            if '"type":"user"' in line:
                last_user_line = i

        if last_user_line is None:
            return None

        # Wait for assistant response to appear
        wait_count = 0
        while wait_count < max_wait:
            # Read from last user message onwards
            with open(transcript_path, "r") as f:
                relevant_lines = f.readlines()[last_user_line:]

            # Extract assistant text responses
            text_parts = []
            for line in relevant_lines:
                if '"type":"assistant"' not in line:
                    continue

                try:
                    data = json.loads(line)
                    if data.get("type") != "assistant":
                        continue

                    message = data.get("message", {})
                    content = message.get("content", [])

                    for block in content:
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                text_parts.append(text)
                except json.JSONDecodeError:
                    continue

            # Check if we got meaningful content
            response = "\n\n".join(text_parts)
            if response and response.strip():
                return response

            wait_count += 1
            time.sleep(0.5)

    except Exception as e:
        logging.error(f"Error extracting from transcript: {e}")

    return None


def extract_from_tmux(tmux) -> Optional[str]:
    """
    Extract response from tmux pane capture.

    Args:
        tmux: TmuxController instance

    Returns:
        Extracted response text, or None if not found
    """
    # Use the TmuxController's extract_response method
    return tmux.extract_response()


def parse_arguments(args: list[str]) -> argparse.Namespace:
    """
    Parse command line arguments.

    Args:
        args: Command line arguments (excluding program name)

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Claude Code Stop hook - sends response back to Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # As a hook (stdin):
  cat hook_data.json | ./send_to_telegram.py

  # Standalone with transcript path:
  ./send_to_telegram.py --transcript /path/to/transcript.jsonl

Environment Variables:
  TELEGRAM_BOT_TOKEN    Bot token (overrides token file)
  CLAUDE_DIR            Claude directory (default: ~/.claude)
  TMUX_SESSION          Tmux session name (default: claude)
  TMUX_SOCKET_PATH      Optional tmux socket path
        """
    )

    parser.add_argument(
        "--transcript",
        type=Path,
        help="Path to transcript file (overrides stdin)"
    )

    return parser.parse_args(args)


def format_for_telegram(text: str) -> str:
    """
    Format markdown text to Telegram HTML.

    Converts markdown code blocks and inline code to HTML,
    escapes HTML entities, and formats bold/italic text.

    Args:
        text: Input text with markdown formatting

    Returns:
        HTML-formatted text suitable for Telegram
    """
    if not text:
        return ""

    # Truncate if too long
    if len(text) > 4000:
        text = text[:4000] + "\n..."

    def escape_html(s: str) -> str:
        """Escape HTML special characters."""
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Store code blocks and inline code temporarily
    code_blocks = []
    inline_codes = []

    # Replace code blocks with placeholders
    def replace_code_block(match):
        lang = match.group(1) or ''
        code = match.group(2)
        code_blocks.append((lang, code))
        return f"\x00B{len(code_blocks)-1}\x00"

    text = re.sub(r'```(\w*)\n?(.*?)```', replace_code_block, text, flags=re.DOTALL)

    # Replace inline code with placeholders
    def replace_inline_code(match):
        code = match.group(1)
        inline_codes.append(code)
        return f"\x00I{len(inline_codes)-1}\x00"

    text = re.sub(r'`([^`\n]+)`', replace_inline_code, text)

    # Escape HTML in the remaining text
    text = escape_html(text)

    # Format bold and italic
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)

    # Restore code blocks
    for i, (lang, code) in enumerate(code_blocks):
        if lang:
            formatted = f'<pre><code class="language-{lang}">{escape_html(code.strip())}</code></pre>'
        else:
            formatted = f'<pre>{escape_html(code.strip())}</pre>'
        text = text.replace(f"\x00B{i}\x00", formatted)

    # Restore inline codes
    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00I{i}\x00", f'<code>{escape_html(code)}</code>')

    return text


def send_message(token: str, chat_id: int, text: str, logger: logging.Logger) -> bool:
    """
    Send message to Telegram.

    Tries HTML formatting first, falls back to plain text on failure.

    Args:
        token: Telegram bot token
        chat_id: Target chat ID
        text: Message text (HTML formatted)
        logger: Logger instance for debugging

    Returns:
        True if message was sent successfully, False otherwise
    """
    def send_request(data: dict) -> bool:
        """Send HTTP request to Telegram API."""
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            req = urllib.request.Request(
                url,
                json.dumps(data).encode('utf-8'),
                {"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    # Try with HTML formatting
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if send_request(data):
        logger.debug("Message sent successfully (HTML)")
        return True

    # Fallback to plain text
    logger.warning("HTML send failed, trying plain text")
    data = {
        "chat_id": chat_id,
        "text": text[:4096]  # Telegram limit for plain text
    }

    success = send_request(data)
    if success:
        logger.debug("Message sent successfully (plain text)")
    else:
        logger.error("Both HTML and plain text sends failed")

    return success


def main(argv: Optional[list[str]] = None) -> int:
    """
    Main hook execution.

    Args:
        argv: Command line arguments (None to use sys.argv)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Parse arguments
    if argv is None:
        argv = sys.argv[1:]
    args = parse_arguments(argv)

    # Set up paths
    claude_dir = Path(os.environ.get("CLAUDE_DIR", Path.home() / ".claude"))
    logger = setup_logging(claude_dir)

    try:
        # Determine transcript path
        transcript_path = None
        if args.transcript:
            # Standalone mode with explicit transcript path
            transcript_path = args.transcript
            logger.debug(f"Standalone mode: transcript={transcript_path}")
        else:
            # Hook mode: read from stdin
            if not sys.stdin.isatty():
                try:
                    input_data = sys.stdin.read()
                    hook_data = json.loads(input_data)
                    transcript_path = Path(hook_data.get("transcript_path", ""))
                    logger.debug("Hook mode: reading from stdin")
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Invalid hook data from stdin: {e}")
                    return 1
            else:
                logger.error("No transcript path provided and stdin is a terminal")
                return 1

        if not transcript_path:
            logger.error("No transcript path available")
            return 1

        logger.debug("Hook started")

        # Check if this is a Telegram-initiated message
        pending_file = claude_dir / "telegram_pending"
        if not pending_file.exists():
            logger.debug("No pending file, exiting")
            return 0

        # Verify pending file is recent (within 10 minutes)
        try:
            pending_time = int(pending_file.read_text().strip())
            now = int(time.time())
            if now - pending_time > 600:
                logger.debug("Pending file expired, cleaning up")
                pending_file.unlink()
                return 0
        except (ValueError, FileNotFoundError):
            logger.debug("Invalid pending file, cleaning up")
            pending_file.unlink(missing_ok=True)
            return 0

        # Get chat ID
        chat_id_file = claude_dir / "telegram_chat_id"
        if not chat_id_file.exists():
            logger.debug("No chat ID file, cleaning up")
            pending_file.unlink()
            return 0

        try:
            chat_id = int(chat_id_file.read_text().strip())
        except (ValueError, FileNotFoundError):
            logger.error("Invalid chat ID")
            pending_file.unlink()
            return 0

        # Get bot token
        bot_token = get_bot_token(claude_dir)
        if bot_token == "YOUR_BOT_TOKEN_HERE":
            logger.error("Bot token not configured")
            pending_file.unlink()
            return 0

        # Try extracting response from transcript first
        response = None
        source = None

        if transcript_path.exists():
            response = extract_from_transcript(transcript_path)
            if response:
                source = "transcript"
                logger.debug("Response extracted from transcript")

        # Fallback to tmux capture
        if not response:
            logger.debug("No text in transcript, trying tmux capture")
            try:
                # Try importing TmuxController from the package
                try:
                    from claudecode_telegram.tmux import TmuxController
                    logger.debug("Imported TmuxController from package")
                except ImportError:
                    # Fallback: try adding parent directory to path
                    logger.debug("Package import failed, trying fallback path")
                    sys.path.insert(0, str(claude_dir.parent))
                    from claudecode_telegram.tmux import TmuxController

                tmux_session = os.environ.get("TMUX_SESSION", "claude")
                tmux_socket = os.environ.get("TMUX_SOCKET_PATH", "")
                tmux = TmuxController(tmux_session, tmux_socket)

                response = extract_from_tmux(tmux)
                if response:
                    source = "tmux"
                    logger.debug("Response captured from tmux")
            except ImportError as e:
                logger.warning(f"Could not import TmuxController: {e}")
                logger.warning("Tmux capture unavailable, continuing without it")
            except Exception as e:
                logger.error(f"Error capturing from tmux: {e}")

        # Check if we got any content
        if not response or not response.strip():
            logger.info("No response found in transcript or tmux")
            pending_file.unlink()
            return 0

        logger.debug(f"Sending response ({len(response)} bytes, source: {source})")

        # Format and send
        formatted_text = format_for_telegram(response)
        success = send_message(bot_token, chat_id, formatted_text, logger)

        if success:
            logger.debug(f"Response sent successfully to {chat_id}")

        # Clean up
        pending_file.unlink()
        return 0 if success else 1

    except Exception as e:
        logger.error(f"Unhandled error in hook: {e}")
        return 1


if __name__ == "__main__":
    # Run main with command line arguments
    exit_code = main()
    sys.exit(exit_code)
