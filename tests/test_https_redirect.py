#!/usr/bin/env python3
"""Tests for HTTP to HTTPS redirect configuration."""

import sys
from pathlib import Path


def test_caddyfile_http_redirect_block():
    """Test that Caddyfile has an explicit HTTP to HTTPS redirect block."""
    caddyfile_path = Path(__file__).parent.parent / "Caddyfile"
    assert caddyfile_path.exists(), "Caddyfile not found"

    content = caddyfile_path.read_text()

    # Check for explicit HTTP redirect block
    assert "http://coder.luandro.com" in content, \
        "Caddyfile missing explicit HTTP redirect block for http://coder.luandro.com"

    # Check for redirect directive
    assert "redir" in content or "redirect" in content, \
        "Caddyfile missing redirect directive"

    print("✓ Caddyfile has HTTP to HTTPS redirect block")


def test_caddyfile_permanent_redirect():
    """Test that Caddyfile uses permanent (301) redirect."""
    caddyfile_path = Path(__file__).parent.parent / "Caddyfile"
    content = caddyfile_path.read_text()

    # Check for permanent redirect indicator
    assert "permanent" in content.lower() or "301" in content, \
        "Caddyfile should use permanent redirect (301) for HTTP to HTTPS"

    print("✓ Caddyfile uses permanent redirect")


def test_caddyfile_https_url_in_redirect():
    """Test that redirect points to HTTPS URL."""
    caddyfile_path = Path(__file__).parent.parent / "Caddyfile"
    content = caddyfile_path.read_text()

    # Extract HTTP block content
    lines = content.split('\n')
    in_http_block = False
    redirect_line = None

    for line in lines:
        if 'http://coder.luandro.com' in line:
            in_http_block = True
        elif in_http_block and 'redir' in line.lower():
            redirect_line = line
            break
        elif in_http_block and line.strip() == '}':
            break

    assert redirect_line is not None, "Could not find redirect directive in HTTP block"
    assert "https://coder.luandro.com" in redirect_line, \
        f"Redirect should point to https://coder.luandro.com, got: {redirect_line}"

    print("✓ Caddyfile redirect points to HTTPS URL")


def test_caddyfile_uri_preservation():
    """Test that redirect preserves URI path and query string."""
    caddyfile_path = Path(__file__).parent.parent / "Caddyfile"
    content = caddyfile_path.read_text()

    # Check for {uri} placeholder in redirect
    lines = content.split('\n')
    in_http_block = False

    for line in lines:
        if 'http://coder.luandro.com' in line:
            in_http_block = True
        elif in_http_block and 'redir' in line.lower():
            assert '{uri}' in line, \
                f"Redirect should preserve URI using {{uri}} placeholder, got: {line}"
            break
        elif in_http_block and line.strip() == '}':
            break

    print("✓ Caddyfile redirect preserves URI path and query string")


def test_caddyfile_https_block_has_proxy():
    """Test that HTTPS block has reverse_proxy configuration."""
    caddyfile_path = Path(__file__).parent.parent / "Caddyfile"
    content = caddyfile_path.read_text()

    lines = content.split('\n')
    in_https_block = False
    has_proxy = False

    for line in lines:
        if 'coder.luandro.com {' in line and 'http://' not in line:
            in_https_block = True
        elif in_https_block:
            if 'reverse_proxy' in line:
                has_proxy = True
                break
            if line.strip() == '}':
                break

    assert has_proxy, "HTTPS block should have reverse_proxy directive"

    print("✓ Caddyfile HTTPS block has reverse_proxy configuration")


def test_caddyfile_hsts_header():
    """Test that HTTPS block has HSTS header for security."""
    caddyfile_path = Path(__file__).parent.parent / "Caddyfile"
    content = caddyfile_path.read_text()

    assert "Strict-Transport-Security" in content, \
        "Caddyfile should have HSTS header for HTTPS security"

    print("✓ Caddyfile has HSTS header configured")


def run_all_tests():
    """Run all tests."""
    tests = [
        test_caddyfile_http_redirect_block,
        test_caddyfile_permanent_redirect,
        test_caddyfile_https_url_in_redirect,
        test_caddyfile_uri_preservation,
        test_caddyfile_https_block_has_proxy,
        test_caddyfile_hsts_header,
    ]

    print("Running HTTP to HTTPS redirect tests...\n")

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
