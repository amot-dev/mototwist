from datetime import datetime
from enum import Enum

from fastapi import Request
from gpxpy.gpx import GPX, GPXRoute, GPXRoutePoint, GPXTrack, GPXTrackPoint, GPXTrackSegment, GPXWaypoint
from typing import Sequence

from app.components.core.models import Twist


class TwistExportCart:
    SESSION_KEY = "export_cart"

    def __init__(self, request: Request):
        self.request = request

        # Load once and ensure it's a list
        self._items: list[int] = list(request.session.get(self.SESSION_KEY, []))

    @property
    def items(self) -> list[int]:
        """
        Return the current list of Twist IDs in the cart.
        """
        return self._items

    @property
    def count(self) -> int:
        """
        Return the current amount of Twist IDs in the cart.
        """
        return len(self._items)

    def _persist(self):
        """
        Synchronize the local state back to the session.
        """
        self.request.session[self.SESSION_KEY] = self._items

    def contains(self, twist_id: int) -> bool:
        """
        Return True if the cart contains the given Twist ID.
        """
        return twist_id in self._items

    def toggle(self, twist_id: int) -> bool:
        """
        Add or removes a Twist ID from the cart.
        Return True if the ID is now in the cart.
        """
        if twist_id in self._items:
            self._items.remove(twist_id)
            in_cart = False
        else:
            self._items.append(twist_id)
            in_cart = True

        self._persist()
        return in_cart

    def clear(self):
        """Empty the cart."""
        self._items = []
        self._persist()

def get_twist_export_cart(request: Request) -> TwistExportCart:
    return TwistExportCart(request)


class TwistExportFormat(str, Enum):
    JSON = "json"
    GPX_TRACK = "gpx_track"
    GPX_ROUTE = "gpx_route"

    @property
    def is_gpx(self) -> bool:
        """
        True only if the export format is a GPX type.
        """
        return self in [self.GPX_TRACK, self.GPX_ROUTE]



def generate_gpx(twists: Sequence[Twist], export_name: str, format: TwistExportFormat) -> str:
    """
    Generate a GPX XML string from a list of Twists.
    """
    gpx = GPX()
    gpx.creator = "MotoTwist"
    gpx.name = export_name

    # Generate description
    now = datetime.now()
    twist_count = len(twists)
    gpx.description = f"{twist_count} Twist{"s" if twist_count > 1 else ""} exported from MotoTwist on {now.strftime('%Y-%m-%d')} at {now.strftime('%H:%M')} UTC"

    for twist in twists:
        # Add named waypoints
        named_waypoints = [wp for wp in twist.waypoints if wp.name and wp.name.strip()]
        for wp in named_waypoints:
            gpx_wpt = GPXWaypoint(
                latitude=wp.lat,
                longitude=wp.lng,
                name=wp.name
            )
            gpx.waypoints.append(gpx_wpt)

        # Build the specific path structure based on format
        if format == TwistExportFormat.GPX_TRACK:
            # Create a track using route_geometry
            gpx_track = GPXTrack(name=twist.name, description=twist.description)
            gpx.tracks.append(gpx_track)
            gpx_segment = GPXTrackSegment()
            gpx_track.segments.append(gpx_segment)

            for coord in twist.route_geometry:
                gpx_segment.points.append(
                    GPXTrackPoint(latitude=coord.lat, longitude=coord.lng)
                )

        elif format == TwistExportFormat.GPX_ROUTE:
            # Create a route using all waypoints (including shaping points)
            gpx_route = GPXRoute(name=twist.name, description=twist.description)
            gpx.routes.append(gpx_route)

            for wp in twist.waypoints:
                gpx_route.points.append(
                    GPXRoutePoint(
                        latitude=wp.lat,
                        longitude=wp.lng,
                        name=wp.name if wp.name and wp.name.strip() else None
                    )
                )

    return gpx.to_xml()
