from datetime import date
from typing import Annotated
from fastapi import Form, Request
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


class TwistRideForm(BaseModel):
    date: date
    weather: Weather
    ratings: dict[str, int]

    # TODO: docs annotations for non-date fields
    @classmethod
    async def as_form(
        cls,
        request: Request,
        date: Annotated[date, Form()]
    ) -> TwistRideForm:
        """
        Parse incoming ride form data into a form model.

        Group all "criterion_" fields into ratings.
        Group all "weather_" fields into weather.

        :param request: The HTTP request containing the form body.
        :param date: The specific date field extracted from the form.
        :return: A complete TwistRideForm instance.
        """
        form_data = await request.form()

        weather: dict[str, str] = {
            "precipitation": Weather.Intensity.NONE
        }
        ratings: dict[str, int] = {}

        for key, value in form_data.items():
            # Guarantee to the type checker that values are strings
            if not isinstance(value, str):
                continue

            if key.startswith("criterion_"):
                slug = key.replace("criterion_", "", 1)
                ratings[slug] = int(value)

            elif key.startswith("weather_"):
                prop = key.replace("weather_", "", 1)
                weather[prop] = value

        return cls.model_validate({
            "date": date,
            "weather": weather,
            "ratings": ratings
        })
