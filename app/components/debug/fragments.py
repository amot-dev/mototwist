from asyncio import gather
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from typing import  cast
from uuid import UUID

from app.components.core.config import templates
from app.components.core.database import get_db
from app.components.core.models import Ride, Twist, User
from app.components.users.services import current_user_optional, current_admin, verify


router = APIRouter(
    prefix="/debug",
    tags=["Debug", "Templates"]
)


@router.get("/templates/menu-button", response_class=HTMLResponse)
async def serve_menu_button(
    request: Request,
    user: User = Depends(current_user_optional),
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the debug menu button.
    """
    return templates.TemplateResponse("fragments/debug/menu_button.html", {
        "request": request,
        "user": user
    })


@router.get("", tags=["Index"], response_class=HTMLResponse)
async def serve_debug_page(
    request: Request,
    admin: User = Depends(verify(current_admin)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve the debug page with database statistics.
    """
    # Define the queries for each statistic
    user_count_query = select(func.count(
        cast(Mapped[UUID], User.id)
    ))

    admin_count_query = select(func.count(
        cast(Mapped[UUID], User.id)
    )).where(
        cast(Mapped[bool], User.is_superuser)
    )

    inactive_count_query = select(func.count(
        cast(Mapped[UUID], User.id)
    )).where(
        cast(Mapped[bool], User.is_active) == False
    )

    twist_count_query = select(func.count(Twist.id))
    ride_count_query = select(func.count(Ride.id))

    # Execute all queries concurrently for better performance
    results = await gather(
        session.execute(user_count_query),
        session.execute(admin_count_query),
        session.execute(inactive_count_query),
        session.execute(twist_count_query),
        session.execute(ride_count_query),
    )

    # Extract the scalar value from each result
    user_count = results[0].scalar_one()
    admin_count = results[1].scalar_one()
    inactive_count = results[2].scalar_one()
    twist_count = results[3].scalar_one()
    ride_count = results[4].scalar_one()

    return templates.TemplateResponse("debug.html", {
        "request": request,
        "user_count": user_count,
        "admin_count": admin_count,
        "inactive_count": inactive_count,
        "twist_count": twist_count,
        "ride_count": ride_count
    })
