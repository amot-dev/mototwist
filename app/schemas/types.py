from dataclasses import dataclass
from enum import Enum

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


@dataclass
class Weather:
    temperature: Temperature
    light: LightLevel
    type: Type
    precipitation: Intensity
    wind: Intensity
    fog: Intensity

    class Intensity(str, Enum):
        NONE = "None"
        LIGHT = "Light"
        MEDIUM = "Medium"
        HEAVY = "Heavy"

    class LightLevel(str, Enum):
        DAY = "Day"
        NIGHT = "Night"
        TWILIGHT = "Twilight"


    class Temperature(str, Enum):
        FREEZING = "Freezing"
        COLD = "Cold"
        NEUTRAL = "Neutral"
        WARM = "Warm"
        HOT = "Hot"


    class Type(str, Enum):
        SUNNY = "Sunny"
        CLOUDY = "Cloudy"
        RAINY = "Rainy"
        SNOWY = "Snowy"
        HAILING = "Hailing"


    HAS_NO_PRECIPITATION = [
        Type.SUNNY,
        Type.CLOUDY
    ]


class Waypoint(Coordinate):
    name: str
