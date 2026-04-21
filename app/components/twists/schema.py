from humanize import intcomma
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from sqlalchemy import Label, literal
from sqlalchemy.orm.attributes import InstrumentedAttribute
from typing import ClassVar
from uuid import UUID

from app.components.core.models import Twist, User
from app.components.core.schema import Coordinate, Waypoint
from app.components.core.settings import settings


class TwistCreateForm(BaseModel):
    name: str = Field(..., max_length=Twist.NAME_MAX_LENGTH)
    description: str
    is_paved: bool
    waypoints: list[Waypoint] = Field(..., min_length=2)
    route_geometry: list[Coordinate] = Field(..., min_length=2)


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

    fields: ClassVar = TwistBasic.fields + (Twist.author_id, User.name.label("author_name"), Twist.length_m, Twist.description)

    length_round_to: ClassVar = 2

    author_id: UUID | None
    author_name: str
    length_m: float
    description: str

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
