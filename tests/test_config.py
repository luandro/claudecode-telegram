"""
Tests for the configuration module.

Tests environment variable parsing, validation, and default values for BridgeConfig.
"""

import os
import pytest
from pathlib import Path
from claudecode_telegram.config import BridgeConfig


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all relevant environment variables for clean testing."""
    env_vars = [
        "TMUX_SESSION",
        "CLAUDE_DIR",
        "TMUX_SOCKET_PATH",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "TELEGRAM_REACTION_EMOJI",
        "PORT",
        "HOST",
        "WEBHOOK_PATH",
        "DEPLOYMENT_MODE",
        "WEBHOOK_DOMAIN",
        "WEBHOOK_AUTO_SETUP",
        "WEBHOOK_STARTUP_DELAY",
        "ALLOWED_TELEGRAM_USER_IDS",
        "DM_ALLOWED_USER_ID",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def minimal_valid_env(clean_env):
    """Minimal valid environment configuration."""
    clean_env.setenv("TELEGRAM_BOT_TOKEN", "test_token_123")
    clean_env.setenv("DEPLOYMENT_MODE", "tunnel")
    return clean_env


class TestBridgeConfigDefaults:
    """Test default values when environment variables are not set."""

    def test_defaults_with_minimal_config(self, minimal_valid_env):
        config = BridgeConfig.from_env()

        # Core defaults
        assert config.tmux_session == "claude"
        assert config.claude_dir == Path.home() / ".claude"
        assert config.tmux_socket_path == ""

        # Telegram defaults
        assert config.bot_token == "test_token_123"
        assert config.telegram_webhook_secret == ""
        assert config.reaction_emoji == "\U0001f44d"  # 👍

        # Server defaults
        assert config.port == 8080
        assert config.host == "127.0.0.1"
        assert len(config.webhook_path) == 64  # 32 bytes hex = 64 chars

        # Deployment defaults
        assert config.deployment_mode == "tunnel"
        assert config.webhook_domain == ""
        assert config.webhook_auto_setup is True
        assert config.webhook_startup_delay == 5

        # Access control defaults
        assert config.allowed_user_ids == set()
        assert config.dm_allowed_user_id == 0


class TestBridgeConfigEnvironmentParsing:
    """Test parsing of environment variables."""

    def test_parse_tmux_session(self, minimal_valid_env):
        minimal_valid_env.setenv("TMUX_SESSION", "my-session")
        config = BridgeConfig.from_env()
        assert config.tmux_session == "my-session"

    def test_parse_claude_dir(self, minimal_valid_env):
        minimal_valid_env.setenv("CLAUDE_DIR", "/custom/path")
        config = BridgeConfig.from_env()
        assert config.claude_dir == Path("/custom/path")

    def test_parse_claude_dir_expands_home(self, minimal_valid_env):
        minimal_valid_env.setenv("CLAUDE_DIR", "~/.custom")
        config = BridgeConfig.from_env()
        # Should expand ~ to user home directory
        assert str(config.claude_dir).startswith(str(Path.home()))

    def test_parse_tmux_socket_path(self, minimal_valid_env):
        minimal_valid_env.setenv("TMUX_SOCKET_PATH", "/tmp/tmux-socket")
        config = BridgeConfig.from_env()
        assert config.tmux_socket_path == "/tmp/tmux-socket"

    def test_parse_bot_token(self, clean_env):
        clean_env.setenv("TELEGRAM_BOT_TOKEN", "my-token-456")
        clean_env.setenv("WEBHOOK_AUTO_SETUP", "false")
        config = BridgeConfig.from_env()
        assert config.bot_token == "my-token-456"

    def test_parse_webhook_secret(self, minimal_valid_env):
        minimal_valid_env.setenv("TELEGRAM_WEBHOOK_SECRET", "secret123")
        config = BridgeConfig.from_env()
        assert config.telegram_webhook_secret == "secret123"

    def test_parse_port(self, minimal_valid_env):
        minimal_valid_env.setenv("PORT", "3000")
        config = BridgeConfig.from_env()
        assert config.port == 3000

    def test_parse_host(self, minimal_valid_env):
        minimal_valid_env.setenv("HOST", "0.0.0.0")
        config = BridgeConfig.from_env()
        assert config.host == "0.0.0.0"

    def test_parse_webhook_path(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_PATH", "my-webhook-path")
        config = BridgeConfig.from_env()
        assert config.webhook_path == "my-webhook-path"

    def test_generate_webhook_path_if_empty(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_PATH", "")
        config = BridgeConfig.from_env()
        # Should generate a random 64-char hex string
        assert len(config.webhook_path) == 64
        assert all(c in "0123456789abcdef" for c in config.webhook_path)

    def test_parse_deployment_mode(self, minimal_valid_env):
        minimal_valid_env.setenv("DEPLOYMENT_MODE", "production")
        minimal_valid_env.setenv("WEBHOOK_DOMAIN", "example.com")
        config = BridgeConfig.from_env()
        assert config.deployment_mode == "production"

    def test_parse_deployment_mode_case_insensitive(self, minimal_valid_env):
        minimal_valid_env.setenv("DEPLOYMENT_MODE", "TUNNEL")
        config = BridgeConfig.from_env()
        assert config.deployment_mode == "tunnel"

    def test_parse_webhook_domain(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_DOMAIN", "example.com")
        config = BridgeConfig.from_env()
        assert config.webhook_domain == "example.com"

    def test_parse_webhook_auto_setup_true(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_AUTO_SETUP", "true")
        config = BridgeConfig.from_env()
        assert config.webhook_auto_setup is True

    def test_parse_webhook_auto_setup_false(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_AUTO_SETUP", "false")
        config = BridgeConfig.from_env()
        assert config.webhook_auto_setup is False

    def test_parse_webhook_auto_setup_zero(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_AUTO_SETUP", "0")
        config = BridgeConfig.from_env()
        assert config.webhook_auto_setup is False

    def test_parse_webhook_startup_delay(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_STARTUP_DELAY", "10")
        config = BridgeConfig.from_env()
        assert config.webhook_startup_delay == 10

    def test_parse_webhook_startup_delay_invalid(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_STARTUP_DELAY", "invalid")
        config = BridgeConfig.from_env()
        # Should default to 5
        assert config.webhook_startup_delay == 5


class TestBridgeConfigReactionEmoji:
    """Test reaction emoji parsing logic."""

    def test_default_reaction_emoji(self, minimal_valid_env):
        config = BridgeConfig.from_env()
        assert config.reaction_emoji == "\U0001f44d"  # 👍

    def test_custom_reaction_emoji(self, minimal_valid_env):
        minimal_valid_env.setenv("TELEGRAM_REACTION_EMOJI", "🎉")
        config = BridgeConfig.from_env()
        assert config.reaction_emoji == "🎉"

    def test_disable_reaction_emoji_none(self, minimal_valid_env):
        minimal_valid_env.setenv("TELEGRAM_REACTION_EMOJI", "none")
        config = BridgeConfig.from_env()
        assert config.reaction_emoji is None

    def test_disable_reaction_emoji_false(self, minimal_valid_env):
        minimal_valid_env.setenv("TELEGRAM_REACTION_EMOJI", "false")
        config = BridgeConfig.from_env()
        assert config.reaction_emoji is None

    def test_disable_reaction_emoji_zero(self, minimal_valid_env):
        minimal_valid_env.setenv("TELEGRAM_REACTION_EMOJI", "0")
        config = BridgeConfig.from_env()
        assert config.reaction_emoji is None

    def test_reaction_emoji_length_validation(self, minimal_valid_env):
        # Too long (>10 chars) should be rejected
        minimal_valid_env.setenv("TELEGRAM_REACTION_EMOJI", "x" * 11)
        config = BridgeConfig.from_env()
        assert config.reaction_emoji is None


class TestBridgeConfigAccessControl:
    """Test access control configuration."""

    def test_parse_single_allowed_user_id(self, minimal_valid_env):
        minimal_valid_env.setenv("ALLOWED_TELEGRAM_USER_IDS", "123456789")
        config = BridgeConfig.from_env()
        assert config.allowed_user_ids == {123456789}

    def test_parse_multiple_allowed_user_ids(self, minimal_valid_env):
        minimal_valid_env.setenv("ALLOWED_TELEGRAM_USER_IDS", "123,456,789")
        config = BridgeConfig.from_env()
        assert config.allowed_user_ids == {123, 456, 789}

    def test_parse_allowed_user_ids_with_spaces(self, minimal_valid_env):
        minimal_valid_env.setenv("ALLOWED_TELEGRAM_USER_IDS", "123, 456 , 789")
        config = BridgeConfig.from_env()
        assert config.allowed_user_ids == {123, 456, 789}

    def test_parse_allowed_user_ids_empty_string(self, minimal_valid_env):
        minimal_valid_env.setenv("ALLOWED_TELEGRAM_USER_IDS", "")
        config = BridgeConfig.from_env()
        assert config.allowed_user_ids == set()

    def test_parse_allowed_user_ids_invalid_format(self, minimal_valid_env, capsys):
        minimal_valid_env.setenv("ALLOWED_TELEGRAM_USER_IDS", "123,abc,456")
        config = BridgeConfig.from_env()
        # Should return empty set on error and print warning
        assert config.allowed_user_ids == set()
        captured = capsys.readouterr()
        assert "Warning: Invalid ALLOWED_TELEGRAM_USER_IDS format" in captured.out

    def test_parse_dm_allowed_user_id(self, minimal_valid_env):
        minimal_valid_env.setenv("DM_ALLOWED_USER_ID", "987654321")
        config = BridgeConfig.from_env()
        assert config.dm_allowed_user_id == 987654321

    def test_parse_dm_allowed_user_id_empty(self, minimal_valid_env):
        minimal_valid_env.setenv("DM_ALLOWED_USER_ID", "")
        config = BridgeConfig.from_env()
        assert config.dm_allowed_user_id == 0

    def test_parse_dm_allowed_user_id_invalid(self, minimal_valid_env, capsys):
        minimal_valid_env.setenv("DM_ALLOWED_USER_ID", "invalid")
        config = BridgeConfig.from_env()
        assert config.dm_allowed_user_id == 0
        captured = capsys.readouterr()
        assert "Warning: Invalid DM_ALLOWED_USER_ID format" in captured.out


class TestBridgeConfigValidation:
    """Test configuration validation logic."""

    def test_validate_minimal_valid_config(self, minimal_valid_env):
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert errors == []

    def test_validate_missing_bot_token(self, clean_env):
        clean_env.setenv("WEBHOOK_AUTO_SETUP", "false")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert "TELEGRAM_BOT_TOKEN is required" in errors

    def test_validate_invalid_port_low(self, minimal_valid_env):
        minimal_valid_env.setenv("PORT", "0")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert any("PORT must be between 1 and 65535" in e for e in errors)

    def test_validate_invalid_port_high(self, minimal_valid_env):
        minimal_valid_env.setenv("PORT", "70000")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert any("PORT must be between 1 and 65535" in e for e in errors)

    def test_validate_missing_deployment_mode(self, minimal_valid_env):
        minimal_valid_env.delenv("DEPLOYMENT_MODE")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert "DEPLOYMENT_MODE must be set when WEBHOOK_AUTO_SETUP is enabled" in errors

    def test_validate_invalid_deployment_mode(self, minimal_valid_env):
        minimal_valid_env.setenv("DEPLOYMENT_MODE", "invalid")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert any("DEPLOYMENT_MODE must be 'tunnel' or 'production'" in e for e in errors)

    def test_validate_production_without_domain(self, minimal_valid_env):
        minimal_valid_env.setenv("DEPLOYMENT_MODE", "production")
        minimal_valid_env.setenv("WEBHOOK_DOMAIN", "")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert "WEBHOOK_DOMAIN is required when DEPLOYMENT_MODE is 'production'" in errors

    def test_validate_production_with_domain(self, minimal_valid_env):
        minimal_valid_env.setenv("DEPLOYMENT_MODE", "production")
        minimal_valid_env.setenv("WEBHOOK_DOMAIN", "example.com")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert errors == []

    def test_validate_negative_startup_delay(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_STARTUP_DELAY", "-5")
        config = BridgeConfig.from_env()
        errors = config.validate()
        assert any("WEBHOOK_STARTUP_DELAY must be non-negative" in e for e in errors)

    def test_validate_webhook_auto_setup_disabled(self, minimal_valid_env):
        minimal_valid_env.setenv("WEBHOOK_AUTO_SETUP", "false")
        minimal_valid_env.delenv("DEPLOYMENT_MODE")
        config = BridgeConfig.from_env()
        errors = config.validate()
        # Should not require DEPLOYMENT_MODE when auto-setup is disabled
        assert not any("DEPLOYMENT_MODE" in e for e in errors)


class TestBridgeConfigComputedProperties:
    """Test computed file path properties."""

    def test_chat_id_file_property(self, minimal_valid_env):
        config = BridgeConfig.from_env()
        expected = config.claude_dir / "telegram_chat_id"
        assert config.chat_id_file == expected

    def test_pending_file_property(self, minimal_valid_env):
        config = BridgeConfig.from_env()
        expected = config.claude_dir / "telegram_pending"
        assert config.pending_file == expected

    def test_history_file_property(self, minimal_valid_env):
        config = BridgeConfig.from_env()
        expected = config.claude_dir / "history.jsonl"
        assert config.history_file == expected

    def test_webhook_state_file_property(self, minimal_valid_env):
        config = BridgeConfig.from_env()
        expected = config.claude_dir / "telegram_webhook_url"
        assert config.webhook_state_file == expected

    def test_tunnel_url_file_property(self, minimal_valid_env):
        config = BridgeConfig.from_env()
        expected = config.claude_dir / "cloudflared_tunnel_url"
        assert config.tunnel_url_file == expected

    def test_properties_with_custom_claude_dir(self, minimal_valid_env):
        minimal_valid_env.setenv("CLAUDE_DIR", "/custom/claude")
        config = BridgeConfig.from_env()
        assert config.chat_id_file == Path("/custom/claude/telegram_chat_id")
        assert config.pending_file == Path("/custom/claude/telegram_pending")
        assert config.history_file == Path("/custom/claude/history.jsonl")
        assert config.webhook_state_file == Path("/custom/claude/telegram_webhook_url")
        assert config.tunnel_url_file == Path("/custom/claude/cloudflared_tunnel_url")


class TestBridgeConfigComplexScenarios:
    """Test complex configuration scenarios."""

    def test_full_production_config(self, clean_env):
        clean_env.setenv("TELEGRAM_BOT_TOKEN", "prod-token")
        clean_env.setenv("TELEGRAM_WEBHOOK_SECRET", "secret123")
        clean_env.setenv("DEPLOYMENT_MODE", "production")
        clean_env.setenv("WEBHOOK_DOMAIN", "bot.example.com")
        clean_env.setenv("PORT", "443")
        clean_env.setenv("HOST", "0.0.0.0")
        clean_env.setenv("ALLOWED_TELEGRAM_USER_IDS", "123,456")
        clean_env.setenv("DM_ALLOWED_USER_ID", "123")

        config = BridgeConfig.from_env()
        errors = config.validate()

        assert errors == []
        assert config.bot_token == "prod-token"
        assert config.deployment_mode == "production"
        assert config.webhook_domain == "bot.example.com"
        assert config.port == 443
        assert config.host == "0.0.0.0"
        assert config.allowed_user_ids == {123, 456}
        assert config.dm_allowed_user_id == 123

    def test_full_tunnel_config(self, clean_env):
        clean_env.setenv("TELEGRAM_BOT_TOKEN", "tunnel-token")
        clean_env.setenv("DEPLOYMENT_MODE", "tunnel")
        clean_env.setenv("WEBHOOK_STARTUP_DELAY", "10")
        clean_env.setenv("TMUX_SESSION", "my-claude")
        clean_env.setenv("CLAUDE_DIR", "/custom/.claude")

        config = BridgeConfig.from_env()
        errors = config.validate()

        assert errors == []
        assert config.deployment_mode == "tunnel"
        assert config.webhook_startup_delay == 10
        assert config.tmux_session == "my-claude"
        assert config.claude_dir == Path("/custom/.claude")
