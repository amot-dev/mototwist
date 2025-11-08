from fastapi import Request, Response
from fastapi_users.authentication import RedisStrategy
from uuid import UUID

from app.events import EventSet
from app.models import User
from app.users import auth_backend
from app.utility import raise_http


async def login_and_set_response_cookie(
    response: Response,
    strategy: RedisStrategy[User, UUID] | None = None,
    user: User | None = None,
    token: str | None = None
) -> None:
    """
    Log in the user and attach the session cookie to the response object.

    :param response: The FastAPI Response object to attach the 'Set-Cookie' header to.
    :param strategy: The RedisStrategy instance used for authentication. Required if user is provided.
    :param user: The authenticated User object. Required if strategy is provided.
    :param token: An existing authentication token string. Used if user and strategy are None.
    :return: None. The function modifies the response object in place.
    :raises: HTTPException if the login fails.
    """
    # Login and create the session cookie response
    if user and strategy:
        cookie_response = await auth_backend.login(strategy, user)
    elif token:
        cookie_response = await auth_backend.transport.get_login_response(token)
    else:
        raise_http("Failed to login")

    # Copy cookie into template response
    cookie = cookie_response.headers.get("Set-Cookie")
    if cookie:
        response.headers["Set-Cookie"] = cookie
        response.headers["HX-Trigger"] = EventSet(EventSet.SESSION_SET).dump()


async def logout_and_set_response_cookie(
    request: Request,
    response: Response,
    strategy: RedisStrategy[User, UUID],
    user: User
) -> None:
    """
    Log out the user and clear the session cookie on the response object.

    :param request: The FastAPI Request object to retrieve the existing cookie/token from.
    :param response: The FastAPI Response object to attach the 'Set-Cookie' header to.
    :param strategy: The RedisStrategy instance used for authentication.
    :param user: The authenticated User object being logged out.
    :return: None. The function modifies the response object in place.
    """
    token = request.cookies.get("mototwist")
    if token:
        # Logout and create the (empty) session cookie response
        cookie_response = await auth_backend.logout(strategy, user, token)

        # Copy cookie into template response
        cookie = cookie_response.headers.get("Set-Cookie")
        if cookie:
            response.headers["Set-Cookie"] = cookie
            response.headers["HX-Trigger"] = EventSet(EventSet.SESSION_CLEARED).dump()