"""Tests for session management utilities."""

import json
import pytest
from pathlib import Path
from claudecode_telegram.sessions import (
    get_recent_sessions,
    get_session_id,
    build_session_keyboard
)


@pytest.fixture
def temp_history_file(tmp_path):
    """Create a temporary history.jsonl file."""
    history_file = tmp_path / "history.jsonl"
    return history_file


@pytest.fixture
def temp_claude_dir(tmp_path):
    """Create a temporary Claude directory structure."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    return claude_dir


class TestGetRecentSessions:
    """Tests for get_recent_sessions function."""

    def test_nonexistent_file(self, temp_history_file):
        """Should return empty list if file doesn't exist."""
        result = get_recent_sessions(temp_history_file)
        assert result == []

    def test_empty_file(self, temp_history_file):
        """Should return empty list for empty file."""
        temp_history_file.write_text("")
        result = get_recent_sessions(temp_history_file)
        assert result == []

    def test_single_session(self, temp_history_file):
        """Should return single session."""
        session = {"timestamp": 1000, "project": "/test", "display": "Test"}
        temp_history_file.write_text(json.dumps(session) + "\n")

        result = get_recent_sessions(temp_history_file)
        assert len(result) == 1
        assert result[0] == session

    def test_multiple_sessions_sorted(self, temp_history_file):
        """Should return sessions sorted by timestamp (most recent first)."""
        sessions = [
            {"timestamp": 1000, "project": "/old", "display": "Old"},
            {"timestamp": 3000, "project": "/newest", "display": "Newest"},
            {"timestamp": 2000, "project": "/middle", "display": "Middle"},
        ]

        temp_history_file.write_text(
            "\n".join(json.dumps(s) for s in sessions) + "\n"
        )

        result = get_recent_sessions(temp_history_file)
        assert len(result) == 3
        assert result[0]["timestamp"] == 3000
        assert result[1]["timestamp"] == 2000
        assert result[2]["timestamp"] == 1000

    def test_limit_parameter(self, temp_history_file):
        """Should respect limit parameter."""
        sessions = [
            {"timestamp": i * 1000, "project": f"/proj{i}", "display": f"Proj {i}"}
            for i in range(10)
        ]

        temp_history_file.write_text(
            "\n".join(json.dumps(s) for s in sessions) + "\n"
        )

        result = get_recent_sessions(temp_history_file, limit=3)
        assert len(result) == 3
        # Should get the 3 most recent (highest timestamps)
        assert all(s["timestamp"] >= 7000 for s in result)

    def test_malformed_lines_skipped(self, temp_history_file):
        """Should skip malformed JSON lines."""
        lines = [
            json.dumps({"timestamp": 1000, "project": "/test1", "display": "Test 1"}),
            "invalid json {{{",
            json.dumps({"timestamp": 2000, "project": "/test2", "display": "Test 2"}),
            "",  # Empty line
            json.dumps({"timestamp": 3000, "project": "/test3", "display": "Test 3"}),
        ]

        temp_history_file.write_text("\n".join(lines) + "\n")

        result = get_recent_sessions(temp_history_file)
        assert len(result) == 3
        assert all("timestamp" in s for s in result)

    def test_missing_timestamp_defaults_to_zero(self, temp_history_file):
        """Should handle sessions without timestamp field."""
        sessions = [
            {"timestamp": 2000, "project": "/with_ts", "display": "With TS"},
            {"project": "/no_ts", "display": "No TS"},
            {"timestamp": 1000, "project": "/with_ts2", "display": "With TS 2"},
        ]

        temp_history_file.write_text(
            "\n".join(json.dumps(s) for s in sessions) + "\n"
        )

        result = get_recent_sessions(temp_history_file)
        assert len(result) == 3
        # Session without timestamp should sort to end (timestamp=0)
        assert result[-1]["project"] == "/no_ts"


class TestGetSessionId:
    """Tests for get_session_id function."""

    def test_nonexistent_projects_dir(self, temp_claude_dir):
        """Should return None if projects directory doesn't exist."""
        result = get_session_id("/some/project", temp_claude_dir)
        assert result is None

    def test_empty_project_path(self, temp_claude_dir):
        """Should return None for empty project path."""
        result = get_session_id("", temp_claude_dir)
        assert result is None

    def test_session_found_without_prefix(self, temp_claude_dir):
        """Should find session ID without leading dash prefix."""
        project_path = "/home/user/project"
        encoded = "home-user-project"

        # Create project directory and session file
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()
        session_file = project_dir / "session123.jsonl"
        session_file.write_text("{}")

        result = get_session_id(project_path, temp_claude_dir)
        assert result == "session123"

    def test_session_found_with_prefix(self, temp_claude_dir):
        """Should find session ID with leading dash prefix."""
        project_path = "/home/user/project"
        encoded = "-home-user-project"

        # Create project directory and session file
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()
        session_file = project_dir / "session456.jsonl"
        session_file.write_text("{}")

        result = get_session_id(project_path, temp_claude_dir)
        assert result == "session456"

    def test_most_recent_session_selected(self, temp_claude_dir):
        """Should return most recent session when multiple exist."""
        project_path = "/test/project"
        encoded = "test-project"

        # Create project directory with multiple session files
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()

        # Create files with different modification times
        old_session = project_dir / "old_session.jsonl"
        old_session.write_text("{}")

        import time
        time.sleep(0.01)  # Ensure different mtime

        new_session = project_dir / "new_session.jsonl"
        new_session.write_text("{}")

        result = get_session_id(project_path, temp_claude_dir)
        assert result == "new_session"

    def test_no_jsonl_files(self, temp_claude_dir):
        """Should return None if project dir exists but has no .jsonl files."""
        project_path = "/test/project"
        encoded = "test-project"

        # Create project directory without session files
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()

        result = get_session_id(project_path, temp_claude_dir)
        assert result is None

    def test_path_encoding(self, temp_claude_dir):
        """Should properly encode project paths with multiple slashes."""
        project_path = "/very/deep/nested/project/path"
        encoded = "very-deep-nested-project-path"

        # Create project directory and session file
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()
        session_file = project_dir / "testsession.jsonl"
        session_file.write_text("{}")

        result = get_session_id(project_path, temp_claude_dir)
        assert result == "testsession"


