import { EVENTS, SETTINGS } from './constants.js';
import { removeTwistLayer, setTwistVisibility, toggleTwistItemEye } from './displayTwist.js';
import { flash } from './flash.js';
import {
    startIcon,
    endIcon,
    shapingPointIcon,
    waypointIcon
} from './map.js';
import { getRootProperty } from './utils.js';


const accentBlueHoverLight = getRootProperty('--accent-blue-hover-light');
const accentOrangeHoverLight = getRootProperty('--accent-orange-hover-light');

/** @returns {HTMLButtonElement | null} */
const getStartTwistButton = () => document.querySelector('#start-new-twist');
/** @returns {HTMLButtonElement | null} */
const getEditTwistButton = () => document.querySelector('#edit-twist');
/** @returns {HTMLButtonElement | null} */
const getFinalizeTwistButton = () => document.querySelector('#finalize-new-twist');
/** @returns {HTMLButtonElement | null} */
const getCancelTwistButton = () => document.querySelector('#cancel-new-twist');

const mapContainer = document.querySelector('#map');
if (!(mapContainer instanceof HTMLElement)) throw new Error("Critical element #map is missing!");

const createWaypointPopupTemplate = document.querySelector('#create-waypoint-popup-template');
if (!(createWaypointPopupTemplate instanceof HTMLTemplateElement)) throw new Error("Critical element #create-waypoint-popup-template is missing or not a <template>!");
const createWaypointPopupTemplateContent = createWaypointPopupTemplate.content;

/** @returns {HTMLFormElement} */
const getTwistForm = () => {
    const form = document.querySelector('#modal-create-edit-twist form');
    if (!(form instanceof HTMLFormElement)) throw new Error("Critical element #modal-create-edit-twist form is missing or not a <form>!");
    return form;
};


/** @type {Waypoint[]} */
let waypoints = [];

/** @type {L.Marker[]} */
let waypointMarkers = [];

/** @type {(() => void) | null} */
let hideLoadingFlash = null;

/** @type {AbortController | null} */
let routeRequestController;

/** @type {L.Polyline | null} */
let newRouteLine = null;

/** @type {string} */
let newRouteColor = accentBlueHoverLight;

/** @type {string | null} */
let editingTwistId = null;


/**
 * Adds a new point to the route.
 * @param {L.Map} map The main Leaflet map instance.
 * @param {L.LatLng} latlng The coordinates for the new point.
 * @param {boolean} insertBeforeEnd Whether to insert right before the final waypoint.
 */
function addPoint(map, latlng, insertBeforeEnd = false) {
    const assertedMapContainer = /** @type {HTMLElement} */ (mapContainer);
    if (!assertedMapContainer.classList.contains('editing-twist')) return;

    // Create a new waypoint
    const newWaypoint = {
        latlng: latlng,
        name: '',
    };
    const insertIndex = (insertBeforeEnd && waypoints.length >= 2) ? waypoints.length - 1 : waypoints.length;
    waypoints.splice(insertIndex, 0, newWaypoint);

    // Create a new marker
    const marker = L.marker(latlng, { draggable: true }).addTo(map);
    waypointMarkers.splice(insertIndex, 0, marker);

    // Bind a function that creates and returns the popup content on demand
    marker.bindPopup(() => createPopupContent(map, marker));

    // Listen for the marker being dragged and update route on end
    marker.on('dragend',
            /** @param {L.LeafletEvent} event */
            (event) => handleMarkerDrag(event, map)
        );

    // Listen for the marker's popup being closed and update icons
    marker.getPopup().on('remove', function() {
        updateMarkerIcons();
    });

    // Update the route line with the new waypoint
    updateRoute(map);
    updateMarkerIcons();
}


/**
 * Shared handler for marker drag events to update the route.
 * * @param {L.LeafletEvent} event The dragend event.
 * @param {L.Map} map The map instance to update the route on.
 */
function handleMarkerDrag(event, map) {
    const marker = event.target;
    const index = waypointMarkers.indexOf(marker);

    if (index === -1) throw new Error("Dragged marker not found in state array!")

    // Redraw the route with the new coordinates
    waypoints[index].latlng = marker.getLatLng();
    updateRoute(map);
}


