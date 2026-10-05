from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from sboard.config import get_settings
from sboard.database import get_db
from sboard.models import Agent

bearer = HTTPBearer(auto_error=False)


def generate_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_hint(token: str) -> str:
    return f"{token[:8]}...{token[-4:]}"


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    expected = get_settings().admin_token
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_admin_token", "message": "Invalid admin token"},
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_agent(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Agent:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_agent_token", "message": "Agent token is required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    digest = hash_token(credentials.credentials)
    agent = db.scalar(select(Agent).where(Agent.token_hash == digest))
    if agent is None or not agent.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_agent_token", "message": "Invalid agent token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return agent
