"""Session management utilities for Claude Code Telegram bridge."""

import json
from pathlib import Path


def get_recent_sessions(history_file: Path, limit: int = 5) -> list[dict]:
    """Get recent sessions from history file, sorted by timestamp.

    Args:
        history_file: Path to history.jsonl file
        limit: Maximum number of sessions to return

    Returns:
        List of session dictionaries sorted by timestamp (most recent first)
        Returns empty list if file doesn't exist or on error
    """
    if not history_file.exists():
        return []

    sessions = []
    try:
        with open(history_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    session = json.loads(line)
                    sessions.append(session)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue
    except (IOError, OSError):
        return []

    # Sort by timestamp (descending) and limit results
    sessions.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return sessions[:limit]


def get_session_id(project_path: str, claude_dir: Path) -> str | None:
    """Find session ID from project path by searching .claude/projects/.

    Args:
        project_path: Absolute path to project directory
        claude_dir: Path to Claude directory (typically ~/.claude)

    Returns:
        Session ID string if found, None otherwise
    """
    if not project_path:
        return None

    # Encode project path: replace / with - and remove leading -
    encoded = project_path.replace("/", "-").lstrip("-")

    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return None

    # Try both with and without leading dash prefix
    for prefix in [f"-{encoded}", encoded]:
        project_dir = projects_dir / prefix
        if not project_dir.exists():
            continue

        # Find most recent .jsonl file in project directory
        try:
            jsonl_files = list(project_dir.glob("*.jsonl"))
            if jsonl_files:
                # Return stem (filename without extension) of most recent file
                most_recent = max(jsonl_files, key=lambda p: p.stat().st_mtime)
                return most_recent.stem
        except (IOError, OSError):
            continue

    return None


def build_session_keyboard(
    sessions: list[dict],
    claude_dir: Path
) -> list[list[dict]]:
    """Build inline keyboard for resume command from session list.

    Args:
        sessions: List of session dictionaries from get_recent_sessions
        claude_dir: Path to Claude directory (typically ~/.claude)

    Returns:
        Telegram inline keyboard markup structure (list of button rows)
    """
    keyboard = []

    # Add "Continue most recent" button as first row
    keyboard.append([{
        "text": "Continue most recent",
        "callback_data": "continue_recent"
    }])

    # Add button for each session with valid session ID
    for session in sessions:
        project_path = session.get("project", "")
        if not project_path:
            continue

        session_id = get_session_id(project_path, claude_dir)
        if not session_id:
            continue

        # Truncate display text to 40 chars
        display_text = session.get("display", "?")[:40]
        if len(session.get("display", "")) > 40:
            display_text += "..."

        keyboard.append([{
            "text": display_text,
            "callback_data": f"resume:{session_id}"
        }])

    return keyboard
