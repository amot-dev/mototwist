from copy import deepcopy
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from geoalchemy2 import Geometry
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from sqlalchemy import and_, false, or_, select, type_coerce
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnExpressionArgument
from typing import Any

from app.config import logger
from app.models import Rating, PavedRating, Twist, UnpavedRating, User
from app.schemas.twists import (
    FilterOwnership, FilterPavement, FilterRatings,
    TwistBasic, TwistDropdown, TwistFilterParameters, TwistListItem, TwistUltraBasic
)
from app.schemas.types import Coordinate, Waypoint
from app.services.ratings import calculate_average_rating
from app.settings import settings
from app.utility import raise_http


def snap_waypoints_to_route(waypoints: list[Waypoint], route_geometry: list[Coordinate]) -> list[Waypoint]:
    """
    Map a list of Waypoints to a route track of Coordinates.
    - The first waypoint is mapped to the first trackpoint.
    - The last waypoint is mapped to the last trackpoint.
    - Intermediate waypoints are mapped to their nearest trackpoint.

    :param waypoints: The list of Waypoints to snap to the route.
    :param route_geometry: The list of Coordinates making up the route to snap to.
    :return: A new list of modified Waypoints.
    """
    if not route_geometry or not waypoints or len(waypoints) < 2:
        return waypoints

    # Create a deep copy to avoid modifying the original list
    snapped_waypoints = deepcopy(waypoints)
    line = LineString([(coord.lat, coord.lng) for coord in route_geometry])

    # Handle the first waypoint
    first_coord = line.coords[0]
    snapped_waypoints[0].lat = first_coord[0]
    snapped_waypoints[0].lng = first_coord[1]

    # Handle the last waypoint
    last_coord = line.coords[-1]
    snapped_waypoints[-1].lat = last_coord[0]
    snapped_waypoints[-1].lng = last_coord[1]

    # Handle intermediate waypoints
    if len(snapped_waypoints) > 2:
        for i in range(1, len(snapped_waypoints) - 1):
            waypoint = snapped_waypoints[i]
            point = Point(waypoint.lat, waypoint.lng)

            # Find the nearest point on the line to the waypoint's location
            snapped_point = nearest_points(line, point)[0]

            # Update the waypoint's coordinates
            waypoint.lat = snapped_point.x
            waypoint.lng = snapped_point.y

    return snapped_waypoints



def simplify_route(coordinates: list[Coordinate]) -> list[Coordinate]:
    """
    Simplify a route's coordinates based off the `TWIST_SIMPLIFICATION_TOLERANCE_M` setting. Reduces storage space for database.

    :param coordinates: The list of Coordinates to simplify.
    :return: A new list of simplified Coordinates.
    """
    # Approximation for 1 degree of latitude in meters
    METERS_PER_DEGREE_APPROX = 111132

    # Only simplify if more than 2 points
    if len(coordinates) < 2:
        return coordinates

    logger.info(f"Simplifying Twist route with tolerance of {settings.TWIST_SIMPLIFICATION_TOLERANCE_M}m")
    epsilon = settings.TWIST_SIMPLIFICATION_TOLERANCE_M / METERS_PER_DEGREE_APPROX

    # Simplify route
    line = LineString([(c.lat, c.lng) for c in coordinates])
    simplified_line = line.simplify(epsilon, preserve_topology=True)
    simplified_coordinates = [Coordinate(lat=x, lng=y) for x, y in simplified_line.coords]

    return simplified_coordinates


templates = Jinja2Templates(directory="templates")


async def render_creation_buttons(
    request: Request,
    user: User | None,
) -> HTMLResponse:
    """
     Build and return the TemplateResponse for the Twist creation buttons.
    """
    return templates.TemplateResponse("fragments/twists/creation_buttons.html", {
        "request": request,
        "user": user
    })


