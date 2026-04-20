from enum import Enum
from math import isqrt
from geoalchemy2 import Geometry
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import ColumnElement, ColumnExpressionArgument, Numeric, and_, case, cast as sqlalchemy_cast, false, func, literal, or_, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Any, cast

from app.components.core.redis_client import redis_client
from app.components.core.models import Criterion, Ride, Twist, User
from app.components.core.schema import Coordinate, Weather
from app.components.core.settings import settings
from app.components.twists.schema import TwistListItem


class FilterOwnership(str, Enum):
    ALL = "all"
    OWN = "own"
    NOT_OWN = "notown"


class FilterPavement(str, Enum):
    ALL = "all"
    PAVED = "paved"
    UNPAVED = "unpaved"


class FilterRide(str, Enum):
    ALL = "all"
    SUBMITTED = "submitted"
    UNSUBMITTED = "unsubmitted"


class FilterMap(BaseModel):
    south_west: Annotated[Coordinate, Field(description="South-West corner")]
    north_east: Annotated[Coordinate, Field(description="North-East corner")]

    # Generated
    center: Annotated[Coordinate | None, Field(exclude=True)] = None


    @model_validator(mode="before")
    @classmethod
    def process_spatial_data(cls, data: dict[str, object] | object) -> dict[str, object] | object:
        try:
        # Ensure we are working with a raw dictionary payload
            if isinstance(data, dict):
                data = cast(dict[str, object], data)
                sw = data.get("south_west")
                ne = data.get("north_east")

                if isinstance(sw, dict) and isinstance(ne, dict):
                    sw = cast(dict[str, str | float], sw)
                    ne = cast(dict[str, str | float], ne)
                    sw_lat, sw_lng = float(sw["lat"]), float(sw["lng"])
                    ne_lat, ne_lng = float(ne["lat"]), float(ne["lng"])

                    # Calculate center before normalizing bounds
                    center_lat = (sw_lat + ne_lat) / 2.0
                    center_lng = (sw_lng + ne_lng) / 2.0

                    # Assign the normalized center
                    data["center"] = {
                        "lat": center_lat,
                        "lng": (center_lng + 180) % 360 - 180
                    }

                    # Normalize the bounds in the raw payload
                    sw["lng"] = (sw_lng + 180) % 360 - 180
                    ne["lng"] = (ne_lng + 180) % 360 - 180

            return data

        except (KeyError, ValueError, TypeError):
            # Pydantic's standard validation will catch the exact error
            pass


    async def calculate_bounds_condition(self) -> ColumnElement[bool]:
        """
        Calculate map bounds condition taking antimeridian into account.
        """
        if self.south_west.lng > self.north_east.lng:
            # Bounding box crosses the antimeridian, need to split it into two envelopes
            bounds_condition = or_(
                # Box 1: From the southwest corner east to the antimeridian (+180)
                Twist.route_geometry.intersects(
                    func.ST_MakeEnvelope(
                        self.south_west.lng, self.south_west.lat,
                        180.0, self.north_east.lat,
                        Coordinate.SRID
                    )
                ),
                # Box 2: From the antimeridian (-180) east to the southwest corner
                Twist.route_geometry.intersects(
                    func.ST_MakeEnvelope(
                        -180.0, self.south_west.lat,
                        self.north_east.lng, self.north_east.lat,
                        Coordinate.SRID
                    )
                )
            )
        else:
            # Standard bounding box (does not cross the antimeridian)
            bounds_condition = Twist.route_geometry.intersects(
                func.ST_MakeEnvelope(
                    self.south_west.lng, self.south_west.lat,
                    self.north_east.lng, self.north_east.lat,
                    Coordinate.SRID
                )
            )
        return bounds_condition


class FilterRatingRange(BaseModel):
    min: Annotated[float, Field(ge=Criterion.MIN_VALUE, le=Criterion.MAX_VALUE)] = Criterion.MIN_VALUE
    max: Annotated[float, Field(ge=Criterion.MIN_VALUE, le=Criterion.MAX_VALUE)] = Criterion.MAX_VALUE

    @property
    def is_active(self) -> bool:
        """
        True only if the range has been modified from the default min/max.
        """
        return self.min > Criterion.MIN_VALUE or self.max < Criterion.MAX_VALUE