/**
 * Fetches and draws the route on the map using the current waypoints.
 * It aborts any previously ongoing route requests.
 *
 * @param {L.Map} map The map to update the route on.
 */
async function updateRoute(map) {
    // Remove old route
    if (newRouteLine) map.removeLayer(newRouteLine);

    // Don't start new route if less than 2 waypoints (start and end)
    if (waypoints.length < 2) return;

    // Abort any ongoing fetch requests
    if (routeRequestController) routeRequestController.abort();

    // Create a new AbortController for the new request
    routeRequestController = new AbortController();
    const signal = routeRequestController.signal;

    // Create a new loading flash if one doesn't already exist
    if (!hideLoadingFlash) hideLoadingFlash = flash("Finding route", { duration: 0, type: 'loading' });

    // Format coordinates
    const coordinates = waypoints.map(waypoint => `${waypoint.latlng.lng},${waypoint.latlng.lat}`).join(';');

    // Call OSRM. The continue_straight option prevents OSRM from taking previous direction into account during the next segment
    const url = `${SETTINGS.OSRM_URL}/route/v1/driving/${coordinates}?overview=full&continue_straight=false&geometries=geojson`;

    try {
        const response = await fetch(url, { signal });
        if (!response.ok) throw new Error('Route not found');

        const data = await response.json();
        const routeGeometry = data.routes[0].geometry.coordinates;

        // OSRM returns [lng, lat], Leaflet needs [lat, lng]
        const latLngs = routeGeometry.map(
            /** @param {number[]} coord */
            coord => [coord[1], coord[0]]
        );

        // Create a new polyline and add it to the map
        const twistForm = getTwistForm();
        newRouteLine = L.polyline(latLngs, { color: newRouteColor }).addTo(map);
    } catch (error) {
        // If the error is an AbortError, do nothing
        if (error instanceof Error && error.name === 'AbortError') {
            return;
        } else {
            console.error("Error fetching route:", error);
            flash("Route not found", { duration: 5000, type: 'error' });
        }
    }

    // Hide loading flash (and clear it) only at the very end. If AbortError, we leave it as loading is still "in progress" from a new request
    if (hideLoadingFlash) {
        hideLoadingFlash();
        hideLoadingFlash = null;
    }
}


/**
 * Configures whether or not a shaping point can be edited, based off the user action and the existing text.
 *
 * @param {boolean} fromClick Whether or not the popup is being configured from an edit button click.
 * @param {HTMLInputElement} nameInput The input element containing the waypoint name.
 */
function configureShapingPointPopup(fromClick, nameInput) {
    // If text exists or we've just clicked on the edit button, enable editing
    if (fromClick || nameInput.value.length > 0) {
        // Re-enable the input
        nameInput.disabled = false;

        const nameInputTemplate = createWaypointPopupTemplateContent.querySelector('input');
        if (!nameInputTemplate) throw new Error("Popup template is corrupted: missing required input element.");
        nameInput.placeholder = nameInputTemplate.placeholder;
    } else {
        // Disable the input and set its text
        nameInput.disabled = true;
        nameInput.placeholder = 'Shaping Point';
        nameInput.title = 'Shaping Points are stored for routing but not displayed'
    }
}


/**
 * Creates and configures the DOM element for a marker's popup.
 *
 * @param {L.Map} map The map to create the popup for.
 * @param {L.Marker} marker The marker for which to create the popup content.
 * @returns {DocumentFragment | null} The configured popup content fragment.
 */
