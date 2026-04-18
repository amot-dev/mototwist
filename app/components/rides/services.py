from sqlalchemy import ColumnExpressionArgument, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.core.config import logger
from app.components.core.models import Criterion, Ride, User
from app.components.rides.schema import AverageRatings
from app.components.twists.schema import FilterOwnership, FilterWeather, TwistBasic, TwistFilterWithRideOwnership


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


def weather_conditions_from(weather_filter: FilterWeather) -> list[ColumnExpressionArgument[bool]]:
    """
    Generate a list of SQLAlchemy AND clauses based on active weather filters.
    """
    conditions: list[ColumnExpressionArgument[bool]] = []

    # Map filter fields to db fields and dynamically build the conditions
    weather_mappings = {
        "temperature": Ride.__table__.c.weather_temperature,
        "light": Ride.__table__.c.weather_light,
        "type": Ride.__table__.c.weather_type,
        "precipitation": Ride.__table__.c.weather_precipitation,
        "wind": Ride.__table__.c.weather_wind,
        "fog": Ride.__table__.c.weather_fog,
    }
    for filter_field, db_column in weather_mappings.items():
        selected_conditions = getattr(weather_filter, filter_field)
        if selected_conditions:
            conditions.append(db_column.in_(selected_conditions))

    return conditions


async def calculate_average_rating(
    session: AsyncSession,
    user: User | None,
    twist: TwistBasic,
    filter: TwistFilterWithRideOwnership
) -> AverageRatings:
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
    ]).where(
        Ride.twist_id == twist.id,
        *weather_conditions_from(filter.weather)
    )

    # Filtering
    if filter.ride_ownership == FilterOwnership.OWN:
        statement = statement.where(Ride.author_id == user.id) if user else statement.where(false())

    result = await session.execute(statement)
    averages = result.first()

    if not averages:
        return AverageRatings(overall=None, by_criteria={})
    averages_dict = averages._asdict()  # pyright: ignore [reportPrivateUsage]

    return AverageRatings.from_averages(averages_dict, criteria)
