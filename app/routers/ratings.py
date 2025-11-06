from datetime import date
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
import json
from sqlalchemy import delete, func, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Literal

from app.config import logger
from app.database import get_db
from app.models import Twist, PavedRating, UnpavedRating, User
from app.schemas.ratings import CRITERIA_NAMES_PAVED, CRITERIA_NAMES_UNPAVED, TwistRateForm
from app.schemas.twists import TwistBasic, TwistUltraBasic
from app.services.ratings import render_averages, render_rate_modal, render_view_modal
from app.users import current_active_user, current_active_user_optional
from app.utility import raise_http


router = APIRouter(
    prefix="/twists/{twist_id}/ratings",
    tags=["Ratings"]
)


@router.post("", response_class=HTMLResponse)
async def create_rating(
    request: Request,
    twist_id: int,
    rating_form: Annotated[TwistRateForm, Form()],
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Create a new rating for the given Twist.
    """
    try:
        result = await session.scalars(
            select(Twist.is_paved).where(Twist.id == twist_id)
        )
        twist_is_paved = result.one()
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple twists found for id '{twist_id}'", status_code=500)

    logger.debug(f"Attempting to rate Twist with id '{twist_id}'")

    if twist_is_paved:
        Rating = PavedRating
        rating_data = rating_form.model_dump(include=CRITERIA_NAMES_PAVED.union({"rating_date"}))
    else:
        Rating = UnpavedRating
        rating_data = rating_form.model_dump(include=CRITERIA_NAMES_UNPAVED.union({"rating_date"}))

    # Create the new rating instance, linking it to the Twist
    rating_data.update({
        "author": user,
        "twist_id": twist_id
    })
    new_rating = Rating(**rating_data)
    session.add(new_rating)
    await session.commit()
    logger.debug(f"Created rating '{new_rating}'")

    events = {
        "flashMessage": "Twist rated successfully!",
        "closeModal": "",
        "refreshAverages": f"{twist_id}"
    }
    response = HTMLResponse(content="")
    response.headers["HX-Trigger-After-Swap"] = json.dumps(events)
    return response


@router.delete("/{rating_id}", response_class=HTMLResponse)
async def delete_rating(
    request: Request,
    twist_id: int,
    rating_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Delete a rating from the given Twist.
    """
    try:
        result = await session.scalars(
            select(Twist.is_paved).where(Twist.id == twist_id)
        )
        twist_is_paved = result.one()
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple twists found for id '{twist_id}'", status_code=500)

    Rating = PavedRating if twist_is_paved else UnpavedRating

    if not user.is_superuser:
        try:
            result = await session.scalars(
                select(Rating.author_id).where(Rating.id == rating_id)
            )
            author_id = result.one()
        except NoResultFound:
            raise_http(f"Rating with id '{rating_id}' not found for Twist with id '{twist_id}'", status_code=404)
        except MultipleResultsFound:
            raise_http(f"Multiple Ratings with id '{rating_id}' found for Twist with id '{twist_id}'", status_code=500)

        if user.id != author_id:
            raise_http("You do not have permission to delete this Rating", status_code=403)

    # Delete the Rating
    result = await session.execute(
        delete(Rating).where(Rating.id == rating_id, Rating.twist_id == twist_id)
    )
    if result.rowcount == 0:
        raise_http(f"Rating with id '{rating_id}' not found for Twist with id '{twist_id}'", status_code=404)

    await session.commit()
    logger.debug(f"Deleted rating with id '{rating_id}' from Twist with id '{twist_id}'")

    # Empty response to "delete" the card
    result = await session.execute(
        select(func.count()).select_from(Rating).where(Rating.twist_id == twist_id)
    )
    remaining_ratings_count = result.scalar_one()
    if remaining_ratings_count > 0:
        response = HTMLResponse(content="")
    else:
        response = HTMLResponse(content="<p>No ratings yet</p>")

    events = {
        "flashMessage": "Rating removed successfully!",
        "refreshAverages": f"{twist_id}"
    }
    response.headers["HX-Trigger-After-Swap"] = json.dumps(events)
    return response


@router.get("/templates/averages", tags=["Templates"], response_class=HTMLResponse)
async def serve_averages(
    request: Request,
    twist_id: int,
    ownership: Literal["all", "own"] = Query("all"),
    user: User | None = Depends(current_active_user_optional),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the ratings averages.
    """
    try:
        result = await session.execute(
            select(*TwistUltraBasic.fields).where(Twist.id == twist_id)
        )
        twist = TwistUltraBasic.model_validate(result.one())
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple twists found for id '{twist_id}'", status_code=500)

    return await render_averages(request, session, user, twist, ownership)


@router.get("/templates/rate-modal", tags=["Templates"], response_class=HTMLResponse)
async def serve_rate_modal(
    request: Request,
    twist_id: int,
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing a modal to rate a given Twist.
    """
    try:
        result = await session.execute(
            select(*TwistBasic.fields).where(Twist.id == twist_id)
        )
        twist = TwistBasic.model_validate(result.one())
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple twists found for id '{twist_id}'", status_code=500)

    return await render_rate_modal(request, twist, date.today())


@router.get("/templates/view-modal", tags=["Templates"], response_class=HTMLResponse)
async def serve_view_modal(
    request: Request,
    twist_id: int,
    offset: int = Query(0),
    user: User | None = Depends(current_active_user_optional),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing a modal to view the ratings for a given Twist.
    """
    try:
        result = await session.execute(
            select(*TwistBasic.fields).where(Twist.id == twist_id)
        )
        twist = TwistBasic.model_validate(result.one())
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple twists found for id '{twist_id}'", status_code=500)

    return await render_view_modal(request, session, user, twist, offset)