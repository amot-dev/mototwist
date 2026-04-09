from copy import deepcopy
from fastapi import Request
from fastapi.responses import HTMLResponse
from geoalchemy2 import Geometry
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from sqlalchemy import ColumnElement, Numeric, and_, case, cast, false, func, literal, select, type_coerce
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnExpressionArgument
from typing import Any

from app.config import logger, templates
from app.models import Criterion, Ride, Twist, User
from app.schemas.twists import (
    FilterOwnership, FilterPavement, FilterRide,
    TwistBasic, TwistPopup, TwistFilter, TwistListItem
)
from app.schemas.types import Coordinate, Waypoint, Weather
from app.services.rides import weather_conditions_from
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


async def render_advanced_filter_modal(
    request: Request,
    criteria: list[Criterion]
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the advanced filter modal.
    """
    return templates.TemplateResponse("fragments/twists/advanced_filter_modal.html", {
        "request": request,
        "criteria": criteria,
        "Weather": Weather
    })


async def render_list(
    request: Request,
    session: AsyncSession,
    user: User | None,
    filter: TwistFilter
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

    # User-submitted Ride Filtering
    if user and filter.rides != FilterRide.ALL:
        ride_exists = select(Ride.id).where(
            Ride.twist_id == Twist.id,
            Ride.author_id == user.id
        ).exists()

        if filter.rides == FilterRide.SUBMITTED:
            statement = statement.where(ride_exists)

        elif filter.rides == FilterRide.UNSUBMITTED:
            statement = statement.where(~ride_exists)

    elif not user and filter.rides == FilterRide.SUBMITTED:
        # If user is not logged in, they can't have Twists with submitted rides
        statement = statement.where(false())

    # Ride Rating Range Filtering
    has_overall_filter = filter.overall_rating_range.is_active
    active_individual_filters = filter.active_individual_rating_ranges
    if has_overall_filter or active_individual_filters:
        having_conditions: list[ColumnElement[bool]] = []

        # Calculate overall average and add it to the conditions
        if has_overall_filter:
            # List is important here to maintain ordering (I... think?)
            paved_criteria_slugs = [
                c.slug for c in await Criterion.get_list(session, is_paved=True)
                if c.slug not in filter.excluded_criteria_slugs
            ]
            unpaved_criteria_slugs = [
                c.slug for c in await Criterion.get_list(session, is_paved=False)
                if c.slug not in filter.excluded_criteria_slugs
            ]

            # Dynamically build the average calculations
            def build_rounded_avg_expression(slugs: list[str]):
                if not slugs:
                    return literal(0.0)

                avg = sum(
                    (func.avg(Ride.ratings[slug].as_integer()) for slug in slugs),
                    start=literal(0.0)
                ) / len(slugs)

                # Round same as UI before comparing to avoid user confusion
                return func.round(cast(avg, Numeric), settings.AVERAGE_ROUNDING_DIGITS)
            paved_avg_rounded = build_rounded_avg_expression(paved_criteria_slugs)
            unpaved_avg_rounded = build_rounded_avg_expression(unpaved_criteria_slugs)

            # Update the having clause
            having_conditions.append(
                case(
                    (Twist.is_paved, paved_avg_rounded),
                    else_=unpaved_avg_rounded
                ).between(
                    filter.overall_rating_range.min,
                    filter.overall_rating_range.max
                )
            )

        # Calculate individual averages and add each to the conditions
        for slug, rating_range in active_individual_filters.items():
            # Calculate average
            condition_avg = func.avg(Ride.ratings[slug].as_integer())

            # Round same as UI before comparing to avoid user confusion
            condition_avg_rounded = func.round(cast(condition_avg, Numeric), settings.AVERAGE_ROUNDING_DIGITS)

            # Update the having clause
            having_conditions.append(
                condition_avg_rounded.between(rating_range.min, rating_range.max)
            )

        # Create the subquery
        rating_subquery = (
            select(Twist.id)
            .outerjoin(Ride, Twist.id == Ride.twist_id)
            .group_by(Twist.id)
            .having(and_(*having_conditions))
        )

        statement = statement.where(Twist.id.in_(rating_subquery))

    # Weather Filtering
    weather_conditions = weather_conditions_from(filter.weather)
    if weather_conditions:
        weather_subquery = (
            select(Ride.id)
            .where(
                Ride.twist_id == Twist.id,
                *weather_conditions
            ).exists()
        )
        statement = statement.where(weather_subquery)

    # Pagination
    page = filter.page
    offset = (page - 1) * settings.DEFAULT_TWISTS_LOADED

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
        statement.order_by(*order_criteria).limit(filter.pages * settings.DEFAULT_TWISTS_LOADED).offset(offset)
    )
    twists = [TwistListItem.model_validate(result) for result in results.all()]

    return templates.TemplateResponse("fragments/twists/list.html", {
        "request": request,
        "twists": twists,
        "start_page": filter.page,
        "next_page": filter.page + filter.pages,
        "twists_per_page": settings.DEFAULT_TWISTS_LOADED
    })


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


async def render_twist_popup(
    request: Request,
    user: User | None,
    twist: TwistPopup,
) -> HTMLResponse:
    """
    Build and return the TemplateResponse for the Twist popup.
    """
    # Check if the user is allowed to delete the Twist
    can_delete_twist = (user.is_superuser or user.id == twist.author_id) if user else False

    return templates.TemplateResponse("fragments/twists/popup.html", {
        "request": request,
        "user": user,
        "twist": twist,
        "can_delete_twist": can_delete_twist,
        "FilterOwnership": FilterOwnership
    })


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
