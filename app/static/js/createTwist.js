import { EVENTS, SETTINGS } from './constants.js';
import { flash } from './flash.js';
import {
    startIcon,
    endIcon,
    shapingPointIcon,
    waypointIcon
} from './map.js';
import { getRootProperty } from './utils.js';


const accentBlueHoverLight = getRootProperty('--accent-blue-hover-light')

/** @returns {HTMLButtonElement | null} */
const getStartTwistButton = () => document.querySelector('#start-new-twist');
/** @returns {HTMLButtonElement | null} */
const getFinalizeTwistButton = () => document.querySelector('#finalize-new-twist');
/** @returns {HTMLButtonElement | null} */
const getCancelTwistButton = () => document.querySelector('#cancel-new-twist');

const mapContainer = document.querySelector('#map');
if (!(mapContainer instanceof HTMLElement)) throw new Error("Critical element #map is missing!");

const createWaypointPopupTemplate = document.querySelector('#create-waypoint-popup-template');
if (!(createWaypointPopupTemplate instanceof HTMLTemplateElement)) throw new Error("Critical element #create-waypoint-popup-template is missing or not a <template>!");
const createWaypointPopupTemplateContent = createWaypointPopupTemplate.content;

const twistForm = document.querySelector('#modal-create-twist form');
if (!(twistForm instanceof HTMLFormElement)) throw new Error("Critical element #modal-create-twist form is missing or not a <form>!");


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


/**
 * Fetches and draws the route on the map using the current waypoints.
 * It aborts any previously ongoing route requests.
 *
 * @param {L.Map} map The map to update the route on.
 */
