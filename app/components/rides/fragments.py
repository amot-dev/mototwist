from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from humanize import intcomma, metric, ordinal
from sqlalchemy import false, func, select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.components.core.config import templates
from app.components.core.database import get_db
from app.components.core.models import Criterion, Twist, Ride, User
from app.components.core.schema import Weather
from app.components.core.settings import settings
from app.components.core.utility import raise_http
from app.components.rides.filter import RideFilter
from app.components.rides.schema import RideList, RideListItem
from app.components.twists.filter import FilterOwnership
from app.components.twists.schema import TwistBasic
from app.components.users.services import current_user_optional


router = APIRouter(
    prefix="/twists/{twist_id}/rides",
    tags=["Rides", "Templates"]
)


@router.get("/templates/ride-modal", response_class=HTMLResponse)
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

    today = date.today()
    tomorrow = today + timedelta(days=1)
    criterion_initial_value = int((Criterion.MIN_VALUE + Criterion.MAX_VALUE) / 2)
    criteria = await Criterion.get_list(session, twist.is_paved)

    return templates.TemplateResponse("fragments/rides/ride_modal.html", {
        "request": request,
        "twist": twist,
        "today": today,
        "tomorrow": tomorrow,
        "Weather": Weather,
        "criteria": criteria,
        "criterion_min_value": Criterion.MIN_VALUE,
        "criterion_max_value": Criterion.MAX_VALUE,
        "criterion_initial_value": criterion_initial_value
    })


@router.post("/templates/averages", response_class=HTMLResponse)
async def serve_averages(
    request: Request,
    twist_id: int,
    filter: RideFilter,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the ratings averages.
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

    average_ratings = await filter.calculate_average_rating_for(session, user, twist)

    return templates.TemplateResponse("fragments/rides/averages.html", {
        "request": request,
        "twist_id": twist.id,
        "overall_average": average_ratings.overall,
        "average_ratings": average_ratings.by_criteria,
        "criterion_max_value": Criterion.MAX_VALUE
    })


@router.post("/templates/view_all_button", response_class=HTMLResponse)
async def serve_view_all_button(
    request: Request,
    twist_id: int,
    filter: RideFilter,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the view all rides button, including the number of rides.
    """
    # Calculate ride filters
    filtered = False
    statement = select(func.count(Ride.id)).where(
        Ride.twist_id == twist_id
    )

    if filter.ride_ownership == FilterOwnership.OWN:
        filtered = True
        statement = statement.where(Ride.author_id == user.id) if user else statement.where(false())

    weather_conditions = filter.weather.calculate_conditions()
    if len(weather_conditions):
        filtered = True
        statement = statement.where(*weather_conditions)

    # Get ride count
    try:
        result = await session.scalars(statement)
        ride_count = result.one()
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)

    # Format output
    if ride_count == 0:
        ride_count_str = "No rides to view"
    elif ride_count == 1:
        ride_count_str = "View single ride"
    elif ride_count > 9999:
        ride_count_str = "View " + metric(ride_count).replace(" ", "") + " rides"
    else:
        ride_count_str = "View " + intcomma(ride_count) + " rides"

    if filtered:
        ride_count_str += " (filtered)"

    return templates.TemplateResponse("fragments/rides/view_all.html", {
        "request": request,
        "twist_id": twist_id,
        "ride_count": ride_count,
        "ride_count_str": ride_count_str
    })


@router.post("/templates/view-modal", response_class=HTMLResponse)
async def serve_view_modal(
    request: Request,
    twist_id: int,
    filter: RideFilter,
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

    # Filtering
    statement = select(Ride).where(
        Ride.twist_id == twist.id
    )

    if filter.ride_ownership == FilterOwnership.OWN:
        statement = statement.where(Ride.author_id == user.id) if user else statement.where(false())

    weather_conditions = filter.weather.calculate_conditions()
    if len(weather_conditions):
        statement = statement.where(*weather_conditions)

    # Collect rides in order, offset and limited by settings
    result = await session.scalars(
        statement
        .order_by(Ride.date.desc())
        .offset(offset)
        .limit(settings.RIDES_FETCHED_PER_QUERY)
        .options(
            selectinload(Ride.author).load_only(User.name)
        )
    )
    rides = result.all()

    # Build list items
    criteria = await Criterion.get_list(session, is_paved=twist.is_paved)
    ride_list_items: list[RideListItem] = []
    for ride in rides:
        # Pre-format the date for easier display in the template
        ordinal_day = ordinal(ride.date.day)
        formatted_date = ride.date.strftime(f"%B {ordinal_day}, %Y")

        # Set author name whether they exist or not
        author_name = ride.author.name if ride.author else settings.DELETED_USER_NAME

        # Check if the user is allowed to delete the ride
        editable = (user.is_superuser or user.id == ride.author_id) if user else False

        ride_list_items.append(RideListItem(
            id=ride.id,
            author_name=author_name,
            editable=editable,
            formatted_date=formatted_date,
            weather=ride.weather,
            ratings={
                c.slug: ride.ratings[c.slug]
                for c in criteria
            }
        ))

    # Compile list with criteria descriptions
    ride_list = RideList(
        criteria_descriptions={
            c.slug: c.description or ""
            for c in criteria
        },
        items=ride_list_items
    )

    # For offset 0 (beginning), use the template including the header, otherwise just the list
    if offset == 0:
        return templates.TemplateResponse("fragments/rides/view_modal.html", {
            "request": request,
            "twist": twist,
            "ride_list": ride_list,
            "next_offset": offset + settings.RIDES_FETCHED_PER_QUERY,
            "criterion_max_value": Criterion.MAX_VALUE
        })
    else:
        return templates.TemplateResponse("fragments/rides/view_list.html", {
            "request": request,
            "twist": twist,
            "ride_list": ride_list,
            "next_offset": offset + settings.RIDES_FETCHED_PER_QUERY,
            "criterion_max_value": Criterion.MAX_VALUE
        })
