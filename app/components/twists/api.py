from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from io import BytesIO
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.components.core.config import logger
from app.components.core.database import get_db
from app.components.core.events import EventSet
from app.components.core.models import Twist, User
from app.components.core.settings import settings
from app.components.core.utility import raise_http
from app.components.twists.fragments import build_single_list_item, build_twist_export_toggle
from app.components.twists.schema import TwistCreateForm, TwistExportFormat, TwistGeometry
from app.components.twists.services import generate_gpx, simplify_route, snap_waypoints_to_route
from app.components.users.services import current_user, verify


router = APIRouter(
    prefix="/twists",
    tags=["Twists"]
)


@router.post("", response_class=HTMLResponse)
async def create_twist(
    request: Request,
    twist_data: TwistCreateForm,
    user: User = Depends(verify(current_user)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Create a new Twist.
    """
    # Process route and waypoints
    simplified_route = simplify_route(twist_data.route_geometry)
    snapped_waypoints = snap_waypoints_to_route(twist_data.waypoints, simplified_route)

    # Create the new Twist
    twist_dict = twist_data.model_dump()
    twist_dict.update({
        "author": user,
        "waypoints": snapped_waypoints,
        "route_geometry": simplified_route,
        "simplification_tolerance_m": settings.TWIST_SIMPLIFICATION_TOLERANCE_M
    })
    twist = Twist(**twist_dict)
    session.add(twist)
    await session.commit()
    logger.debug(f"Created Twist '{twist}' for User '{user.id}'")

    # Render the twist list fragment with the new data
    response = await build_single_list_item(request, session, user, twist.id)
    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH("Twist created successfully!"),
        EventSet.TWIST_CHANGED(twist.id),
        EventSet.CLOSE_MODAL
    ).dump()
    return response


@router.put("/{twist_id}", response_class=HTMLResponse)
async def edit_twist(
    request: Request,
    twist_id: int,
    twist_data: TwistCreateForm,
    user: User = Depends(verify(current_user)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Edit an existing Twist.
    """
    try:
        result = await session.scalars(
            select(Twist).where(Twist.id == twist_id).options(
                load_only(Twist.id, Twist.author_id)
            )
        )
        twist = result.one()
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple Twists found for id '{twist_id}'", status_code=500)

    # If not admin, check if the user authored the Twist (and can edit it)
    if not user.is_superuser and user.id != twist:
        raise_http("You do not have permission to edit this Twist", status_code=403)

    # Process new route and waypoints
    simplified_route = simplify_route(twist_data.route_geometry)
    snapped_waypoints = snap_waypoints_to_route(twist_data.waypoints, simplified_route)

    # Edit the Twist
    twist_dict = twist_data.model_dump()
    twist_dict.update({
        "author": user,
        "waypoints": snapped_waypoints,
        "route_geometry": simplified_route,
        "simplification_tolerance_m": settings.TWIST_SIMPLIFICATION_TOLERANCE_M
    })
    for key, value in twist_dict.items():
        setattr(twist, key, value)
    await session.commit()
    logger.debug(f"Edited Twist '{twist}' for User '{user.id}'")

    # Render the twist list fragment with the new data
    response = await build_single_list_item(request, session, user, twist.id)
    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH("Twist edited successfully!"),
        EventSet.TWIST_CHANGED(twist.id),
        EventSet.CLOSE_MODAL
    ).dump()
    return response


@router.delete("/{twist_id}", response_class=HTMLResponse)
async def delete_twist(
    request: Request,
    twist_id: int,
    user: User = Depends(verify(current_user)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Delete a Twist and all related rides.
    """
    try:
        result = await session.scalars(
            select(Twist).where(Twist.id == twist_id).options(
                load_only(Twist.id, Twist.author_id)
            )
        )
        twist = result.one()
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple Twists found for id '{twist_id}'", status_code=500)

    # If not admin, check if the user authored the Twist (and can delete it)
    if not user.is_superuser and user.id != twist.author_id:
        raise_http("You do not have permission to delete this Twist", status_code=403)

    # Delete the Twist
    await session.delete(twist)
    await session.commit()
    logger.debug(f"Deleted Twist with id '{twist_id}'")

    # Empty response to "delete" the list item
    response = HTMLResponse(content="")
    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.FLASH("Twist deleted successfully!"),
        EventSet.TWIST_DELETED(twist_id),
        EventSet.CLOSE_MODAL
    ).dump()
    return response


@router.get("/{twist_id}/geometry", response_class=JSONResponse)
async def get_twist_geometry(
    request: Request,
    twist_id: int,
    session: AsyncSession = Depends(get_db)
) -> TwistGeometry:
    """
    Serve JSON containing the geometry data for a given Twist.
    """
    try:
        result = await session.execute(
            select(*TwistGeometry.fields).where(Twist.id == twist_id)
        )
        twist_geometry = TwistGeometry.model_validate(result.one())
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple Twists found for id '{twist_id}'", status_code=500)

    return twist_geometry


@router.post("/{twist_id}/toggle-export", response_class=HTMLResponse)
async def toggle_twist_export(
    request: Request,
    twist_id: int
) -> HTMLResponse:
    """
    Toggle a Twist in the user's session exports and return the updated button.
    """
    export_cart = request.session.get("export_cart", [])

    if twist_id in export_cart:
        export_cart.remove(twist_id)
        in_export_cart = False
    else:
        export_cart.append(twist_id)
        in_export_cart = True

    request.session["export_cart"] = export_cart

    response = await build_twist_export_toggle(request, twist_id, in_export_cart)
    response.headers["HX-Trigger-After-Swap"] = EventSet(
        EventSet.EXPORT_CART_CHANGED
    ).dump()
    return response


@router.get("/{twist_id}/export", response_class=StreamingResponse)
async def export_twist(
    request: Request,
    twist_id: int,
    format: TwistExportFormat = Query(),
    session: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """
    Export a single Twist as a GPX Track or GPX Route.
    """
    try:
        result = await session.scalars(
            select(Twist).where(Twist.id == twist_id)
        )
        twist = result.one()
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple Twists found for id '{twist_id}'", status_code=500)

    if TwistExportFormat.is_gpx:
        # Generate the GPX XML string
        export_string = generate_gpx(twist, format)
    else:
        raise_http("Export format not yet supported", status_code=501)

    # Convert the string to bytes for streaming
    export_bytes = export_string.encode("utf-8")
    file_stream = BytesIO(export_bytes)

    # Clean up the filename so it doesn't break browser downloads
    safe_filename = "".join([c if c.isalnum() else "_" for c in twist.name]).strip("_")

    return StreamingResponse(
        content=file_stream,
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}.gpx"'
        }
    )
