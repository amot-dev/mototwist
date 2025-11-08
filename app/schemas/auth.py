from pydantic import BaseModel


class ResetPasswordForm(BaseModel):
    token: str
    password: str
    password_confirmation: str