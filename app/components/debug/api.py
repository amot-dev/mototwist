from asyncio import gather
from collections import Counter
from datetime import date, timedelta
from gzip import compress, decompress
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from io import BytesIO
import json
from random import choice, choices, randint
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from typing import Annotated, cast
from uuid import UUID

from app.components.core.config import templates
from app.components.core.database import get_db
from app.components.core.models import Ride, Twist, User
from app.components.core.schema import Coordinate, Waypoint
from app.components.core.utility import raise_http
from app.components.debug.schema import SeedRidesForm
from app.components.debug.services import generate_weights, reset_id_sequences_for, seed_twist_rides
from app.components.users.services import current_user_optional, current_admin, verify


router = APIRouter(
    prefix="/debug",
    tags=["Debug"]
)


@router.get("", tags=["Index", "Templates"], response_class=HTMLResponse)
async def render_debug_page(
    request: Request,
    admin: User = Depends(verify(current_admin)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve the debug page with database statistics.
    """
    # Define the queries for each statistic
    user_count_query = select(func.count(
        cast(Mapped[UUID], User.id)
    ))

    admin_count_query = select(func.count(
        cast(Mapped[UUID], User.id)
    )).where(
        cast(Mapped[bool], User.is_superuser)
    )

    inactive_count_query = select(func.count(
        cast(Mapped[UUID], User.id)
    )).where(
        cast(Mapped[bool], User.is_active) == False
    )

    twist_count_query = select(func.count(Twist.id))
    ride_count_query = select(func.count(Ride.id))

    # Execute all queries concurrently for better performance
    results = await gather(
        session.execute(user_count_query),
        session.execute(admin_count_query),
        session.execute(inactive_count_query),
        session.execute(twist_count_query),
        session.execute(ride_count_query),
    )

    # Extract the scalar value from each result
    user_count = results[0].scalar_one()
    admin_count = results[1].scalar_one()
    inactive_count = results[2].scalar_one()
    twist_count = results[3].scalar_one()
    ride_count = results[4].scalar_one()

    return templates.TemplateResponse("debug.html", {
        "request": request,
        "user_count": user_count,
        "admin_count": admin_count,
        "inactive_count": inactive_count,
        "twist_count": twist_count,
        "ride_count": ride_count
    })


@router.post("/save", response_class=StreamingResponse)
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
    json_data = json.dumps(jsonable_encoder(db_state)).encode("utf-8")

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

        data = json.loads(contents)
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

    # Isolate the popular twist from the general pool
    popular_twist = next((twist for twist in all_twists if twist.name == seed_data.popular_twist_name), None)
    if not popular_twist:
        raise_http(f"Twist '{seed_data.popular_twist_name}' not found", 422)
    general_twists = [twist for twist in all_twists if twist.id != popular_twist.id]

    # Generate a smaller pool of random dates to encourage date collisions
    start_date = date.today() - timedelta(days=730)  # ~2 years ago
    total_rides = seed_data.ride_count + seed_data.popular_twist_ride_count
    date_pool = [
        start_date + timedelta(days=randint(0, 730))
        for _ in range(total_rides // 2)  # Create a pool half the size of rides
    ]
    if not date_pool: date_pool.append(date.today())  # Ensure pool is not empty

    twist_ride_counts: Counter[Twist] = Counter()

    # Set ride count for the "popular" Twist
    if seed_data.popular_twist_ride_count > 0:
        twist_ride_counts[popular_twist] += seed_data.popular_twist_ride_count

    # Set ride count for remaining Twists using weighted random choices
    if seed_data.ride_count > 0 and general_twists:
        # Generate a list of weights to make twists in the center of the list more likely to be chosen
        # This is a poor man's numpy normal distribution
        twist_weights = generate_weights(
            num_items=len(general_twists),
            focus=seed_data.distribution_focus
        )

        # Select all the twists at once based on the generated weights
        chosen_twists = choices(
            population=general_twists,
            weights=twist_weights,
            k=seed_data.ride_count
        )
        twist_ride_counts.update(chosen_twists)

    # Seed rides based off counts for each Twist
    new_rides = await seed_twist_rides(session, twist_ride_counts, authors, date_pool)

    # Add all generated rides to the session and commit
    session.add_all(new_rides)
    await session.commit()

    request.session["flash"] = f"Database seeded with {len(new_rides)} new rides!"
    return Response(headers={"HX-Redirect": "/"})


@router.get("/templates/menu-button", tags=["Templates"], response_class=HTMLResponse)
async def serve_menu_button(
    request: Request,
    user: User = Depends(current_user_optional),
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the debug menu button.
    """
    return templates.TemplateResponse("fragments/debug/menu_button.html", {
        "request": request,
        "user": user
    })
