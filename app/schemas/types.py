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
    class Intensity(str, Enum):
        NONE = "None"
        LIGHT = "Light"
        MEDIUM = "Medium"
        HEAVY = "Heavy"

        def __bool__(self) -> bool:
            # Returns False if the instance is NONE, True otherwise
            return self != self.NONE


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


    temperature: Temperature
    light: LightLevel
    type: Type
    precipitation: Intensity = Intensity.NONE
    wind: Intensity = Intensity.NONE
    fog: Intensity = Intensity.NONE


    @property
    def emoji(self) -> str:
        INTENSITY_MULTIPLIERS = {
            self.Intensity.NONE: 0,
            self.Intensity.LIGHT: 1,
            self.Intensity.MEDIUM: 2,
            self.Intensity.HEAVY: 3
        }

        LIGHT_LEVEL_EMOJIS = {
            self.LightLevel.DAY: "🏙",
            self.LightLevel.NIGHT: "🌃",
            self.LightLevel.TWILIGHT: "🌆"
        }

        TEMPERATURE_EMOJIS = {
            self.Temperature.FREEZING: "🥶",
            self.Temperature.COLD: "🧣",
            self.Temperature.NEUTRAL: "🌡️",
            self.Temperature.WARM: "😌",
            self.Temperature.HOT: "🥵"
        }

        TYPE_EMOJIS = {
            self.Type.SUNNY: "☀️",
            self.Type.CLOUDY: "☁️",
            self.Type.RAINY: "🌧️",
            self.Type.SNOWY: "❄️",
            self.Type.HAILING: "🧊"
        }

        SPACER = " " * 2

        # Temperature and light
        emojis = [
            TEMPERATURE_EMOJIS.get(self.temperature, ""),
            LIGHT_LEVEL_EMOJIS.get(self.light, "")
        ]

        # Precipitation intensity
        if self.precipitation:
            emojis.append(SPACER)
            emojis.append(TYPE_EMOJIS.get(self.type, "") * INTENSITY_MULTIPLIERS[self.precipitation])
        else:
            emojis.append(TYPE_EMOJIS.get(self.type, ""))

        # Wind intensity
        if self.wind:
            emojis.append(SPACER)
            emojis.append("💨" * INTENSITY_MULTIPLIERS[self.wind])

        # Fog intensity
        if self.fog:
            emojis.append(SPACER)
            emojis.append("🌫️" * INTENSITY_MULTIPLIERS[self.fog])

        return "".join(emojis)


    def __str__(self) -> str:
        name = f"{self.temperature.value} {self.type.value} {self.light.value}."
        name += f" {self.precipitation.value} precipitation." if self.precipitation else ""
        name += f" {self.wind.value} wind." if self.wind else ""
        name += f" {self.fog.value} fog." if self.fog else ""
        return name.rstrip(".")


class Waypoint(Coordinate):
    name: str
