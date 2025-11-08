from pydantic import BaseModel


class ForgotPasswordForm(BaseModel):
    email: str


class ResetPasswordForm(BaseModel):
    token: str
    password: str
    password_confirmation: str


class VerifyAccountForm(BaseModel):
    token: str