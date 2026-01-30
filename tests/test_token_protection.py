"""Tests for token protection pre-commit hook."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestTokenProtection(unittest.TestCase):
    """Test the pre-commit hook's token detection capabilities."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.test_dir.name)
        self.hook_path = Path(__file__).parent.parent / "githooks" / "pre-commit"

    def tearDown(self):
        """Clean up test fixtures."""
        self.test_dir.cleanup()

    def _run_hook_on_file(self, content: str, filename: str = "test.py") -> tuple:
        """Run the pre-commit hook on a test file.

        Returns:
            tuple: (return_code, stdout, stderr)
        """
        test_file = self.test_path / filename
        test_file.write_text(content)

        # Create a minimal git repo for testing
        subprocess.run(["git", "init"], cwd=self.test_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.test_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.test_path, capture_output=True)
        subprocess.run(["git", "add", filename], cwd=self.test_path, capture_output=True)

        # Run the hook
        result = subprocess.run(
            [str(self.hook_path)],
            cwd=self.test_path,
            capture_output=True,
            text=True
        )

        return result.returncode, result.stdout, result.stderr

    def test_telegram_bot_token_detected(self):
        """Test that Telegram bot tokens are detected."""
        # Real token format: bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz
        content = 'BOT_TOKEN = "bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz012345ABCdefGHIjklMNO"'
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertNotEqual(return_code, 0, "Hook should reject commits with bot tokens")
        self.assertIn("Potential token found", stdout)

    def test_webhook_secret_detected(self):
        """Test that webhook secrets are detected."""
        # Base64-like string 40+ chars with = padding
        content = 'SECRET = "abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ="'  # 64 chars
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertNotEqual(return_code, 0, "Hook should reject commits with webhook secrets")
        self.assertIn("Potential token found", stdout)

    def test_hardcoded_token_assignment_detected(self):
        """Test that hardcoded TELEGRAM_BOT_TOKEN assignments are detected."""
        content = 'TELEGRAM_BOT_TOKEN = "bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz012345ABCdefGHIjklMNO"'
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertNotEqual(return_code, 0, "Hook should reject commits with hardcoded token assignments")
        self.assertIn("Potential token found", stdout)

    def test_hardcoded_secret_assignment_detected(self):
        """Test that hardcoded TELEGRAM_WEBHOOK_SECRET assignments are detected."""
        content = 'TELEGRAM_WEBHOOK_SECRET = "super_secret_key_1234567890abcdefghijABCDEFGHIJ="'  # 50+ chars
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertNotEqual(return_code, 0, "Hook should reject commits with hardcoded secret assignments")
        self.assertIn("Potential token found", stdout)

    def test_safe_code_passes(self):
        """Test that safe code passes the hook."""
        content = '''
import os
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
'''
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertEqual(return_code, 0, "Hook should allow safe code using environment variables")
        self.assertIn("No sensitive tokens detected", stdout)

    def test_example_files_excluded(self):
        """Test that .example files are excluded from scanning."""
        content = 'BOT_TOKEN = "bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz012345ABCdefGHIjklMNO"'
        return_code, stdout, _ = self._run_hook_on_file(content, "config.example.py")
        self.assertEqual(return_code, 0, "Hook should exclude .example files")
        self.assertIn("No sensitive tokens detected", stdout)

    def test_test_files_excluded(self):
        """Test that test files are excluded from scanning."""
        content = 'BOT_TOKEN = "bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz012345ABCdefGHIjklMNO"'
        return_code, stdout, _ = self._run_hook_on_file(content, "test_config.py")
        self.assertEqual(return_code, 0, "Hook should exclude test files")
        self.assertIn("No sensitive tokens detected", stdout)

    def test_placeholder_values_pass(self):
        """Test that placeholder values pass the hook."""
        content = 'TELEGRAM_BOT_TOKEN = "your_bot_token_here"'
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertEqual(return_code, 0, "Hook should allow placeholder values")
        self.assertIn("No sensitive tokens detected", stdout)

    def test_empty_token_passes(self):
        """Test that empty token values pass the hook."""
        content = 'TELEGRAM_BOT_TOKEN = ""'
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertEqual(return_code, 0, "Hook should allow empty token values")
        self.assertIn("No sensitive tokens detected", stdout)

    def test_short_strings_pass(self):
        """Test that short strings (not token-like) pass the hook."""
        content = '''
API_KEY = "abc123"
SHORT_VAR = "test"
'''
        return_code, stdout, _ = self._run_hook_on_file(content)
        self.assertEqual(return_code, 0, "Hook should allow short strings")
        self.assertIn("No sensitive tokens detected", stdout)

    def test_no_staged_files(self):
        """Test hook behavior when no files are staged."""
        # Create repo but don't stage any files
        subprocess.run(["git", "init"], cwd=self.test_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.test_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.test_path, capture_output=True)

        result = subprocess.run(
            [str(self.hook_path)],
            cwd=self.test_path,
            capture_output=True,
            text=True
        )

        self.assertEqual(result.returncode, 0, "Hook should succeed when no files are staged")


if __name__ == "__main__":
    unittest.main()
