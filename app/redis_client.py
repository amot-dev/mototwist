from contextlib import asynccontextmanager
from enum import Enum
from fastapi_users.authentication import RedisStrategy
from redis import asyncio as aioredis
from typing import AsyncGenerator
from uuid import UUID

from app.models import User
from app.settings import settings
from app.utility import raise_http


redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)  # pyright: ignore [reportUnknownMemberType]
def get_redis_strategy() -> RedisStrategy[User, UUID]:
    return RedisStrategy(redis_client, lifetime_seconds=settings.AUTH_COOKIE_MAX_AGE)


class CooldownReason(Enum):
    """
    Defines titles and cooldown periods for rate limiting.
    Cooldown periods are in seconds.
    """
    FORGOT_PASSWORD = ("Forgot Password", 60)
    VERIFY_EMAIL = ("Email Verification", 60)

    def __init__(self, title: str, duration: int):
        self.title = title
        self.duration = duration


@asynccontextmanager
async def redis_cooldown(
    reason: CooldownReason, 
    key: str,
) -> AsyncGenerator[None, None]:
    """
    An asynchronous context manager to enforce a cooldown using Redis.

    :param reason: A CooldownReason enum defining duration and context.
    :param key: The composite key string for Redis (e.g., "cooldown:fp:user:123").

    :raises HTTPException(429): If the user is currently in the cooldown period.
    """
    compound_key = reason.title.replace(" ", "") + key

    remaining_time = await redis_client.ttl(compound_key)
    if remaining_time > 0:
        raise_http(f"{reason.title} is on cooldown for another {remaining_time}s", status_code=429)

    try:
        yield

    finally:
        await redis_client.setex(compound_key, reason.duration, "1")