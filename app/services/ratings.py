from datetime import date, timedelta
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from humanize import ordinal
from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import cast, Literal

from app.models import Rating, PavedRating, UnpavedRating, User
from app.schemas.ratings import (
    CRITERIA_NAMES_PAVED, CRITERIA_NAMES_UNPAVED, RATING_CRITERIA_PAVED, RATING_CRITERIA_UNPAVED,
    AverageRating, RatingList, RatingListItem
)
from app.schemas.twists import TwistBasic, TwistUltraBasic
from app.settings import settings


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
    if twist.is_paved:
        target_model = PavedRating
        criteria_list = RATING_CRITERIA_PAVED
    else:
        target_model = UnpavedRating
        criteria_list = RATING_CRITERIA_UNPAVED
    criteria_columns = [getattr(target_model, criterion.name) for criterion in criteria_list]

    # Query averages for target ratings columns for this twist
    statement = select(*[func.avg(col).label(col.key) for col in criteria_columns]).where(target_model.twist_id == twist.id)

    # Filtering
    if filter == "own":
        statement = statement.where(target_model.author_id == user.id) if user else statement.where(false())

    result = await session.execute(
        statement
    )
    averages = result.first()

    if not averages:
        return {}

    # Create a lookup dictionary for descriptions for easy access
    descriptions = {criteria.name: criteria.desc for criteria in criteria_list}

    return {
        key: cast(AverageRating, {
            "rating": round(value, round_to),
            "desc": descriptions.get(key, "")
        })
        for key, value in averages._asdict().items()  # pyright: ignore [reportPrivateUsage]
        if value is not None
    }


templates = Jinja2Templates(directory="templates")


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
    return templates.TemplateResponse("fragments/ratings/averages.html", {
        "request": request,
        "average_rating_criteria": await calculate_average_rating(session, user, twist, ownership, round_to=1),
        "criterion_max_value": Rating.CRITERION_MAX_VALUE
    })


async def render_rate_modal(
    request: Request,
    twist: TwistBasic,
    today: date
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the rate modal.
    """
    tomorrow = today + timedelta(days=1)
    criterion_initial_value = int((Rating.CRITERION_MIN_VALUE + Rating.CRITERION_MAX_VALUE) / 2)

    return templates.TemplateResponse("fragments/ratings/rate_modal.html", {
        "request": request,
        "twist": twist,
        "today": today,
        "tomorrow": tomorrow,
        "criteria_list": RATING_CRITERIA_PAVED if twist.is_paved else RATING_CRITERIA_UNPAVED,
        "criterion_min_value": Rating.CRITERION_MIN_VALUE,
        "criterion_max_value": Rating.CRITERION_MAX_VALUE,
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
    Build and return the TemplateResponse for the rate modal.
    """
    Rating = PavedRating if twist.is_paved else UnpavedRating

    # Collect ratings in order, offset and limited by settings
    result = await session.scalars(
        select(Rating)
        .where(Rating.twist_id == twist.id)
        .order_by(Rating.rating_date.desc())
        .offset(offset)
        .limit(settings.RATINGS_FETCHED_PER_QUERY)
        .options(
            selectinload(Rating.author).load_only(User.name)
        )
    )
    ratings = result.all()

    # Build list items
    rating_list_items: list[RatingListItem] = []
    for rating in ratings:
        # Pre-format the date for easier display in the template
        ordinal_day = ordinal(rating.rating_date.day)
        formatted_date = rating.rating_date.strftime(f"%B {ordinal_day}, %Y")

        # Set author name whether they exist or not
        author_name = rating.author.name if rating.author else settings.DELETED_USER_NAME

        # Check if the user is allowed to delete the rating
        can_delete_rating = (user.is_superuser or user.id == rating.author_id) if user else False

        rating_list_items.append(RatingListItem(
            id=rating.id,
            author_name=author_name,
            can_delete_rating=can_delete_rating,
            formatted_date=formatted_date,
            criteria={
                criterion_name: getattr(rating, criterion_name)
                for criterion_name in (CRITERIA_NAMES_PAVED if twist.is_paved else CRITERIA_NAMES_UNPAVED)
            }
        ))

    # Compile list with criteria descriptions
    rating_list = RatingList(
        criteria_descriptions={
            criteria.name: criteria.desc or ""
            for criteria in (RATING_CRITERIA_PAVED if twist.is_paved else RATING_CRITERIA_UNPAVED)
        },
        items=rating_list_items
    )

    # For offset 0 (beginning), use the template including the header, otherwise just the list
    if offset == 0:
        return templates.TemplateResponse("fragments/ratings/view_modal.html", {
            "request": request,
            "twist": twist,
            "rating_list": rating_list,
            "next_offset": offset + settings.RATINGS_FETCHED_PER_QUERY,
            "criterion_max_value": Rating.CRITERION_MAX_VALUE
        })
    else:
        return templates.TemplateResponse("fragments/ratings/view_list.html", {
            "request": request,
            "twist": twist,
            "rating_list": rating_list,
            "next_offset": offset + settings.RATINGS_FETCHED_PER_QUERY,
            "criterion_max_value": Rating.CRITERION_MAX_VALUE
        })