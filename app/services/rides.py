from datetime import date, timedelta
from fastapi import Request
from fastapi.responses import HTMLResponse
from humanize import intcomma, metric, ordinal
from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import cast, Literal

from app.config import logger, templates
from app.models import Criterion, Ride, User
from app.schemas.rides import AverageRating, RideList, RideListItem
from app.schemas.twists import TwistBasic, TwistUltraBasic
from app.settings import settings


async def initialize_criteria(session: AsyncSession) -> bool:
    """
    Populate the database with the default suite of rating criteria.

    :param session: The database session for criteria creation.
    :return: True if criteria were initialized, False if data already exists.
    """
    result = await session.execute(
        select(func.count()).select_from(Criterion)
    )
    criteria_count = result.scalar_one()
    if criteria_count == 0:
        criteria = [
            # Shared Criteria
            Criterion(
                slug="seclusion",
                description="Infrequency of other vehicles on the road",
                for_paved=True,
                for_unpaved=True,
            ),
            Criterion(
                slug="scenery",
                description="Visual appeal of surroundings",
                for_paved=True,
                for_unpaved=True,
            ),

            # Paved Criteria
            Criterion(
                slug="pavement",
                description="Quality of road surface",
                for_paved=True,
                for_unpaved=False,
            ),
            Criterion(
                slug="twistyness",
                description="Tightness and frequency of turns",
                for_paved=True,
                for_unpaved=False,
            ),
            Criterion(
                slug="intensity",
                description="Overall riding energy the road draws out",
                for_paved=True,
                for_unpaved=False,
            ),

            # Unpaved Criteria
            Criterion(
                slug="surface_consistency",
                description="Predictability of traction across the route",
                for_paved=False,
                for_unpaved=True,
            ),
            Criterion(
                slug="technicality",
                description="Challenge level from terrain features like rocks, ruts, sand, or mud",
                for_paved=False,
                for_unpaved=True,
            ),
            Criterion(
                slug="flow",
                description="Smoothness of the trail without constant disruptions or awkward sections",
                for_paved=False,
                for_unpaved=True,
            ),
        ]

        session.add_all(criteria)
        await session.commit()

        logger.info(f"Rating criteria populated and table locked")
        return True
    else:
        return False


async def calculate_average_rating(
    session: AsyncSession,
    user: User | None,
    twist: TwistUltraBasic,
    filter: Literal["all", "own"],
    round_to: int
) -> dict[str, AverageRating]:
    """
    Calculate the average ratings for a Twist.

    :param session: The session to use for database transactions.
    :param twist_id: The id of the Twist for which to calculate average ratings.
    :param twist_is_paved: Whether or not the Twist is paved.
    :param round_to: The number of decimal places to round to.
    :return: A dictionary of each criteria and its average rating.
    """
    criteria = await Criterion.get_list(session, is_paved=twist.is_paved)

    # Query averages for target ratings columns for this twist
    statement = select(*[
        func.avg(Ride.ratings[c.slug].as_integer()).label(c.slug)
        for c in criteria
    ]).where(Ride.twist_id == twist.id)

    # Filtering
    if filter == "own":
        statement = statement.where(Ride.author_id == user.id) if user else statement.where(false())

    result = await session.execute(statement)
    averages = result.first()

    if not averages:
        return {}

    # Create a lookup dictionary for descriptions for easy access
    descriptions = {c.slug: c.description for c in criteria}

    return {
        slug: cast(AverageRating, {
            "rating": round(criterion, round_to),
            "description": descriptions.get(slug, "")
        })
        for slug, criterion in averages._asdict().items()  # pyright: ignore [reportPrivateUsage]
        if criterion is not None
    }


async def render_averages(
    request: Request,
    session: AsyncSession,
    user: User | None,
    twist: TwistUltraBasic,
    ownership: Literal["all", "own"] = "all",
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the ratings averages.
    """
    return templates.TemplateResponse("fragments/rides/averages.html", {
        "request": request,
        "average_ratings": await calculate_average_rating(session, user, twist, ownership, round_to=1),
        "criterion_max_value": Criterion.MAX_VALUE
    })


async def render_view_all_button(
    request: Request,
    twist_id: int,
    ride_count: int
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the view all rides button.
    """
    if ride_count > 9999:
        ride_count_str = metric(ride_count).replace(" ", "")
    else:
        ride_count_str = intcomma(ride_count)

    return templates.TemplateResponse("fragments/rides/view_all.html", {
        "request": request,
        "twist_id": twist_id,
        "ride_count": ride_count_str
    })


async def render_ride_modal(
    request: Request,
    twist: TwistBasic,
    criteria: list[Criterion],
    today: date
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the ride modal.
    """
    tomorrow = today + timedelta(days=1)
    criterion_initial_value = int((Criterion.MIN_VALUE + Criterion.MAX_VALUE) / 2)

    return templates.TemplateResponse("fragments/rides/ride_modal.html", {
        "request": request,
        "twist": twist,
        "today": today,
        "tomorrow": tomorrow,
        "criteria": criteria,
        "criterion_min_value": Criterion.MIN_VALUE,
        "criterion_max_value": Criterion.MAX_VALUE,
        "criterion_initial_value": criterion_initial_value
    })


async def render_view_modal(
    request: Request,
    session: AsyncSession,
    user: User | None,
    twist: TwistBasic,
    offset: int
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the ride view modal.
    """
    criteria = await Criterion.get_list(session, is_paved=twist.is_paved)

    # Collect rides in order, offset and limited by settings
    result = await session.scalars(
        select(Ride)
        .where(Ride.twist_id == twist.id)
        .order_by(Ride.date.desc())
        .offset(offset)
        .limit(settings.RIDES_FETCHED_PER_QUERY)
        .options(
            selectinload(Ride.author).load_only(User.name)
        )
    )
    rides = result.all()

    # Build list items
    ride_list_items: list[RideListItem] = []
    for ride in rides:
        # Pre-format the date for easier display in the template
        ordinal_day = ordinal(ride.date.day)
        formatted_date = ride.date.strftime(f"%B {ordinal_day}, %Y")

        # Set author name whether they exist or not
        author_name = ride.author.name if ride.author else settings.DELETED_USER_NAME

        # Check if the user is allowed to delete the ride
        can_delete = (user.is_superuser or user.id == ride.author_id) if user else False

        ride_list_items.append(RideListItem(
            id=ride.id,
            author_name=author_name,
            can_delete=can_delete,
            formatted_date=formatted_date,
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