class FilterWeather(BaseModel):
    temperature: Annotated[list[Weather.Temperature], Field()] = []
    light: Annotated[list[Weather.LightLevel], Field()] = []
    type: Annotated[list[Weather.Type], Field()] = []
    precipitation: Annotated[list[Weather.Intensity], Field()] = []
    wind: Annotated[list[Weather.Intensity], Field()] = []
    fog: Annotated[list[Weather.Intensity], Field()] = []


    @model_validator(mode="before")
    @classmethod
    def ensure_lists(cls, data: dict[str, object]) -> dict[str, object]:
        """
        Ensure that all input values are lists (even if just one item).
        """
        for key, value in data.items():
            if key in cls.model_fields and not isinstance(value, list):
                # Coerce single values into a list
                data[key] = [value]
        return data


    def calculate_conditions(self) -> list[ColumnExpressionArgument[bool]]:
        """
        Generate a list of SQLAlchemy AND clauses based on active weather filters.
        """
        conditions: list[ColumnExpressionArgument[bool]] = []

        # Map filter fields to db fields and dynamically build the conditions
        weather_mappings = {
            "temperature": Ride.__table__.c.weather_temperature,
            "light": Ride.__table__.c.weather_light,
            "type": Ride.__table__.c.weather_type,
            "precipitation": Ride.__table__.c.weather_precipitation,
            "wind": Ride.__table__.c.weather_wind,
            "fog": Ride.__table__.c.weather_fog,
        }
        for filter_field, db_column in weather_mappings.items():
            selected_conditions = getattr(self, filter_field)
            if selected_conditions:
                conditions.append(db_column.in_(selected_conditions))

        return conditions


class FilterSortOrder(str, Enum):
    BEST = "best"
    CLOSEST = "closest"
    TRENDING = "trending"
    HIDDEN_GEMS = "hidden_gems"


