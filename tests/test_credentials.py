"""Unit tests for src/credentials.py obfuscation module.

Tests ROT13 + Base64 obfuscation/deobfuscation for PostgreSQL connection strings.
"""

import base64
import pytest

from src.credentials import obfuscate, deobfuscate


def test_obfuscate_deobfuscate_roundtrip():
    """Test reversibility: obfuscate → deobfuscate = identity."""
    original = "postgresql://user:pass@host:5432/db"
    obfuscated = obfuscate(original)
    deobfuscated = deobfuscate(obfuscated)
    assert deobfuscated == original


def test_obfuscate_empty_string():
    """Edge case: empty string."""
    assert deobfuscate(obfuscate("")) == ""


def test_obfuscate_special_chars():
    """Special chars in PostgreSQL connection strings."""
    original = "postgresql://user:p@ss!w0rd@host:5432/db?sslmode=require"
    assert deobfuscate(obfuscate(original)) == original


def test_obfuscate_unicode_chars():
    """Unicode characters (edge case)."""
    original = "postgresql://user:pässwörd@host:5432/db"
    assert deobfuscate(obfuscate(original)) == original


def test_deobfuscate_invalid_base64():
    """Exception si base64 invalide."""
    with pytest.raises(Exception):  # base64.binascii.Error or ValueError
        deobfuscate("invalid_base64!!!")


def test_obfuscate_output_is_base64():
    """Verify obfuscated output is valid base64."""
    obfuscated = obfuscate("test")
    # Should not raise exception
    decoded = base64.b64decode(obfuscated)
    assert isinstance(decoded, bytes)


def test_obfuscate_output_different_from_input():
    """Obfuscated string should be different from plaintext."""
    plaintext = "postgresql://user:pass@host:5432/db"
    obfuscated = obfuscate(plaintext)
    assert obfuscated != plaintext


def test_obfuscate_deterministic():
    """Same input produces same output (deterministic)."""
    plaintext = "postgresql://user:pass@host:5432/db"
    obfuscated1 = obfuscate(plaintext)
    obfuscated2 = obfuscate(plaintext)
    assert obfuscated1 == obfuscated2


def test_obfuscate_long_string():
    """Long connection string (realistic case)."""
    original = (
        "postgresql://leaguestats_readonly:veryLongP@ssw0rd123!@"
        "ep-cool-silence-12345678.us-east-2.aws.neon.tech:5432/"
        "leaguestats?sslmode=require&connect_timeout=10"
    )
    assert deobfuscate(obfuscate(original)) == original
