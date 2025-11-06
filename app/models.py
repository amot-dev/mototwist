from datetime import date
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from geoalchemy2 import Geometry, WKBElement
from geoalchemy2.shape import from_shape, to_shape  # type: ignore[reportUnknownVariableType]
from pydantic import BaseModel
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from sqlalchemy import Boolean, Date, ForeignKey, Integer, SmallInteger, String, inspect, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator
from typing import Any, Type
from uuid import UUID

from app.schemas.types import Coordinate, Waypoint


Base = declarative_base()


class SerializationMixin:
    """Provides a `to_dict` method to SQLAlchemy models."""
    def to_dict(self) -> dict[str, Any]:
        """
        Converts the model instance into a dictionary,
        serializing special types like UUID and date.
        """
        inspection_object = inspect(type(self))
        assert inspection_object != None

        columns = [c.name for c in inspection_object.columns]

        data: dict[str, Any] = {}
        for column in columns:
            value = getattr(self, column)

            # Handle special Python types
            if isinstance(value, UUID):
                data[column] = str(value)
            elif isinstance(value, date):
                data[column] = value.isoformat()
            else:
                data[column] = value

        return data


class PydanticJSONB(TypeDecorator[list[BaseModel]]):
    """
    Store a list[BaseModel] as JSONB.

    Usage:
        waypoints: Mapped[list[Waypoint]] = mapped_column(PydanticJson(Waypoint))
    """
    impl = JSONB
    cache_ok = True

    def __init__(self, pydantic_type: Type[BaseModel], *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.pydantic_type = pydantic_type

    def process_bind_param(self, value: list[BaseModel] | None, dialect: Any) -> list[dict[Any, Any]] | None:
        """
        Called when sending data TO the database.
        Converts a list of Pydantic models to a list of dicts.
        """
        if value is None:
            return None
        return [item.model_dump(mode='json') for item in value]

    def process_result_value(self, value: list[dict[Any, Any]] | None, dialect: Any) -> list[BaseModel] | None:
        """
        Called when receiving data FROM the database.
        Converts a list of dicts back to a list of Pydantic models.
        """
        if value is None:
            return None
        return [self.pydantic_type.model_validate(item) for item in value]


class PostGISLine(TypeDecorator[list[Coordinate]]):
    """
    Stores a list[Coordinate] as a native PostGIS LINESTRING.

    Usage:
        waypoints: Mapped[list[Coordinate]] = mapped_column(PostGISLine(Coordinate))
    """
    impl = Geometry(geometry_type='LINESTRING', srid=Coordinate.SRID)
    cache_ok = True

    def process_bind_param(self, value: list[Coordinate] | None, dialect: Any) -> WKBElement | None:
        """
        Called when sending data TO the database.
        Converts a list[Coordinate] to a WKT LINESTRING.
        """
        # A Linestring requires at least 2 points
        # If value is None, empty, or has only 1 point, store NULL
        if value is None or len(value) < 2:
            return None

        # Shapely uses lng, lat
        line = LineString([(c.lng, c.lat) for c in value])
        return from_shape(line, srid=Coordinate.SRID)

    def process_result_value(self, value: Any | None, dialect: Any) -> list[Coordinate] | None:
        """
        Called when receiving data FROM the database.
        Converts a WKBElement (binary geometry) back to a list[Coordinate].
        """
        if value is None:
            return None

        shape: BaseGeometry = to_shape(value)

        if not isinstance(shape, LineString):
            # This should ideally never happen if the column type is correct
            raise TypeError(f"Expected a LineString from database, but got {type(shape)}")

        # Convert shapely's (lng, lat) tuples back to Pydantic models
        return [Coordinate(lat=lat, lng=lng) for lng, lat in shape.coords]

    def column_expression(self, column: Any) -> Any:
        """
        Intercept the column when used in a SELECT statement.

        This wraps the raw column (col) in type_coerce(col, self), which forces SQLAlchemy to run 'process_result_value'
        on the result. Not sure why it doesn't run that automatically, like it does with PydanticJSONB.
        """
        return type_coerce(column, self)


class User(SQLAlchemyBaseUserTableUUID, SerializationMixin, Base):
    __tablename__ = "users"

    # Constraints
    NAME_MAX_LENGTH = 255
    EMAIL_MAX_LENGTH = 320  # Hardcoded in SQLAlchemyBaseUserTable

    # Data
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)

    # Children
    twists: Mapped[list["Twist"]] = relationship("Twist", back_populates="author")
    paved_ratings: Mapped[list["PavedRating"]] = relationship("PavedRating", back_populates="author")
    unpaved_ratings: Mapped[list["UnpavedRating"]] = relationship("UnpavedRating", back_populates="author")

    def __repr__(self):
        return f"[{self.id}] {self.email}"


