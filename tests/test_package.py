"""
Test basic package structure and imports.
"""
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
