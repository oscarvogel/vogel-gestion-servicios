from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_token(
    user_id: int,
    token_type: str,
    delta: timedelta,
    company_id: int | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + delta,
    }
    if company_id is not None:
        payload["company_id"] = company_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(user_id: int, company_id: int | None = None) -> str:
    return create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_minutes),
        company_id,
    )


def create_refresh_token(user_id: int) -> str:
    return create_token(
        user_id,
        "refresh",
        timedelta(days=settings.refresh_token_days),
    )