function createPopupContent(map, marker) {
    const index = waypointMarkers.indexOf(marker);
    if (index === -1) throw new Error("Clicked marker not found in state array!")

    const waypoint = waypoints[index];
    const totalMarkers = waypointMarkers.length;

    // Create a fresh clone of the template
    const popupContent = /** @type {DocumentFragment} */ (createWaypointPopupTemplateContent.cloneNode(true));
    const nameInput = popupContent.querySelector('.create-waypoint-name-input');
    const editButton = popupContent.querySelector('.popup-button-edit');
    const deleteButton = popupContent.querySelector('.popup-button-delete');

    if (!nameInput || !editButton || !deleteButton || !(nameInput instanceof HTMLInputElement)) {
        throw new Error("Popup template is corrupted: missing required elements.");
    }

    // Input for the waypoint name
    nameInput.value = waypoint.name;
    nameInput.addEventListener('input', (event) => {
        const target = /** @type {HTMLInputElement} */ (event.target);
        waypoint.name = target.value; // Persist name change
    });

    // Close popup on enter
    nameInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            map.closePopup();
        }
    });

    // Toggle visibility of the edit button for start/end markers
    const isStart = index === 0;
    const isEnd = index === totalMarkers - 1 && totalMarkers > 1;
    editButton.classList.toggle('gone', isStart || isEnd);

    // Set midpoints as shaping points
    if (!(isStart || isEnd)) {
        configureShapingPointPopup(false, nameInput)
    }

    // Edit button
    editButton.addEventListener('click', () => {
        configureShapingPointPopup(true, nameInput)
    });

    // Delete button
    deleteButton.addEventListener('click', () => {
        const index = waypointMarkers.indexOf(marker);
        if (index === -1) throw new Error("Deleted marker not found in state array!")

        map.closePopup();
        marker.remove();
        waypointMarkers.splice(index, 1);
        waypoints.splice(index, 1);
        updateRoute(map);
        updateMarkerIcons();
    });

    // Return the newly created and configured DOM element for Leaflet to display
    return popupContent;
}


/**
 * Updates a single waypoint marker icon on the map to reflect its
 * current status.
 *
 * @param {L.Marker} marker The marker to update.
 * @param {Waypoint} waypoint The corresponding waypoint data object.
 * @param {number} index The index of the marker in the array.
 * @param {number} totalMarkers The total number of markers.
 */
function updateMarkerIcon(marker, waypoint, index, totalMarkers) {
    const isStart = totalMarkers === 1 || index === 0;
    const isEnd = index === totalMarkers - 1 && totalMarkers > 1;

    // Set map icon based on position and presence of name
    if (isStart) marker.setIcon(startIcon);
    else if (isEnd) marker.setIcon(endIcon);
    else if (waypoint.name.length === 0) marker.setIcon(shapingPointIcon);
    else marker.setIcon(waypointIcon);
}


/**
 * Updates all waypoint marker icons on the map to reflect their current
 * status (start, end, shaping, named waypoint).
 */
function updateMarkerIcons() {
    const totalMarkers = waypointMarkers.length;

    waypointMarkers.forEach((marker, index) => {
        const waypoint = waypoints[index];
        updateMarkerIcon(marker, waypoint, index, totalMarkers);
    });
}


/**
 * Sets the enabled or disabled status of the submit button on the Twist Form.
 * The check is based off of form and route validity.
 */
function updateTwistFormSubmitState() {
    const twistForm = getTwistForm()

    /** @type {HTMLButtonElement | null} */
    const submitButton = twistForm.querySelector('[type="submit"]');
    if (!submitButton) throw new Error("Critical element [type=\"submit\"] is missing from .twist-form!")

    submitButton.disabled = !twistForm.checkValidity() || twistForm.dataset.routeValid != 'true';
}


/**
 * Updates a container element with a new message paragraph.
 *
 * @param {HTMLElement} element The container element to update.
 * @param {string} message The text content for the new paragraph.
 * @param {'w' | 'a'} mode 'w' to write (overwrite), 'a' to append. Defaults to 'w'.
 */
function writeToStatus(element, message, mode = 'w') {
    // If mode is 'write', clear the container first.
    if (mode === 'w') {
    element.innerHTML = '';
    }

    // Create a new paragraph, set its text, and append it.
    const p = document.createElement('p');
    p.textContent = message;
    element.appendChild(p);
}


/**
 * Initiates the Twist editing state, setting UI elements
 * accordingly.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @param {string} flashMessage The message to display to the user.
 */
export function startTwistEdit(map, flashMessage) {
    // Allow map interaction
    const assertedMapContainer = /** @type {HTMLElement} */ (mapContainer);
    assertedMapContainer.classList.add('editing-twist');
    map.closePopup();
    flash(flashMessage, { duration: 5000 });

    // Swap button visibility
    getStartTwistButton()?.classList.add('gone');
    getFinalizeTwistButton()?.classList.remove('gone');
    getCancelTwistButton()?.classList.remove('gone');
}


