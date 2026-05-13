from json import JSONDecodeError, load
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.core.config import logger
from app.components.core.models import Criterion


CRITERIA_FILE_PATH = "/config/criteria.json"


async def initialize_criteria(session: AsyncSession) -> bool:
    """
    Populate the database with rating criteria from a JSON file.

    :param session: The database session for criteria creation.
    :return: True if criteria were initialized or pre-exising, False if criteria could not be initialized.
    """
    # Check if the table is already seeded
    result = await session.execute(
        select(func.count()).select_from(Criterion)
    )
    criteria_count = result.scalar_one()

    if criteria_count > 0:
        return True

    # Ensure the criteria file actually exists
    if not Path(CRITERIA_FILE_PATH).exists():
        logger.error(f"Initialization failed: Criteria file not found at {CRITERIA_FILE_PATH}")
        return False

    # Load and parse the JSON
    try:
        with open(CRITERIA_FILE_PATH, "r") as f:
            data = load(f)

        # Unpack the dicts directly into the Criterion model
        criteria = [Criterion(**item) for item in data]

        session.add_all(criteria)
        await session.commit()

        logger.info(f"Rating criteria populated from {CRITERIA_FILE_PATH} and table locked")
        return True

    except JSONDecodeError as e:
        logger.error(f"Failed to parse criteria JSON: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during criteria initialization: {e}")
        await session.rollback()
        return False