async def render_list(
    request: Request,
    session: AsyncSession,
    user: User | None,
    filter: TwistFilterParameters
) -> HTMLResponse:
    """
     Build and return the TemplateResponse for the Twist list.
    """
    # Filtering
    statement = select(*TwistListItem.get_fields(user))

    if filter.search:
        statement = statement.where(Twist.name.icontains(filter.search))

    if filter.ownership == FilterOwnership.OWN:
        statement = statement.where(Twist.author_id == user.id) if user else statement.where(false())
    elif user and filter.ownership == FilterOwnership.NOT_OWN:
        statement = statement.where(Twist.author_id != user.id)

    if filter.pavement == FilterPavement.PAVED:
        statement = statement.where(Twist.is_paved == True)
    elif filter.pavement == FilterPavement.UNPAVED:
        statement = statement.where(Twist.is_paved == False)

    if user and filter.ratings != FilterRatings.ALL:
        paved_rating_exists = select(PavedRating.id).where(
            PavedRating.twist_id == Twist.id,
            PavedRating.author_id == user.id
        ).exists()
        unpaved_rating_exists = select(UnpavedRating.id).where(
            UnpavedRating.twist_id == Twist.id,
            UnpavedRating.author_id == user.id
        ).exists()

        if filter.ratings == FilterRatings.RATED:
            # Either exists
            statement = statement.where(or_(paved_rating_exists, unpaved_rating_exists))

        elif filter.ratings == FilterRatings.UNRATED:
            # Neither exists
            statement = statement.where(and_(~paved_rating_exists, ~unpaved_rating_exists))

    elif not user and filter.ratings == FilterRatings.RATED:
        # If user is not logged in, they can't have rated Twists
        statement = statement.where(false())

    # Pagination
    page = filter.page
    offset = (page - 1) * settings.DEFAULT_TWISTS_PER_PAGE

    # Ordering
    order_criteria: list[ColumnExpressionArgument[Any]] = []

    if filter.map_center:
        distance: ColumnExpressionArgument[float] = Twist.route_geometry.distance_centroid(
            type_coerce(filter.map_center.to_spatial(), Geometry)
        )
        order_criteria.append(distance)

    order_criteria.append(Twist.name)

    # Querying
    results = await session.execute(
        statement.order_by(*order_criteria).limit(filter.pages * settings.DEFAULT_TWISTS_PER_PAGE).offset(offset)
    )
    twists = [TwistListItem.model_validate(result) for result in results.all()]

    # Prepare open Twist dropdown if needed
    open_twist_id = None
    dropdown_context = None
    if filter.open_id:
        # Check that the open Twist is still in the Twist list
        if any(twist.id == filter.open_id for twist in twists):
            result = await session.execute(
                select(*TwistDropdown.fields)
                .join(Twist.author, isouter=True)
                .where(Twist.id == filter.open_id)
            )
            twist = result.one_or_none()
            if twist:
                twist_dropdown = TwistDropdown.model_validate(twist)
                dropdown_context = await _build_twist_dropdown_context(session, user, twist_dropdown)
                open_twist_id = twist_dropdown.id

    # Build the base context
    list_context: dict[str, Any] = {
        "request": request,
        "twists": twists,
        "open_twist_id": open_twist_id,
        "start_page": filter.page,
        "next_page": filter.page + filter.pages,
        "twists_per_page": settings.DEFAULT_TWISTS_PER_PAGE
    }

    # If the dropdown context was generated, merge it into the main context
    if dropdown_context:
        list_context.update(dropdown_context)

    return templates.TemplateResponse("fragments/twists/list.html", list_context)


async def render_single_list_item(
    request: Request,
    session: AsyncSession,
    user: User,
    twist_id: int,
) -> HTMLResponse:
    """
     Build and return the TemplateResponse for the Twist list, for a single Twist.
    """
    try:
        result = await session.execute(
            select(*TwistListItem.get_fields(user)).where(Twist.id == twist_id)
        )
        twist_list_item = TwistListItem.model_validate(result.one())
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple Twists found for id '{twist_id}'", status_code=500)

    return templates.TemplateResponse("fragments/twists/list.html", {
        "request": request,
        "twists": [twist_list_item],
        "start_page": 1,
        "twists_per_page": 1
    })


async def _build_twist_dropdown_context(
    session: AsyncSession,
    user: User | None,
    twist: TwistDropdown
) -> dict[str, Any]:
    """
    Build and return the template context for the Twist dropdown.
    """
    # Check if the user is allowed to delete the Twist
    can_delete_twist = (user.is_superuser or user.id == twist.author_id) if user else False

    twist_basic = TwistUltraBasic.model_validate(twist)

    return {
        "user": user,
        "twist_id": twist.id,
        "twist_author_name": twist.author_name,
        "can_delete_twist": can_delete_twist,
        "average_rating_criteria": await calculate_average_rating(session, user, twist_basic, "all", round_to=1),
        "criterion_max_value": Rating.CRITERION_MAX_VALUE
    }


async def render_twist_dropdown(
    request: Request,
    session: AsyncSession,
    user: User | None,
    twist: TwistDropdown,
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the Twist dropdown.
    """
    context = await _build_twist_dropdown_context(session, user, twist)
    context["request"] = request

    return templates.TemplateResponse("fragments/twists/dropdown.html", context)


async def render_delete_modal(
    request: Request,
    twist: TwistBasic
) -> HTMLResponse:
    """
     Build and return the TemplateResponse for the Twist delete modal.
    """
    return templates.TemplateResponse("fragments/twists/delete_modal.html", {
        "request": request,
        "twist": twist
    })