class Twist(SerializationMixin, Base):
    __tablename__ = "twists"

    # Constraints
    NAME_MAX_LENGTH = 255

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Parents
    author_id: Mapped[UUID | None] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author: Mapped[User | None] = relationship("User", back_populates="twists")

    # Data
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), index=True, nullable=False)
    is_paved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    waypoints: Mapped[list[Waypoint]] = mapped_column(PydanticJSONB(Waypoint), nullable=False)
    route_geometry: Mapped[list[Coordinate]] = mapped_column(PostGISLine(Coordinate), nullable=False)  # Geometry object automatically creates an index
    simplification_tolerance_m: Mapped[int] = mapped_column(SmallInteger)

    # Children
    paved_ratings: Mapped[list["PavedRating"]] = relationship("PavedRating", back_populates="twist", cascade="all, delete-orphan")
    unpaved_ratings: Mapped[list["UnpavedRating"]] = relationship("UnpavedRating", back_populates="twist", cascade="all, delete-orphan")

    def __repr__(self):
        paved = "Paved" if self.is_paved else "Unpaved"
        return f"[{self.id}] {self.name} ({paved})"


class Rating:
    CRITERION_MIN_VALUE = 0
    CRITERION_MAX_VALUE = 10


class PavedRating(SerializationMixin, Base, Rating):
    __tablename__ = "paved_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Parents
    author_id: Mapped[UUID | None] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author: Mapped[User | None] = relationship("User", back_populates="paved_ratings")

    twist_id: Mapped[int] = mapped_column(Integer, ForeignKey("twists.id", ondelete="CASCADE"))
    twist: Mapped[Twist] = relationship("Twist", back_populates="paved_ratings")

    # Metadata
    rating_date: Mapped[date] = mapped_column(Date, default=date.today)

    # Data
    traffic: Mapped[int] = mapped_column(SmallInteger, doc="Level of vehicle traffic on the road")
    scenery: Mapped[int] = mapped_column(SmallInteger, doc="Visual appeal of surroundings")
    pavement: Mapped[int] = mapped_column(SmallInteger, doc="Quality of road surface")
    twistyness: Mapped[int] = mapped_column(SmallInteger, doc="Tightness and frequency of turns")
    intensity: Mapped[int] = mapped_column(SmallInteger, doc="Overall riding energy the road draws out, from mellow to adrenaline-pumping")

    def __repr__(self):
        return f"[{self.id}] (Paved)"


class UnpavedRating(SerializationMixin, Base, Rating):
    __tablename__ = "unpaved_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Parents
    author_id: Mapped[UUID | None] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author: Mapped[User | None] = relationship("User", back_populates="unpaved_ratings")

    twist_id: Mapped[int] = mapped_column(Integer, ForeignKey("twists.id", ondelete="CASCADE"))
    twist: Mapped[Twist] = relationship("Twist", back_populates="unpaved_ratings")

    # Metadata
    rating_date: Mapped[date] = mapped_column(Date, default=date.today)

    # Data
    traffic: Mapped[int] = mapped_column(SmallInteger, doc="Frequency of other vehicles or trail users")
    scenery: Mapped[int] = mapped_column(SmallInteger, doc="Visual appeal of surroundings")
    surface_consistency: Mapped[int] = mapped_column(SmallInteger, doc="Predictability of traction across the route")
    technicality: Mapped[int] = mapped_column(SmallInteger, doc="Challenge level from terrain features like rocks, ruts, sand, or mud")
    flow: Mapped[int] = mapped_column(SmallInteger, doc="Smoothness of the trail without constant disruptions or awkward sections")

    def __repr__(self):
        return f"[{self.id}] (Unpaved)"