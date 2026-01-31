#!/usr/bin/env python3
"""Tests for HTTPS connectivity verification.

This test verifies that the HTTPS endpoint is accessible and returns
valid responses. Used for deployment verification.

Set RUN_DEPLOYMENT_CHECKS=1 to enable network-dependent tests.
Set DEPLOYMENT_DOMAIN to override the default domain.
"""

import os
import re
import socket
import ssl
import sys
import time
from pathlib import Path
from typing import Callable, TypeVar

import pytest

# Type variable for retry decorator
T = TypeVar('T')

# Configuration from environment
DOMAIN = os.getenv("DEPLOYMENT_DOMAIN", "coder.luandro.com")
# Strip scheme if present (e.g., https://example.com → example.com)
if DOMAIN.startswith(("http://", "https://")):
    DOMAIN = DOMAIN.split("://", 1)[1]
# Strip trailing slash if present
DOMAIN = DOMAIN.rstrip("/")
RUN_DEPLOYMENT_CHECKS = os.getenv("RUN_DEPLOYMENT_CHECKS", "0") == "1"

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 0.5  # seconds


def retry_with_backoff(max_attempts: int = MAX_RETRIES, initial_delay: float = INITIAL_BACKOFF):
    """Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)

    Returns:
        Decorated function that retries on exception
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_attempts:
                        print(f"   Attempt {attempt}/{max_attempts} failed: {e}")
                        print(f"   Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                    else:
                        print(f"   All {max_attempts} attempts failed")
                        # Re-raise with preserved traceback
                        raise

        return wrapper
    return decorator


@pytest.mark.integration
def test_https_connectivity_curl():
    """Test HTTPS connectivity using curl (deployment verification)."""
    if not RUN_DEPLOYMENT_CHECKS:
        pytest.skip("Set RUN_DEPLOYMENT_CHECKS=1 to enable network-dependent tests")

    import subprocess

    print(f"Testing HTTPS connectivity to https://{DOMAIN}...")

    @retry_with_backoff()
    def check_https():
        """Inner function to check HTTPS connectivity with retry."""
        # Use -w to extract HTTP status code robustly
        result = subprocess.run(
            [
                "curl",
                "-I",  # HEAD request
                "-s",  # Silent
                "-S",  # Show errors
                "-w", "%{http_code}",  # Write out HTTP status code
                "-o", "/dev/null",  # Discard response body
                f"https://{DOMAIN}"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            error_msg = f"curl failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f": {result.stderr.strip()}"
            raise ConnectionError(error_msg)

        # Extract HTTP status code from stdout (last 3 characters)
        status_code = result.stdout.strip()
        if not status_code.isdigit() or len(status_code) != 3:
            raise ValueError(f"Invalid HTTP status code: {status_code}")

        status = int(status_code)
        if status not in [200, 301, 302, 307, 308]:
            raise AssertionError(f"Unexpected HTTP status: {status}")

        print(f"✓ HTTPS endpoint responds with HTTP {status}")
        return status

    try:
        check_https()
    except FileNotFoundError:
        # curl not available - always skip (regardless of RUN_DEPLOYMENT_CHECKS)
        pytest.skip("curl not available - cannot test live HTTPS connectivity")
    except (ConnectionError, subprocess.TimeoutExpired, ValueError, AssertionError) as e:
        # Network/deployment errors
        if RUN_DEPLOYMENT_CHECKS:
            # Strict mode: fail the test
            pytest.fail(f"HTTPS connectivity check failed: {e}")
        else:
            # Development mode: skip
            print(f"⚠ HTTPS connectivity test failed: {e}")
            print(f"   This is expected during local development.")
            pytest.skip(f"HTTPS endpoint not accessible - expected during local development: {e}")


@pytest.mark.integration
def test_dns_resolution():
    """Test that the domain resolves to an IP address."""
    if not RUN_DEPLOYMENT_CHECKS:
        pytest.skip("Set RUN_DEPLOYMENT_CHECKS=1 to enable network-dependent tests")

    @retry_with_backoff()
    def resolve_dns():
        """Inner function to resolve DNS with retry."""
        ip = socket.gethostbyname(DOMAIN)
        if not ip:
            raise ValueError(f"DNS resolution returned empty IP for {DOMAIN}")
        print(f"✓ DNS resolution: {DOMAIN} → {ip}")
        return ip

    try:
        resolve_dns()
    except (socket.gaierror, ValueError) as e:
        if RUN_DEPLOYMENT_CHECKS:
            # Strict mode: fail the test
            pytest.fail(f"DNS resolution failed for {DOMAIN}: {e}")
        else:
            # Development mode: skip
            pytest.skip(f"DNS resolution failed for {DOMAIN} - expected during local development: {e}")


@pytest.mark.integration
def test_ssl_handshake():
    """Test SSL/TLS handshake (certificate validation)."""
    if not RUN_DEPLOYMENT_CHECKS:
        pytest.skip("Set RUN_DEPLOYMENT_CHECKS=1 to enable network-dependent tests")

    port = 443

    @retry_with_backoff()
    def perform_ssl_handshake():
        """Inner function to perform SSL handshake with retry."""
        # Create SSL context
        context = ssl.create_default_context()

        # Attempt connection
        with socket.create_connection((DOMAIN, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=DOMAIN) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    raise ValueError("No certificate returned from SSL handshake")
                print(f"✓ SSL/TLS handshake successful")
                print(f"   Certificate subject: {cert.get('subject', 'N/A')}")
                return cert

    try:
        perform_ssl_handshake()
    except ssl.SSLCertVerificationError as e:
        # SSL certificate verification errors are always real problems - fail regardless
        pytest.fail(f"SSL certificate verification failed: {e}")
    except (ConnectionRefusedError, socket.timeout, OSError, ValueError) as e:
        if RUN_DEPLOYMENT_CHECKS:
            # Strict mode: fail the test
            pytest.fail(f"SSL/TLS handshake failed: {e}")
        else:
            # Development mode: skip
            pytest.skip(f"SSL handshake error - expected during local development: {e}")
    except Exception as e:
        # Unexpected errors
        if RUN_DEPLOYMENT_CHECKS:
            pytest.fail(f"Unexpected SSL handshake error: {e}")
        else:
            pytest.skip(f"SSL handshake error (may be temporary): {e}")


@pytest.mark.integration
def test_local_https_ports():
    """Test that local Caddy HTTPS port is accessible (for local testing)."""
    try:
        with socket.create_connection(("127.0.0.1", 8443), timeout=2):
            print("✓ Local Caddy HTTPS port (8443) is accessible")
    except (ConnectionRefusedError, socket.timeout) as e:
        pytest.skip(f"Local Caddy HTTPS port (8443) not accessible. Start with: docker compose up -d ({e})")


def test_caddyfile_https_config():
    """Test that Caddyfile has HTTPS configuration."""
    caddyfile_path = Path(__file__).parent.parent / "Caddyfile"

    assert caddyfile_path.exists(), "Caddyfile not found"

    content = caddyfile_path.read_text()

    # Check for HTTPS block (domain without http:// prefix) using regex
    # Matches "domain.com {" or "domain.com{" with optional whitespace
    domain_pattern = re.compile(rf'^\s*{re.escape(DOMAIN)}\s*\{{', re.MULTILINE)
    has_https_block = domain_pattern.search(content) is not None

    assert has_https_block, f"Caddyfile missing HTTPS block for {DOMAIN}"
    print(f"✓ Caddyfile has HTTPS configuration block for {DOMAIN}")

    # Check for reverse_proxy directive
    assert "reverse_proxy" in content, "Caddyfile missing reverse_proxy directive"
    print("✓ Caddyfile has reverse_proxy configuration")

    # Check for security headers (warning only, not a failure)
    required_headers = [
        "Strict-Transport-Security",
    ]

    for header in required_headers:
        if header in content:
            print(f"✓ Caddyfile has {header} header")
        else:
            print(f"⚠ Caddyfile missing {header} header (recommended)")


def run_all_tests():
    """Run all tests (for standalone execution).

    When run via pytest, use: pytest tests/test_https_connectivity.py
    For network tests: RUN_DEPLOYMENT_CHECKS=1 pytest tests/test_https_connectivity.py -m integration
    """
    tests = [
        ("Caddyfile HTTPS config", test_caddyfile_https_config),
        ("Local HTTPS ports", test_local_https_ports),
        ("DNS resolution", test_dns_resolution),
        ("SSL/TLS handshake", test_ssl_handshake),
        ("HTTPS connectivity (curl)", test_https_connectivity_curl),
    ]

    print("Running HTTPS connectivity tests...\n")
    print(f"Domain: {DOMAIN}")
    print(f"Network tests: {'enabled' if RUN_DEPLOYMENT_CHECKS else 'disabled (set RUN_DEPLOYMENT_CHECKS=1 to enable)'}")
    print("=" * 60)

    failed = []
    skipped = []
    for name, test_func in tests:
        print(f"\nTest: {name}")
        print("-" * 60)
        try:
            test_func()
            print(f"✓ {name} passed")
        except AssertionError as e:
            print(f"✗ {name} failed: {e}")
            failed.append((name, str(e)))
        except pytest.skip.Exception as e:
            print(f"⊘ {name} skipped: {e}")
            skipped.append(name)
        except Exception as e:
            print(f"✗ {name} error: {e}")
            failed.append((name, str(e)))

    print("\n" + "=" * 60)
    print(f"Results: {len(tests) - len(failed) - len(skipped)} passed, {len(skipped)} skipped, {len(failed)} failed")

    if failed:
        print(f"\nFAILED tests:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        return 1
    else:
        print("\nSUCCESS: All critical tests passed!")
        if skipped:
            print(f"\nSkipped tests: {', '.join(skipped)}")
            print("These are expected during local development or when RUN_DEPLOYMENT_CHECKS=0")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
