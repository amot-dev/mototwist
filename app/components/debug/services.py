from datetime import date
from random import choice, choices, gauss, random, sample, uniform
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Type

from app.components.core.models import Criterion, Ride, Twist, User
from app.components.core.schema import Weather


async def reset_id_sequences_for(
    session: AsyncSession,
    models: list[Type[Twist | Ride ]]
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
    criteria_slugs: list[str],
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
    biases = {slug: target_bias for slug in criteria_slugs}

    # Shuffle points around a few times to create "personality"
    num_shuffles = len(criteria_slugs) * 4

    for _ in range(num_shuffles):
        # Pick two different criteria to trade points
        c1, c2 = sample(criteria_slugs, 2)

        # Calculate maximum trade amounts without breaking the min-max boundaries
        max_give_c1 = biases[c1] - Criterion.MIN_VALUE
        max_receive_c2 = Criterion.MAX_VALUE - biases[c2]
        max_transfer_1_to_2 = min(max_give_c1, max_receive_c2)

        max_give_c2 = biases[c2] - Criterion.MIN_VALUE
        max_receive_c1 = Criterion.MAX_VALUE - biases[c1]
        max_transfer_2_to_1 = min(max_give_c2, max_receive_c1)

        # Pick a random transfer amount
        # Negative means c2 gives to c1, positive means c1 gives to c2
        transfer = uniform(-max_transfer_2_to_1, max_transfer_1_to_2)

        biases[c1] -= transfer
        biases[c2] += transfer

    return biases


def create_random_weather() -> Weather:
    """
    Generate a randomized Weather object with logically consistent attributes.

    Enforces logical weather patterns (e.g., no precipitation when sunny,
    no hot snowstorms) while providing a varied spread of data for testing.
    Fog is weighted to be less frequent to mimic real-world distribution.

    :return: A logically consistent, randomized Weather instance.
    """
    # Choose a base weather type
    weather_type = choice(list(Weather.Type))

    # Determine precipitation based on type
    if weather_type in Weather.HAS_NO_PRECIPITATION:
        precipitation = Weather.Intensity.NONE
    else:
        # If it's rainy, snowy, or hailing, it must have some intensity > NONE
        precipitation = choice([
            Weather.Intensity.LIGHT,
            Weather.Intensity.MEDIUM,
            Weather.Intensity.HEAVY
        ])

    # Determine temperature based on precipitation type to prevent logical contradictions
    if weather_type == Weather.Type.SNOWY or weather_type == Weather.Type.HAILING:
        temperature = choice([Weather.Temperature.FREEZING, Weather.Temperature.COLD])
    elif weather_type == Weather.Type.RAINY:
        temperature = choice([
            Weather.Temperature.COLD,
            Weather.Temperature.NEUTRAL,
            Weather.Temperature.WARM,
            Weather.Temperature.HOT
        ])
    else:
        temperature = choice(list(Weather.Temperature))

    # Light and Wind can be evenly distributed
    light = choice(list(Weather.LightLevel))
    wind = choice(list(Weather.Intensity))

    # Fog is heavily weighted toward NONE or LIGHT for realistic distribution
    fog = choices(
        population=list(Weather.Intensity),
        weights=[60, 25, 10, 5], # 60% chance of None, 5% chance of Heavy
        k=1
    )[0]

    return Weather(
        temperature=temperature,
        light=light,
        type=weather_type,
        precipitation=precipitation,
        wind=wind,
        fog=fog
    )


def create_random_ride(
    twist: Twist,
    author: User,
    date: date,
    criteria_biases: dict[str, float],
    is_outlier: bool = False
) -> Ride:
    """
    Create a ride object with randomly generated data clustered around a target bias.

    If the ride rating is flagged as an outlier, the generated scores will actively oppose the target bias.

    :param twist: The Twist object for which to create a ride.
    :param author: The user who is the author of the ride.
    :param ride_date: The date to assign to the ride.
    :param criteria_biases: A dictionary mapping criteria slugs to their target mathematical means (biases).
    :param is_outlier: If True, forces the generated ride rating to the opposite end of the spectrum.
    :return: A new Ride object with random rating values.
    """
    ratings: dict[str, int] = {}

    for slug, bias in criteria_biases.items():
        # Invert bias for outliers
        if is_outlier:
            bias = (Criterion.MIN_VALUE + Criterion.MAX_VALUE) - bias

        # Calculate score using bias as mean
        raw_score = gauss(mu=bias, sigma=0.8)

        # Clamp score
        ratings[slug] = max(Criterion.MIN_VALUE, min(Criterion.MAX_VALUE, round(raw_score)))

    return Ride(
        author=author,
        twist=twist,
        date=date,
        weather=create_random_weather(),
        ratings=ratings
    )


async def seed_twist_rides(
    session: AsyncSession,
    twist_ride_counts: dict[Twist, int],
    authors: list[User],
    date_pool: list[date],
    outlier_chance: float = 0.1
) -> list[Ride]:
    """
    Take a dictionary mapping Twists to the number of rides they need.
    Generate rides clustered around a specific bias for each twist.

    :param session: The database session for criteria retrieval.
    :param twist_ride_counts: A dictionary mapping Twist objects to the desired number of generated rides.
    :param authors: A list of User objects from which to randomly select ride authors.
    :param date_pool: A list of date objects from which to randomly select the date for each ride.
    :param outlier_chance: The probability (between 0.0 and 1.0) that a generated ride will act as an outlier. Defaults to 0.1.
    :return: A list containing the newly generated ride objects.
    """
    new_rides: list[Ride] = []

    for twist, count in twist_ride_counts.items():
        # Determine the target average for the whole twist
        twist_bias = uniform(Criterion.MIN_VALUE, Criterion.MAX_VALUE)

        # Generate the specific road profile
        criteria_slugs = await Criterion.get_set(session, twist.is_paved)
        criteria_biases = generate_criteria_biases(
            criteria_slugs=list(criteria_slugs),
            target_bias=twist_bias
        )

        for _ in range(count):
            # Roll the dice to see if this ride rating is an outlier
            is_outlier = random() < outlier_chance

            new_rides.append(create_random_ride(
                twist=twist,
                author=choice(authors),
                date=choice(date_pool),
                criteria_biases=criteria_biases,
                is_outlier=is_outlier
            ))

    return new_rides
