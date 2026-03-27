from __future__ import annotations

import secrets
from fastapi import Header, HTTPException

from config import settings


def verify_internal_token(x_internal_token: str = Header(default="")) -> None:
    expected = settings.INTERNAL_API_TOKEN
    if not expected:
        return
    if not secrets.compare_digest(x_internal_token or "", expected):
        raise HTTPException(status_code=401, detail="unauthorized internal token")
