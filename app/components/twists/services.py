from copy import deepcopy
from math import isqrt
from geoalchemy2 import Geometry
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from sqlalchemy import ColumnElement, Numeric, and_, case, cast, false, func, literal, or_, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnExpressionArgument
from typing import Any

from app.components.core.redis_client import redis_client
from app.components.core.config import logger
from app.components.core.models import Criterion, Ride, Twist, User
from app.components.twists.schema import FilterMap, FilterOwnership, FilterPavement, FilterRide, TwistFilter, TwistListItem
from app.components.core.schema import Coordinate, Waypoint
from app.components.rides.services import weather_conditions_from
from app.components.core.settings import settings


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


async def get_bayesian_constants(session: AsyncSession) -> tuple[float, float]:
    """
    Retrieve or recalculate the Bayesian constants m and c for Twist filtering.

    The function implements a dynamic caching strategy via Redis to avoid expensive
    SQL aggregation on every request. Invalidation occurs after 24 hours or if the
    cache is empty or if the number of new ratings since the last calculation exceeds a
    sliding threshold: max(10, sqrt(total_ratings) * 2).

    Bayesian Components:
    * **m (Prior Mean):** The global average rating across all rides.
    * **c (Confidence Weight):** The number of ratings required to be
        considered statistically significant.
    """
    # Fetch cached constants and the total ratings baseline
    cached_m: str | None = await redis_client.get("twist_filter_bayes_m")
    cached_c: str | None = await redis_client.get("twist_filter_bayes_c")
    cached_total_str = await redis_client.get("twist_filter_bayes_total_ratings")

    # Fetch mutation count
    new_ratings_count = int(await redis_client.get("twist_filter_ratings_since_bayes_calculation") or 0)

    # Determine the dynamic new rating threshold with the square root formula, with a minimum threshold of 10
    cached_total = int(cached_total_str) if cached_total_str else 0
    threshold = max(10, isqrt(cached_total) * 2)

    # Invalidate cache if missing OR if new ratings exceed the dynamic threshold
    if cached_m is None or cached_c is None or new_ratings_count >= threshold:
        paved_criteria_slugs = [c.slug for c in await Criterion.get_list(session, is_paved=True)]
        unpaved_criteria_slugs = [c.slug for c in await Criterion.get_list(session, is_paved=False)]

        # Dynamically build the total calculations
        def build_total_expression(slugs: list[str]):
            if not slugs:
                return literal(0.0)

            # We just sum the keys for the current row and divide by the count
            total_rating = sum(
                (Ride.ratings[slug].as_integer() for slug in slugs),
                start=literal(0.0)
            )
            return total_rating / len(slugs)
        paved_total = build_total_expression(paved_criteria_slugs)
        unpaved_total = build_total_expression(unpaved_criteria_slugs)

        calculated_m = await session.scalar(
            select(case(
                (Twist.is_paved, paved_total),
                else_=unpaved_total
            ))
            .join(Ride.twist)
        ) or 0.0

        # Calculate c (nth percentile of ride counts per Twist)
        rides_per_twist_subquery = (
            select(func.count(Ride.id).label("ride_count"))
            .select_from(Ride)
            .group_by(Ride.twist_id)
            .subquery()
        )
        calculated_c = await session.scalar(
            select(func.percentile_cont(settings.INSIGNIFICANT_RIDE_COUNT_PERCENTILE / 100).within_group(rides_per_twist_subquery.c.ride_count))
        ) or 1.0

        # Calculate the new baseline total
        ratings_count = await session.scalar(
            select(func.count(Ride.id))
        ) or 0

        # Save to Redis with a 24-hour TTL
        await redis_client.setex("twist_filter_bayes_m", 86400, calculated_m)
        await redis_client.setex("twist_filter_bayes_c", 86400, calculated_c)
        await redis_client.setex("twist_filter_bayes_total_ratings", 86400, ratings_count)

        # Reset the mutation counter
        await redis_client.set("twist_filter_ratings_since_bayes_calculation", 0)

        return calculated_m, calculated_c

    return float(cached_m), float(cached_c)


async def calculate_map_bounds_condition(map: FilterMap) -> ColumnElement[bool]:
    """
    Calculate map bounds condition based off map filter,
    taking antimeridian into account.
    """
    if map.south_west.lng > map.north_east.lng:
        # Bounding box crosses the antimeridian, need to split it into two envelopes
        bounds_condition = or_(
            # Box 1: From the southwest corner east to the antimeridian (+180)
            Twist.route_geometry.intersects(
                func.ST_MakeEnvelope(
                    map.south_west.lng, map.south_west.lat,
                    180.0, map.north_east.lat,
                    Coordinate.SRID
                )
            ),
            # Box 2: From the antimeridian (-180) east to the southwest corner
            Twist.route_geometry.intersects(
                func.ST_MakeEnvelope(
                    -180.0, map.south_west.lat,
                    map.north_east.lng, map.north_east.lat,
                    Coordinate.SRID
                )
            )
        )
    else:
        # Standard bounding box (does not cross the antimeridian)
        bounds_condition = Twist.route_geometry.intersects(
            func.ST_MakeEnvelope(
                map.south_west.lng, map.south_west.lat,
                map.north_east.lng, map.north_east.lat,
                Coordinate.SRID
            )
        )
    return bounds_condition


async def filter_twist_list(
    session: AsyncSession,
    user: User | None,
    filter: TwistFilter
) -> list[TwistListItem]:
    """
    Determine which Twists match the Filter and return them,
    ordered accordingly as well.
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

    # Map Bounds Filtering
    map_bounds_condition = await calculate_map_bounds_condition(filter.map)
    statement = statement.where(map_bounds_condition)

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

    if filter.map.center:
        distance: ColumnExpressionArgument[float] = Twist.route_geometry.distance_centroid(
            type_coerce(filter.map.center.to_spatial(), Geometry)
        )
        order_criteria.append(distance)

    order_criteria.append(Twist.name)

    # Querying
    results = await session.execute(
        statement.order_by(*order_criteria).limit(filter.pages * settings.DEFAULT_TWISTS_LOADED).offset(offset)
    )
    return [TwistListItem.model_validate(result) for result in results.all()]
