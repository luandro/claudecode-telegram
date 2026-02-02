"""
Tmux session management and message injection.

Handles tmux session detection, validation, and message injection
for sending Telegram messages to the running Claude Code instance.
"""

import logging
import subprocess
import time
from typing import Optional


logger = logging.getLogger(__name__)


class TmuxController:
    """
    Encapsulates all tmux operations for Claude Code session management.

    Provides methods for session detection, validation, and message injection
    with proper error handling and logging.
    """

    def __init__(self, session: str, socket_path: str = ""):
        """
        Initialize tmux controller.

        Args:
            session: Name of the tmux session (e.g., 'claude')
            socket_path: Optional socket path for Docker/mounted socket scenarios
        """
        self.session = session
        self.socket_path = socket_path
        logger.debug(f"TmuxController initialized: session={session}, socket_path={socket_path or 'default'}")

    def _build_cmd(self, args: list[str]) -> list[str]:
        """
        Build tmux command with optional socket path.

        Args:
            args: tmux command arguments (e.g., ['has-session', '-t', 'claude'])

        Returns:
            Complete command list ready for subprocess execution
        """
        cmd = ["tmux"]
        if self.socket_path:
            cmd.extend(["-S", self.socket_path])
        cmd.extend(args)
        return cmd

    def exists(self) -> bool:
        """
        Check if the tmux session exists.

        Returns:
            True if session exists, False otherwise
        """
        cmd = self._build_cmd(["has-session", "-t", self.session])
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            exists = result.returncode == 0
            logger.debug(f"Session '{self.session}' exists: {exists}")
            return exists
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout checking tmux session '{self.session}'")
            return False
        except FileNotFoundError:
            logger.error("tmux binary not found in PATH")
            return False
        except Exception as e:
            logger.error(f"Error checking tmux session: {e}")
            return False

    def send_keys(self, text: str, literal: bool = True) -> None:
        """
        Send keys/text to the tmux session.

        Args:
            text: Text to send
            literal: If True, send literally (bypass key bindings).
                    If False, interpret special keys like Enter, Escape, etc.

        Raises:
            RuntimeError: If tmux command fails
        """
        args = ["send-keys", "-t", self.session]
        if literal:
            args.append("-l")
        args.append(text)

        cmd = self._build_cmd(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
                check=True
            )
            logger.debug(f"Sent keys to '{self.session}': {text[:50]}{'...' if len(text) > 50 else ''}")
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout sending keys to tmux session '{self.session}'"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to send keys to tmux session '{self.session}': {e.stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except FileNotFoundError:
            error_msg = "tmux binary not found in PATH"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error sending keys to tmux: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def send_enter(self) -> None:
        """
        Send Enter key to the tmux session.

        Raises:
            RuntimeError: If tmux command fails
        """
        cmd = self._build_cmd(["send-keys", "-t", self.session, "Enter"])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
                check=True
            )
            logger.debug(f"Sent Enter to '{self.session}'")
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout sending Enter to tmux session '{self.session}'"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to send Enter to tmux session '{self.session}': {e.stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except FileNotFoundError:
            error_msg = "tmux binary not found in PATH"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error sending Enter to tmux: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def send_escape(self) -> None:
        """
        Send Escape key to the tmux session.

        Raises:
            RuntimeError: If tmux command fails
        """
        cmd = self._build_cmd(["send-keys", "-t", self.session, "Escape"])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
                check=True
            )
            logger.debug(f"Sent Escape to '{self.session}'")
        except subprocess.TimeoutExpired:
            error_msg = f"Timeout sending Escape to tmux session '{self.session}'"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to send Escape to tmux session '{self.session}': {e.stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except FileNotFoundError:
            error_msg = "tmux binary not found in PATH"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error sending Escape to tmux: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def capture_pane(self, lines: int = 100) -> Optional[str]:
        """
        Capture content from the tmux pane.

        Args:
            lines: Number of lines to capture from history (negative for scrollback)

        Returns:
            Captured pane content as string, or None if capture fails
        """
        cmd = self._build_cmd([
            "capture-pane",
            "-t", self.session,
            "-p",  # Print to stdout
            "-S", f"-{lines}"  # Start from N lines back
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
                check=True,
                text=True
            )
            content = result.stdout
            logger.debug(f"Captured {len(content)} chars from '{self.session}'")
            return content
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout capturing pane from tmux session '{self.session}'")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to capture pane from tmux session '{self.session}': {e.stderr}")
            return None
        except FileNotFoundError:
            logger.error("tmux binary not found in PATH")
            return None
        except Exception as e:
            logger.error(f"Unexpected error capturing pane from tmux: {e}")
            return None

    # High-level convenience methods

    def send_text(self, text: str, press_enter: bool = True) -> None:
        """
        Send text to the tmux session, optionally followed by Enter.

        This is a convenience method that combines send_keys() with an optional
        send_enter() call, encapsulating a common pattern used throughout the codebase.

        Args:
            text: Text to send to the session
            press_enter: If True, automatically press Enter after sending text

        Raises:
            RuntimeError: If tmux command fails
        """
        self.send_keys(text, literal=True)
        if press_enter:
            self.send_enter()
        logger.debug(f"Sent text to '{self.session}' (enter={press_enter}): {text[:50]}{'...' if len(text) > 50 else ''}")

    def interrupt(self) -> None:
        """
        Interrupt the current operation by sending Escape.

        This is a convenience method that sends the Escape key to interrupt
        any running command in the Claude Code session.

        Raises:
            RuntimeError: If tmux command fails
        """
        self.send_escape()
        logger.debug(f"Interrupted '{self.session}' with Escape")

    def interrupt_and_send(self, text: str, delay: float = 0.2) -> None:
        """
        Interrupt current operation, wait, then send text with Enter.

        This encapsulates a common pattern: escape, sleep, send text, enter.
        Used when you need to interrupt Claude and immediately send a new command.

        Args:
            text: Text to send after interruption
            delay: Seconds to wait after interrupt before sending text

        Raises:
            RuntimeError: If tmux command fails
        """
        self.send_escape()
        time.sleep(delay)
        self.send_keys(text, literal=True)
        self.send_enter()
        logger.debug(f"Interrupted '{self.session}', waited {delay}s, sent text: {text[:50]}{'...' if len(text) > 50 else ''}")

    def exit_and_run(self, command: str, delay: float = 0.5) -> None:
        """
        Exit current Claude session and run a new command.

        This encapsulates the pattern: escape, /exit, enter, sleep, command, enter.
        Used for resume/continue operations where you need to exit the current
        session and start a new one.

        Args:
            command: Command to run after exiting (e.g., 'claude --continue --dangerously-skip-permissions')
            delay: Seconds to wait after /exit before running command

        Raises:
            RuntimeError: If tmux command fails
        """
        self.send_escape()
        time.sleep(0.2)
        self.send_keys("/exit", literal=True)
        self.send_enter()
        time.sleep(delay)
        self.send_keys(command, literal=True)
        self.send_enter()
        logger.debug(f"Exited and ran command in '{self.session}': {command[:50]}{'...' if len(command) > 50 else ''}")
