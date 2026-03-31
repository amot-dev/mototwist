from datetime import date
from pydantic import BaseModel

from app.schemas.types import Weather


class AverageRating(BaseModel):
    rating: float
    description: str


class RideListItem(BaseModel):
    id: int
    author_name: str
    can_delete: bool

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
