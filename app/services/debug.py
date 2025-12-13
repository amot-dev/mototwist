from datetime import date
from random import randint
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Type

from app.models import PavedRating, Twist, UnpavedRating, User
from app.schemas.ratings import CRITERIA_NAMES_PAVED, CRITERIA_NAMES_UNPAVED


async def reset_id_sequences_for(
    session: AsyncSession,
    models: list[Type[Twist | PavedRating | UnpavedRating]]
) -> None:
    """
    Reset the primary key ID sequences for a list of SQLAlchemy models.

    :param session: The session to use for database transactions.
    :param models: A list of the models for which to reset the ID sequences.
    """
    # For each model that uses an integer sequence for its primary key, we need to set it to the proper next value manually
    for model in models:
        table_name = model.__tablename__
        # Set the value of the serial sequence for the table to the next available
        # If the table has values, it's MAX(id)+1
        # If the table is empty, it's 1
        query = text(f"""
            SELECT setval(
                pg_get_serial_sequence(:table_name, 'id'),
                COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                (MAX(id) IS NOT NULL)
            ) FROM {table_name};
        """)
        await session.execute(query, {"table_name": table_name})
    await session.commit()


def create_random_rating(
    twist: Twist,
    author: User,
    ride_date: date
) -> PavedRating | UnpavedRating:
    """
    Create a rating object with randomly generated data.

    The type of rating object returned (PavedRating or UnpavedRating)
    depends on the provided Twist's `is_paved` attribute.

    :param twist: The Twist object for which to create a rating.
    :param author: The user who is the author of the rating.
    :param ride_date: The date to assign to the rating.
    :return: A new PavedRating or UnpavedRating object with random rating values.
    """
    # Determine the correct Rating class and criteria list based on the twist's surface
    if twist.is_paved:
        Rating = PavedRating
        criteria_names = CRITERIA_NAMES_PAVED
    else:
        Rating = UnpavedRating
        criteria_names = CRITERIA_NAMES_UNPAVED

    # Build the dictionary for the new rating object, adding random ratings for each criterion
    rating_data: dict[str, User | Twist | date | int] = {name: randint(0, 10) for name in criteria_names}
    rating_data.update({
        "author": author,
        "twist": twist,
        "ride_date": ride_date
    })

    return Rating(**rating_data)


def generate_weights(num_items: int, focus: float) -> list[float]:
    """
    Generate a list of weights that form a 'peak' in the middle.

    A higher focus value creates a steeper peak, concentrating the weights
    around the center of the list.

    :param num_items: The number of weights to generate.
    :param focus: The exponent controlling the steepness of the weight distribution curve.
    :return: A list of float values representing the weights.
    """
    center = (num_items - 1) / 2
    weights: list[float] = []
    for i in range(num_items):
        distance_from_center = abs(i - center)
        # The weight is calculated to decrease as distance from the center grows
        # Raising to the power of 'focus' controls the curve's steepness
        weight = (center - distance_from_center) ** focus
        weights.append(weight)
    return weights