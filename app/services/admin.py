
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from typing import cast
from uuid import UUID

from app.settings import settings
from app.config import logger
from app.models import User
from app.schemas.users import UserCreate
from app.users import UserManager, get_user_db


async def create_first_admin(session: AsyncSession) -> bool:
    """
    TODO
    """
    result = await session.execute(
        select(func.count()).select_from(User)
    )
    user_count = result.scalar_one()
    if user_count == 0:
        user_data = UserCreate(
            email=settings.MOTOTWIST_ADMIN_EMAIL,
            password=settings.MOTOTWIST_ADMIN_PASSWORD,
            is_active=True,
            is_superuser=True,
            is_verified=True,  # Force verification for initial admin to prevent oopsies
        )
        user_db = await anext(get_user_db(session))
        user_manager = UserManager(user_db)
        await user_manager.create(user_data)
        logger.info(f"Admin user '{settings.MOTOTWIST_ADMIN_EMAIL}' created")
        return True
    else:
        logger.info("Admin user creation skipped")
        return False


async def is_last_active_admin(session: AsyncSession, user: User) -> bool:
    """
    Check if the given user is the last active administrator.

    :param session: The session to use for database transactions.
    :param user_id: The user to check.
    :return: True if the user is the last active admin.
    """
    if user.is_superuser and user.is_active:
        result = await session.scalars(
            select(func.count(
                cast(Mapped[UUID], User.id)
            )).where(
                cast(Mapped[bool], User.is_active),
                cast(Mapped[bool], User.is_superuser)
            )
        )

        admin_count = result.one()
        return admin_count <= 1
    return False
