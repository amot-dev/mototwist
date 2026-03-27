from datetime import date
from typing import Annotated
from fastapi import Form, Request
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

    # TODO: docs annotations for criteria fields
    @classmethod
    async def as_form(
        cls,
        request: Request,
        date: Annotated[date, Form()]
    ) -> TwistRideForm:
        """
        Parse incoming ride form data into a form model.

        Group all non-date fields (criteria) into ratings.

        :param request: The HTTP request containing the form body.
        :param date: The specific date field extracted from the form.
        :return: A complete TwistRideForm instance.
        """
        form_data = await request.form()

        # Scoop up all non-date fields into the ratings dictionary
        ratings = {
            key: value for key, value in form_data.items()
            if key != "date"
        }

        # Instantiate and return the model
        return cls.model_validate({
            "date": date,
            "ratings": ratings
        })
