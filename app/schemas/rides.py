from datetime import date
from fastapi import Request
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

    @classmethod
    async def as_form(cls, request: Request) -> TwistRideForm:
        """
        TODO
        """
        form_data = await request.form()

        # Extract the date
        date = form_data.get("date")

        # Scoop up all remaining fields into the ratings dictionary
        ratings = {
            key: value for key, value in form_data.items()
            if key != "date"
        }

        # Instantiate and return the model
        return cls.model_validate({
            "date": date,
            "ratings": ratings
        })
