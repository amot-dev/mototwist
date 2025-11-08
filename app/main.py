from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from httpx import AsyncClient, HTTPStatusError
from pydantic_core import ErrorDetails
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware
import sys
from time import time
from typing import Awaitable, Callable, cast
import uvicorn

from app.config import logger, tags_metadata, templates
from app.database import apply_migrations, create_automigration, get_db, wait_for_db
from app.events import EventSet
from app.models import User
from app.routers import admin, auth, debug, ratings, twists, users
from app.schemas.users import UserCreate
from app.settings import Settings, settings
from app.users import UserManager, auth_backend, current_active_user_optional, get_user_db, redis_client
from app.utility import format_loc_for_user, raise_http, sort_schema_names, update_schema_name


@asynccontextmanager
async def lifespan(app: FastAPI):
    async for session in get_db():
        # Create initial admin user
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
                is_verified=True,
            )
            user_db = await anext(get_user_db(session))
            user_manager = UserManager(user_db)
            await user_manager.create(user_data)
            logger.info(f"Admin user '{settings.MOTOTWIST_ADMIN_EMAIL}' created")
        else:
            logger.info("Admin user creation skipped")

    yield

    # Runs on shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="MotoTwist",
    version=settings.MOTOTWIST_VERSION,
    contact={
        "name": "Alexander Mot",
        "url": "https://github.com/amot-dev/mototwist/issues"
    },
    license_info={
        "name": "GNU General Public License v3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.html"
    },
    lifespan=lifespan,
    openapi_tags=tags_metadata
)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> None:
    """
    Catches Pydantic's validation errors and returns a neat HTTPException.
    """
    first_error = cast(ErrorDetails, exc.errors()[0])
    raise_http(f"{first_error["msg"]} ({format_loc_for_user(first_error["loc"])})", status_code=422, exception=exc)


@app.middleware("http")
async def log_process_time(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start_time = time()
    response = await call_next(request)
    process_time = (time() - start_time) * 1000

    logger.debug(f"Request processing took {process_time:.2f}ms")

    return response


@app.middleware("http")
async def dispatch(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.force_session_renewal = False
    response = await call_next(request)

    # Skip if cookie is session cookie and does not need renewal
    if not settings.AUTH_COOKIE_MAX_AGE:
        return response

    # Skip if we are not forcing renewal and the sliding window is disabled
    if not request.state.force_session_renewal and not settings.AUTH_SLIDING_WINDOW_ENABLED:
        return response

    # Perform sliding session logic only if a token exists
    token = request.cookies.get("mototwist")
    if token:
        redis_key = f"fastapi_users_token:{token}"
        remaining_seconds = await redis_client.ttl(redis_key)

        # Calculate the threshold value (20% of the max age)
        refresh_threshold = settings.AUTH_COOKIE_MAX_AGE * 0.2

        # Check if the remaining time is low
        meets_refresh_threshold = remaining_seconds < refresh_threshold
        is_warned = remaining_seconds < settings.AUTH_EXPIRY_WARNING_OFFSET
        if remaining_seconds > 0 and (meets_refresh_threshold or is_warned):
            # Refresh the Redis Token
            await redis_client.expire(redis_key, settings.AUTH_COOKIE_MAX_AGE)

            # Send a new Set-Cookie header to the browser
            cookie_response = await auth_backend.transport.get_login_response(token)
            cookie = cookie_response.headers.get("Set-Cookie")
            if cookie:
                response.headers["Set-Cookie"] = cookie
                response.headers["HX-Trigger"] = EventSet(EventSet.SESSION_SET).dump()

    return response


app.add_middleware(SessionMiddleware, secret_key=settings.MOTOTWIST_SECRET_KEY)


@app.get("/", tags=["Index", "Templates"], response_class=HTMLResponse)
async def render_index_page(
    request: Request,
    user: User | None = Depends(current_active_user_optional)
) -> HTMLResponse:
    """
    Serve the main page of MotoTwist.

    :param request: FastAPI request.
    :param user: Optional logged in user.
    :return: TemplateResponse containing main page.
    """
    # Add a flash message if it exists in the session
    flash_message: str = request.session.pop("flash", None)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "flash_message": flash_message
    })


@app.get("/latest-version", tags=["Templates"], response_class=HTMLResponse)
async def get_latest_version(request: Request) -> HTMLResponse:
    """
    Serve an HTML fragment containing the latest version from GitHub, or "Unchecked" if running a dev build.

    :param request: FastAPI request.
    :raises HTTPException: Unable to read from the GitHub API.
    :return: TemplateResponse containing version HTML fragment.
    """
    # Default version indicates a development environment
    if settings.MOTOTWIST_VERSION == Settings.model_fields["MOTOTWIST_VERSION"].default:
        return HTMLResponse(
            content="<strong title='To limit use of the GitHub API, the latest version is not checked on dev builds'>Unchecked</strong>"
        )

    url = f"https://api.github.com/repos/{settings.MOTOTWIST_UPSTREAM}/releases/latest"

    try:
        async with AsyncClient() as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()  # Raise an exception for 4XX/5XX responses
            data = response.json()
            latest_version = data.get("tag_name")
    except HTTPStatusError as e:
        # Handle cases where the repo is not found or there are no releases
        raise_http("Could not read latest version from GitHub API",
            status_code=e.response.status_code,
            exception=e
        )

    if settings.MOTOTWIST_VERSION != latest_version:
        response = templates.TemplateResponse("fragments/new_version.html", {
            "request": request,
            "latest_version": latest_version
        })
        response.headers["HX-Trigger-After-Swap"] = EventSet(
            EventSet.FLASH(f"MotoTwist {latest_version} is now available!")
        ).dump()
        return response
    return HTMLResponse(content=f"<strong>{latest_version}</strong>")


app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(debug.router)
app.include_router(ratings.router)
app.include_router(twists.router)
app.include_router(users.router)

update_schema_name(app, auth.login, "UserLoginForm")
update_schema_name(app, debug.load_state, "StateLoadUploadFile")
sort_schema_names(app)

if __name__ == "__main__":
    wait_for_db()

    # Check if the create-migration command was given
    if len(sys.argv) > 1 and sys.argv[1] == "create-migration":
        # Make sure a message was also provided
        if len(sys.argv) < 3:
            logger.error("create-migration requires a message")
            print("Usage: python main.py create-migration <your_message_here>", file=sys.stderr)
            sys.exit(1)

        # Get the message from the third argument
        migration_message = sys.argv[2]

        # Create migration and exit
        create_automigration(migration_message)
        sys.exit(0)

    apply_migrations()
    logger.info("Starting MotoTwist...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.UVICORN_RELOAD,
        log_config=None # Explicitly disable Uvicorn's default logging config
    )