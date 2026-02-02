"""
Configuration management for claudecode-telegram.

Handles loading and validation of environment variables, default paths,
and runtime configuration for the Telegram bridge server.
"""

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """Configuration validation error."""
    pass


def _parse_allowed_user_ids(raw: str) -> set[int]:
    """Parse comma-separated user IDs into a set of integers.

    Args:
        raw: Comma-separated user ID string (e.g., "123,456,789")

    Returns:
        Set of parsed user IDs, empty set on parse error
    """
    if not raw.strip():
        return set()

    try:
        return set(
            int(uid.strip())
            for uid in raw.split(",")
            if uid.strip()
        )
    except ValueError:
        print(f"Warning: Invalid user IDs format: {raw}")
        return set()


def _parse_reaction_emoji(raw: str) -> str | None:
    """Parse and validate reaction emoji configuration.

    Args:
        raw: Raw emoji string from environment variable

    Returns:
        Validated emoji string, None if disabled or invalid
    """
    raw = raw.strip()

    if not raw:
        return "\U0001f44d"  # Default: 👍

    if raw.lower() in ("none", "false", "0"):
        return None

    # Basic validation: emoji should be reasonable length (1-10 chars)
    if len(raw) <= 10:
        return raw

    return None


def _generate_webhook_path() -> str:
    """Generate a secure random webhook path.

    Returns:
        64-character hexadecimal string
    """
    return secrets.token_hex(32)


def _is_valid_domain(domain: str) -> bool:
    """Basic domain name validation.

    Args:
        domain: Domain name to validate (e.g., 'example.com', 'sub.example.com')

    Returns:
        True if domain format is valid, False otherwise
    """
    if not domain or len(domain) > 253:
        return False
    # Basic pattern: alphanumeric + hyphens + dots, proper TLD
    pattern = r'^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$'
    return bool(re.match(pattern, domain.lower()))


@dataclass
class BridgeConfig:
    """Centralized configuration for the Telegram bridge.

    All configuration values are loaded from environment variables with
    sensible defaults. Use BridgeConfig.from_env() to create an instance.
    """

    # Core paths and session
    tmux_session: str
    claude_dir: Path
    tmux_socket_path: str

    # Telegram API
    bot_token: str
    telegram_webhook_secret: str
    reaction_emoji: str | None

    # Server configuration
    port: int
    host: str
    webhook_path: str

    # Deployment configuration
    deployment_mode: str
    webhook_domain: str
    webhook_auto_setup: bool
    webhook_startup_delay: int

    # Access control
    allowed_user_ids: set[int] = field(default_factory=set)
    dm_allowed_user_id: int = 0

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        """Load configuration from environment variables.

        Returns:
            BridgeConfig instance with all values loaded from environment
        """
        # Core paths and session
        tmux_session = os.environ.get("TMUX_SESSION", "claude")
        claude_dir = Path(os.path.expanduser(os.environ.get("CLAUDE_DIR", "~/.claude")))
        tmux_socket_path = os.environ.get("TMUX_SOCKET_PATH", "")

        # Telegram API
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        telegram_webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

        # Reaction emoji with validation
        reaction_emoji = _parse_reaction_emoji(os.environ.get("TELEGRAM_REACTION_EMOJI", ""))

        # Server configuration
        port = int(os.environ.get("PORT", "8080"))
        host = os.environ.get("HOST", "127.0.0.1")

        # Generate webhook path if not provided
        webhook_path = os.environ.get("WEBHOOK_PATH", "").strip()
        if not webhook_path:
            webhook_path = _generate_webhook_path()

        # Deployment configuration
        deployment_mode = os.environ.get("DEPLOYMENT_MODE", "").lower().strip()
        webhook_domain = os.environ.get("WEBHOOK_DOMAIN", "").strip()
        webhook_auto_setup = os.environ.get("WEBHOOK_AUTO_SETUP", "true").lower() not in ("false", "0", "no")

        # Parse startup delay
        raw_delay = os.environ.get("WEBHOOK_STARTUP_DELAY", "5")
        try:
            webhook_startup_delay = int(raw_delay)
        except ValueError:
            webhook_startup_delay = 5

        # Access control - parse allowed user IDs
        allowed_user_ids = _parse_allowed_user_ids(
            os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "")
        )

        # Parse DM allowed user ID
        dm_allowed_user_id = 0
        dm_allowed_raw = os.environ.get("DM_ALLOWED_USER_ID", "").strip()
        if dm_allowed_raw:
            try:
                dm_allowed_user_id = int(dm_allowed_raw)
            except ValueError:
                print(f"Warning: Invalid DM_ALLOWED_USER_ID format: {dm_allowed_raw}")

        return cls(
            tmux_session=tmux_session,
            claude_dir=claude_dir,
            tmux_socket_path=tmux_socket_path,
            bot_token=bot_token,
            telegram_webhook_secret=telegram_webhook_secret,
            reaction_emoji=reaction_emoji,
            port=port,
            host=host,
            webhook_path=webhook_path,
            deployment_mode=deployment_mode,
            webhook_domain=webhook_domain,
            webhook_auto_setup=webhook_auto_setup,
            webhook_startup_delay=webhook_startup_delay,
            allowed_user_ids=allowed_user_ids,
            dm_allowed_user_id=dm_allowed_user_id,
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of error messages.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors = []

        # Required fields
        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")

        # Port validation
        if not (1 <= self.port <= 65535):
            errors.append(f"PORT must be between 1 and 65535, got {self.port}")

        # Deployment mode validation
        if self.webhook_auto_setup:
            if not self.deployment_mode:
                errors.append("DEPLOYMENT_MODE must be set when WEBHOOK_AUTO_SETUP is enabled")
            elif self.deployment_mode not in ("tunnel", "production"):
                errors.append(f"DEPLOYMENT_MODE must be 'tunnel' or 'production', got '{self.deployment_mode}'")

            # Production mode requires valid domain
            if self.deployment_mode == "production":
                if not self.webhook_domain:
                    errors.append("WEBHOOK_DOMAIN is required when DEPLOYMENT_MODE is 'production'")
                elif not _is_valid_domain(self.webhook_domain):
                    errors.append(f"WEBHOOK_DOMAIN has invalid format: '{self.webhook_domain}'")

        # Startup delay validation
        if self.webhook_startup_delay < 0:
            errors.append(f"WEBHOOK_STARTUP_DELAY must be non-negative, got {self.webhook_startup_delay}")

        # Path validation
        if not self.claude_dir:
            errors.append("CLAUDE_DIR cannot be empty")

        # Webhook path validation
        if not self.webhook_path:
            errors.append("WEBHOOK_PATH cannot be empty")

        return errors

    # Computed properties for backward compatibility

    @property
    def chat_id_file(self) -> Path:
        """Path to chat ID state file."""
        return self.claude_dir / "telegram_chat_id"

    @property
    def pending_file(self) -> Path:
        """Path to pending message state file."""
        return self.claude_dir / "telegram_pending"

    @property
    def history_file(self) -> Path:
        """Path to session history file."""
        return self.claude_dir / "history.jsonl"

    @property
    def webhook_state_file(self) -> Path:
        """Path to webhook state file."""
        return self.claude_dir / "telegram_webhook_url"

    @property
    def tunnel_url_file(self) -> Path:
        """Path to cloudflared tunnel URL file."""
        return self.claude_dir / "cloudflared_tunnel_url"