class TestBuildSessionKeyboard:
    """Tests for build_session_keyboard function."""

    def test_empty_sessions_list(self, temp_claude_dir):
        """Should return keyboard with only continue button."""
        result = build_session_keyboard([], temp_claude_dir)

        assert len(result) == 1
        assert result[0][0]["text"] == "Continue most recent"
        assert result[0][0]["callback_data"] == "continue_recent"

    def test_session_without_project_skipped(self, temp_claude_dir):
        """Should skip sessions without project field."""
        sessions = [
            {"timestamp": 1000, "display": "No project"},
            {"timestamp": 2000},  # Missing display and project
        ]

        result = build_session_keyboard(sessions, temp_claude_dir)

        # Only continue button should be present
        assert len(result) == 1

    def test_session_with_invalid_session_id_skipped(self, temp_claude_dir):
        """Should skip sessions where session ID cannot be found."""
        sessions = [
            {"timestamp": 1000, "project": "/nonexistent", "display": "Test"},
        ]

        result = build_session_keyboard(sessions, temp_claude_dir)

        # Only continue button should be present
        assert len(result) == 1

    def test_valid_session_added(self, temp_claude_dir):
        """Should add button for valid session."""
        project_path = "/test/project"
        encoded = "test-project"

        # Create project directory and session file
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()
        session_file = project_dir / "session123.jsonl"
        session_file.write_text("{}")

        sessions = [
            {"timestamp": 1000, "project": project_path, "display": "Test Project"},
        ]

        result = build_session_keyboard(sessions, temp_claude_dir)

        assert len(result) == 2
        assert result[0][0]["text"] == "Continue most recent"
        assert result[1][0]["text"] == "Test Project"
        assert result[1][0]["callback_data"] == "resume:session123"

    def test_display_text_truncation(self, temp_claude_dir):
        """Should truncate display text to 40 characters."""
        project_path = "/test/project"
        encoded = "test-project"

        # Create project directory and session file
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()
        session_file = project_dir / "session123.jsonl"
        session_file.write_text("{}")

        long_display = "This is a very long display name that exceeds forty characters"
        sessions = [
            {"timestamp": 1000, "project": project_path, "display": long_display},
        ]

        result = build_session_keyboard(sessions, temp_claude_dir)

        assert len(result) == 2
        button_text = result[1][0]["text"]
        assert len(button_text) <= 43  # 40 chars + "..."
        assert button_text.endswith("...")
        assert button_text.startswith("This is a very long display name that ex")

    def test_multiple_valid_sessions(self, temp_claude_dir):
        """Should add buttons for all valid sessions."""
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()

        # Create multiple project directories with sessions
        for i in range(3):
            project_path = f"/test/project{i}"
            encoded = f"test-project{i}"
            project_dir = projects_dir / encoded
            project_dir.mkdir()
            session_file = project_dir / f"session{i}.jsonl"
            session_file.write_text("{}")

        sessions = [
            {"timestamp": 1000, "project": "/test/project0", "display": "Project 0"},
            {"timestamp": 2000, "project": "/test/project1", "display": "Project 1"},
            {"timestamp": 3000, "project": "/test/project2", "display": "Project 2"},
        ]

        result = build_session_keyboard(sessions, temp_claude_dir)

        assert len(result) == 4  # Continue button + 3 sessions
        assert result[0][0]["text"] == "Continue most recent"
        assert result[1][0]["callback_data"] == "resume:session0"
        assert result[2][0]["callback_data"] == "resume:session1"
        assert result[3][0]["callback_data"] == "resume:session2"

    def test_missing_display_field(self, temp_claude_dir):
        """Should use '?' as display text if display field is missing."""
        project_path = "/test/project"
        encoded = "test-project"

        # Create project directory and session file
        projects_dir = temp_claude_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / encoded
        project_dir.mkdir()
        session_file = project_dir / "session123.jsonl"
        session_file.write_text("{}")

        sessions = [
            {"timestamp": 1000, "project": project_path},  # No display field
        ]

        result = build_session_keyboard(sessions, temp_claude_dir)

        assert len(result) == 2
        assert result[1][0]["text"] == "?"
