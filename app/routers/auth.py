from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.authentication import RedisStrategy
from fastapi_users.exceptions import InvalidResetPasswordToken, UserInactive, UserNotExists
from typing import Annotated
from uuid import UUID

from app.config import templates
from app.events import EventSet
from app.models import User
from app.schemas.auth import ResetPasswordForm
from app.services.auth import login_and_set_response_cookie, logout_and_set_response_cookie
from app.users import UserManager, current_active_user_optional, get_user_manager, get_redis_strategy
from app.utility import raise_http


router = APIRouter(
    prefix="",
    tags=["Authentication"]
)

@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: RedisStrategy[User, UUID] = Depends(get_redis_strategy),
) -> HTMLResponse:
    """
    Login and serve an HTML fragment containing the auth widget.
    """
    user = await user_manager.authenticate(credentials)

    # Handle failed login
    if not user or not user.is_active:
        raise_http("Invalid credentials or deactivated account", status_code=401)

    response = templates.TemplateResponse("fragments/auth/widget.html", {
        "request": request,
        "user": user
    })

    await login_and_set_response_cookie(response, strategy=strategy, user=user)

    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH(f"Welcome back, {user.name}!"),
        EventSet.AUTH_CHANGE,
        EventSet.CLOSE_MODAL
    ).dump()
    return response


@router.post("/logout", response_class=HTMLResponse)
async def logout(
    request: Request,
    response: Response,
    user: User | None = Depends(current_active_user_optional),
    strategy: RedisStrategy[User, UUID] = Depends(get_redis_strategy),
) -> HTMLResponse:
    """
    Logout and serve an HTML fragment containing the auth widget.
    """
    flash_message = "You have been logged out"
    response = templates.TemplateResponse("fragments/auth/widget.html", {
        "request": request,
        "user": None
    })

    if user:
        await logout_and_set_response_cookie(request, response, strategy=strategy, user=user)
        flash_message = f"See you soon, {user.name}!"

    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH(flash_message),
        EventSet.AUTH_CHANGE
    ).dump()
    return response


@router.post("/refresh")
def refresh(request: Request) -> HTMLResponse:
    """
    Force a refresh of the auth token via middleware.
    """
    # Force renewal and return blank response
    request.state.force_session_renewal = True
    return HTMLResponse()


@router.get("/register", tags=["Index", "Templates"], response_class=HTMLResponse)
async def render_register_page(request: Request) -> HTMLResponse:
    """
    Serve the register page.
    """

    return templates.TemplateResponse("register.html", {
        "request": request
    })


@router.post("/reset-password", response_class=Response)
async def reset_password(
    request: Request,
    reset_form: Annotated[ResetPasswordForm, Form()],
    user_manager: UserManager = Depends(get_user_manager),
) -> Response:
    """
    Reset a user password by token, then redirect to the main page of MotoTwist.
    """
    if reset_form.password != reset_form.password_confirmation:
        raise_http("Passwords do not match", status_code=422)

    try:
        await user_manager.reset_password(reset_form.token, reset_form.password, request=request)
    except (InvalidResetPasswordToken, UserInactive, UserNotExists):
        raise_http("This link is invalid or has expired", status_code=400)

    request.session["flash"] = "Password updated!"
    return Response(headers={"HX-Redirect": "/"})


@router.get("/reset-password", tags=["Index", "Templates"], response_class=HTMLResponse)
async def render_reset_password_page(
    request: Request,
    token: str
) -> HTMLResponse:
    """
    Serve the password reset page.
    """

    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "token": token
    })