from datetime import date
from random import choice, gauss, random, sample, uniform
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Type

from app.models import PavedRating, Rating, Twist, UnpavedRating, User
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


def generate_criteria_biases(
    criteria_names: list[str],
    target_bias: float
) -> dict[str, float]:
    """
    Create a unique profile for a twist where individual criteria can be
    wildly different, but their mathematical mean perfectly matches the target_bias.

    :param criteria_names: A list of strings representing the names of the criteria to bias.
    :param target_bias: The target mathematical mean for the criteria biases.
    :return: A dictionary mapping each criterion name to its calculated bias float value.
    """
    # Start with a boring, flat profile
    biases = {name: target_bias for name in criteria_names}

    # Shuffle points around a few times to create "personality"
    num_shuffles = len(criteria_names) * 4

    for _ in range(num_shuffles):
        # Pick two different criteria to trade points
        c1, c2 = sample(criteria_names, 2)

        # Calculate maximum trade amounts without breaking the min-max boundaries
        max_give_c1 = biases[c1] - Rating.CRITERION_MIN_VALUE
        max_receive_c2 = Rating.CRITERION_MAX_VALUE - biases[c2]
        max_transfer_1_to_2 = min(max_give_c1, max_receive_c2)

        max_give_c2 = biases[c2] - Rating.CRITERION_MIN_VALUE
        max_receive_c1 = Rating.CRITERION_MAX_VALUE - biases[c1]
        max_transfer_2_to_1 = min(max_give_c2, max_receive_c1)

        # Pick a random transfer amount
        # Negative means c2 gives to c1, positive means c1 gives to c2
        transfer = uniform(-max_transfer_2_to_1, max_transfer_1_to_2)

        biases[c1] -= transfer
        biases[c2] += transfer

    return biases


def create_random_rating(
    twist: Twist,
    author: User,
    ride_date: date,
    criteria_biases: dict[str, float],
    is_outlier: bool = False
) -> PavedRating | UnpavedRating:
    """
    Create a rating object with randomly generated data clustered around a target bias.

    The type of rating object returned (PavedRating or UnpavedRating)
    depends on the provided Twist's `is_paved` attribute. If the rating is flagged 
    as an outlier, the generated scores will actively oppose the target bias.

    :param twist: The Twist object for which to create a rating.
    :param author: The user who is the author of the rating.
    :param ride_date: The date to assign to the rating.
    :param criteria_biases: A dictionary mapping rating criteria names to their target mathematical means (biases).
    :param is_outlier: If True, forces the generated rating to the opposite end of the spectrum.
    :return: A new PavedRating or UnpavedRating object with random rating values.
    """
    rating_data: dict[str, User | Twist | date | int] = {
        "author": author,
        "twist": twist,
        "ride_date": ride_date
    }

    for name, bias in criteria_biases.items():
        # Invert bias for outliers
        if is_outlier:
            bias = (Rating.CRITERION_MIN_VALUE + Rating.CRITERION_MAX_VALUE) - bias

        # Calculate score using bias as mean
        raw_score = gauss(mu=bias, sigma=0.8)

        # Clamp score
        rating_data[name] = max(Rating.CRITERION_MIN_VALUE, min(Rating.CRITERION_MAX_VALUE, round(raw_score)))

    return (PavedRating if twist.is_paved else UnpavedRating)(**rating_data)


def seed_twist_ratings(
    twist_rating_counts: dict[Twist, int],
    raters: list[User],
    date_pool: list[date],
    outlier_chance: float = 0.1
) -> list[PavedRating | UnpavedRating]:
    """
    Take a dictionary mapping Twists to the number of ratings they need.
    Generate ratings clustered around a specific bias for each twist.

    :param twist_rating_counts: A dictionary mapping Twist objects to the desired number of generated ratings.
    :param raters: A list of User objects from which to randomly select rating authors.
    :param date_pool: A list of date objects from which to randomly select the ride date for each rating.
    :param outlier_chance: The probability (between 0.0 and 1.0) that a generated rating will act as an outlier. Defaults to 0.1.
    :return: A list containing the newly generated PavedRating and UnpavedRating objects.
    """
    ratings_to_add: list[PavedRating | UnpavedRating] = []

    for twist, count in twist_rating_counts.items():
        # Determine the target average for the whole twist
        twist_bias = uniform(Rating.CRITERION_MIN_VALUE, Rating.CRITERION_MAX_VALUE)

        # Generate the specific road profile
        criteria_biases = generate_criteria_biases(
            criteria_names=list(CRITERIA_NAMES_PAVED if twist.is_paved else CRITERIA_NAMES_UNPAVED),
            target_bias=twist_bias
        )

        for _ in range(count):
            # Roll the dice to see if this rating is an outlier
            is_outlier = random() < outlier_chance

            rating = create_random_rating(
                twist=twist,
                author=choice(raters),
                ride_date=choice(date_pool),
                criteria_biases=criteria_biases,
                is_outlier=is_outlier
            )
            ratings_to_add.append(rating)

    return ratings_to_add
