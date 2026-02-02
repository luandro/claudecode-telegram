"""
Test basic package structure and imports.
"""
import subprocess
import sys
import pytest


def test_package_import():
    """Test that the main package can be imported."""
    import claudecode_telegram
    assert hasattr(claudecode_telegram, '__version__')


def test_modules_import():
    """Test that all modules can be imported."""
    from claudecode_telegram import config
    from claudecode_telegram import telegram
    from claudecode_telegram import tmux
    from claudecode_telegram import state
    from claudecode_telegram import webhook
    from claudecode_telegram import handler
    from claudecode_telegram import server
    from claudecode_telegram.commands import base
    from claudecode_telegram.commands import registry

    # Just verify they import without error
    assert config is not None
    assert telegram is not None
    assert tmux is not None
    assert state is not None
    assert webhook is not None
    assert handler is not None
    assert server is not None
    assert base is not None
    assert registry is not None


def test_bridge_module_import():
    """Test that bridge module can be imported."""
    import bridge
    assert hasattr(bridge, 'main')
    assert callable(bridge.main)


def test_console_script_exists():
    """Test that the claudecode-telegram console script is installed."""
    result = subprocess.run(
        ["claudecode-telegram", "--help"],
        capture_output=True,
        text=True,
        timeout=5
    )
    assert result.returncode == 0
    assert "Claude Code <-> Telegram Bridge" in result.stdout


def test_console_script_imports():
    """Test that the console script properly imports from the package."""
    # Import bridge and verify it uses the package
    import bridge
    import inspect

    # Get the source code
    source = inspect.getsource(bridge)

    # Verify it imports from claudecode_telegram package
    assert "from claudecode_telegram.config import BridgeConfig" in source
    assert "from claudecode_telegram.server import run_server" in source
    assert "from claudecode_telegram.telegram import TelegramClient" in source


def test_pyproject_toml_configuration():
    """Test that pyproject.toml has correct package configuration."""
    from pathlib import Path

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"

    # Read pyproject.toml as text and verify key configurations
    with open(pyproject_path, "r") as f:
        content = f.read()

    # Check project configuration
    assert 'name = "claudecode-telegram"' in content
    assert 'claudecode-telegram = "bridge:main"' in content

    # Check setuptools configuration
    assert 'packages = ["claudecode_telegram"]' in content
    assert 'py-modules = ["bridge"]' in content
