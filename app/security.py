import logging

import bcrypt

logger = logging.getLogger(__name__)


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash string for the given plaintext password."""
    salt = bcrypt.gensalt()
    digest = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return digest.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Timing-safe bcrypt verification. Returns False on malformed hashes."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        logger.warning("Stored password hash is not a valid bcrypt hash.")
        return False
