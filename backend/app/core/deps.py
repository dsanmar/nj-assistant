from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth import verify_jwt

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Optional[dict[str, Any]]:
    """
    Optional auth: returns claims dict if token present+valid, else None.
    """
    if creds is None or not creds.credentials:
        return None
    return verify_jwt(creds.credentials)


def require_user(
    user: Optional[dict[str, Any]] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Required auth: raises 401 if no valid user.
    """
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
