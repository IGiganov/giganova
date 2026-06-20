import secrets
from typing import Optional

from fastapi import HTTPException, Request

from app.config import settings
from app.security import verify_password
from app.users import user_count, verify_user


def needs_setup() -> bool:
    """True when login is on but no account has been created yet."""
    return settings.auth_enabled and user_count() == 0


def _env_fallback_matches(username: str, password: str) -> bool:
    """Optional recovery admin defined in .env. Disabled unless fully configured."""
    if not settings.auth_username:
        return False
    if not (settings.auth_password_hash or settings.auth_password):
        return False

    username_ok = secrets.compare_digest(username.strip(), settings.auth_username.strip())
    if settings.auth_password_hash:
        password_ok = verify_password(password, settings.auth_password_hash.strip())
    else:
        password_ok = secrets.compare_digest(password, settings.auth_password)
    return username_ok and password_ok


def authenticate(username: str, password: str) -> bool:
    if verify_user(username, password):
        return True
    return _env_fallback_matches(username, password)


def get_session_user(request: Request) -> Optional[str]:
    if not settings.auth_enabled:
        return "local"
    user = request.session.get("user")
    if isinstance(user, str) and user:
        return user
    return None


def require_user(request: Request) -> str:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
