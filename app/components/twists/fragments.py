from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.core.config import templates
from app.components.core.database import get_db
from app.components.core.events import EventSet
from app.components.core.models import Criterion, Twist, User
from app.components.core.schema import Weather
from app.components.core.settings import settings
from app.components.core.utility import raise_http
from app.components.twists.export import TwistExportCart, get_twist_export_cart
from app.components.twists.schema import FilterOwnership, TwistBasic, TwistExportFormat, TwistListItem, TwistPopup, TwistFilter
from app.components.twists.services import filter_twist_list
from app.components.users.services import current_user, current_user_optional, verify


router = APIRouter(
    prefix="/twists",
    tags=["Twists", "Templates"]
)


@router.get("/templates/action-buttons", response_class=HTMLResponse)
async def serve_action_buttons(
    request: Request,
    export_cart: TwistExportCart = Depends(get_twist_export_cart),
    user: User | None = Depends(current_user_optional)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the Twist creation buttons.
    """
    return templates.TemplateResponse("fragments/twists/action_buttons.html", {
        "request": request,
        "user": user,
        "export_cart_count": export_cart.count
    })


@router.get("/templates/create-edit-modal", response_class=HTMLResponse)
async def serve_create_edit_modal(
    request: Request,
    twist_id: int | None = None,
    user: User = Depends(verify(current_user)),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the Twist create/edit modal.
    """
    twist = None

    if twist_id is not None:
        try:
            result = await session.execute(
                select(*TwistBasic.fields).where(Twist.id == twist_id)
            )
            twist = TwistBasic.model_validate(result.one())
        except NoResultFound:
            raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
        except MultipleResultsFound:
            raise_http(f"Multiple Twists found for id '{twist_id}'", status_code=500)

    return templates.TemplateResponse("fragments/twists/create_edit_modal.html", {
        "request": request,
        "twist": twist
    })


@router.get("/templates/advanced-filter-modal", response_class=HTMLResponse)
async def serve_advanced_filter_modal(
    request: Request,
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the advanced filter modal.
    """
    criteria = await Criterion.get_list(session)

    return templates.TemplateResponse("fragments/twists/advanced_filter_modal.html", {
            "request": request,
            "criteria": criteria,
            "Weather": Weather
        })


@router.post("/templates/list", response_class=HTMLResponse)
async def serve_list(
    request: Request,
    filter: TwistFilter,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the sorted list of Twists.
    """
    twists = await filter_twist_list(session, user, filter)

    response = templates.TemplateResponse("fragments/twists/list.html", {
        "request": request,
        "twists": twists,
        "start_page": filter.page,
        "next_page": filter.page + filter.pages,
        "twists_per_page": settings.DEFAULT_TWISTS_LOADED
    })
    response.headers["HX-Trigger-After-Settle"] = EventSet(
        EventSet.TWISTS_LOADED(filter.page, filter.pages)
    ).dump()
    return response


async def build_single_list_item(
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


@router.get("/{twist_id}/templates/popup", response_class=HTMLResponse)
async def serve_popup(
    request: Request,
    twist_id: int,
    export_cart: TwistExportCart = Depends(get_twist_export_cart),
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the Twist popup for a given Twist.
    """
    try:
        result = await session.execute(
            select(*TwistPopup.fields)
            .join(Twist.author, isouter=True)
            .where(Twist.id == twist_id)
        )
        twist = TwistPopup.model_validate(result.one())
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple twists found for id '{twist_id}'", status_code=500)

    # Check if the user is allowed to edit/delete the Twist
    editable = (user.is_superuser or user.id == twist.author_id) if user else False

    return templates.TemplateResponse("fragments/twists/popup.html", {
        "request": request,
        "user": user,
        "twist": twist,
        "editable": editable,
        "in_export_cart": export_cart.contains(twist_id),
        "FilterOwnership": FilterOwnership
    })


async def build_twist_export_toggle(
    request: Request,
    twist_id: int,
    in_export_cart: bool
) -> HTMLResponse:
    """
     Build and return the TemplateResponse for the Twist export toggle.
    """
    return templates.TemplateResponse("fragments/twists/export_toggle.html", {
        "request": request,
        "twist": {"id": twist_id}, # So {{ twist.id }} resolves in the template
        "in_export_cart": in_export_cart
    })


@router.get("/templates/export-modal", response_class=HTMLResponse)
async def serve_export_modal(
    request: Request,
    export_cart: TwistExportCart = Depends(get_twist_export_cart),
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the Twist export cart modal.
    """
    result = await session.execute(
        select(*TwistBasic.fields).where(
            Twist.id.in_(export_cart.items)
        ).order_by(Twist.name)
    )
    twists = [TwistBasic.model_validate(row) for row in result.all()]

    return templates.TemplateResponse("fragments/twists/export_modal.html", {
        "request": request,
        "twists": twists,
        "export_cart": export_cart,
        "TwistExportFormat": TwistExportFormat
    })


@router.get("/{twist_id}/templates/delete-modal", response_class=HTMLResponse)
async def serve_delete_modal(
    request: Request,
    twist_id: int,
    session: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """
    Serve an HTML fragment containing the Twist deletion confirmation modal.
    """
    try:
        result = await session.execute(
            select(*TwistBasic.fields).where(Twist.id == twist_id)
        )
        twist = TwistBasic.model_validate(result.one())
    except NoResultFound:
        raise_http(f"Twist with id '{twist_id}' not found", status_code=404)
    except MultipleResultsFound:
        raise_http(f"Multiple Twists found for id '{twist_id}'", status_code=500)

    return templates.TemplateResponse("fragments/twists/delete_modal.html", {
        "request": request,
        "twist": twist
    })
