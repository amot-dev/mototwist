from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi_users.authentication import RedisStrategy
from fastapi_users.exceptions import UserNotExists
from secrets import choice
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from string import ascii_letters, digits
from typing import Annotated
from uuid import UUID

from app.config import templates
from app.database import get_db
from app.events import Event, EventSet
from app.models import User
from app.redis_client import get_redis_strategy
from app.schemas.admin import UserCreateFormAdmin
from app.schemas.users import UserCreate, UserUpdate
from app.services.admin import is_last_active_admin
from app.services.auth import logout_and_set_response_cookie
from app.settings import settings
from app.users import InvalidUsernameException, UserManager, current_admin, get_user_manager, verify
from app.utility import raise_http


router = APIRouter(
    prefix="/admin",
    tags=["Administration"]
)


@router.post("/users", response_class=HTMLResponse)
async def create_user(
    request: Request,
    user_form: Annotated[UserCreateFormAdmin, Form()],
    admin: User = Depends(verify(current_admin)),
    user_manager: UserManager = Depends(get_user_manager)
) -> HTMLResponse:
    """
    Create a new user.
    """
    try:
        await user_manager.get_by_email(user_form.email)
        raise_http("This email address is already in use", status_code=409)
    except UserNotExists:
        pass

    # Create the user with a long, random, unusable password. The user will never need to know this password
    placeholder_password = "".join(choice(ascii_letters + digits) for _ in range(32))
    user_data = UserCreate(
        name=user_form.name,
        email=user_form.email.lower(),
        password=placeholder_password,
        is_active=True,
        is_superuser=user_form.is_superuser,
        is_verified=False,
    )
    try:
        user = await user_manager.create(user_data, request=request)
    except InvalidUsernameException as e:
        raise_http("Invalid username", status_code=422, exception=e)

    # Generate a password-reset token for the new user
    user_manager.user_forgot_password = False
    await user_manager.forgot_password(user, request=request)

    # Send verification email
    if settings.EMAIL_ENABLED:
        await user_manager.request_verify(user, request=request)

    response = templates.TemplateResponse("fragments/admin/settings_user.html", {
        "request": request,
        "user": user,
        "reset_password_link": f"{settings.MOTOTWIST_BASE_URL}/reset-password?token={user_manager.generated_token}"
    })
    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH("User created!"),
        EventSet.RESET_FORM
    ).dump()
    return response


@router.delete("/users/{user_id}", response_class=HTMLResponse)
async def delete_user(
    request: Request,
    user_id: UUID,
    admin: User = Depends(verify(current_admin)),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: RedisStrategy[User, UUID] = Depends(get_redis_strategy),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Delete a user.
    """
    try:
        user = await user_manager.get(user_id)
    except UserNotExists:
        raise_http(f"User with id '{user_id}' not found", status_code=404)

    # Prevent last active admin from being deleted
    if await is_last_active_admin(session, user):
        raise_http("Cannot delete the last active administrator", status_code=403)

    response = HTMLResponse(content="")
    events: list[Event] = [EventSet.FLASH("User deleted!")]

    if user == admin:
        await logout_and_set_response_cookie(request, response, strategy=strategy, user=user)
        events = [
            EventSet.FLASH("Account deleted!"),
            EventSet.AUTH_CHANGE,
            EventSet.CLOSE_MODAL
        ]

    await user_manager.delete(user, request=request)

    response.headers["HX-Trigger-After-Swap"] = EventSet(*events).dump()
    return response


@router.post("/users/{user_id}/toggle/active", response_class=HTMLResponse)
async def toggle_user_active(
    request: Request,
    user_id: UUID,
    admin: User = Depends(verify(current_admin)),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: RedisStrategy[User, UUID] = Depends(get_redis_strategy),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Toggle the active state for a given user.
    """
    try:
        user = await user_manager.get(user_id)
    except UserNotExists:
        raise_http(f"User with id '{user_id}' not found", status_code=404)

    # Prevent last active admin from being disabled
    if await is_last_active_admin(session, user):
        raise_http("Cannot disable the last active administrator", status_code=403)

    user_updates = UserUpdate()
    user_updates.is_active = not user.is_active
    await user_manager.update(user_updates, user, request=request)

    response = templates.TemplateResponse("fragments/admin/settings_user.html", {
        "request": request,
        "user": user
    })

    if user == admin:
        await logout_and_set_response_cookie(request, response, strategy=strategy, user=user)
        response.headers["HX-Trigger-After-Swap"] = EventSet(
            EventSet.FLASH("Account deactivated!"),
            EventSet.AUTH_CHANGE,
            EventSet.CLOSE_MODAL
        ).dump()

    return response


@router.post("/users/{user_id}/toggle/admin", response_class=HTMLResponse)
async def toggle_user_admin(
    request: Request,
    user_id: UUID,
    admin: User = Depends(verify(current_admin)),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Toggle the superuser state for a given user.
    """
    try:
        user = await user_manager.get(user_id)
    except UserNotExists:
        raise_http(f"User with id '{user_id}' not found", status_code=404)

    # Prevent last active admin from losing privileges
    if await is_last_active_admin(session, user):
        raise_http("Cannot remove privileges from the last active administrator", status_code=403)

    user_updates = UserUpdate()
    user_updates.is_superuser = not user.is_superuser
    await user_manager.update(user_updates, user, request=request)

    response = templates.TemplateResponse("fragments/admin/settings_user.html", {
        "request": request,
        "user": user
    })

    if user == admin:
        response.headers["HX-Trigger-After-Swap"] = EventSet(
            EventSet.FLASH("Account privileges revoked!"),
            EventSet.AUTH_CHANGE,
            EventSet.CLOSE_MODAL
        ).dump()

    return response


@router.get("/templates/settings-modal", tags=["Templates"], response_class=HTMLResponse)
async def render_settings_modal(
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