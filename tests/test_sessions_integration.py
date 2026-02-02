"""Integration tests for session management utilities with bridge.py usage."""

import json
import time
from pathlib import Path
import pytest

from claudecode_telegram.sessions import (
    get_recent_sessions,
    get_session_id,
    build_session_keyboard
)


@pytest.fixture
def mock_project_structure(tmp_path):
    """Create a mock Claude project structure."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    # Create history file
    history_file = claude_dir / "history.jsonl"

    # Create projects directory
    projects_dir = claude_dir / "projects"
    projects_dir.mkdir()

    return {
        "claude_dir": claude_dir,
        "history_file": history_file,
        "projects_dir": projects_dir
    }


def test_full_resume_workflow(mock_project_structure):
    """Test complete workflow from history to keyboard generation."""
    claude_dir = mock_project_structure["claude_dir"]
    history_file = mock_project_structure["history_file"]
    projects_dir = mock_project_structure["projects_dir"]

    # Step 1: Create history entries
    sessions_data = [
        {
            "timestamp": 1000,
            "project": "/home/user/project1",
            "display": "Project One"
        },
        {
            "timestamp": 2000,
            "project": "/home/user/project2",
            "display": "Project Two - This is a very long name that should be truncated"
        },
        {
            "timestamp": 3000,
            "project": "/home/user/project3",
            "display": "Project Three"
        }
    ]

    # Write history file
    with open(history_file, "w") as f:
        for session in sessions_data:
            f.write(json.dumps(session) + "\n")

    # Step 2: Create project directories with session files
    for i, session in enumerate(sessions_data, 1):
        project_path = session["project"]
        encoded = project_path.replace("/", "-").lstrip("-")
        project_dir = projects_dir / encoded
        project_dir.mkdir()

        # Create session file with increasing mtime
        session_file = project_dir / f"session{i}.jsonl"
        session_file.write_text("{}")
        time.sleep(0.01)  # Ensure different mtime

    # Step 3: Get recent sessions
    recent_sessions = get_recent_sessions(history_file, limit=5)
    assert len(recent_sessions) == 3
    assert recent_sessions[0]["timestamp"] == 3000  # Most recent first

    # Step 4: Build keyboard
    keyboard = build_session_keyboard(recent_sessions, claude_dir)

    # Verify keyboard structure
    assert len(keyboard) == 4  # Continue button + 3 sessions

    # Verify continue button
    assert keyboard[0][0]["text"] == "Continue most recent"
    assert keyboard[0][0]["callback_data"] == "continue_recent"

    # Verify session buttons (should be in order from recent_sessions)
    assert keyboard[1][0]["callback_data"] == "resume:session3"
    assert keyboard[2][0]["callback_data"] == "resume:session2"
    assert keyboard[3][0]["callback_data"] == "resume:session1"

    # Verify truncation
    assert len(keyboard[2][0]["text"]) <= 43
    assert keyboard[2][0]["text"].endswith("...")


def test_bridge_compatibility_pattern(mock_project_structure):
    """Test that the module follows the same pattern as bridge.py."""
    claude_dir = mock_project_structure["claude_dir"]
    history_file = mock_project_structure["history_file"]
    projects_dir = mock_project_structure["projects_dir"]

    # Create a session structure similar to bridge.py usage
    project_path = "/test/myproject"
    encoded = "test-myproject"

    # Create project directory with session
    project_dir = projects_dir / encoded
    project_dir.mkdir()
    session_file = project_dir / "abc123.jsonl"
    session_file.write_text('{"test": "data"}')

    # Create history entry
    history_data = {
        "timestamp": int(time.time()),
        "project": project_path,
        "display": "My Test Project"
    }
    history_file.write_text(json.dumps(history_data) + "\n")

    # Simulate bridge.py workflow
    sessions = get_recent_sessions(history_file)
    assert len(sessions) == 1

    session = sessions[0]
    session_id = get_session_id(session["project"], claude_dir)
    assert session_id == "abc123"

    # Build keyboard
    keyboard = build_session_keyboard([session], claude_dir)
    assert len(keyboard) == 2
    assert keyboard[1][0]["callback_data"] == "resume:abc123"


def test_handles_missing_sessions_gracefully(mock_project_structure):
    """Test graceful handling when some sessions are missing."""
    claude_dir = mock_project_structure["claude_dir"]
    history_file = mock_project_structure["history_file"]
    projects_dir = mock_project_structure["projects_dir"]

    # Create history with mix of valid and invalid sessions
    sessions_data = [
        {
            "timestamp": 1000,
            "project": "/valid/project",
            "display": "Valid Project"
        },
        {
            "timestamp": 2000,
            "project": "/missing/project",
            "display": "Missing Project"
        },
        {
            "timestamp": 3000,
            "project": "/another/valid",
            "display": "Another Valid"
        }
    ]

    # Write history
    with open(history_file, "w") as f:
        for session in sessions_data:
            f.write(json.dumps(session) + "\n")

    # Only create session files for two projects
    for project_path in ["/valid/project", "/another/valid"]:
        encoded = project_path.replace("/", "-").lstrip("-")
        project_dir = projects_dir / encoded
        project_dir.mkdir()
        session_file = project_dir / "testsession.jsonl"
        session_file.write_text("{}")

    # Get recent sessions
    recent_sessions = get_recent_sessions(history_file)
    assert len(recent_sessions) == 3

    # Build keyboard - should skip missing project
    keyboard = build_session_keyboard(recent_sessions, claude_dir)
    assert len(keyboard) == 3  # Continue button + 2 valid sessions

    # Verify only valid sessions are in keyboard
    callback_data = [row[0]["callback_data"] for row in keyboard[1:]]
    assert "testsession" in str(callback_data)
    assert all("resume:" in cd for cd in callback_data)


def test_empty_state_handling(mock_project_structure):
    """Test handling of completely empty state."""
    claude_dir = mock_project_structure["claude_dir"]
    history_file = mock_project_structure["history_file"]

    # Don't create history file - test nonexistent state
    sessions = get_recent_sessions(history_file)
    assert sessions == []

    keyboard = build_session_keyboard(sessions, claude_dir)
    assert len(keyboard) == 1  # Only continue button
    assert keyboard[0][0]["text"] == "Continue most recent"
