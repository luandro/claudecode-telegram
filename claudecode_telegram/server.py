"""
HTTP server for Telegram webhook bridge.

Implements the main server setup logic that receives Telegram webhook requests
and serves the bridge between Telegram and Claude Code.
"""

import shutil
from http.server import HTTPServer
from pathlib import Path
from typing import Tuple

from .config import BridgeConfig
from .handler import create_handler_class
from .state import StateManager
from .telegram import TelegramClient
from .tmux import TmuxController
from .webhook import WebhookManager
from .commands.registry import CommandRegistry


def setup_hooks(claude_dir: Path, source_dir: Path) -> None:
    """Install the Claude Code Stop hook if it doesn't exist or update if needed.

    Copies the send-to-telegram.sh hook script from the package's hooks
    directory to the Claude Code hooks directory, making it executable.

    Args:
        claude_dir: Path to Claude configuration directory (typically ~/.claude)
        source_dir: Path to the source directory containing the hooks/ folder
                   (typically the package installation directory)

    Raises:
        FileNotFoundError: If the source hook script cannot be found
        PermissionError: If unable to write to hooks directory or set permissions
    """
    # Ensure hooks directory exists
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Define source and destination paths
    hook_dest = hooks_dir / "send-to-telegram.sh"
    hook_src = source_dir / "hooks" / "send-to-telegram.sh"

    # Check if source hook exists
    if not hook_src.exists():
        raise FileNotFoundError(
            f"Hook source not found at {hook_src}. "
            "This may indicate a package installation issue."
        )

    # Copy hook script to destination
    print(f"Installing hook to {hook_dest}", flush=True)
    shutil.copy2(hook_src, hook_dest)

    # Make hook executable (rwxr-xr-x)
    hook_dest.chmod(0o755)

    print(f"Hook installed successfully at {hook_dest}", flush=True)


def create_server(
    config: BridgeConfig
) -> Tuple[HTTPServer, WebhookManager, CommandRegistry]:
    """Create and configure the HTTP server with all dependencies.

    Initializes all components required for the Telegram bridge:
    - TelegramClient for API calls
    - StateManager for file-based state
    - TmuxController for tmux integration
    - WebhookManager for webhook setup
    - CommandRegistry for command handling
    - HTTPServer with handler class

    Args:
        config: BridgeConfig instance with all configuration values

    Returns:
        Tuple of (HTTPServer, WebhookManager, CommandRegistry)
        - HTTPServer: Configured server ready to serve_forever()
        - WebhookManager: Manager for webhook recovery loop
        - CommandRegistry: Registry for testing/inspection

    Raises:
        ValueError: If configuration is invalid
    """
    # Validate configuration
    errors = config.validate()
    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
        raise ValueError(error_msg)

    # Initialize core components
    telegram = TelegramClient(config.bot_token)
    state = StateManager(config.claude_dir)
    tmux = TmuxController(
        session=config.tmux_session,
        socket_path=config.tmux_socket_path or None
    )

    # Initialize webhook manager
    webhook = WebhookManager(telegram, state, config)

    # Initialize command registry with blocked commands
    blocked_commands = [
        "/mcp", "/help", "/settings", "/config", "/model", "/compact", "/cost",
        "/doctor", "/init", "/login", "/logout", "/memory", "/permissions",
        "/pr", "/review", "/terminal", "/vim", "/approved-tools", "/listen"
    ]
    registry = CommandRegistry(blocked_commands=blocked_commands)

    # Import and manually register builtin commands
    # Note: We can't rely on the @register decorator because it runs at import time
    # before we've had a chance to set the registry, so we manually register here
    from .commands.builtin import (
        StatusCommand, StopCommand, ClearCommand,
        ContinueCommand, LoopCommand, ResumeCommand
    )

    # Register each command class
    for command_class in [StatusCommand, StopCommand, ClearCommand,
                          ContinueCommand, LoopCommand, ResumeCommand]:
        registry.register(command_class)

    # Register bot commands menu with Telegram
    bot_commands = [
        {"command": cmd.name, "description": cmd.description}
        for name, cmd in registry._commands.items()
        if not registry.is_blocked(name)
    ]
    if bot_commands:
        telegram.set_commands(bot_commands)

    # Create handler class with injected dependencies
    handler_class = create_handler_class(
        config=config,
        telegram=telegram,
        tmux=tmux,
        state=state,
        webhook=webhook,
        registry=registry
    )

    # Create HTTP server
    server = HTTPServer((config.host, config.port), handler_class)

    print(
        f"Server created: {config.host}:{config.port}/{config.webhook_path}",
        flush=True
    )
    print(f"Tmux session: {config.tmux_session}", flush=True)

    return server, webhook, registry


def run_server(config: BridgeConfig) -> int:
    """Run the Telegram bridge server with complete lifecycle management.

    This function:
    1. Sets up Claude Code hooks (installs send-to-telegram.sh)
    2. Creates server and initializes all components
    3. Starts webhook recovery loop in background
    4. Runs the HTTP server until interrupted
    5. Handles graceful shutdown on KeyboardInterrupt

    Args:
        config: BridgeConfig instance with all configuration values

    Returns:
        Exit code (0 for success, 1 for error)

    Example:
        >>> config = BridgeConfig.from_env()
        >>> exit_code = run_server(config)
    """
    try:
        # Step 1: Setup hooks
        # Determine source directory (package installation directory)
        source_dir = Path(__file__).parent

        try:
            setup_hooks(config.claude_dir, source_dir)
        except FileNotFoundError as e:
            print(f"Warning: {e}", flush=True)
            print("Continuing without hook installation - hook may need manual setup", flush=True)
        except PermissionError as e:
            print(f"Warning: Permission error installing hook: {e}", flush=True)
            print("Continuing without hook installation - check directory permissions", flush=True)

        # Step 2: Create server and components
        server, webhook_manager, _ = create_server(config)

        # Step 3: Start webhook recovery loop
        webhook_manager.start_recovery_loop(
            startup_delay=config.webhook_startup_delay
        )

        # Step 4: Run server
        print(f"Bridge running on {config.host}:{config.port}/{config.webhook_path}", flush=True)
        print(f"Deployment mode: {config.deployment_mode}", flush=True)
        print("Press Ctrl+C to stop", flush=True)

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down gracefully...", flush=True)
            server.shutdown()
            print("Server stopped", flush=True)

        return 0

    except ValueError as e:
        # Configuration validation error
        print(f"Configuration error: {e}", flush=True)
        return 1
    except OSError as e:
        # Server binding error (port in use, permission denied, etc.)
        print(f"Server error: {e}", flush=True)
        return 1
    except Exception as e:
        # Unexpected error
        print(f"Unexpected error: {e}", flush=True)
        return 1
