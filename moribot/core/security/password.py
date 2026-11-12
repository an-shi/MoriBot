"""Password hashing utilities.

Passwords are stored as salted PBKDF2-HMAC-SHA256 digests. The format is
``pbkdf2_sha256$<iterations>$<salt-hex>$<digest-hex>`` so the iteration count
can be raised later without invalidating existing credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string

from ..i18n import DEFAULT_LOCALE, translate

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000
PBKDF2_SALT_BYTES = 16
PASSWORD_MIN_LENGTH = 8
GENERATED_PASSWORD_LENGTH = 20


def hash_password(raw_password: str) -> str:
    """Hash a plaintext password with a random salt.

    Args:
        raw_password: Password supplied by the user.

    Returns:
        The encoded password digest.

    Raises:
        ValueError: If the password is empty.
    """
    if not isinstance(raw_password, str) or raw_password == "":
        raise ValueError("Password cannot be empty")

    salt = secrets.token_hex(PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(stored_hash: str, candidate_password: str) -> bool:
    """Verify a candidate password against a stored digest.

    Args:
        stored_hash: Encoded password digest.
        candidate_password: Plaintext password to check.

    Returns:
        ``True`` when the password matches.
    """
    if not isinstance(stored_hash, str) or not isinstance(candidate_password, str):
        return False

    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != PBKDF2_ALGORITHM:
        return False

    _, iterations_raw, salt, expected_hex = parts
    try:
        iterations = int(iterations_raw)
        salt_bytes = bytes.fromhex(salt)
        expected = bytes.fromhex(expected_hex)
    except (TypeError, ValueError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        candidate_password.encode("utf-8"),
        salt_bytes,
        iterations,
    )
    return hmac.compare_digest(expected, candidate)


def validate_password_strength(
    raw_password: str,
    *,
    locale: str = DEFAULT_LOCALE,
) -> None:
    """Validate the minimum password policy.

    Args:
        raw_password: Candidate password.
        locale: Language used for the error message.

    Raises:
        ValueError: If the password does not satisfy the policy.
    """
    if not isinstance(raw_password, str) or raw_password == "":
        raise ValueError(translate("password.empty", locale))
    if len(raw_password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            translate(
                "password.too_short",
                locale,
                min_length=PASSWORD_MIN_LENGTH,
            )
        )
    if not re.search(r"[A-Z]", raw_password):
        raise ValueError(translate("password.needs_uppercase", locale))
    if not re.search(r"[a-z]", raw_password):
        raise ValueError(translate("password.needs_lowercase", locale))
    if not re.search(r"\d", raw_password):
        raise ValueError(translate("password.needs_digit", locale))


def generate_password(length: int = GENERATED_PASSWORD_LENGTH) -> str:
    """Generate a random password that satisfies the strength policy."""
    length = max(length, 12)
    alphabet = string.ascii_letters + string.digits
    chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        *(secrets.choice(alphabet) for _ in range(length - 3)),
    ]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
