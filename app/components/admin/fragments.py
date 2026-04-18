from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.core.config import templates
from app.components.core.database import get_db
from app.components.core.models import User
from app.components.users.services import current_admin, verify


router = APIRouter(
    prefix="/admin",
    tags=["Administration", "Templates"]
)


@router.get("/templates/settings-modal", response_class=HTMLResponse)
async def serve_settings_modal(
    request: Request,
    admin: User = Depends(verify(current_admin)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the admin settings modal.
    """
    result = await session.scalars(
        select(User).order_by(User.name)
    )
    users = result.all()

    response = templates.TemplateResponse("fragments/admin/settings_modal.html", {
        "request": request,
        "users": users
    })

    # Prevent browser caching
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response
