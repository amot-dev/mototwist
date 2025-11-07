from enum import Enum
from pydantic import BaseModel


class AuthStatus(str, Enum):
    RENEWED = "authRenewed"
    CLEARED = "authCleared"


class ResetPasswordForm(BaseModel):
    token: str
    password: str
    password_confirmation: str