from pydantic import BaseModel, Field

from app.components.core.models import Twist


class SeedRidesForm(BaseModel):
    ride_count: int = Field(..., gt=0)
    popular_twist_name: str = Field(..., max_length=Twist.NAME_MAX_LENGTH)
    popular_twist_ride_count: int = Field(..., gt=0)
    trending_twist_count: int = Field(default=3, ge=0)
    hidden_gem_names: str = Field(default="")
    distribution_focus: float = Field(default=2.0, gt=1.0)