async function updateRoute(map) {
    if (newRouteLine) map.removeLayer(newRouteLine);

    if (waypoints.length < 2) return;

    // Abort any ongoing fetch requests
    if (routeRequestController) {
        routeRequestController.abort();
    }

    // Create a new AbortController for the new request
    routeRequestController = new AbortController();
    const signal = routeRequestController.signal;

    // Create a new loading flash if one doesn't already exist
    if (!hideLoadingFlash)
        hideLoadingFlash = flash("Finding route", { duration: 0, type: 'loading' });

    // Format coordinates and call the OSRM API
    const coordinates = waypoints.map(waypoint => `${waypoint.latlng.lng},${waypoint.latlng.lat}`).join(';');
    const url = `${SETTINGS.OSRM_URL}/route/v1/driving/${coordinates}?overview=full&geometries=geojson`;

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
        newRouteLine = L.polyline(latLngs, { color: accentBlueHoverLight }).addTo(map);
    } catch (error) {
        // If the error is an AbortError, do nothing
        if (error instanceof Error && error.name === 'AbortError') {
            return;
        } else {
            console.error("Error fetching route:", error);
            flash("Error drawing route", { duration: 5000, type: 'error' });
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
    const assertedTwistForm = /** @type {HTMLFormElement} */ (twistForm);

    /** @type {HTMLButtonElement | null} */
    const submitButton = assertedTwistForm.querySelector('[type="submit"]');
    if (!submitButton) throw new Error("Critical element [type=\"submit\"] is missing from .twist-form!")

    submitButton.disabled = !assertedTwistForm.checkValidity() || assertedTwistForm.dataset.routeValid != 'true';
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
 * Resets the Twist creation state, removing all waypoints, markers,
 * and the route line from the map and resetting UI elements.
 *
 * @param {L.Map} map The map to stop Twist creation on.
 */
export function stopTwistCreation(map) {
    const assertedMapContainer = /** @type {HTMLElement} */ (mapContainer);
    const assertedTwistForm = /** @type {HTMLFormElement} */ (twistForm);

    // Immediate return if not creating Twist
    if (!assertedMapContainer.classList.contains('creating-twist')) return;

    assertedMapContainer.classList.remove('creating-twist');

    map.closePopup();
    waypointMarkers.forEach(marker => marker.remove());
    waypoints.length = 0;
    waypointMarkers.length = 0;

    if (newRouteLine) {
        map.removeLayer(newRouteLine);
        newRouteLine = null;
    }

    // Reset the status indicator and submit button
    /** @type {HTMLButtonElement | null} */
    const submitButton = assertedTwistForm.querySelector('[type="submit"]');
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
 * Sets up event listeners for conditional Twist creation buttons.
 * These are reloaded by htmx after auth changes.
 *
 * @param {L.Map} map The main Leaflet map instance.
 */
function registerTwistCreationButtonListeners(map) {
    const assertedMapContainer = /** @type {HTMLElement} */ (mapContainer);
    const assertedTwistForm = /** @type {HTMLFormElement} */ (twistForm);

    // Begin recording route geometry
    getStartTwistButton()?.addEventListener('click', () => {
        assertedMapContainer.classList.add('creating-twist');
        flash('Click on the map to create a Twist!', { duration: 5000 });

        // Swap button visibility
        getStartTwistButton()?.classList.add('gone');
        getFinalizeTwistButton()?.classList.remove('gone');
        getCancelTwistButton()?.classList.remove('gone');
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
                assertedTwistForm.dataset.routeValid = "true";
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
                assertedTwistForm.dataset.routeValid = "false";
                writeToStatus(
                    statusIndicator,
                    '⚠️ Start/End waypoint(s) remain unnamed.'
                );
            }
        } else {
            // Handle case where user finalizes without a valid route
            assertedTwistForm.dataset.routeValid = "false";
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
        stopTwistCreation(map);
    });
}


/**
 * Sets up all event listeners for creation of new Twists.
 *
 * This function attaches listeners for:
 * - The 'Start New Twist' button to enter creation mode.
 * - The 'Finalize Twist' button to validate and prepare route data.
 * - The 'Cancel Twist' button to stop creation mode.
 * - The main map 'click' event (only when in creation mode)
 * to add new waypoints.
 *
 * This should be called once on application startup.
 *
 * @param {L.Map} map The main Leaflet map instance.
 */
export function registerTwistCreationListeners(map) {
    const assertedMapContainer = /** @type {HTMLElement} */ (mapContainer);
    const assertedTwistForm = /** @type {HTMLFormElement} */ (twistForm);

    // Add Twist Form validation listener and set initial state
    assertedTwistForm.addEventListener('input', updateTwistFormSubmitState);
    updateTwistFormSubmitState();

    // Register Twist creation button listeners both on initial load and after htmx swap
    document.body.addEventListener('htmx:afterSwap', (event) => {
        const customEvent = /** @type {CustomEvent<{elt: Element}>} */ (event);
        if (customEvent.detail.elt.id === 'twist-creation-buttons') {
            registerTwistCreationButtonListeners(map);
        }
    });
    registerTwistCreationButtonListeners(map);

    // Listen for the custom event sent from the server after an auth change
    document.body.addEventListener(EVENTS.AUTH_CHANGE, () => {
        stopTwistCreation(map);
    });

    // Listen for map clicks when recording route geometry
    map.on('click',
        /** @param {{ latlng: L.LatLng }} event */
        function(event) {
        if (!assertedMapContainer.classList.contains('creating-twist')) return;

        // Create a new waypoint
        const newWaypoint = {
            latlng: event.latlng,
            name: '',
        };
        waypoints.push(newWaypoint);

        // Create a new marker
        const marker = L.marker(event.latlng, { draggable: true }).addTo(map);
        waypointMarkers.push(marker);

        // Bind a function that creates and returns the popup content on demand
        marker.bindPopup(() => createPopupContent(map, marker));

        // Listen for the marker being dragged and update route on end
        marker.on('dragend',
            /** @param {{ target: L.Marker }} event */
            (event) => {
            const index = waypointMarkers.indexOf(marker);
            if (index === -1) throw new Error("Dragged marker not found in state array!")

            // Redraw the route with the new coordinates
            waypoints[index].latlng = event.target.getLatLng();
            updateRoute(map);
        });

        // Listen for the marker's popup being closed and update icons
        marker.getPopup().on('remove', function() {
            updateMarkerIcons();
        });

        // Update the route line with the new waypoint
        updateRoute(map);
        updateMarkerIcons();
    });
}


/**
 * Overrides the global XMLHttpRequest.prototype.send and .open methods
 * to intercept the HTMX form submission for creating a new Twist.
 *
 * This function finds the POST request to '/twists', parses its
 * JSON body, injects the 'waypoints' and 'route_geometry' data
 * from the twistCreation module, and sends the modified request.
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
        // Check if this is a POST request to /twists
        if (this._url && this._url.endsWith('/twists') && this._method === 'POST') {
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