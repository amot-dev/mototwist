from enum import Enum
from humanize import intcomma
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from sqlalchemy import Label, literal
from sqlalchemy.orm.attributes import InstrumentedAttribute
from typing import Annotated, ClassVar
from uuid import UUID

from app.models import Criterion, Twist, User
from app.schemas.types import Coordinate, Waypoint, Weather
from app.settings import settings


class TwistCreateForm(BaseModel):
    name: str = Field(..., max_length=Twist.NAME_MAX_LENGTH)
    is_paved: bool
    waypoints: list[Waypoint] = Field(..., min_length=2)
    route_geometry: list[Coordinate] = Field(..., min_length=2)


class FilterOwnership(str, Enum):
    ALL = "all"
    OWN = "own"
    NOT_OWN = "notown"


class FilterPavement(str, Enum):
    ALL = "all"
    PAVED = "paved"
    UNPAVED = "unpaved"


class FilterRide(str, Enum):
    ALL = "all"
    SUBMITTED = "submitted"
    UNSUBMITTED = "unsubmitted"


class FilterRatingRange(BaseModel):
    min: Annotated[float, Field(ge=Criterion.MIN_VALUE, le=Criterion.MAX_VALUE)] = Criterion.MIN_VALUE
    max: Annotated[float, Field(ge=Criterion.MIN_VALUE, le=Criterion.MAX_VALUE)] = Criterion.MAX_VALUE

    @property
    def is_active(self) -> bool:
        """
        True only if the range has been modified from the default min/max.
        """
        return self.min > Criterion.MIN_VALUE or self.max < Criterion.MAX_VALUE


class FilterWeather(BaseModel):
    temperature: Annotated[list[Weather.Temperature], Field()] = []
    light: Annotated[list[Weather.LightLevel], Field()] = []
    type: Annotated[list[Weather.Type], Field()] = []
    precipitation: Annotated[list[Weather.Intensity], Field()] = []
    wind: Annotated[list[Weather.Intensity], Field()] = []
    fog: Annotated[list[Weather.Intensity], Field()] = []


    @model_validator(mode="before")
    @classmethod
    def ensure_lists(cls, data: dict[str, object]) -> dict[str, object]:
        """
        Ensure that all input values are lists (even if just one item).
        """
        for key, value in data.items():
            if key in cls.model_fields and not isinstance(value, list):
                # Coerce single values into a list
                data[key] = [value]
        return data


class TwistFilter(BaseModel):
    # Display
    page: Annotated[int, Field(gt=0)] = 1
    pages: Annotated[int, Field(gt=0)] = 1

    # Basic Filtering
    search: Annotated[str | None, Field()] = None
    ownership: Annotated[FilterOwnership, Field()] = FilterOwnership.ALL
    pavement: Annotated[FilterPavement, Field()] = FilterPavement.ALL
    rides: Annotated[FilterRide, Field()] = FilterRide.ALL

    # Range Filtering
    overall_rating_range: Annotated[FilterRatingRange, Field()] = FilterRatingRange()
    individual_rating_ranges: Annotated[dict[str, FilterRatingRange], Field()] = {}

    @property
    def active_individual_rating_ranges(self) -> dict[str, FilterRatingRange]:
        """
        Return only the individual rating ranges that are currently active.
        """
        return {
            slug: rating_range
            for slug, rating_range in self.individual_rating_ranges.items()
            if rating_range.is_active
        }

    # Criteria Exclusion
    excluded_criteria_slugs: Annotated[set[str], Field()] = set()

    # Weather Filtering
    weather: Annotated[FilterWeather, Field()] = FilterWeather()

    # Ordering
    map_center: Annotated[Coordinate | None, Field()] = None


    # Ensure excluded criteria slugs is a set
    @field_validator("excluded_criteria_slugs", mode="before")
    @classmethod
    def excluded_criteria_slugs_to_set(cls, value: str | list[str]) -> set[str]:
        if not isinstance(value, list):
            return {value}
        else:
            return set(value)


    @model_validator(mode="after")
    def normalize_map_center(self) -> TwistFilter:
        """
        Normalize map longitude from potentially "unwrapped" values (ex. 388) to the required [-180, 180] range.
        """
        if self.map_center is not None:
            self.map_center.lng = (self.map_center.lng + 180) % 360 - 180
        return self


class TwistFilterWithRideOwnership(TwistFilter):
    ride_ownership: Annotated[FilterOwnership, Field()] = FilterOwnership.ALL


class TwistBasic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fields: ClassVar = (Twist.id, Twist.name, Twist.is_paved)

    id: int
    name: str
    is_paved: bool


class TwistGeometry(TwistBasic):
    model_config = ConfigDict(from_attributes=True)

    fields: ClassVar = TwistBasic.fields + (Twist.waypoints, Twist.route_geometry)

    waypoints: list[Waypoint]
    route_geometry: list[Coordinate]


class TwistListItem(TwistBasic):
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def get_fields(cls, user: User | None) -> tuple[InstrumentedAttribute[int], InstrumentedAttribute[str], InstrumentedAttribute[bool], Label[bool]]:
        """
        Determine database fields needed to populate this model,
        including dynamic expressions based on the current user.

        :param user: Optional user viewing the Twist list.
        :return: A tuple of all database fields needed to populate this model.
        """
        if user:
            author_expression = (Twist.author_id == user.id)
        else:
            author_expression = literal(False)

        # Combine the parent's static fields with the new dynamic one
        return cls.fields + (
            author_expression.label("viewer_is_author"),
        )

    viewer_is_author: bool

    @field_validator("viewer_is_author", mode="before")
    @classmethod
    def set_default_viewer_is_author(cls, value: bool | None) -> bool:
        return value or False


class TwistPopup(TwistBasic):
    model_config = ConfigDict(from_attributes=True)

    fields: ClassVar = TwistBasic.fields + (Twist.author_id, User.name.label("author_name"), Twist.length_m)

    length_round_to: ClassVar = 2

    author_id: UUID | None
    author_name: str
    length_m: float

    @computed_field
    @property
    def length_str(self) -> str:
        # At 1005, jump to 1.01km (1004 would be 1.00 otherwise which is lame)
        if self.length_m < 1005:
            return f"{round(self.length_m, self.length_round_to)}m"
        else:
            return f"{intcomma(self.length_m/1000, self.length_round_to)}km"

    @field_validator("author_name", mode="before")
    @classmethod
    def set_default_author_name(cls, value: str | None) -> str:
        return value or settings.DELETED_USER_NAME
