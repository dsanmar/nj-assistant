from __future__ import annotations

import json
import os
import time
from typing import Any

import jwt
from fastapi import HTTPException, status

try:
    import httpx
except Exception:  # pragma: no cover - fallback if httpx isn't installed
    httpx = None  # type: ignore
    import requests  # type: ignore


_JWKS_TTL_SECONDS = 600
_JWKS_CACHE: dict[str, dict[str, Any]] = {}


def _get_supabase_url() -> str:
    url = (os.getenv("SUPABASE_URL") or "").strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_URL is not configured",
        )
    return url.rstrip("/")


def _fetch_jwks(supabase_url: str) -> dict[str, Any]:
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        if httpx is not None:
            resp = httpx.get(jwks_url, timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        resp = requests.get(jwks_url, timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch JWKS",
        )


def _get_jwks_keys(supabase_url: str, force_refresh: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    entry = _JWKS_CACHE.get(supabase_url)

    if not force_refresh and entry:
        age = now - float(entry.get("fetched_at", 0.0))
        if age < _JWKS_TTL_SECONDS:
            return entry.get("keys", {})

    jwks = _fetch_jwks(supabase_url)
    keys = {k.get("kid"): k for k in jwks.get("keys", []) if k.get("kid")}
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWKS did not contain any keys",
        )

    _JWKS_CACHE[supabase_url] = {"keys": keys, "fetched_at": now}
    return keys


def verify_jwt(token: str) -> dict[str, Any]:
    """
    Verify Supabase ES256 access token using JWKS with caching and issuer/audience checks.
    """
    supabase_url = _get_supabase_url()
    expected_iss = f"{supabase_url}/auth/v1"

    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    kid = header.get("kid")
    keys = _get_jwks_keys(supabase_url, force_refresh=False)
    jwk = keys.get(kid) if kid else None

    if not jwk:
        keys = _get_jwks_keys(supabase_url, force_refresh=True)
        jwk = keys.get(kid) if kid else None

    if not jwk:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        public_key = jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        unverified_claims = jwt.decode(token, options={"verify_signature": False})
        aud_present = "aud" in unverified_claims
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated" if aud_present else None,
            options={"verify_aud": aud_present, "verify_iss": False},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    iss = (claims.get("iss") or "").rstrip("/")
    if iss != expected_iss.rstrip("/"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")

    if "aud" in claims:
        aud = claims.get("aud")
        if isinstance(aud, list):
            valid_aud = "authenticated" in aud
        else:
            valid_aud = aud == "authenticated"
        if not valid_aud:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token audience")

    return claims
