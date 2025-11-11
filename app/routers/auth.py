from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.authentication import RedisStrategy
from fastapi_users.exceptions import InvalidResetPasswordToken, InvalidVerifyToken, UserAlreadyVerified, UserInactive, UserNotExists
from typing import Annotated
from uuid import UUID

from app.config import templates
from app.events import EventSet
from app.models import User
from app.redis_client import get_redis_strategy
from app.schemas.auth import ForgotPasswordForm, ResetPasswordForm, VerifyAccountForm
from app.services.auth import login_and_set_response_cookie, logout_and_set_response_cookie
from app.settings import settings
from app.users import UserManager, current_user_optional, get_user_manager
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

    response = HTMLResponse(content="")

    await login_and_set_response_cookie(response, strategy=strategy, user=user)

    if not user.is_verified and settings.EMAIL_ENABLED:
        response.headers["HX-Trigger"] = EventSet(
            EventSet.FLASH(f"Remember to verify your account"),
        ).dump()

    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH(f"Welcome back, {user.name}!"),
        EventSet.AUTH_CHANGE,
        EventSet.CLOSE_MODAL
    ).dump()
    return response


@router.post("/logout", response_class=HTMLResponse)
async def logout(
    request: Request,
    user: User | None = Depends(current_user_optional),
    strategy: RedisStrategy[User, UUID] = Depends(get_redis_strategy),
) -> HTMLResponse:
    """
    Logout and serve an HTML fragment containing the auth widget.
    """
    flash_message = "You have been logged out"
    response = HTMLResponse(content="")

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
    return HTMLResponse(content="")


@router.get("/auth/widget", response_class=HTMLResponse)
async def serve_auth_widget(
    request: Request,
    user: User | None = Depends(current_user_optional)
) -> HTMLResponse:
    """
    Serve the auth widget.
    """
    return templates.TemplateResponse("fragments/auth/widget.html", {
        "request": request,
        "user": user
    })


@router.get("/register", tags=["Index", "Templates"], response_class=HTMLResponse)
async def render_register_page(request: Request) -> HTMLResponse:
    """
    Serve the register page.
    """

    return templates.TemplateResponse("register.html", {
        "request": request
    })


@router.get("/verify", tags=["Index", "Templates"], response_class=HTMLResponse)
async def render_verify_page(
    request: Request,
    token: str
) -> HTMLResponse:
    """
    Serve the verify page.
    """

    return templates.TemplateResponse("verify.html", {
        "request": request,
        "token": token
    })


@router.post("/verify", response_class=Response)
async def verify_account(
    request: Request,
    verify_form: Annotated[VerifyAccountForm, Form()],
    user_manager: UserManager = Depends(get_user_manager),
) -> Response:
    """
    Verify an account by token.
    """
    try:
        await user_manager.verify(verify_form.token)
    except InvalidVerifyToken:
        raise_http("This link is invalid or has expired", status_code=400)
    except UserAlreadyVerified:
        request.session["flash"] = "Account already verified!"
    else:
        request.session["flash"] = "Successfully verified account!"

    return Response(headers={"HX-Redirect": "/"})


@router.post("/forgot-password", response_class=Response)
async def send_forgot_password_email(
    request: Request,
    forgot_form: Annotated[ForgotPasswordForm, Form()],
    user_manager: UserManager = Depends(get_user_manager),
) -> Response:
    """
    Send a forgot password email.
    """
    try:
        user = await user_manager.get_by_email(forgot_form.email)
        await user_manager.forgot_password(user, request=request)
    except (UserInactive, UserNotExists):
        pass

    response = HTMLResponse(content="")

    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH("Reset password link sent"),
        EventSet.CLOSE_MODAL
    ).dump()
    return response


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