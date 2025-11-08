from enum import Enum
from json import dumps
from typing import TypeAlias

class EventKey(str, Enum):
    FLASH = "flashMessage"
    """
    Triggers a client-side notification/toast message.

    Expected value is the message string.
    """

    AUTH_CHANGE = "authChange"
    """
    Signals that the user's authentication status may have changed (e.g., login, logout).

    No expected value.
    """

    SESSION_SET = "sessionSet"
    """
    Signals that a new session cookie has been set.

    No expected value.
    """

    SESSION_CLEARED = "sessionCleared"
    """
    Signals that the existing session cookie has been cleared.

    No expected value.
    """

    RESET_FORM = "resetForm"
    """
    Signals that the open modal should have its forms reset.

    No expected value.
    """

    CLOSE_MODAL = "closeModal"
    """
    Signals that the open modal should be closed, and its forms reset.

    No expected value.
    """

    TWIST_ADDED = "twistAdded"
    """
    Signals that a new Twist has been added.

    Expected value is the Twist's ID.
    """

    TWIST_DELETED = "twistDeleted"
    """
    Signals that a Twist has been deleted.

    Expected value is the Twist's ID.
    """

    TWISTS_LOADED = "twistsLoaded"
    """
    Signals that a set of Twists has been loaded into the list.

    Expected value is a dictionary containing startPage and numPages loaded.
    """

    REFRESH_TWISTS = "refreshTwists"
    """
    Signals that the Twist List needs to be refreshed.

    No expected value.
    """

    LOAD_DROPDOWN = "loadDropdown"
    """
    Signals that the dropdown associated with the header must be loaded.

    No expected value. Must be triggered directly on `.twist-header`.
    """

    REFRESH_AVERAGES = "refreshAverages"
    """
    Signals that the average ratings for a Twist must be re-calculated.

    Expected value is the Twist's ID.
    """

    RELOAD_PROFILE = "reloadProfile"
    """
    Signals that the profile modal needs to be reloaded.

    No expected value.
    """

    PROFILE_LOADED = "profileLoaded"
    """
    Signals that the profile modal has been loaded.

    No expected value.
    """


Event: TypeAlias = tuple[EventKey, str]


class EventSet:
        """
        A class designed to assemble HTMX events and serialize itself directly to
        the required JSON string when assigned to a header.
        """
        def __init__(self, *events: Event):
            self._events = events

        def dump(self) -> str:
            return dumps(dict(self._events))


        @staticmethod
        def FLASH(message: str) -> Event:
            return (EventKey.FLASH, message)

        AUTH_CHANGE = (EventKey.AUTH_CHANGE, "")
        SESSION_SET = (EventKey.SESSION_SET, "")
        SESSION_CLEARED = (EventKey.SESSION_CLEARED, "")
        RESET_FORM = (EventKey.RESET_FORM, "")
        CLOSE_MODAL = (EventKey.CLOSE_MODAL, "")

        @staticmethod
        def TWIST_ADDED(twist_id: int) -> Event:
            return (EventKey.TWIST_ADDED, str(twist_id))

        @staticmethod
        def TWIST_DELETED(twist_id: int) -> Event:
            return (EventKey.TWIST_DELETED, str(twist_id))

        @staticmethod
        def TWISTS_LOADED(start_page: int, num_pages: int) -> Event:
            json_string = dumps({
                "startPage": start_page,
                "numPages": num_pages
            })

            return (EventKey.TWISTS_LOADED, json_string)

        REFRESH_TWISTS = (EventKey.REFRESH_TWISTS, "")

        @staticmethod
        def REFRESH_AVERAGES(twist_id: int) -> Event:
            return (EventKey.REFRESH_AVERAGES, str(twist_id))

        RELOAD_PROFILE = (EventKey.RELOAD_PROFILE, "")
        PROFILE_LOADED = (EventKey.PROFILE_LOADED, "")