class TwistFilter(BaseModel):
    # Display
    page: Annotated[int, Field(gt=0)] = 1
    pages: Annotated[int, Field(gt=0)] = 1

    # Basic Filtering
    search: Annotated[str | None, Field()] = None
    ownership: Annotated[FilterOwnership, Field()] = FilterOwnership.ALL
    pavement: Annotated[FilterPavement, Field()] = FilterPavement.ALL
    rides: Annotated[FilterRide, Field()] = FilterRide.ALL

    # Map Filtering and Ordering
    map: Annotated[FilterMap, Field()]

    # Range Filtering
    overall_rating_range: Annotated[FilterRatingRange, Field()] = FilterRatingRange()
    individual_rating_ranges: Annotated[dict[str, FilterRatingRange], Field()] = {}

    @property
    def active_individual_rating_ranges(self) -> dict[str, FilterRatingRange]:
        """
        Return only the individual rating ranges that are currently active.
        """
        return {
            slug: rating_range
            for slug, rating_range in self.individual_rating_ranges.items()
            if rating_range.is_active
        }

    # Criteria Exclusion
    excluded_criteria_slugs: Annotated[set[str], Field()] = set()

    # Weather Filtering
    weather: Annotated[FilterWeather, Field()] = FilterWeather()

    # Ordering
    sort_order: Annotated[FilterSortOrder, Field()] = FilterSortOrder.BEST

    # Ensure excluded criteria slugs is a set
    @field_validator("excluded_criteria_slugs", mode="before")
    @classmethod
    def excluded_criteria_slugs_to_set(cls, value: str | list[str]) -> set[str]:
        if not isinstance(value, list):
            return {value}
        else:
            return set(value)


    @staticmethod
    async def _get_bayesian_constants(session: AsyncSession) -> tuple[float, float]:
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


    async def apply_for(
        self,
        session: AsyncSession,
        user: User | None
    ) -> list[TwistListItem]:
        """
        Determine which Twists match the Filter and return them,
        ordered accordingly as well.
        """
        statement = select(*TwistListItem.get_fields(user))
        order_criteria: list[ColumnExpressionArgument[Any]] = []

        # Basic Filtering
        if self.search:
            statement = statement.where(Twist.name.icontains(self.search))

        if self.ownership == FilterOwnership.OWN:
            statement = statement.where(Twist.author_id == user.id) if user else statement.where(false())
        elif user and self.ownership == FilterOwnership.NOT_OWN:
            statement = statement.where(Twist.author_id != user.id)

        if self.pavement == FilterPavement.PAVED:
            statement = statement.where(Twist.is_paved == True)
        elif self.pavement == FilterPavement.UNPAVED:
            statement = statement.where(Twist.is_paved == False)

        # User-submitted Ride Filtering
        if user and self.rides != FilterRide.ALL:
            ride_exists = select(Ride.id).where(
                Ride.twist_id == Twist.id,
                Ride.author_id == user.id
            ).exists()

            if self.rides == FilterRide.SUBMITTED:
                statement = statement.where(ride_exists)

            elif self.rides == FilterRide.UNSUBMITTED:
                statement = statement.where(~ride_exists)

        elif not user and self.rides == FilterRide.SUBMITTED:
            # If user is not logged in, they can't have Twists with submitted rides
            statement = statement.where(false())

        # Map Bounds Filtering
        map_bounds_condition = await self.map.calculate_bounds_condition()
        statement = statement.where(map_bounds_condition)

        # Ride Rating Filtering and Ordering
        is_sorting_by_rating = self.sort_order in (FilterSortOrder.BEST, FilterSortOrder.HIDDEN_GEMS)
        is_filtering_overall = self.overall_rating_range.is_active
        is_filtering_individual = bool(self.active_individual_rating_ranges)
        needs_overall_average = is_sorting_by_rating or is_filtering_overall
        needs_any_rating_logic = needs_overall_average or is_filtering_individual
        if needs_any_rating_logic:
            having_conditions: list[ColumnElement[bool]] = []
            overall_average = None
            ride_count = None

            # Calculate overall average and add it to the subquery
            if needs_overall_average:
                # List is important here to maintain ordering (I... think?)
                paved_criteria_slugs = [
                    c.slug for c in await Criterion.get_list(session, is_paved=True)
                    if c.slug not in self.excluded_criteria_slugs
                ]
                unpaved_criteria_slugs = [
                    c.slug for c in await Criterion.get_list(session, is_paved=False)
                    if c.slug not in self.excluded_criteria_slugs
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
                    return func.round(sqlalchemy_cast(avg, Numeric), settings.AVERAGE_ROUNDING_DIGITS)
                paved_avg_rounded = build_rounded_avg_expression(paved_criteria_slugs)
                unpaved_avg_rounded = build_rounded_avg_expression(unpaved_criteria_slugs)

                overall_average = case(
                    (Twist.is_paved, paved_avg_rounded),
                    else_=unpaved_avg_rounded
                ).label("overall_average")
                ride_count = func.count(Ride.id).label("ride_count")

                # Filter by overall average
                if is_filtering_overall:
                    having_conditions.append(
                        overall_average.between(self.overall_rating_range.min, self.overall_rating_range.max)
                    )

            # Calculate individual averages and add each to the conditions
            for slug, rating_range in self.active_individual_rating_ranges.items():
                # Calculate average
                condition_avg = func.avg(Ride.ratings[slug].as_integer())

                # Round same as UI before comparing to avoid user confusion
                condition_avg_rounded = func.round(sqlalchemy_cast(condition_avg, Numeric), settings.AVERAGE_ROUNDING_DIGITS)

                # Update the having clause
                having_conditions.append(
                    condition_avg_rounded.between(rating_range.min, rating_range.max)
                )

            # Create the subquery
            rating_statement = (
                select(Twist.id)
                .outerjoin(Ride, Twist.id == Ride.twist_id)
                .group_by(Twist.id)
            )

            if having_conditions:
                rating_statement = rating_statement.having(and_(*having_conditions))

            if is_sorting_by_rating and overall_average is not None and ride_count is not None:
                # Add overall_average and ride_count to rating subquery
                rating_subquery = rating_statement.add_columns(overall_average, ride_count).subquery()

                if having_conditions:
                    # If there are having conditions (rating filters) applied, Twists without rides are hidden
                    statement = statement.join(rating_subquery, Twist.id == rating_subquery.c.id)
                else:
                    # Otherwise, outer join ensures 0-ride Twists are still returned for the sort calculations
                    statement = statement.outerjoin(rating_subquery, Twist.id == rating_subquery.c.id)

                global_average, confident_ride_count = await self._get_bayesian_constants(session)
                print(f"Global average: {global_average}, Confidence Weight: {confident_ride_count}")

                twist_average = func.coalesce(rating_subquery.c.overall_average, 0.0)
                twist_ride_count = func.coalesce(rating_subquery.c.ride_count, 0)

                if self.sort_order == FilterSortOrder.BEST:
                    # Use Bayesian to determine sort order
                    bayesian_calc = (
                        (twist_average * twist_ride_count) + (confident_ride_count * global_average)
                    ) / (twist_ride_count + confident_ride_count)
                    order_criteria.append(bayesian_calc.desc())

                elif self.sort_order == FilterSortOrder.HIDDEN_GEMS:
                    # Show all highly rated Twists with unconfident ride count first, then remaining
                    hidden_gem_threshold = max(
                        Criterion.MAX_VALUE,
                        global_average * settings.HIDDEN_GEM_AVERAGE_MULTIPLIER
                    )
                    is_hidden_gem = case(
                        (and_(
                            twist_average >= hidden_gem_threshold,
                            twist_ride_count <= confident_ride_count,
                            twist_ride_count > 0
                        ), 1),
                        else_=0
                    )
                    order_criteria.extend([
                        is_hidden_gem.desc(),
                        twist_average.desc()
                    ])
            else:
                # Not sorting (no need to do heavy join)
                statement = statement.where(Twist.id.in_(rating_statement))

        # Weather Filtering
        weather_conditions = self.weather.calculate_conditions()
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
        offset = (self.page - 1) * settings.DEFAULT_TWISTS_LOADED

        # Always fallback to ordering by proximity then name (all 0-ride Twists rank the same under BEST / HIDDEN_GEMS)
        if self.map.center:
            distance: ColumnExpressionArgument[float] = Twist.route_geometry.distance_centroid(
                type_coerce(self.map.center.to_spatial(), Geometry)
            )
            order_criteria.append(distance)
        order_criteria.append(Twist.name)

        # Querying
        results = await session.execute(
            statement.order_by(*order_criteria).limit(self.pages * settings.DEFAULT_TWISTS_LOADED).offset(offset)
        )
        return [TwistListItem.model_validate(result) for result in results.all()]
