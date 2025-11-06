import { stopTwistCreation } from './createTwist.js';
import { flash } from './flash.js';
import {
    startIcon,
    endIcon,
    waypointIcon
} from './map.js';
import { debounce, doubleClickTimeout, getRootProperty } from './utils.js';


// Object to store the map layers
/** @type {Object<string, L.FeatureGroup>} */
const mapLayers = {};

const accentBlue = getRootProperty('--accent-blue');
const accentOrange = getRootProperty('--accent-orange');

let currentPageLoaded = 1;


/**
 * Pans and zooms the map to fit the bounds of a specific Twist if it
 * is loaded. Does not check visibility.
 *
 * @param {L.Map} map - The map to pan and zoom to the Twist on.
 * @param {string} twistId - The ID of the Twist to show.
 */
function showTwistOnMap(map, twistId) {
    // Pan and zoom the map
    const layer = mapLayers[twistId];
    if (layer) {
        const bounds = layer.getBounds();
        if (bounds.isValid()) {
            map.fitBounds(bounds);
        } else {
            console.warn(`Cannot fit map to Twist '${twistId}' because its layer has no valid bounds.`);
        }
    }
}


/**
 * Loads a Twist's geometry data and adds it to the map as a new layer.
 *
 * @param {L.Map} map The map to load a Twist onto.
 * @param {string} twistId The ID of the Twist to load.
 * @param {boolean} [show=false] If true, pan/zoom to the Twist after load.
 */
async function loadTwistLayer(map, twistId, show = false) {
    // If layer already exists, don't re-load it
    if (mapLayers[twistId]) return;

    // Fetch Twist data
    try {
        const response = await fetch(`/twists/${twistId}/geometry`);
        if (!response.ok) {
            throw new Error(`Server responded with status: ${response.status}`);
        }

        /** @type {TwistGeometryData} */
        const twist_data = await response.json();

        // Create the route line
        const lineColor = twist_data.is_paved ? accentBlue : accentOrange;
        const routeLine = L.polyline(twist_data.route_geometry, {
            color: lineColor,
            weight: 5,
            opacity: 0.85
        });
        routeLine.bindPopup(`<b>${twist_data.name}</b>`);

        // Create the waypoint markers
        const namedWaypoints = twist_data.waypoints.filter(wp => wp.name.length > 0);
        const waypointMarkers = namedWaypoints.map((point, index) => {
            let icon = waypointIcon;
            const totalPoints = namedWaypoints.length;

            if (totalPoints === 1 || index === 0) icon = startIcon;
            else if (index === totalPoints - 1) icon = endIcon;

            return L.marker(point, { icon: icon })
                .bindPopup(`<b>${twist_data.name}</b>${point.name ? `<br>${point.name}` : ''}`);
        });

        // Group all layers together
        const twistLayer = L.featureGroup([routeLine, ...waypointMarkers]);

        // Store and add the complete layer to the map
        mapLayers[twistId] = twistLayer;
        twistLayer.addTo(map);
        if (show) showTwistOnMap(map, twistId);

    } catch (error) {
        console.error(`Failed to load route for Twist '${twistId}':`, error);
        flash(`Failed to load route for Twist '${twistId}'`, { duration: 5000, type: 'error' })

        // Ensure a failed layer doesn't stick around
        delete mapLayers[twistId];
    }
}


/**
 * Set the visibility state of a Twist layer.
 *
 * @param {L.Map} map The map to set the visibility of a Twist on.
 * @param {string} twistId The ID of the Twist to modify.
 * @param {boolean} makeVisible True to show the layer, false to hide it.
 * @param {boolean} [show=false] If true and `makeVisible` is true, show Twist on map.
 */
async function setTwistVisibility(map, twistId, makeVisible, show = false) {
    const layer = mapLayers[twistId];

    // Unload if hiding
    if (!makeVisible) {
        if (layer && map.hasLayer(layer)) {
            map.removeLayer(layer);
        }
        return;
    }

    // Load layer if showing
    if (layer) {
        // Layer is already loaded, just add it back to the map
        layer.addTo(map);
        if (show) showTwistOnMap(map, twistId);
    } else {
        // First time showing this layer, load the Twist data
        await loadTwistLayer(map, twistId, show);
    }
}


/**
 * Gets the geographic coordinates (Lat/Lng) at the center of the viewport,
 * accounting for map offsets (such as the sidebar).
 *
 * @param {L.Map} map - The active Leaflet map instance.
 * @returns {L.LatLng} The coordinates at the visual center of the screen.
 */
function getVisualMapCenter(map) {
    // Get the pixel center of the entire window
    const visualCenterX = window.innerWidth / 2;
    const visualCenterY = window.innerHeight / 2;

    // Get the map div's position and size
    const mapRect = map.getContainer().getBoundingClientRect();

    // Calculate the center point relative to the map's div
    const relativeX = visualCenterX - mapRect.left;
    const relativeY = visualCenterY - mapRect.top;

    // Convert this relative pixel coordinate to a Lat/Lng and return it
    return map.containerPointToLatLng(L.point(relativeX, relativeY));
}


/**
 * Sets up all event listeners related to managing and interacting
 * with the list of Twists.
 *
 * This function uses event delegation on the body and '#twist-list'
 * to handle:
 * - Loading initial layer visibility ('twistsLoaded').
 * - Adding/removing layers on create/delete ('twistAdded', 'twistDeleted').
 * - Toggling layer visibility via the '.visibility-toggle' button.
 * - Expanding/collapsing Twist dropdowns and fitting map bounds on click.
 * - Modifying Twist list requests to include visible Twist IDs.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @returns {void}
 */
