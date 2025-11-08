from asyncio import gather
from datetime import date, timedelta
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from io import BytesIO
import json
from random import choice, choices, randint
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped
from typing import Annotated, cast
from uuid import UUID

from app.config import templates
from app.database import get_db
from app.models import PavedRating, Twist, UnpavedRating, User
from app.schemas.debug import SeedRatingsForm
from app.schemas.types import Coordinate, Waypoint
from app.services.debug import create_random_rating, generate_weights, reset_id_sequences_for
from app.users import current_active_user_optional, current_admin_user
from app.utility import raise_http


router = APIRouter(
    prefix="/debug",
    tags=["Debug"]
)


@router.get("", tags=["Index", "Templates"], response_class=HTMLResponse)
async def render_debug_page(
    request: Request,
    admin: User = Depends(current_admin_user),
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
    paved_rating_count_query = select(func.count(PavedRating.id))
    unpaved_rating_count_query = select(func.count(UnpavedRating.id))

    # Execute all queries concurrently for better performance
    results = await gather(
        session.execute(user_count_query),
        session.execute(admin_count_query),
        session.execute(inactive_count_query),
        session.execute(twist_count_query),
        session.execute(paved_rating_count_query),
        session.execute(unpaved_rating_count_query)
    )

    # Extract the scalar value from each result
    user_count = results[0].scalar_one()
    admin_count = results[1].scalar_one()
    inactive_count = results[2].scalar_one()
    twist_count = results[3].scalar_one()
    rating_count = results[4].scalar_one()

    return templates.TemplateResponse("debug.html", {
        "request": request,
        "user_count": user_count,
        "admin_count": admin_count,
        "inactive_count": inactive_count,
        "twist_count": twist_count,
        "rating_count": rating_count
    })


@router.post("/save", response_class=StreamingResponse)
async def save_state(
    request: Request,
    admin: User = Depends(current_admin_user),
    session: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """
    Save the entire database state to a single JSON file for download.
    """

    # Fetch all data from the database in parallel
    results = await gather(
        session.execute(select(User)),
        session.execute(select(Twist)),
        session.execute(select(PavedRating)),
        session.execute(select(UnpavedRating))
    )

    # Serialize the data using SerializationMixin methods
    db_state = {
        "users": [user.to_dict() for user in results[0].scalars().all()],
        "twists": [twist.to_dict() for twist in results[1].scalars().all()],
        "paved_ratings": [paved_rating.to_dict() for paved_rating in results[2].scalars().all()],
        "unpaved_ratings": [unpaved_rating.to_dict() for unpaved_rating in results[3].scalars().all()],
    }

    # Convert the Python dictionary to a JSON string
    json_data = json.dumps(db_state, indent=2)

    # Create a file-like object in memory to stream the response
    json_stream = BytesIO(json_data.encode("utf-8"))

    return StreamingResponse(
        content=json_stream,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=\"mototwist_debug_db.json\""
        }
    )


@router.post("/load", response_class=Response)
async def load_state(
    request: Request,
    json_file: UploadFile = File(...),
    admin: User = Depends(current_admin_user),
    session: AsyncSession = Depends(get_db)
) -> Response:
    """
    Wipes the current database state and loads a new state from an uploaded JSON file.
    """
    try:
        contents = await json_file.read()
        data = json.loads(contents)
    except Exception as e:
        raise_http("Invalid JSON", status_code=422, exception=e)
    
    # Read data
    users_data = data.get("users", [])
    twists_data = data.get("twists", [])
    paved_ratings_data = data.get("paved_ratings", [])
    unpaved_ratings_data = data.get("unpaved_ratings", [])

    if not (users_data or twists_data or paved_ratings_data or unpaved_ratings_data):
        raise_http("No data to load", status_code=422)

    # Create model instances
    try:
        users_to_create = [User(**user) for user in users_data]
    except Exception as e:
        raise_http("Failed to parse users from JSON", status_code=422, exception=e)
    try:
        twists_to_create = [
            Twist(**{
                **twist,
                "waypoints": [Waypoint.model_validate(wp) for wp in twist.get("waypoints", [])],
                "route_geometry": [Coordinate.model_validate(coord) for coord in twist.get("route_geometry", [])]
            }) for twist in twists_data
        ]
    except Exception as e:
        raise_http("Failed to parse Twists from JSON", status_code=422, exception=e)
    try:
        paved_ratings_to_create = [PavedRating(**rating) for rating in paved_ratings_data]
    except Exception as e:
        raise_http("Failed to parse users from JSON", status_code=422, exception=e)
    try:
        unpaved_ratings_to_create = [UnpavedRating(**rating) for rating in unpaved_ratings_data]
    except Exception as e:
        raise_http("Failed to parse users from JSON", status_code=422, exception=e)

    # Removing Twists cascade deletes all ratings
    await session.execute(delete(Twist))
    await session.execute(delete(User))

    # Add all new objects to the session for insertion
    session.add_all(users_to_create)
    session.add_all(twists_to_create)
    session.add_all(paved_ratings_to_create)
    session.add_all(unpaved_ratings_to_create)

    # Commit so the database has the new updated data
    await session.commit()

    # Reset id sequences
    await reset_id_sequences_for(session, [Twist, PavedRating, UnpavedRating])

    request.session["flash"] = "Data loaded!"
    return Response(headers={"HX-Redirect": "/"})


@router.post("/seed-ratings", response_class=Response)
async def seed_ratings(
    request: Request,
    seed_data: Annotated[SeedRatingsForm, Form()],
    admin: User = Depends(current_admin_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """
    Seed the database with procedurally generated rating data for debugging.

    This endpoint will:
    1. Delete all existing PavedRating and UnpavedRating records.
    2. Fetch all twists and users.
    3. Exclude one random active, non-superuser from being a rater.
    4. Designate one twist as "popular" and seed it with a specific number of ratings.
    5. Distribute the remaining ratings across other twists using a normal
       distribution to ensure some twists remain unrated.
    6. Randomize rating dates to create realistic data patterns.
    """
    # Clear all existing ratings for a clean slate
    await session.execute(delete(PavedRating))
    await session.execute(delete(UnpavedRating))
    await session.commit()
    await reset_id_sequences_for(session, [PavedRating, UnpavedRating])

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

    # Identify a pool of "regular" users (active, non-superuser) from which to select one to exclude from rating
    regular_users_to_exclude_from = [
        user for user in all_users if user.is_active and not user.is_superuser
    ]
    if len(regular_users_to_exclude_from) < 2:
        raise_http("At least 2 active, non-superusers are required", 422)

    # Exclude a user
    user_to_exclude = choice(regular_users_to_exclude_from)
    raters = [user for user in all_users if user.id != user_to_exclude.id]

    # Isolate the popular twist from the general pool
    popular_twist = next((twist for twist in all_twists if twist.name == seed_data.popular_twist_name), None)
    if not popular_twist:
        raise_http(f"Twist '{seed_data.popular_twist_name}' not found", 422)
    general_twists = [twist for twist in all_twists if twist.id != popular_twist.id]

    # Generate a smaller pool of random dates to encourage date collisions
    start_date = date.today() - timedelta(days=730)  # ~2 years ago
    total_ratings = seed_data.rating_count + seed_data.popular_rating_count
    date_pool = [
        start_date + timedelta(days=randint(0, 730))
        for _ in range(total_ratings // 2)  # Create a pool half the size of ratings
    ]
    if not date_pool: date_pool.append(date.today())  # Ensure pool is not empty

    ratings_to_add: list[PavedRating | UnpavedRating] = []

    # Seed the "popular" twist
    for _ in range(seed_data.popular_rating_count):
        rating = create_random_rating(
            twist=popular_twist,
            author=choice(raters),
            rating_date=choice(date_pool),
        )
        ratings_to_add.append(rating)

    # Distribute the general ratings using weighted random choices
    if seed_data.rating_count > 0 and general_twists:
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
            k=seed_data.rating_count
        )

        # For each Twist (Twists may appear in chosen_twists multiple times), create a rating
        for twist in chosen_twists:
            rating = create_random_rating(
                twist=twist,
                author=choice(raters),
                rating_date=choice(date_pool),
            )
            ratings_to_add.append(rating)

    # Add all generated ratings to the session and commit
    session.add_all(ratings_to_add)
    await session.commit()

    request.session["flash"] = f"Database seeded with {len(ratings_to_add)} new ratings!"
    return Response(headers={"HX-Redirect": "/"})


@router.get("/templates/menu-button", tags=["Templates"], response_class=HTMLResponse)
async def serve_menu_button(
    request: Request,
    user: User = Depends(current_active_user_optional),
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the debug menu button.
    """
    return templates.TemplateResponse("fragments/debug/menu_button.html", {
        "request": request,
        "user": user
    })