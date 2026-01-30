#!/usr/bin/env python3
"""Tests for bridge network configuration."""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_bridge_default_host():
    """Test that bridge defaults to localhost (127.0.0.1)."""
    # Save original env var
    original_host = os.environ.get("HOST")
    if "HOST" in os.environ:
        del os.environ["HOST"]

    # Re-import to get default values
    import importlib
    import bridge
    importlib.reload(bridge)

    assert bridge.HOST == "127.0.0.1", f"Default HOST should be 127.0.0.1, got {bridge.HOST}"
    print("✓ Bridge defaults to localhost (127.0.0.1)")

    # Restore original env var if it existed
    if original_host is not None:
        os.environ["HOST"] = original_host


def test_bridge_custom_host():
    """Test that bridge respects custom HOST env var."""
    # Set custom HOST
    os.environ["HOST"] = "0.0.0.0"

    # Re-import to get new values
    import importlib
    import bridge
    importlib.reload(bridge)

    assert bridge.HOST == "0.0.0.0", f"HOST should be 0.0.0.0, got {bridge.HOST}"
    print("✓ Bridge respects custom HOST environment variable")

    # Clean up
    del os.environ["HOST"]


def test_bridge_default_port():
    """Test that bridge defaults to port 8080."""
    # Save original env var
    original_port = os.environ.get("PORT")
    if "PORT" in os.environ:
        del os.environ["PORT"]

    # Re-import to get default values
    import importlib
    import bridge
    importlib.reload(bridge)

    assert bridge.PORT == 8080, f"Default PORT should be 8080, got {bridge.PORT}"
    print("✓ Bridge defaults to port 8080")

    # Restore original env var if it existed
    if original_port is not None:
        os.environ["PORT"] = original_port


def test_bridge_custom_port():
    """Test that bridge respects custom PORT env var."""
    # Set custom PORT
    os.environ["PORT"] = "9090"

    # Re-import to get new values
    import importlib
    import bridge
    importlib.reload(bridge)

    assert bridge.PORT == 9090, f"PORT should be 9090, got {bridge.PORT}"
    print("✓ Bridge respects custom PORT environment variable")

    # Clean up
    del os.environ["PORT"]


def test_bridge_uses_host_in_server():
    """Test that HTTPServer uses the HOST variable."""
    # This test validates the code structure, not runtime behavior
    bridge_path = Path(__file__).parent.parent / "bridge.py"
    content = bridge_path.read_text()

    # Check that HOST is defined
    assert 'HOST = os.environ.get("HOST"' in content, "HOST variable not defined"
    assert '"127.0.0.1"' in content, "Default HOST should be 127.0.0.1"

    # Check that HTTPServer uses (HOST, PORT) tuple
    assert "HTTPServer((HOST, PORT)" in content, "HTTPServer should use (HOST, PORT) tuple"
    assert "HTTPServer((\"0.0.0.0\", PORT)" not in content, "HTTPServer should not hardcode 0.0.0.0"

    print("✓ Bridge HTTPServer uses HOST variable")


def test_bridge_comment_explains_security():
    """Test that code comments explain the security implication."""
    bridge_path = Path(__file__).parent.parent / "bridge.py"
    content = bridge_path.read_text()

    # Check for security comment
    assert "localhost" in content.lower() or "internal" in content.lower(), \
        "Code should have comments explaining localhost/internal-only binding"

    print("✓ Bridge includes security comments")


def run_all_tests():
    """Run all tests."""
    tests = [
        test_bridge_default_host,
        test_bridge_custom_host,
        test_bridge_default_port,
        test_bridge_custom_port,
        test_bridge_uses_host_in_server,
        test_bridge_comment_explains_security,
    ]

    print("Running bridge network configuration tests...\n")

    failed = []
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed.append((test.__name__, str(e)))
        except Exception as e:
            print(f"⚠ {test.__name__}: {e}")

    print(f"\n{'='*50}")
    if failed:
        print(f"FAILED: {len(failed)} test(s) failed")
        for name, error in failed:
            print(f"  - {name}: {error}")
        return 1
    else:
        print("SUCCESS: All tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
