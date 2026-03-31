from datetime import date
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.config import logger
from app.database import get_db
from app.events import EventSet
from app.models import Criterion, Twist, Ride, User
from app.schemas.rides import TwistRideData
from app.schemas.twists import TwistBasic, TwistFilter, TwistUltraBasic
from app.services.rides import render_averages, render_ride_modal, render_view_all_button, render_view_modal, weather_conditions_from
from app.users import current_user, current_user_optional, verify
from app.utility import raise_http


router = APIRouter(
    prefix="/twists/{twist_id}/rides",
    tags=["Rides"]
)


@router.post("", response_class=HTMLResponse)
async def create_ride(
    request: Request,
    twist_id: int,
    ride_data: TwistRideData,
    user: User = Depends(verify(current_user)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Create a new ride for the given Twist.
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

    logger.debug(f"Attempting to submit ride Twist with id '{twist_id}'")

    # Ensure there are no missing or extra criteria
    ride_criteria = {slug for slug in ride_data.ratings.keys()}
    valid_criteria = await Criterion.get_set(session, twist_is_paved)
    if ride_criteria != valid_criteria:
        missing = valid_criteria - ride_criteria
        extra = ride_criteria - valid_criteria

        error_msg = "Rating criteria mismatch."
        if missing:
            error_msg += f" Missing: {", ".join(missing)}."
        if extra:
            error_msg += f" Unexpected: {", ".join(extra)}."

        raise_http(error_msg.rstrip("."), status_code=500)

    new_ride = Ride(
        author=user,
        twist_id=twist_id,
        date=ride_data.date,
        weather=ride_data.weather,
        ratings=ride_data.ratings
    )
    session.add(new_ride)
    await session.commit()
    logger.debug(f"Created ride '{new_ride}'")

    response = HTMLResponse(content="")
    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH("Ride submitted successfully!"),
        EventSet.CLOSE_MODAL,
        EventSet.REFRESH_AVERAGES(twist_id)
    ).dump()
    return response


@router.delete("/{ride_id}", response_class=HTMLResponse)
async def delete_ride(
    request: Request,
    twist_id: int,
    ride_id: int,
    user: User = Depends(verify(current_user)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Delete a ride from the given Twist.
    """
    if not user.is_superuser:
        try:
            result = await session.scalars(
                select(Ride.author_id).where(Ride.id == ride_id)
            )
            author_id = result.one()
        except NoResultFound:
            raise_http(f"Ride with id '{ride_id}' not found for Twist with id '{twist_id}'", status_code=404)
        except MultipleResultsFound:
            raise_http(f"Multiple rides with id '{ride_id}' found for Twist with id '{twist_id}'", status_code=500)

        if user.id != author_id:
            raise_http("You do not have permission to delete this ride", status_code=403)

    # Delete the Ride
    result = await session.scalar(
        delete(Ride).where(Ride.id == ride_id, Ride.twist_id == twist_id).returning(Ride.id)
    )
    if result is None:
        raise_http(f"Ride with id '{ride_id}' not found for Twist with id '{twist_id}'", status_code=404)

    await session.commit()
    logger.debug(f"Deleted ride with id '{ride_id}' from Twist with id '{twist_id}'")

    # Empty response to "delete" the card
    result = await session.execute(
        select(func.count()).select_from(Ride).where(Ride.twist_id == twist_id)
    )
    remaining_rides_count = result.scalar_one()
    if remaining_rides_count > 0:
        response = HTMLResponse(content="")
    else:
        response = HTMLResponse(content="<p>No rides yet</p>")

    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH("Ride removed successfully!"),
        EventSet.REFRESH_AVERAGES(twist_id)
    ).dump()
    return response


@router.post("/templates/averages", tags=["Templates"], response_class=HTMLResponse)
async def serve_averages(
    request: Request,
    twist_id: int,
    filter: TwistFilter,
    ride_ownership: Literal["all", "own"] = Query("all"),
    user: User | None = Depends(current_user_optional),
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

    return await render_averages(request, session, user, twist, filter, ride_ownership)


@router.post("/templates/view_all_button", tags=["Templates"], response_class=HTMLResponse)
async def serve_view_all_button(
    request: Request,
    twist_id: int,
    filter: TwistFilter,
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the view all rides button, including the number of rides.
    """
    # Calculate filters
    weather_conditions = weather_conditions_from(filter.weather)
    filtered = True if len(weather_conditions) else False

    try:
        result = await session.scalars(
            select(func.count(Ride.id)).where(
                Ride.twist_id == Twist.id,
                Twist.id == twist_id,
                *weather_conditions
            )
        )
        ride_count = result.one()
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)

    return await render_view_all_button(request, twist_id, ride_count, filtered)


@router.get("/templates/ride-modal", tags=["Templates"], response_class=HTMLResponse)
async def serve_ride_modal(
    request: Request,
    twist_id: int,
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing a modal to ride a given Twist.
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

    criteria = await Criterion.get_list(session, twist.is_paved)
    return await render_ride_modal(request, twist, criteria, date.today())


@router.post("/templates/view-modal", tags=["Templates"], response_class=HTMLResponse)
async def serve_view_modal(
    request: Request,
    twist_id: int,
    filter: TwistFilter,
    offset: int = Query(0),
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing a modal to view the rides for a given Twist.
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

    return await render_view_modal(request, session, user, twist, filter, offset)
