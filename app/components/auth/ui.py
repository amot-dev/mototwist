from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.components.core.config import templates
from app.components.core.models import User
from app.components.users.services import current_user_optional


router = APIRouter(
    prefix="",
    tags=["Authentication", "Templates"]
)


@router.get("/auth/ui/widget", response_class=HTMLResponse)
async def serve_auth_widget(
    request: Request,
    user: User | None = Depends(current_user_optional)
) -> HTMLResponse:
    """
    Serve the auth widget.
    """
    return templates.TemplateResponse(request, "fragments/auth/widget.html", {
        "user": user
    })


@router.get("/register", tags=["Index"], response_class=HTMLResponse)
async def serve_register_page(request: Request) -> HTMLResponse:
    """
    Serve the register page.
    """

    return templates.TemplateResponse(request, "register.html")


@router.get("/verify", tags=["Index"], response_class=HTMLResponse)
async def serve_verify_page(
    request: Request,
    token: str
) -> HTMLResponse:
    """
    Serve the verify page.
    """

    return templates.TemplateResponse(request, "verify.html", {
        "token": token
    })


@router.get("/reset-password", tags=["Index"], response_class=HTMLResponse)
async def serve_reset_password_page(
    request: Request,
    token: str
) -> HTMLResponse:
    """
    Serve the password reset page.
    """

    return templates.TemplateResponse(request, "reset_password.html", {
        "token": token
    })
