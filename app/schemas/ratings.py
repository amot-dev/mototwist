from datetime import date
from sqlalchemy import inspect
from sqlalchemy.orm import Mapper
from pydantic import BaseModel, Field, create_model, model_validator
from typing import Any, Self, cast

from app.models import Rating, PavedRating, UnpavedRating


class AverageRating(BaseModel):
    rating: float
    desc: str


class RatingCriterion(BaseModel):
    name: str
    desc: str | None


class RatingListItem(BaseModel):
    id: int
    author_name: str
    can_delete_rating: bool
    formatted_date: str

    criteria: dict[str, int]


class RatingList(BaseModel):
    items: list[RatingListItem]
    criteria_descriptions: dict[str, str]


# Criteria columns
RATING_EXCLUDED_COLUMNS = {"id", "author_id", "twist_id", "ride_date"}
RATING_CRITERIA_PAVED: list[RatingCriterion] = [
    RatingCriterion(name=col.name, desc=col.doc)
    for col in cast(Mapper[PavedRating], inspect(PavedRating)).columns
    if col.name not in RATING_EXCLUDED_COLUMNS
]
RATING_CRITERIA_UNPAVED: list[RatingCriterion] = [
    RatingCriterion(name=col.name, desc=col.doc)
    for col in cast(Mapper[UnpavedRating], inspect(UnpavedRating)).columns
    if col.name not in RATING_EXCLUDED_COLUMNS
]

# Use with care as these are sets, and thus unordered!
CRITERIA_NAMES_PAVED = {criteria.name for criteria in RATING_CRITERIA_PAVED}
CRITERIA_NAMES_UNPAVED = {criteria.name for criteria in RATING_CRITERIA_UNPAVED}
CRITERIA_NAMES_ALL = CRITERIA_NAMES_PAVED.union(CRITERIA_NAMES_UNPAVED)


class TwistRateForm(BaseModel):
    ride_date: date

    @model_validator(mode="after")
    def validate_criteria_fields(self) -> Self:
        """
        Validate that exactly one complete set of criteria (Paved or Unpaved)
        is provided. If a set is complete, fields outside that set must be None.
        """

        # Determine which criteria were rated
        provided_criteria_names = {
            name for name in CRITERIA_NAMES_ALL if getattr(self, name) is not None
        }
        only_paved_complete = (provided_criteria_names == CRITERIA_NAMES_PAVED)
        only_unpaved_complete = (provided_criteria_names == CRITERIA_NAMES_UNPAVED)

        # Check that we have exactly one complete set (impossible for both to be true)
        if only_paved_complete or only_unpaved_complete:
            return self

        raise ValueError("Rating must have only Paved or Unpaved criteria")


# Inject criteria name fields into TwistRateForm (type checkers will not see these fields, but they exist)
TwistRateForm = create_model(
    "TwistRateForm",
    __base__=TwistRateForm,
    **cast(dict[str, Any], {
        name: (int | None, Field(None, ge=Rating.CRITERION_MIN_VALUE, le=Rating.CRITERION_MAX_VALUE))
        for name in CRITERIA_NAMES_ALL
    })
)