from asyncio import gather
from collections import Counter
from datetime import date, timedelta
from gzip import compress, decompress
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from io import BytesIO
from json import dumps, loads
from random import choice, choices, randint, sample
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from app.components.core.database import get_db
from app.components.core.models import Criterion, Ride, Twist, User
from app.components.core.schema import Coordinate, Waypoint
from app.components.core.settings import settings
from app.components.core.utility import raise_http
from app.components.debug.schema import SeedRidesForm
from app.components.debug.services import generate_weights, reset_id_sequences_for, seed_twist_rides
from app.components.users.services import current_admin, verify


router = APIRouter(
    prefix="/debug",
    tags=["Debug"]
)


@router.get("/save", response_class=StreamingResponse)
async def save_state(
    request: Request,
    admin: User = Depends(verify(current_admin)),
    session: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """
    Save the entire database state to a single JSON file for download.
    """

    # Fetch all data from the database in parallel
    results = await gather(
        session.execute(select(User)),
        session.execute(select(Twist)),
        session.execute(select(Ride))
    )

    # Serialize the data using SerializationMixin methods
    db_state = {
        "users": [user.to_dict() for user in results[0].scalars().all()],
        "twists": [twist.to_dict() for twist in results[1].scalars().all()],
        "rides": [ride.to_dict() for ride in results[2].scalars().all()]
    }

    # Convert the Python dictionary to a JSON string
    json_data = dumps(jsonable_encoder(db_state)).encode("utf-8")

    # Compress the json
    compressed_bytes = compress(json_data)

    # Create a file-like object in memory to stream the response
    file_stream = BytesIO(compressed_bytes)

    return StreamingResponse(
        content=file_stream,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=\"mototwist_debug_db.json.gz\""
        }
    )


@router.post("/load", response_class=Response)
async def load_state(
    request: Request,
    json_file: UploadFile = File(...),
    admin: User = Depends(verify(current_admin)),
    session: AsyncSession = Depends(get_db)
) -> Response:
    """
    Wipes the current database state and loads a new state from an uploaded JSON file.
    """
    try:
        contents = await json_file.read()

        # Decompress if it's a gzip file, otherwise treat as raw JSON
        if json_file.filename and json_file.filename.endswith('.gz'):
            contents = decompress(contents)

        data = loads(contents)
    except Exception as e:
        raise_http("Invalid JSON", status_code=422, exception=e)

    # Read data
    users_data = data.get("users", [])
    twists_data = data.get("twists", [])
    rides_data = data.get("rides", [])

    if not (users_data or twists_data or rides_data):
        raise_http("No data to load", status_code=422)

    # Create model instances
    try:
        users_to_create = [User(**user) for user in users_data]
    except Exception as e:
        raise_http("Failed to parse users from JSON", status_code=422, exception=e)
    try:
        twists_to_create = [
            Twist(
                id=t.get("id"),
                name=t.get("name"),
                author_id=t.get("author_id"),
                is_paved=t.get("is_paved"),
                waypoints=[Waypoint.model_validate(wp) for wp in t.get("waypoints", [])],
                route_geometry=[Coordinate.model_validate(c) for c in t.get("route_geometry", [])],
                simplification_tolerance_m=t.get("simplification_tolerance_m"),
                rides=t.get("rides", [])
            ) for t in twists_data
        ]
    except Exception as e:
        raise_http("Failed to parse Twists from JSON", status_code=422, exception=e)
    try:
        rides_to_create = [Ride(**ride) for ride in rides_data]
    except Exception as e:
        raise_http("Failed to parse rides from JSON", status_code=422, exception=e)

    # Removing Twists cascade deletes all rides
    await session.execute(delete(Twist))
    await session.execute(delete(User))

    # Add all new objects to the session for insertion
    session.add_all(users_to_create)
    session.add_all(twists_to_create)
    session.add_all(rides_to_create)

    # Commit so the database has the new updated data
    await session.commit()

    # Reset id sequences
    await reset_id_sequences_for(session, [Twist, Ride])

    request.session["flash"] = "Data loaded!"
    return Response(headers={"HX-Redirect": "/"})