export function registerTwistListeners(map) {
    const manualUpdateButton = document.getElementById('manual-update-button');
    if (!manualUpdateButton) throw new Error("Critical element #manual-update-button is missing!");

    // Listen for the custom event sent from the server after the Twist list is initially loaded
    document.body.addEventListener('twistsLoaded', (event) => {
        const customEvent = /** @type {CustomEvent<{value: string}>} */ (event);
        currentPageLoaded = Number(customEvent.detail.value);
        manualUpdateButton.classList.remove('button--visible');

        // Only the first scroll is automatically visible
        if (currentPageLoaded === 1) {
            setTimeout(() => {
                /** @type {NodeListOf<HTMLElement>} */
                const allTwistItems = document.querySelectorAll('.twist-item');
                allTwistItems.forEach(item => {
                    const twistId = item.dataset.twistId;
                    if (!twistId) throw new Error("Critical element .twist-item is missing twistId data!");

                    // Visible if the item has the 'is-visible' class
                    const shouldBeVisible = item.classList.contains('is-visible');
                    setTwistVisibility(map, twistId, shouldBeVisible);
                });
            }, 0);
        }
    });

    // Listen for the custom event sent from the server after a new Twist is created
    document.body.addEventListener('twistAdded', (event) => {
        const customEvent = /** @type {CustomEvent<{value: string}>} */ (event);

        const newTwistId = customEvent.detail.value;
        if (newTwistId) {
            stopTwistCreation(map);
            setTwistVisibility(map, newTwistId, true, true);
        }
    });

    // Listen for the custom event sent from the server after a Twist is deleted
    document.body.addEventListener('twistDeleted', (event) => {
        const customEvent = /** @type {CustomEvent<{value: string}>} */ (event);

        const deletedTwistId = customEvent.detail.value;
        if (deletedTwistId) {
            setTwistVisibility(map, deletedTwistId, false);
        }
    });

    const twistList = document.getElementById('twist-list');
    if (!twistList) throw new Error("Critical element #twist-list is missing!");

    /** @type {string | null} */
    let activeTwistId = null;

    // Listen for clicks on Twists
    let twistListClickCount = 0
    let twistListClickTimer = 0;
    twistList.addEventListener('click', function(event) {
        if (!(event.target instanceof Element)) return;

        /** @type {HTMLElement | null} */
        const twistItem = event.target.closest('.twist-item');
        if (!twistItem) return;

        const twistId = twistItem.dataset.twistId;
        if (!twistId) throw new Error("Critical element .twist-item is missing twistId data!");

        twistListClickCount++;
        if (twistListClickCount === 1) {
            twistListClickTimer = setTimeout(function() {
                twistListClickCount = 0;
                if (!(event.target instanceof Element)) return;

                // Toggle visibility or dropdown on single click
                if (event.target.closest('.visibility-toggle')) {
                    // Clicked on the eye icon
                    const visibility = twistItem.classList.contains('is-visible');
                    const icon = twistItem.querySelector('.visibility-toggle i');
                    if (!icon) throw new Error("Critical element .visibility-toggle icon is missing!");

                    twistItem.classList.toggle('is-visible', visibility);
                    icon.classList.toggle('fa-eye', visibility);
                    icon.classList.toggle('fa-eye-slash', !visibility);
                    setTwistVisibility(map, twistId, !visibility);
                } else if (event.target.closest('.twist-header')) {
                    activeTwistId = null;

                    // Clicked on the Twist header
                    const twistDropdown = twistItem.querySelector('.twist-dropdown');
                    if (!(twistDropdown instanceof HTMLElement)) throw new Error("Critical element .twist-dropdown is missing!");
                    const isCurrentlyOpen = twistDropdown.classList.contains('is-open');

                    // Hide all Twist dropdowns
                    const alltwistDropdowns = twistList.querySelectorAll('.twist-dropdown');
                    alltwistDropdowns.forEach(container => {
                        container.classList.remove('is-open');
                    });

                    // Show current Twist dropdown if it was hidden
                    if (!isCurrentlyOpen) {
                        twistDropdown.classList.add('is-open');
                        activeTwistId = twistItem.dataset.twistId ?? null;

                        // Load content if needed
                        if (twistDropdown.querySelector('.loading')) {
                            const twistHeader = twistItem.querySelector('.twist-header')
                            htmx.trigger(twistHeader, 'loadDropdown');
                        }
                    }
                }
            }, doubleClickTimeout);
        } else if (twistListClickCount === 2) {
            clearTimeout(twistListClickTimer);
            twistListClickCount = 0;

            // Show the Twist on the map on double click
            showTwistOnMap(map, twistId)

            // Clear text selection
            const selection = document.getSelection();
            if(selection) selection.empty();
        }
    });

    // Show button to manually update Twists on map move
    map.on('moveend', debounce(() => {
        manualUpdateButton.classList.add('button--visible');
    }, 500));

    // Include additional parameters for Twist list requests
    document.body.addEventListener('htmx:configRequest', function(event) {
        const customEvent = /** @type {CustomEvent<{path: string, parameters: Record<string, any>, triggeringEvent: Event | null}>} */ (event);

        // Check if this is a request to the Twist list endpoint
        if (customEvent.detail.path === '/twists/templates/list') {
            // Maintain current list on authChange
            const trigger = customEvent.detail.triggeringEvent;
            if (trigger) {
                if (trigger.type === 'authChange') {
                    customEvent.detail.parameters['pages'] = currentPageLoaded;
                }
            }

            if (activeTwistId) customEvent.detail.parameters['open_id'] = activeTwistId;

            /** @type {L.LatLng} */
            const mapCenter = getVisualMapCenter(map);
            customEvent.detail.parameters['map_center_lat'] = mapCenter.lat;
            customEvent.detail.parameters['map_center_lng'] = mapCenter.lng;
        }
    });
}