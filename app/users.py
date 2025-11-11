from css_inline import CSSInliner
from fastapi import Depends, Request, status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import FastAPIUsersException
from fastapi_users.schemas import BaseUserCreate
import sass
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, AsyncGenerator, cast
from uuid import UUID

from app.config import logger, templates
from app.database import get_db
from app.smtp import SMTPEmailTransport
from app.models import User
from app.redis_client import CooldownReason, get_redis_strategy, redis_cooldown
from app.schemas.users import UserCreate
from app.settings import settings
from app.utility import raise_http


class InvalidUsernameException(FastAPIUsersException):
    pass


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = settings.MOTOTWIST_SECRET_KEY
    verification_token_secret = settings.MOTOTWIST_SECRET_KEY


    # Not using sass, but CSSInliner doesn't support nested blocks
    try:
        _css_text = sass.compile(filename="static/css/style.css")
    except FileNotFoundError:
        _css_text = ""


    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.generated_token: str = ""
        self.user_forgot_password: bool = True


    async def create(self, user_create: BaseUserCreate, safe: bool = False, request: Request | None = None) -> User:
        if isinstance(user_create, UserCreate):

            # If a name isn't provided, create one from the email
            if user_create.name is None:
                user_create.name = user_create.email.partition("@")[0]

            # Prevent naming to deleted user name
            if user_create.name == settings.DELETED_USER_NAME:
                raise InvalidUsernameException

        # Call the original create method to finish the process
        created_user = await super().create(user_create, safe, request)

        return created_user


    async def on_after_forgot_password(self, user: User, token: str, request: Request | None = None) -> None:
        logger.debug(f"Generated forgot password token for {user.id}")

        # If email is not enabled, save the generated_token for the admin user create route to grab
        if not settings.EMAIL_ENABLED:
            self.generated_token = token
            return

        async with redis_cooldown(CooldownReason.FORGOT_PASSWORD, str(user.id)):
            if self.user_forgot_password:
                title = "Forgot password"
                context = {
                    "css_block": f"<style>\n{self._css_text}\n</style>",
                    "title": title,
                    "message": "If you did not initiate this request, feel free to ignore this message.",
                    "action": "Reset Password",
                    "action_label": "Please reset your password",
                    "action_url": f"{settings.MOTOTWIST_BASE_URL}/reset-password?token={token}"
                }
            else:
                title = f"Welcome to {settings.MOTOTWIST_INSTANCE_NAME}!"
                context = {
                    "css_block": f"<style>\n{self._css_text}\n</style>",
                    "title": title,
                    "message": f"An administrator has created a new <a href=\"{settings.MOTOTWIST_BASE_URL}\"\
                        class=\"button button-link\">{settings.MOTOTWIST_INSTANCE_NAME}</a> account for you.\
                        After setting your password, you may sign in using this email.",
                    "action": "Set Password",
                    "action_label": "Please set your password",
                    "action_url": f"{settings.MOTOTWIST_BASE_URL}/reset-password?token={token}"
                }

            content = cast(str, templates.get_template("fragments/auth/email.html").render(context))  # pyright: ignore [reportUnknownMemberType]
            await SMTPEmailTransport.send_mail(user.email, title, CSSInliner().inline(content))


    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None) -> None:
        logger.debug(f"Generated verification token for {user.id}")

        async with redis_cooldown(CooldownReason.VERIFY_EMAIL, str(user.id)):
            title = "Verify your account"
            content = cast(str, templates.get_template("fragments/auth/email.html").render({  # pyright: ignore [reportUnknownMemberType]
                "css_block": f"<style>\n{self._css_text}\n</style>",
                "title": title,
                "message": f"Thank you for signing up for {settings.MOTOTWIST_INSTANCE_NAME}!",
                "action": "Verify",
                "action_label": "Please verify your account",
                "action_url": f"{settings.MOTOTWIST_BASE_URL}/verify?token={token}"
            }))

            await SMTPEmailTransport.send_mail(user.email, title, CSSInliner().inline(content))


async def get_user_db(
    session: AsyncSession = Depends(get_db)
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, UUID], None]:
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, UUID] = Depends(get_user_db)
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


cookie_transport = CookieTransport(cookie_name="mototwist", cookie_max_age=settings.AUTH_COOKIE_MAX_AGE)
auth_backend = AuthenticationBackend(
    name="cookie-auth",
    transport=cookie_transport,
    get_strategy=get_redis_strategy
)


fastapi_users = FastAPIUsers[User, UUID](
    get_user_manager,
    [auth_backend],
)


current_user = fastapi_users.current_user(active=True)
current_user_optional = fastapi_users.current_user(active=True, optional=True)
current_admin = fastapi_users.current_user(active=True, superuser=True)


from typing import Awaitable, Callable
def verify(
    user_dependency: Callable[..., Awaitable[User]]
):
    """
    Return a dependency callable that checks if the authenticated user
    from the base user_dependency is verified. Raises 403 if not.
    """
    async def verified_check(user: User = Depends(user_dependency)) -> User:
        if not user:
            # Should not call this with an optional. Force logged in user.
            raise_http("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
        if not user.is_verified:
            raise_http("Please verify your account", status_code=status.HTTP_403_FORBIDDEN)
        return user

    return verified_check