@router.post("/seed-rides", response_class=Response)
async def seed_rides(
    request: Request,
    seed_data: Annotated[SeedRidesForm, Form()],
    admin: User = Depends(verify(current_admin)),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """
    Seed the database with procedurally generated ride data for debugging.

    This endpoint will:
    1. Delete all existing Ride objects.
    2. Fetch all Twists and users.
    3. Exclude one random active, non-superuser from being an author.
    4. Designate one Twist as "popular" and seed it with a specific number of rides.
    5. Distribute the remaining rides across other Twists using a normal
       distribution to ensure some Twists remain unrated.
    6. Randomize ride dates to create realistic data patterns.
    """
    # Clear all existing rides for a clean slate
    await session.execute(delete(Ride))
    await session.commit()
    await reset_id_sequences_for(session, [Ride])

    # Fetch Twists and users from the database
    twists_result = await session.scalars(select(Twist))
    all_twists = twists_result.all()

    users_result = await session.scalars(select(User))
    all_users = users_result.all()

    # Validate that we have enough data to proceed
    if len(all_twists) < 21:
        raise_http("At least 21 total Twists are required", 422)
    if len(all_users) < 4:
        raise_http("At least 4 total users are required", 422)

    # Identify a pool of "regular" users (active, non-superuser) from which to select one to exclude from submitting rides
    regular_users_to_exclude_from = [
        user for user in all_users if user.is_active and not user.is_superuser
    ]
    if len(regular_users_to_exclude_from) < 2:
        raise_http("At least 2 active, non-superusers are required", 422)

    # Exclude a user
    user_to_exclude = choice(regular_users_to_exclude_from)
    authors = [user for user in all_users if user.id != user_to_exclude.id]

    # Determine the different Twist pools
    all_twists_pool = list(all_twists)

    popular_twist = next((twist for twist in all_twists_pool if twist.name == seed_data.popular_twist_name), None)
    if not popular_twist:
        raise_http(f"Popular Twist '{seed_data.popular_twist_name}' not found", 422)
    all_twists_pool.remove(popular_twist)

    gem_twists: list[Twist] = []
    if seed_data.hidden_gem_names:
        gem_names = [name.strip() for name in seed_data.hidden_gem_names.split(",")]
        for gem_name in gem_names:
            # Look for a match
            found_twist = next((twist for twist in all_twists_pool if twist.name == gem_name), None)
            if not found_twist:
                raise_http(f"Hidden Gem Twist '{gem_name}' not found", 422)

            gem_twists.append(found_twist)
            all_twists_pool.remove(found_twist)

    trending_count = min(seed_data.trending_twist_count, len(all_twists_pool))
    trending_twists = sample(all_twists_pool, trending_count) if trending_count > 0 else []

    general_twists = [twist for twist in all_twists_pool if twist not in trending_twists]

    # Date Pools & Dynamic Thresholds
    start_date = date.today() - timedelta(days=730)
    standard_date_pool = [start_date + timedelta(days=randint(0, 730)) for _ in range(500)] # ~2 years ago
    recent_date_pool = [date.today() - timedelta(days=randint(0, settings.TRENDING_TIMEFRAME_DAYS)) for _ in range(50)]
    gem_min_bias = Criterion.MAX_VALUE - ((Criterion.MAX_VALUE - Criterion.MIN_VALUE) * 0.05) # Top 5% scores

    average_rides_per_twist = seed_data.ride_count // max(1, len(all_twists))
    hidden_gem_ride_target = max(3, int(average_rides_per_twist * 0.05)) # Hidden Gem Twists get roughly 5% of the average
    trending_ride_target = max(12, int(average_rides_per_twist * 2)) # Trending Twists get roughly 150% of the average (boosted by recency too)

    # Seed each pool
    new_rides: list[Ride] = []

    if gem_twists:
        # +/- 50% variance, minimum 1
        gem_counts = {
            twist: randint(max(1, int(hidden_gem_ride_target * 0.5)), int(hidden_gem_ride_target * 1.5))
            for twist in gem_twists
        }
        new_rides.extend(await seed_twist_rides(
            session, gem_counts, authors, standard_date_pool,
            outlier_chance=0.0, min_bias=gem_min_bias, max_bias=Criterion.MAX_VALUE
        ))

    if trending_twists:
        # +/- 20% variance
        trending_counts = {
            twist: randint(int(trending_ride_target * 0.8), int(trending_ride_target * 1.2))
            for twist in trending_twists
        }
        new_rides.extend(await seed_twist_rides(
            session, trending_counts, authors, recent_date_pool, outlier_chance=0.05
        ))

    if popular_twist:
        new_rides.extend(await seed_twist_rides(
            session, {popular_twist: seed_data.popular_twist_ride_count}, authors, standard_date_pool
        ))

    if seed_data.ride_count > 0 and general_twists:
        # Generate a list of weights to make twists in the center of the list more likely to be chosen
        # This is a poor man's numpy normal distribution
        twist_weights = generate_weights(
            num_items=len(general_twists),
            focus=seed_data.distribution_focus
        )

        # Select all the twists at once based on the generated weights
        general_counts = Counter(choices(
            population=general_twists,
            weights=twist_weights,
            k=seed_data.ride_count
        ))
        new_rides.extend(await seed_twist_rides(session, general_counts, authors, standard_date_pool))

    # Add all generated rides to the session and commit
    session.add_all(new_rides)
    await session.commit()

    request.session["flash"] = f"Database seeded with {len(new_rides)} new rides!"
    return Response(headers={"HX-Redirect": "/"})

