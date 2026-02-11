"""Credential obfuscation module for LeagueStats.

This module provides simple obfuscation (NOT encryption) for embedding sensitive
credentials in the distributed .exe file. The obfuscation uses ROT13 + Base64
encoding to prevent trivial extraction via strings command on the binary.

SECURITY NOTE:
    This is OBFUSCATION, not cryptographic encryption. The PostgreSQL user is
    READ-ONLY with limited permissions, so the risk is acceptable if extracted.
    The goal is to raise the bar above trivial string extraction from the .exe.

Functions:
    obfuscate(plaintext: str) -> str:
        Obfuscate a plaintext string using ROT13 + Base64 encoding.

    deobfuscate(obfuscated: str) -> str:
        Deobfuscate a string encoded with obfuscate() (Base64 decode + ROT13).

Constants:
    OBFUSCATED_READONLY_CONNECTION_STRING:
        PostgreSQL connection string for read-only user (obfuscated).
        This is a placeholder and will be updated with the real connection string
        after T13 (manual PostgreSQL setup) is completed.
"""

import base64
import codecs


def obfuscate(plaintext: str) -> str:
    """Obfuscate a plaintext string using ROT13 + Base64 encoding.

    This function applies two layers of simple encoding:
    1. ROT13 cipher (letter substitution)
    2. Base64 encoding (binary-safe encoding)

    Args:
        plaintext: The plaintext string to obfuscate.

    Returns:
        The obfuscated string (Base64-encoded ROT13 text).

    Example:
        >>> obfuscated = obfuscate("postgresql://user:pass@host/db")
        >>> print(obfuscated)
        'Y205c...'  # Base64-encoded string
    """
    # Step 1: ROT13 encoding (letter substitution cipher)
    rot13_encoded = codecs.encode(plaintext, "rot13")

    # Step 2: Base64 encoding (converts to binary-safe ASCII)
    b64_encoded = base64.b64encode(rot13_encoded.encode("utf-8"))

    return b64_encoded.decode("utf-8")


def deobfuscate(obfuscated: str) -> str:
    """Deobfuscate a string encoded with obfuscate().

    This function reverses the obfuscation process:
    1. Base64 decode
    2. ROT13 decode

    Args:
        obfuscated: The obfuscated string (from obfuscate() function).

    Returns:
        The original plaintext string.

    Example:
        >>> plaintext = deobfuscate("Y205c...")
        >>> print(plaintext)
        'postgresql://user:pass@host/db'
    """
    # Step 1: Base64 decode
    b64_decoded = base64.b64decode(obfuscated.encode("utf-8"))

    # Step 2: ROT13 decode (reverse letter substitution)
    plaintext = codecs.decode(b64_decoded.decode("utf-8"), "rot13")

    return plaintext


# Obfuscated PostgreSQL connection string (READ-ONLY user)
# Connection string for Neon PostgreSQL database (eu-west-2)
# Obfuscated with ROT13 + Base64 to prevent trivial extraction from .exe
# Original connection string stored in config/.env.neon (gitignored)
OBFUSCATED_READONLY_CONNECTION_STRING = "Y2JmZ3RlcmZkeTovL3lybnRocmZnbmdmX2VybnFiYXlsOmp4cmlPRmVsclBrT1hkd296ak1ja0xsVEByYy1waGV5bC1mdW5xYmotbm94dWg5dWYtY2JieXJlLnJoLWpyZmctMi5uamYuYXJiYS5ncnB1OjU0MzIvYXJiYXFvP2ZmeXpicXI9ZXJkaHZlcg=="


# Validation example (for development/testing only)
if __name__ == "__main__":
    # Test roundtrip: plaintext -> obfuscate -> deobfuscate -> plaintext
    test_string = (
        "postgresql://leaguestats_readonly:test123@localhost:5432/leaguestats?sslmode=require"
    )

    obfuscated = obfuscate(test_string)
    deobfuscated = deobfuscate(obfuscated)

    print(f"Original:     {test_string}")
    print(f"Obfuscated:   {obfuscated}")
    print(f"Deobfuscated: {deobfuscated}")
    print(f"Roundtrip OK: {test_string == deobfuscated}")
