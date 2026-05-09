from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.core.config import logger
from app.components.core.models import Criterion


async def initialize_criteria(session: AsyncSession) -> bool:
    """
    Populate the database with the default suite of rating criteria.

    :param session: The database session for criteria creation.
    :return: True if criteria were initialized, False if data already exists.
    """
    result = await session.execute(
        select(func.count()).select_from(Criterion)
    )
    criteria_count = result.scalar_one()
    if criteria_count == 0:
        criteria = [
            # Shared Criteria
            Criterion(
                slug="seclusion",
                description="Infrequency of other vehicles on the road",
                for_paved=True,
                for_unpaved=True,
            ),
            Criterion(
                slug="scenery",
                description="Visual appeal of surroundings",
                for_paved=True,
                for_unpaved=True,
            ),

            # Paved Criteria
            Criterion(
                slug="pavement",
                description="Quality of road surface",
                for_paved=True,
                for_unpaved=False,
            ),
            Criterion(
                slug="twistyness",
                description="Tightness and frequency of turns",
                for_paved=True,
                for_unpaved=False,
            ),
            Criterion(
                slug="intensity",
                description="Overall riding energy the road draws out",
                for_paved=True,
                for_unpaved=False,
            ),

            # Unpaved Criteria
            Criterion(
                slug="surface_consistency",
                description="Predictability of traction across the route",
                for_paved=False,
                for_unpaved=True,
            ),
            Criterion(
                slug="technicality",
                description="Challenge level from terrain features like rocks, ruts, sand, or mud",
                for_paved=False,
                for_unpaved=True,
            ),
            Criterion(
                slug="flow",
                description="Smoothness of the trail without constant disruptions or awkward sections",
                for_paved=False,
                for_unpaved=True,
            ),
        ]

        session.add_all(criteria)
        await session.commit()

        logger.info(f"Rating criteria populated and table locked")
        return True
    else:
        return False
