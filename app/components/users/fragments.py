from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.components.core.config import templates
from app.components.core.events import EventSet
from app.components.core.models import User
from app.components.users.services import current_user


router = APIRouter(
    prefix="/users",
    tags=["Users", "Templates"]
)


@router.get("/templates/profile-modal", response_class=HTMLResponse)
async def render_profile_modal(
    request: Request,
    user: User = Depends(current_user)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the current user's profile modal.
    """

    response = templates.TemplateResponse("fragments/users/profile_modal.html", {
        "request": request,
        "user": user
    })
    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.PROFILE_LOADED
    ).dump()
    return response
