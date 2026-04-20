from typing import Annotated

from pydantic import BaseModel, Field
from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.core.models import Criterion, Ride, User
from app.components.rides.schema import AverageRatings
from app.components.twists.filter import FilterOwnership, FilterWeather
from app.components.twists.schema import TwistBasic


class RideFilter(BaseModel):
    # Basic Filtering
    ride_ownership: Annotated[FilterOwnership, Field()] = FilterOwnership.ALL

    # Weather Filtering
    weather: Annotated[FilterWeather, Field()] = FilterWeather()

    async def calculate_average_rating_for(
        self,
        session: AsyncSession,
        user: User | None,
        twist: TwistBasic
    ) -> AverageRatings:
        """
        Calculate the average ratings for a Twist.
        """
        criteria = await Criterion.get_list(session, is_paved=twist.is_paved)

        # Query averages for target ratings columns for this twist
        statement = select(*[
            func.avg(Ride.ratings[c.slug].as_integer()).label(c.slug)
            for c in criteria
        ]).where(
            Ride.twist_id == twist.id,
            *self.weather.calculate_conditions()
        )

        # Filtering
        if self.ride_ownership == FilterOwnership.OWN:
            statement = statement.where(Ride.author_id == user.id) if user else statement.where(false())

        result = await session.execute(statement)
        averages = result.first()

        if not averages:
            return AverageRatings(overall=None, by_criteria={})
        averages_dict = averages._asdict()  # pyright: ignore [reportPrivateUsage]

        return AverageRatings.from_averages(averages_dict, criteria)
