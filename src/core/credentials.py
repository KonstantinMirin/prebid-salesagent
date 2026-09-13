"""Buyer credentials: minted once, stored as a hash, matched by hash.

A principal's token is a 256-bit random value. It is shown to the operator exactly once,
when it is minted or rotated, and what the database keeps is ``sha256(token)`` plus a short
display prefix so an operator can tell tokens apart. A random token of that size is not a
password, so no slow hash and no salt: an attacker with the table cannot invert SHA-256 on
256 bits of entropy, and the equality lookup stays an index hit.

This module is the one place the three facts about a token are spelled out: how one is
minted, how one is hashed, and how much of one is shown. The resolver hashes what a request
presents (``src/core/auth_utils.get_principal_from_token``); the ``Principal`` row hashes
what it stores; nothing else touches a plaintext.
"""

from __future__ import annotations

import hashlib
import secrets

#: How much of a token the admin UI shows. Enough to tell two apart, useless to present.
TOKEN_PREFIX_LENGTH = 12


def mint_token() -> str:
    """A fresh buyer token: ``tok_`` and 32 URL-safe random bytes."""
    return f"tok_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    """The stored form of *token*: hex SHA-256 of its UTF-8 bytes."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_prefix(token: str) -> str:
    """The displayable head of *token*."""
    return token[:TOKEN_PREFIX_LENGTH]