/**
 * Loads existing Twist data into the map's editing state.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @param {TwistGeometryData} twistData The fetched geometry data.
 */
export function loadTwistEdit(map, twistData) {
    // Populate waypoints
    waypoints = twistData.waypoints.map(wp => ({
        latlng: L.latLng(wp.lat, wp.lng),
        name: wp.name
    }));

    // Create markers
    waypointMarkers = waypoints.map((wp) => {
        const marker = L.marker(wp.latlng, { draggable: true }).addTo(map);

        // Bind existing popup and drag logic
        marker.bindPopup(() => createPopupContent(map, marker));
        marker.on('dragend',
            /** @param {L.LeafletEvent} event */
            (event) => handleMarkerDrag(event, map)
        );

        marker.getPopup().on('remove', () => updateMarkerIcons());
        return marker;
    });

    // Hide original route
    editingTwistId = `${twistData.id}`;
    if (!editingTwistId) throw new Error("Critical twistId data is missing from Twist Geometry!");

    const twistItem = document.getElementById(`twist-item-${editingTwistId}`);
    if (twistItem) toggleTwistItemEye(twistItem);
    setTwistVisibility(map, editingTwistId, false);

    const list = document.getElementById('twist-list');
    if (list) list.dataset.editingId = editingTwistId;

    // Update route and icons
    newRouteColor = twistData.is_paved ? accentBlueHoverLight : accentOrangeHoverLight;
    updateRoute(map);
    updateMarkerIcons();
}


/**
 * Resets the Twist editing state, removing all waypoints, markers,
 * and the route line from the map and resetting UI elements.
 *
 * @param {L.Map} map The main Leaflet map instance.
 */
export function stopTwistEdit(map) {
    // Immediate return if not editing Twist
    const assertedMapContainer = /** @type {HTMLElement} */ (mapContainer);
    if (!assertedMapContainer.classList.contains('editing-twist')) return;

    const twistForm = getTwistForm()

    // Abort any ongoing fetch requests
    if (routeRequestController) routeRequestController.abort();
    if (hideLoadingFlash) {
        hideLoadingFlash();
        hideLoadingFlash = null;
    }

    // Reset map state
    assertedMapContainer.classList.remove('editing-twist');
    map.closePopup();

    // Remove waypoints
    waypointMarkers.forEach(marker => marker.remove());
    waypoints.length = 0;
    waypointMarkers.length = 0;

    // Clear route line and reset default color
    if (newRouteLine) {
        map.removeLayer(newRouteLine);
        newRouteLine = null;
    }
    newRouteColor = accentBlueHoverLight;

    // Unset editing Twist
    if (editingTwistId) {
        const twistItem = document.getElementById(`twist-item-${editingTwistId}`);
        if (twistItem) toggleTwistItemEye(twistItem);

        setTwistVisibility(map, editingTwistId, true);
        editingTwistId = null;

        const list = document.getElementById('twist-list');
        if (list) delete list.dataset.editingId;
    }

    // Reset the status indicator and submit button
    /** @type {HTMLButtonElement | null} */
    const submitButton = twistForm.querySelector('[type="submit"]');
    if (!submitButton) throw new Error("Critical element [type=\"submit\"] is missing from .twist-form!")
    const statusIndicator = document.querySelector('#route-status-indicator');
    if (!statusIndicator || !(statusIndicator instanceof HTMLElement)) {
        throw new Error("Critical element #route-status-indicator is missing!");
    }
    submitButton.disabled = true;
    statusIndicator.classList.add('gone');
    writeToStatus(statusIndicator, "");

    // Reset button visibility to the initial state
    getFinalizeTwistButton()?.classList.add('gone');
    getCancelTwistButton()?.classList.add('gone');
    getStartTwistButton()?.classList.remove('gone');
}


