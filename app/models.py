from datetime import date
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from geoalchemy2 import Geometry, WKBElement
from geoalchemy2.shape import from_shape, to_shape  # type: ignore[reportUnknownVariableType]
from pydantic import BaseModel
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Sequence, SmallInteger, String, inspect, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, composite, mapped_column, relationship
from sqlalchemy.types import TypeDecorator
from typing import Any, Type
from uuid import UUID

from app.schemas.types import Coordinate, Waypoint, Weather

class Base(DeclarativeBase):
    pass


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
    rides: Mapped[list["Ride"]] = relationship("Ride", back_populates="author")


    def __repr__(self):
        return f"[{self.id}] {self.email}"


class Twist(SerializationMixin, Base):
    __tablename__ = "twists"

    # Constraints
    NAME_MAX_LENGTH = 255

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    # Parents
    author_id: Mapped[UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    author: Mapped[User | None] = relationship(
        "User",
        back_populates="twists"
    )

    # Data
    name: Mapped[str] = mapped_column(
        String(NAME_MAX_LENGTH), index=True, nullable=False
    )
    is_paved: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    waypoints: Mapped[list[Waypoint]] = mapped_column(
        PydanticJSONB(Waypoint), nullable=False
    )
    route_geometry: Mapped[list[Coordinate]] = mapped_column(
        PostGISLine(Coordinate), nullable=False
    )  # Geometry object automatically creates an index
    simplification_tolerance_m: Mapped[int] = mapped_column(
        SmallInteger, nullable=False
    )

    # Children
    rides: Mapped[list["Ride"]] = relationship(
        "Ride",
        back_populates="twist",
        cascade="all, delete-orphan"
    )


    def __repr__(self):
        paved = "Paved" if self.is_paved else "Unpaved"
        return f"[{self.id}] {self.name} ({paved})"


class Ride(SerializationMixin, Base):
    __tablename__ = "rides"

    WEATHER_TEMPERATURE_ENUM = Enum(Weather.Temperature, name="weather_temperature")
    WEATHER_LIGHT_LEVEL_ENUM = Enum(Weather.LightLevel, name="weather_light_level")
    WEATHER_TYPE_ENUM = Enum(Weather.Type, name="weather_type")
    WEATHER_INTENSITY_ENUM = Enum(Weather.Intensity, name="weather_intensity")

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    # Parents
    author_id: Mapped[UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    author: Mapped[User | None] = relationship(
        "User",
        back_populates="rides"
    )

    twist_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("twists.id", ondelete="CASCADE"),
        nullable=False
    )
    twist: Mapped[Twist] = relationship(
        "Twist",
        back_populates="rides"
    )

    # Data
    date: Mapped[date] = mapped_column(
        Date, nullable=False
    )
    ratings: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False
    )
    weather: Mapped[Weather] = composite(
        mapped_column("weather_temperature", WEATHER_TEMPERATURE_ENUM, nullable=False),
        mapped_column("weather_light", WEATHER_LIGHT_LEVEL_ENUM, nullable=False),
        mapped_column("weather_type", WEATHER_TYPE_ENUM, nullable=False),
        mapped_column("weather_precipitation", WEATHER_INTENSITY_ENUM, nullable=False),
        mapped_column("weather_wind", WEATHER_INTENSITY_ENUM, nullable=False),
        mapped_column("weather_fog", WEATHER_INTENSITY_ENUM, nullable=False)
    )


    def __repr__(self):
        return f"[{self.twist_id}.{self.id}]"


class Criterion(SerializationMixin, Base):
    __tablename__ = "criteria"

    MIN_VALUE = 0
    MAX_VALUE = 10

    slug: Mapped[str] = mapped_column(
        String(100), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        Sequence("criteria_sort_order_seq"),
        server_default=Sequence("criteria_sort_order_seq").next_value()
    )

    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    for_paved: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    for_unpaved: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )


    @classmethod
    async def get_list(cls, session: AsyncSession, is_paved: bool | None = None) -> list[Criterion]:
        """
        Retrieve a sorted list of criteria filtered by pavement type.

        :param session: The database session for the query.
        :param is_paved: Filter for paved (True), unpaved (False), or all (None) criteria.
        :return: A list of Criterion objects.
        """
        if is_paved is None:
            filter = cls.for_paved or cls.for_unpaved
        else:
            filter = cls.for_paved if is_paved else cls.for_unpaved

        result = await session.scalars(
            select(cls).where(filter == True).order_by(cls.sort_order)
        )
        return list(result.all())


    @classmethod
    async def get_set(cls, session: AsyncSession, is_paved: bool | None = None) -> set[str]:
        """
        Retrieve a set of unique criteria slugs filtered by pavement type.

        :param session: The database session for the query.
        :param is_paved: Filter for paved (True), unpaved (False), or all (None) criteria.
        :return: A set of strings containing the criteria slugs.
        """
        if is_paved is None:
            filter = cls.for_paved or cls.for_unpaved
        else:
            filter = cls.for_paved if is_paved else cls.for_unpaved

        result = await session.scalars(
            select(cls.slug).where(filter == True)
        )
        return set(result.all())


    def __repr__(self):
        return f"[{self.slug}]"
