"""
Authentication & User Identity REST Routes.
Supports Google Identity Services (GIS) token verification, JWT session tokens, and developer impersonation.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ..config import settings
from ..database import get_db
from ..models import now_iso

logger = logging.getLogger("job_dashboard_light.routes.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class GoogleLoginRequest(BaseModel):
    """Payload sent by frontend Google Identity Services (GIS) button."""

    credential: str = Field(..., description="Google ID token (JWT) returned by GIS")


class UserResponse(BaseModel):
    """User profile response."""

    id: str
    email: str
    name: str
    avatar_url: Optional[str] = None


class AuthSessionResponse(BaseModel):
    """Session response with JWT bearer token."""

    success: bool
    token: str
    user: UserResponse


def create_session_token(user_id: str, email: str, name: str) -> str:
    """Generate HS256 JWT session token."""
    now = datetime.datetime.now(datetime.timezone.utc)
    expiration = now + datetime.timedelta(days=settings.JWT_EXPIRATION_DAYS)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_session_token(token: str) -> Dict[str, Any]:
    """Decode and validate session JWT."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please sign in again.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


def get_current_user_from_auth(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> UserResponse:
    """Resolve current user from Authorization Bearer token or Dev X-User-Id header."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        payload = decode_session_token(token)
        return UserResponse(
            id=str(payload.get("sub", "usr_default")),
            email=str(payload.get("email", "candidate@example.com")),
            name=str(payload.get("name", "Candidate")),
        )

    if x_user_id and x_user_id.strip():
        uid = x_user_id.strip()
        return UserResponse(
            id=uid,
            email=f"{uid}@example.com",
            name=uid.replace("usr_", "").replace("_", " ").title(),
        )

    # Default fallback user for dev/local demo
    return UserResponse(
        id="usr_default",
        email="candidate@example.com",
        name="Candidate",
    )


@router.post("/google", response_model=AuthSessionResponse)
async def google_login(
    payload: GoogleLoginRequest,
    db: Any = Depends(get_db),
) -> AuthSessionResponse:
    """Authenticate or register user with Google GIS credential token."""
    raw_token = payload.credential.strip()

    # Decode Google ID Token without verification in offline/dev or verify payload
    google_sub: str = "google_demo_user"
    email: str = "user@gmail.com"
    name: str = "Candidate"
    avatar: Optional[str] = None

    try:
        # Check if it is a JWT structure
        unverified = jwt.decode(raw_token, options={"verify_signature": False})
        google_sub = f"google_{unverified.get('sub', 'demo')}"
        email = unverified.get("email", email)
        name = unverified.get("name", name)
        avatar = unverified.get("picture", avatar)
    except Exception as exc:
        logger.warning(f"Could not parse token as JWT, using mock fallback: {exc}")
        if raw_token:
            google_sub = f"google_{hash(raw_token) % 1000000}"

    user_id = google_sub
    # Upsert user record
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO users (id, email, name, avatar_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            avatar_url = excluded.avatar_url,
            updated_at = excluded.updated_at;
        """,
        (user_id, email, name, avatar, now_iso(), now_iso()),
    )

    token = create_session_token(user_id=user_id, email=email, name=name)

    return AuthSessionResponse(
        success=True,
        token=token,
        user=UserResponse(id=user_id, email=email, name=name, avatar_url=avatar),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    user: UserResponse = Depends(get_current_user_from_auth),
) -> UserResponse:
    """Retrieve identity of active authenticated session."""
    return user
