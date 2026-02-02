"""
State file management for claudecode-telegram.

Manages persistent state files in CLAUDE_DIR including:
- telegram_chat_id: Current active chat ID
- telegram_pending: Timestamp flag for Telegram-initiated messages
- telegram_webhook_url: Last configured webhook URL
- cloudflared_tunnel_url: Tunnel URL from cloudflared
- history.jsonl: Session history
"""

import json
import time
from pathlib import Path
from typing import Optional


class StateManager:
    """Manages all file-based state operations for the bridge."""

    def __init__(self, claude_dir: Path):
        """Initialize StateManager with the Claude directory path.

        Args:
            claude_dir: Path to the Claude configuration directory (typically ~/.claude)
        """
        self.claude_dir = Path(claude_dir)

    @property
    def chat_id_file(self) -> Path:
        """Path to the chat ID state file."""
        return self.claude_dir / "telegram_chat_id"

    @property
    def pending_file(self) -> Path:
        """Path to the pending message timestamp file."""
        return self.claude_dir / "telegram_pending"

    @property
    def webhook_state_file(self) -> Path:
        """Path to the webhook URL state file."""
        return self.claude_dir / "telegram_webhook_url"

    @property
    def tunnel_url_file(self) -> Path:
        """Path to the cloudflared tunnel URL file."""
        return self.claude_dir / "cloudflared_tunnel_url"

    @property
    def history_file(self) -> Path:
        """Path to the session history file."""
        return self.claude_dir / "history.jsonl"

    def _read_text_file(self, path: Path) -> Optional[str]:
        """Read text from a file safely.

        Args:
            path: Path to the file to read

        Returns:
            File contents as string, or None if file doesn't exist or is empty
        """
        try:
            if not path.exists():
                return None
            value = path.read_text().strip()
            return value if value else None
        except Exception:
            return None

    def _write_text_file(self, path: Path, text: str) -> bool:
        """Write text to a file safely.

        Args:
            path: Path to the file to write
            text: Text content to write

        Returns:
            True if successful, False otherwise
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            return True
        except Exception:
            return False

    def _delete_file(self, path: Path) -> None:
        """Delete a file safely.

        Args:
            path: Path to the file to delete
        """
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    def get_chat_id(self) -> Optional[int]:
        """Get the current active chat ID.

        Returns:
            Chat ID as integer, or None if not set
        """
        value = self._read_text_file(self.chat_id_file)
        if value:
            try:
                return int(value)
            except ValueError:
                return None
        return None

    def set_chat_id(self, chat_id: int) -> None:
        """Set the current active chat ID.

        Args:
            chat_id: Telegram chat ID to store
        """
        self._write_text_file(self.chat_id_file, str(chat_id))

    def is_pending(self, max_age_seconds: int = 600) -> bool:
        """Check if there's a pending message within the age limit.

        Args:
            max_age_seconds: Maximum age in seconds for a pending message (default: 600)

        Returns:
            True if there's a pending message within max_age_seconds, False otherwise
        """
        timestamp_str = self._read_text_file(self.pending_file)
        if not timestamp_str:
            return False

        try:
            timestamp = int(timestamp_str)
            age = int(time.time()) - timestamp
            return age <= max_age_seconds
        except ValueError:
            return False

    def set_pending(self) -> None:
        """Mark a message as pending with current timestamp."""
        self._write_text_file(self.pending_file, str(int(time.time())))

    def clear_pending(self) -> None:
        """Clear the pending message flag."""
        self._delete_file(self.pending_file)

    def get_webhook_url(self) -> Optional[str]:
        """Get the last configured webhook URL.

        Returns:
            Webhook URL string, or None if not set
        """
        return self._read_text_file(self.webhook_state_file)

    def set_webhook_url(self, url: str) -> None:
        """Store the configured webhook URL.

        Args:
            url: Webhook URL to store
        """
        self._write_text_file(self.webhook_state_file, url)

    def clear_webhook_url(self) -> None:
        """Clear the stored webhook URL."""
        self._delete_file(self.webhook_state_file)

    def get_tunnel_url(self) -> Optional[str]:
        """Get the cloudflared tunnel URL.

        Returns:
            Tunnel URL string, or None if not set
        """
        return self._read_text_file(self.tunnel_url_file)

    def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        """Get recent Claude Code sessions from history.

        Args:
            limit: Maximum number of sessions to return (default: 5)

        Returns:
            List of session dicts sorted by timestamp (most recent first)
        """
        if not self.history_file.exists():
            return []

        sessions = []
        try:
            with open(self.history_file) as f:
                for line in f:
                    try:
                        sessions.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []

        # Sort by timestamp (most recent first)
        sessions.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return sessions[:limit]

    def get_session_id(self, project_path: str) -> Optional[str]:
        """Get the session ID for a given project path.

        Looks up the most recent .jsonl file in the Claude projects directory
        that matches the encoded project path.

        Args:
            project_path: Project path (e.g., '/home/user/projects/myproject')

        Returns:
            Session ID string (filename stem), or None if not found
        """
        # Encode project path (replace slashes with hyphens, strip leading hyphen)
        encoded = project_path.replace("/", "-").lstrip("-")

        # Try both with and without leading hyphen prefix
        projects_dir = self.claude_dir / "projects"
        for prefix in [f"-{encoded}", encoded]:
            project_dir = projects_dir / prefix
            if not project_dir.exists():
                continue

            # Find all .jsonl files in this project directory
            jsonl_files = list(project_dir.glob("*.jsonl"))
            if not jsonl_files:
                continue

            # Return the most recently modified file's stem (filename without extension)
            most_recent = max(jsonl_files, key=lambda p: p.stat().st_mtime)
            return most_recent.stem

        return None