/**
 * Sets up all event listeners for creation/editing of Twists.
 *
 * This function attaches listeners for:
 * - The 'Start New Twist' button to enter editing mode and start a new Twist.
 * - The 'Finalize Twist' button to validate and prepare route data.
 * - The 'Cancel Twist' button to stop editing mode.
 * - The 'Edit Twist' button to enter editing mode and edit an existing Twist.
 * - The main map 'click' event (only when in editing mode)
 * to add new waypoints.
 *
 * This should be called once on application startup.
 *
 * @param {L.Map} map The main Leaflet map instance.
 */
export function registerTwistEditingListeners(map) {
    document.body.addEventListener('htmx:afterSwap', (event) => {
        const customEvent = /** @type {CustomEvent<{elt: Element}>} */ (event);

        // Register listener for Create Twist button
        if (customEvent.detail.elt.id === 'twist-action-buttons') {
            getStartTwistButton()?.addEventListener('click', () => {
                stopTwistEdit(map);
                startTwistEdit(map, 'Click on the map to create a Twist!')
            });
        }

        // Register listener for Edit Twist button
        if (customEvent.detail.elt.classList.contains('twist-popup')) {
            getEditTwistButton()?.addEventListener('click', async () => {
                const editButton = getEditTwistButton()
                if (!editButton) throw new Error("Critical element #edit-twist is missing!");

                const twistId = editButton.dataset.twistId;
                if (!twistId) throw new Error("Element #edit-twist is missing twistId data!");

                try {
                    const response = await fetch(`/twists/${twistId}/geometry`);
                    if (!response.ok) throw new Error(`Server responded with status: ${response.status}`);

                    /** @type {TwistGeometryData} */
                    const twistData = await response.json();

                    // Ensure a clean state before starting
                    stopTwistEdit(map);
                    loadTwistEdit(map, twistData);
                    startTwistEdit(map, 'Interact with the map to edit this Twist!')

                } catch (error) {
                    console.error(`Failed to load route editing for Twist '${twistId}':`, error);
                    flash(`Failed to load route for editing for Twist '${twistId}'`, { duration: 5000, type: 'error' })
                }
            });
        }

        // Register listeners for form finalization when Twist Form is swapped in (on start create/edit)
        if (customEvent.detail.elt.id === 'modal-create-edit-twist') {
            const twistForm = getTwistForm();
            twistForm.addEventListener('input', updateTwistFormSubmitState);
            updateTwistFormSubmitState();

            // Handle changing of route color on radio button select
            const pavementRadios = twistForm.querySelectorAll('input[name="is_paved"]');
            pavementRadios.forEach(radio => {
                if (!(radio instanceof HTMLInputElement)) return;
                radio.addEventListener('change', () => {
                    if (newRouteLine) {
                        newRouteColor = radio.value === 'false' ? accentOrangeHoverLight : accentBlueHoverLight;
                        newRouteLine.setStyle({ color: newRouteColor });
                    }
                });
            });

            // Handle saving of route geometry
            getFinalizeTwistButton()?.addEventListener('click', () => {
                const statusIndicator = document.querySelector('#route-status-indicator');
                if (!statusIndicator || !(statusIndicator instanceof HTMLElement)) {
                    throw new Error("Critical element #route-status-indicator is missing!");
                }

                // Check if there's a route to save
                const namedWaypoints = waypoints.filter(wp => wp.name.length > 0);
                const shapingPoints = waypoints.filter(wp => wp.name.length === 0);
                if (waypoints.length > 1 && newRouteLine) {
                    // Check if first and last waypoints have names
                    if (waypoints[0].name.length > 0 && waypoints[waypoints.length - 1].name.length > 0) {
                        twistForm.dataset.routeValid = "true";
                        writeToStatus(
                            statusIndicator,
                            `✅ Route captured with ${namedWaypoints.length} waypoints and ${newRouteLine.getLatLngs().length} geometry points.`
                        );

                        // Inform about shaping points on a new line
                        if (shapingPoints.length > 0) {
                            const noun = shapingPoints.length === 1 ? "shaping point" : "shaping points";
                            const message = `ℹ️ ${shapingPoints.length} ${noun} will be stored for routing but not displayed.`;

                            writeToStatus(statusIndicator, message, "a");
                        }
                    } else {
                        // Handle case where user finalizes without naming start or end
                        twistForm.dataset.routeValid = "false";
                        writeToStatus(
                            statusIndicator,
                            '⚠️ Start/End waypoint(s) remain unnamed.'
                        );
                    }
                } else {
                    // Handle case where user finalizes without a valid route
                    twistForm.dataset.routeValid = "false";
                    writeToStatus(
                        statusIndicator,
                        '⚠️ No valid route was created.'
                    );
                }
                updateTwistFormSubmitState()
                statusIndicator.classList.remove('gone');
            });

            // Handle cancellation of route geometry recording
            getCancelTwistButton()?.addEventListener('click', () => {
                stopTwistEdit(map);
            });
        }
    });

    // Listen for the custom event sent from the server after a new Twist is created/edited
    document.body.addEventListener(EVENTS.TWIST_CHANGED, (event) => {
        const customEvent = /** @type {CustomEvent<{value: string}>} */ (event);

        const newTwistId = customEvent.detail.value;
        if (newTwistId) {
            // Stop editing, remove old geometry layer (if any), then load new geometry and display
            stopTwistEdit(map);
            removeTwistLayer(map, newTwistId);
            setTwistVisibility(map, newTwistId, true, true);
        }
    });

    // Listen for the custom event sent from the server after an auth change
    document.body.addEventListener(EVENTS.AUTH_CHANGE, () => {
        stopTwistEdit(map);
    });

    // Listen for map clicks when recording route geometry
    map.on('click',
        /** @param {{ latlng: L.LatLng }} event */
        function(event) {

        addPoint(map, event.latlng);
    });

    // On right-click specifically, insert before final point
    map.on('contextmenu',
        /** @param {{ latlng: L.LatLng }} event */
        function(event) {

        if (waypoints.length < 2) {
            addPoint(map, event.latlng)
        } else {
            addPoint(map, event.latlng, true);
        }
    });
}


