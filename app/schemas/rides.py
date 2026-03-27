from datetime import date
from pydantic import BaseModel


class AverageRating(BaseModel):
    rating: float
    description: str


class RideListItem(BaseModel):
    id: int
    author_name: str
    can_delete: bool
    formatted_date: str

    ratings: dict[str, int]


class RideList(BaseModel):
    items: list[RideListItem]
    criteria_descriptions: dict[str, str]


class TwistRideForm(BaseModel):
    date: date
    ratings: dict[str, int]
