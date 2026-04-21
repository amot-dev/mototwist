from typing import Annotated

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.core.models import Criterion, Ride, User
from app.components.rides.schema import AverageRatings
from app.components.twists.filter import FilterAuthor, FilterWeather
from app.components.twists.schema import TwistBasic


class RideFilter(BaseModel):
    # Basic Filtering
    author: Annotated[FilterAuthor, Field()] = FilterAuthor.ALL

    # Criteria Exclusion
    excluded_criteria_slugs: Annotated[set[str], Field()] = set()

    # Weather Filtering
    weather: Annotated[FilterWeather, Field()] = FilterWeather()


    # Ensure excluded criteria slugs is a set
    @field_validator("excluded_criteria_slugs", mode="before")
    @classmethod
    def excluded_criteria_slugs_to_set(cls, value: str | list[str]) -> set[str]:
        if not isinstance(value, list):
            return {value}
        else:
            return set(value)


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
        if self.author == FilterAuthor.OWN:
            statement = statement.where(Ride.author_id == user.id) if user else statement.where(false())

        result = await session.execute(statement)
        averages = result.first()

        if not averages:
            return AverageRatings(overall=None, by_criteria={})
        averages_dict = averages._asdict()  # pyright: ignore [reportPrivateUsage]

        return AverageRatings.from_averages(averages_dict, criteria, self.excluded_criteria_slugs)
