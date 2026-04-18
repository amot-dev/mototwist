from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.components.core.config import logger
from app.components.core.database import get_db
from app.components.core.events import EventSet
from app.components.core.models import Criterion, Twist, Ride, User
from app.components.core.utility import raise_http
from app.components.rides.schema import TwistRideData
from app.components.users.services import current_user, verify


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
    try:
        result = await session.scalars(
            select(Ride).where(Ride.id == ride_id).options(
                load_only(Ride.id, Ride.author_id)
            )
        )
        ride = result.one()
    except NoResultFound:
        raise_http(f"Ride with id '{ride_id}' not found for Twist with id '{twist_id}'", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple rides with id '{ride_id}' found for Twist with id '{twist_id}'", status_code=500)

    # If not admin, check if the user authored the ride (and can delete it)
    if not user.is_superuser and user.id != ride.author_id:
        raise_http("You do not have permission to delete this ride", status_code=403)

    # Delete the Ride
    await session.delete(ride)
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
