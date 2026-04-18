from fastapi_users import schemas
from pydantic import BaseModel, Field
from uuid import UUID

from app.components.core.models import User

class UserRead(schemas.BaseUser[UUID]):
    name: str
    pass

class UserCreate(schemas.BaseUserCreate):
    name: str | None = None
    pass

class UserUpdate(schemas.BaseUserUpdate):
    name: str | None = None
    pass


class UserCreateForm(BaseModel):
    name: str = Field(..., max_length=User.NAME_MAX_LENGTH)
    email: str = Field(..., max_length=User.EMAIL_MAX_LENGTH)
    password: str
    password_confirmation: str


class UserUpdateForm(BaseModel):
    name: str = Field(..., max_length=User.NAME_MAX_LENGTH)
    email: str = Field(..., max_length=User.EMAIL_MAX_LENGTH)
    password: str | None = None
    password_confirmation: str | None = None
