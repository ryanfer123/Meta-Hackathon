"""Validate user tokens with Supabase Auth. Never decode-and-trust browser claims."""

from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.config import Settings


async def authenticate(settings: Settings, authorization: str) -> str:
    if not settings.auth_required:
        return "local-private"
    if not authorization.startswith("Bearer ") or len(authorization) > 16384:
        raise HTTPException(401, "Sign in to access your workspace")
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, "Account verification is not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                settings.supabase_url.rstrip("/") + "/auth/v1/user",
                headers={
                    "Authorization": authorization,
                    "apikey": settings.supabase_publishable_key,
                },
            )
        if response.status_code in (401, 403):
            raise HTTPException(401, "Your session expired. Sign in again.")
        if response.status_code != 200:
            raise HTTPException(503, "Account verification is temporarily unavailable")
        user: dict[str, Any] = response.json()
        owner = str(UUID(user["id"]))
        if user.get("is_anonymous") or not user.get("email_confirmed_at"):
            raise HTTPException(403, "Confirm your email before using the workspace")
        return owner
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Account verification is temporarily unavailable") from exc
