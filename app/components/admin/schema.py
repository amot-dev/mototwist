from pydantic import BaseModel, Field

from app.components.core.models import User


class UserCreateFormAdmin(BaseModel):
    name: str = Field(..., max_length=User.NAME_MAX_LENGTH)
    email: str = Field(..., max_length=User.EMAIL_MAX_LENGTH)
    is_superuser: bool = False
