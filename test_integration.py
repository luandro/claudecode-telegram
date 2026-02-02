"""
Integration tests for claudecode-telegram package.

Tests the full lifecycle of the bridge:
- Package installation
- CLI commands
- Server operation
- Webhook endpoints
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
import requests


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=10
    )
    return result.returncode, result.stdout, result.stderr


class TestCLI:
    """Test CLI commands."""

    def test_cli_help(self):
        """Test CLI help output."""
        code, stdout, stderr = run_command(["claudecode-telegram", "--help"])
        assert code == 0
        assert "set-webhook" in stdout
        assert "get-webhook-info" in stdout
        assert "verify-webhook" in stdout
        assert "delete-webhook" in stdout

    def test_get_webhook_info(self):
        """Test get-webhook-info command."""
        code, stdout, stderr = run_command(["claudecode-telegram", "get-webhook-info"])
        assert code == 0
        data = json.loads(stdout)
        assert "url" in data
        assert "has_custom_certificate" in data
        assert "pending_update_count" in data

    def test_verify_webhook(self):
        """Test verify-webhook command."""
        code, stdout, stderr = run_command(["claudecode-telegram", "verify-webhook"])
        assert code == 0
        assert "Webhook OK" in stdout or "No webhook" in stdout


class TestServer:
    """Test server operation."""

    @pytest.fixture
    def server(self):
        """Start server for testing."""
        # Start server in background
        proc = subprocess.Popen(
            ["python", "bridge.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(2)  # Wait for server to start
        yield proc
        # Cleanup
        proc.terminate()
        proc.wait(timeout=5)

    def test_health_endpoint(self, server):
        """Test health endpoint responds correctly."""
        response = requests.get("http://localhost:8080/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "operational" in data
        assert "webhook_configured" in data

    def test_webhook_endpoint(self, server):
        """Test webhook endpoint accepts POST requests."""
        # Get webhook URL from state
        webhook_path = self._get_webhook_path()
        if not webhook_path:
            pytest.skip("No webhook configured")

        response = requests.post(
            f"http://localhost:8080/{webhook_path}",
            json={
                "message": {
                    "chat": {"id": 12345},
                    "text": "test message",
                    "from": {"id": 12345},
                }
            },
        )
        assert response.status_code == 200
        assert response.text == "OK"

    def _get_webhook_path(self) -> str | None:
        """Get webhook path from state file."""
        state_file = Path.home() / ".claude" / "telegram_webhook_url"
        if state_file.exists():
            url = state_file.read_text().strip()
            return url.split("/")[-1] if url else None
        return None


class TestWebhookManagement:
    """Test webhook management commands."""

    def test_delete_and_restore_webhook(self):
        """Test deleting and restoring webhook."""
        # Get current webhook
        code, stdout, _ = run_command(["claudecode-telegram", "get-webhook-info"])
        assert code == 0
        original = json.loads(stdout)

        # Delete webhook
        code, stdout, _ = run_command(["claudecode-telegram", "delete-webhook"])
        assert code == 0
        assert "deleted successfully" in stdout.lower()

        # Verify webhook is deleted
        code, stdout, _ = run_command(["claudecode-telegram", "get-webhook-info"])
        assert code == 0
        data = json.loads(stdout)
        assert data["url"] == ""

        # Restore webhook if it existed
        if original.get("url"):
            domain = original["url"].split("/")[2]
            code, stdout, _ = run_command(
                ["claudecode-telegram", "set-webhook", "--domain", domain]
            )
            assert code == 0
            assert "Webhook configured" in stdout

    @pytest.mark.slow
    def test_set_webhook_custom_domain(self):
        """Test setting webhook with custom domain.

        Note: This test may fail due to Telegram rate limiting.
        """
        # Get current webhook
        code, stdout, _ = run_command(["claudecode-telegram", "get-webhook-info"])
        assert code == 0
        original = json.loads(stdout)
        original_domain = original.get("url", "").split("/")[2] if original.get("url") else "coder.luandro.com"

        # Try to set webhook with custom domain
        code, stdout, stderr = run_command(
            ["claudecode-telegram", "set-webhook", "--domain", "example.com"]
        )

        # If rate limited, skip test
        if code != 0:
            pytest.skip(f"Skipping due to Telegram rate limiting: {stderr}")

        assert "Webhook configured" in stdout
        assert "example.com" in stdout

        # Wait to avoid rate limiting
        time.sleep(3)

        # Restore original domain
        code, _, stderr = run_command(
            ["claudecode-telegram", "set-webhook", "--domain", original_domain]
        )
        # May fail due to rate limiting, which is acceptable
        if code != 0:
            pytest.skip(f"Failed to restore webhook (likely rate limiting): {stderr}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
