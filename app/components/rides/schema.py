from datetime import date
from pydantic import BaseModel

from app.components.core.models import Criterion
from app.components.core.schema import Weather
from app.components.core.settings import settings


class AverageRating(BaseModel):
    rating: float
    description: str


class AverageRatings(BaseModel):
    overall: float | None
    by_criteria: dict[str, AverageRating]

    @classmethod
    def from_averages(cls, averages: dict[str, float | None], criteria: list[Criterion]) -> AverageRatings:
        # Create a lookup dictionary for descriptions for easy access
        descriptions = {c.slug: c.description for c in criteria}

        # List valid ratings to use to calculate overall average
        valid_ratings = [v for v in averages.values() if v is not None]

        overall = round(
            sum(valid_ratings) / len(valid_ratings),
            settings.AVERAGE_ROUNDING_DIGITS
        ) if valid_ratings else None

        by_criteria = {
            slug: AverageRating(
                rating=round(rating, settings.AVERAGE_ROUNDING_DIGITS),
                description=descriptions.get(slug) or ""
            )
            for slug, rating in averages.items()
            if rating is not None
        }

        return cls(overall=overall, by_criteria=by_criteria)


class RideListItem(BaseModel):
    id: int
    author_name: str
    editable: bool

    formatted_date: str
    weather: Weather
    ratings: dict[str, int]


class RideList(BaseModel):
    items: list[RideListItem]
    criteria_descriptions: dict[str, str]


class TwistRideData(BaseModel):
    date: date
    weather: Weather
    ratings: dict[str, int]
