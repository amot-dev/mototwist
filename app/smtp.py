from email.mime.text import MIMEText
from smtplib import SMTP

from app.settings import settings
from app.utility import raise_http


class SMTPEmailTransport:
    """
    A custom email transport using Python's built-in smtplib.
    """

    @staticmethod
    async def send_mail(to_email: str, subject: str, content: str):
        msg = MIMEText(content, "html")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email

        # Use smtplib to connect and send (this should be a coroutine 'async def')
        # A simple, sync smtplib implementation is shown here, but you should
        # wrap this in a thread or use an async library like aiosmtplib in production.
        try:
            with SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())
        except Exception as e:
            raise_http(f"Error sending email to {to_email}", exception=e)