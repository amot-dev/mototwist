from fastapi.templating import Jinja2Templates
import logging.config
from typing import Any

from app.events import EventKey
from app.settings import settings


# Configure logging
LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(level_custom)-10s %(asctime)s %(name_custom)-20s %(message)s",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": settings.LOG_LEVEL,
        "handlers": ["default"],
    },
}
logging.config.dictConfig(LOGGING_CONFIG)

# Prettify records for formatter
old_factory = logging.getLogRecordFactory()
def record_factory(*args: Any, **kwargs: Any):
    record = old_factory(*args, **kwargs)
    record.level_custom = f"[{record.levelname}]"
    record.name_custom = f"({record.name}):"
    return record
logging.setLogRecordFactory(record_factory)

# Set app logger
logger = logging.getLogger("mototwist")


# Configure templates
templates = Jinja2Templates(directory="templates")
templates.env.globals["EVENTS"] = { key.name: key.value for key in EventKey }  # type: ignore[reportUnknownVariableType]
templates.env.globals["SETTINGS"] = settings.model_dump()  # type: ignore[reportUnknownVariableType]


# Configure documentation tag order
tags_metadata = [
    {
        "name": "Index",
        "description": "Main entry points.",
    },
    {
        "name": "Administration",
        "description": "Endpoints for administrative utilities.",
    },
    {
        "name": "Authentication",
        "description": "Endpoints for user login, registration, and token management.",
    },
    {
        "name": "Debug",
        "description": "Endpoints for debug utilities.",
    },
    {
        "name": "Ratings",
        "description": "Endpoints for Twist rating management.",
    },
    {
        "name": "Twists",
        "description": "Endpoints for Twist management.",
    },
    {
        "name": "Users",
        "description": "Endpoints for user account management.",
    },
    {
        "name": "Templates",
        "description": "Endpoints that serve HTML templates.",
    },
]