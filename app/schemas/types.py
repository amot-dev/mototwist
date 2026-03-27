from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import from_shape  # type: ignore[reportUnknownVariableType]
from pydantic import BaseModel, Field
from shapely.geometry import Point
from typing import ClassVar


class Coordinate(BaseModel):
    SRID: ClassVar = 4326  # Standard Spatial Reference Identifier for GPS Coordinates

    lat: float = Field(..., ge=-90, le=90)  # Latitude must be between -90 and 90
    lng: float = Field(..., ge=-180, le=180)  # Longitude must be between -180 and 180

    def to_spatial(self) -> WKBElement:
        """
        Convert this coordinate to a GeoAlchemy2-compatible spatial element.
        """
        # Shapely uses lng, lat
        return from_shape(Point(self.lng, self.lat), srid=self.SRID)


class Waypoint(Coordinate):
    name: str