/**
 * Overrides the global XMLHttpRequest.prototype.send and .open methods
 * to intercept the HTMX form submission for creating a new Twist.
 *
 * This function finds the POST request to '/twists', parses its
 * JSON body, injects the 'waypoints' and 'route_geometry' data,
 * and sends the modified request.
 *
 * This should be called once on application startup.
 *
 * @returns {void}
 */
export function overrideXHR() {
    /**
    * @typedef {XMLHttpRequest & {_url?: string, _method?: string}} PatchedXMLHttpRequest
    */

    // Save the original send method so we can call it later
    const originalSend = XMLHttpRequest.prototype.send;

    // Override XHR send to intercept outgoing requests
    XMLHttpRequest.prototype.send = /** @this {PatchedXMLHttpRequest} */ function(/** @type {any} */ body) {
        // Check if this is a POST/PUT request to /twists
        const isCoreTwistEndpoint = this._url && /\/twists(\/\d+)?$/.test(this._url);
        const isModifying = this._method === 'POST' || this._method === 'PUT';

        if (isCoreTwistEndpoint && isModifying) {
            if (!newRouteLine) {
                throw new Error("Route missing from final payload!");
            }

            // Serialize JSON
            const bodyJSON = JSON.parse(body);

            // Build payload
            bodyJSON.waypoints = waypoints.map(wp => ({
                lat: wp.latlng.lat,
                lng: wp.latlng.lng,
                name: wp.name
            }));
            bodyJSON.route_geometry = newRouteLine.getLatLngs().map(
                /** @param {L.LatLng} coord */
                coord => ({ lat: coord.lat, lng: coord.lng })
            );

            // Stringify JSON
            body = JSON.stringify(bodyJSON);
        }
        // Call the original send function to actually send the request
        return originalSend.apply(this, [body]);
    };

    // Save the original open method
    const originalOpen = XMLHttpRequest.prototype.open;

    // Override XHR open to capture the method and URL (for send)
    XMLHttpRequest.prototype.open = /** @this {PatchedXMLHttpRequest} */ function(
        /** @type {string} */ method, 
        /** @type {string | URL} */ url
    ) {
        this._method = method;
        this._url = url.toString();
        return originalOpen.apply(this, /** @type {any} */ (arguments));
    };
};
