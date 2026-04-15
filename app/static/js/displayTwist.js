import { EVENTS } from './constants.js';
import { flash } from './flash.js';
import {
    startIcon,
    endIcon,
    waypointIcon
} from './map.js';
import { debounce, getRootProperty } from './utils.js';


// Object to store the map layers
/** @type {Object<string, L.FeatureGroup>} */
const mapLayers = {};

const accentBlue = getRootProperty('--accent-blue');
const accentOrange = getRootProperty('--accent-orange');

let numPagesLoaded = 1;


/**
 * Loads a Twist's geometry data and adds it to the map as a new layer.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @param {string} twistId The ID of the Twist to load.
 * @param {boolean} [show=false] If true, pan/zoom to the Twist after load.
 */
async function loadTwistLayer(map, twistId, show = false) {
    // If layer already exists, don't re-load it
    if (mapLayers[twistId]) return;

    // Add empty layer to the map
    const twistLayer = L.featureGroup();
    mapLayers[twistId] = twistLayer;
    twistLayer.addTo(map);

    // Fetch Twist data
    try {
        const response = await fetch(`/twists/${twistId}/geometry`);
        if (!response.ok) throw new Error(`Server responded with status: ${response.status}`);

        /** @type {TwistGeometryData & {name: string, is_paved: boolean}} */
        const twistData = await response.json();

        // Create the Twist route line
        const lineColor = twistData.is_paved ? accentBlue : accentOrange;
        const routeLine = L.polyline(twistData.route_geometry, {
            color: lineColor,
            weight: 5,
            opacity: 0.85
        });

        // Create the Twist popup
        const popupContent = document.createElement('div');
        popupContent.classList.add('twist-popup');
        popupContent.setAttribute('hx-get', `/twists/${twistId}/templates/popup`);
        popupContent.setAttribute('hx-swap', 'innerHTML');
        popupContent.setAttribute('hx-trigger', `intersect once, ${EVENTS.AUTH_CHANGE} from:body`);
        popupContent.innerHTML = '<p class="loading">Loading details...</p>';
        htmx.process(popupContent);
        routeLine.bindPopup(popupContent, {
            autoPan: true,
            autoPanPaddingTopLeft: L.point(60, 60),
            autoPanPaddingBottomRight: L.point(60, 60)
        });

        // Update popup pan after data loads
        popupContent.addEventListener('htmx:afterSettle', function(event) {
            const popup = routeLine.getPopup();

            // If the popup is still open when the data arrives, tell Leaflet to resize/pan
            if (popup && popup.isOpen()) {
                popup.update();
            }
        });

        // Create the waypoint markers
        const namedWaypoints = twistData.waypoints.filter(wp => wp.name.length > 0);
        const waypointMarkers = namedWaypoints.map((point, index) => {
            let icon = waypointIcon;
            const totalPoints = namedWaypoints.length;

            if (totalPoints === 1 || index === 0) icon = startIcon;
            else if (index === totalPoints - 1) icon = endIcon;

            return L.marker(point, { icon: icon })
                .bindPopup(`<b>${twistData.name}</b>${point.name ? `<br>${point.name}` : ''}`);
        });

        // On mobile, create a thicker invisible line to make it easier to tap
        if (L.Browser.mobile) {
            const tapLine = L.polyline(twistData.route_geometry, {
                weight: 30,
                opacity: 0
            });

            // Forward the tap event
            tapLine.on('click',
                /** @param {{ latlng: L.LatLng }} event */
                function(event) {

                routeLine.fire('click', event);
            });

            // Automatically add/remove from the map along with actual route
            routeLine.on('add', function() {
                if (map) {
                    tapLine.addTo(map);
                    // Keep it behind markers
                    tapLine.bringToBack();
                }
            });
            routeLine.on('remove', function() {
                tapLine.remove();
            });
        }

        // Group all layers together (already on the map)
        routeLine.addTo(twistLayer);
        waypointMarkers.forEach(marker => marker.addTo(twistLayer));

        if (show) showTwistOnMap(map, twistId);

    } catch (error) {
        console.error(`Failed to load route for Twist '${twistId}':`, error);
        flash(`Failed to load route for Twist '${twistId}'`, { duration: 5000, type: 'error' })

        // Ensure a failed layer doesn't stick around
        removeTwistLayer(map, twistId);
    }
}


/**
 * Removes a given Twist's geometry layer from the map.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @param {string} twistId The ID of the Twist to remove.
 */
export async function removeTwistLayer(map, twistId) {
    const layer = mapLayers[twistId];
    if (!layer) return;

    if (map.hasLayer(layer)) map.removeLayer(layer);
    delete mapLayers[twistId];
}


/**
 * Opens the map popup for a specific Twist if it is loaded.
 * Does not check visibility.
 *
 * @param {string} twistId The ID of the Twist for which to open the popup.
 */
function openTwistPopup(twistId) {
    const layer = mapLayers[twistId];
    if (layer) {
        const routeLine = layer.getLayers().find(layer => layer instanceof L.Polyline);
        // Open popup (even if already open, to maintain autopan)
        if (routeLine instanceof L.Polyline) {
            routeLine.openPopup();
        } else {
            console.warn(`Cannot open popup of Twist '${twistId}' because its layer has no valid route.`);
        }
    }
}


/**
 * Pans and zooms the map to fit the bounds of a specific Twist if it
 * is loaded. Does not check visibility.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @param {string} twistId The ID of the Twist to show.
 */
function showTwistOnMap(map, twistId) {
    const layer = mapLayers[twistId];
    if (layer) {
        const bounds = layer.getBounds();
        if (bounds.isValid()) {
            // Pan and zoom the map
            map.fitBounds(bounds);
        } else {
            console.warn(`Cannot fit map to Twist '${twistId}' because its layer has no valid bounds.`);
        }
    }
}


/**
 * Set the visibility state of a Twist layer.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @param {string} twistId The ID of the Twist to modify.
 * @param {boolean} makeVisible True to show the layer, false to hide it.
 * @param {boolean} [show=false] If true and `makeVisible` is true, show Twist on map.
 */
export async function setTwistVisibility(map, twistId, makeVisible, show = false) {
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
 * Toggles the visibility icon of a Twist Item. Does NOT update the map.
 *
 * @param {HTMLElement} twistItem The TwistItem to toggle the visibility eye for.
 */
export async function toggleTwistItemEye(twistItem) {
    const visibility = twistItem.classList.contains('is-visible');
    const icon = twistItem.querySelector('.visibility-toggle i');
    if (!icon) throw new Error("Critical element .visibility-toggle icon is missing!");

    twistItem.classList.toggle('is-visible', !visibility);
    icon.classList.toggle('fa-eye', !visibility);
    icon.classList.toggle('fa-eye-slash', visibility);
}


// Define the custom control class
L.Control.hideAllTwists = L.Control.extend({
    options: {
        position: 'topleft'
    },
    /** @param {Object} options */
    initialize: function (options) {
        L.setOptions(this, options);
        /** @type {Set<string>} */
        this._hiddenTwistIds = new Set();
    },
    /** @param {L.Map} map */
    onAdd: function (map) {
        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');

        // Leaflet uses anchors for buttons
        this.link = L.DomUtil.create('a', 'leaflet-control-visibility', container);
        this.link.href = '#';

        // Attach the click event handler
        L.DomEvent.on(this.link, 'click', L.DomEvent.stop)  // Stop map events
            .on(this.link, 'click', this.hideShowTwists, this);  // Hide/Show Twists

        this._map = map;
        return container;
    },
    /** @param {L.Map} map */
    onRemove: function (map) {
        // Clean up events
        L.DomEvent.off(this.link, 'click', this.hideShowTwists, this);
    },
    hideShowTwists: function () {
        if (this._hiddenTwistIds.size === 0) {
            /** @type {NodeListOf<HTMLElement>} */
            const twistItems = document.querySelectorAll('.twist-item.is-visible');
            twistItems.forEach(item => {
                const twistId = item.dataset.twistId;
                if (!twistId) throw new Error("Critical element .twist-item is missing twistId data!");

                // Save and hide Twists
                this._hiddenTwistIds.add(twistId);
                toggleTwistItemEye(item)
                setTwistVisibility(this._map, twistId, false);
            });
            this.link.title = 'Restore Hidden Twists';
            this.link.innerHTML = '<i class="far fa-eye"></i>';
        } else {
            // Restore the hidden Twists
            this._hiddenTwistIds.forEach(/** @param {string} twistId */ twistId => {
                const twistItem = document.querySelector(`.twist-item[data-twist-id="${twistId}"]`)
                if (twistItem instanceof HTMLElement) {
                    toggleTwistItemEye(twistItem)
                    setTwistVisibility(this._map, twistId, true);
                }
            });

            this.reset()
        }
    },
    reset: function() {
        // Clear state
        this._hiddenTwistIds.clear();
        this.link.title = 'Hide All Twists';
        this.link.innerHTML = '<i class="far fa-eye-slash"></i>';
    }
});
const hideAllTwists = new L.Control.hideAllTwists();


/**
 * Gets the geographic coordinates (Lat/Lng) at the center of the viewport,
 * accounting for map offsets (such as the sidebar).
 *
 * @param {L.Map} map The main Leaflet map instance.
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
 * - Fitting map bounds to Twist on click.
 * - Modifying Twist list requests to include visible Twist IDs.
 *
 * @param {L.Map} map The main Leaflet map instance.
 * @returns {void}
 */
export function registerTwistListeners(map) {
    const manualUpdateButton = document.getElementById('refresh-twists-button');
    if (!manualUpdateButton) throw new Error("Critical element #refresh-twists-button is missing!");

    // Listen for the custom event sent from the server after a Twist list chunk is received
    document.body.addEventListener(EVENTS.TWISTS_LOADED, (event) => {
        const customEvent = /** @type {CustomEvent<{value: string}>} */ (event);
        const detail = JSON.parse(customEvent.detail.value);
        const startPage = Number(detail.startPage);
        const numPages = Number(detail.numPages);

        manualUpdateButton.classList.remove('button--visible');

        // Only the first scroll is automatically visible
        if (startPage === 1) {
            numPagesLoaded = numPages;

            /** @type {NodeListOf<HTMLElement>} */
            const visibleTwistItems = document.querySelectorAll('.twist-item.is-visible');

            // Set of IDs of first page Twists
            const visibleTwistIds = new Set();
            visibleTwistItems.forEach(item => {
                const twistId = item.dataset.twistId;
                if (!twistId) throw new Error("Critical element .twist-item is missing twistId data!");

                visibleTwistIds.add(twistId);
            });

            // Set visibility for first page Twists
            const editingId = document.getElementById('twist-list')?.dataset.editingId;
            visibleTwistIds.forEach(twistId => {
                // The Twist being edited (if any) should remain hidden
                if (twistId === editingId) return;

                setTwistVisibility(map, twistId, true);
            });

            // Unset visibility for Twists no longer on the first page
            Object.keys(mapLayers).forEach(mapTwistId => {
                if (!visibleTwistIds.has(mapTwistId)) {
                    setTwistVisibility(map, mapTwistId, false);
                }
            });

            // Reset the hide all button
            hideAllTwists.reset()
        } else {
            numPagesLoaded += numPages;
        }
    });

    // Listen for the custom event sent from the server after a Twist is deleted
    document.body.addEventListener(EVENTS.TWIST_DELETED, async (event) => {
        const customEvent = /** @type {CustomEvent<{value: string}>} */ (event);

        const deletedTwistId = customEvent.detail.value;
        if (deletedTwistId) {
            await setTwistVisibility(map, deletedTwistId, false);
        }

        removeTwistLayer(map, deletedTwistId);
    });

    const twistList = document.getElementById('twist-list');
    if (!twistList) throw new Error("Critical element #twist-list is missing!");

    // Listen for clicks on Twists
    twistList.addEventListener('click', function(event) {
        if (!(event.target instanceof Element)) return;

        /** @type {HTMLElement | null} */
        const twistItem = event.target.closest('.twist-item');
        if (!twistItem) return;

        const twistId = twistItem.dataset.twistId;
        if (!twistId) throw new Error("Critical element .twist-item is missing twistId data!");

        if (event.target.closest('.visibility-toggle')) {
            // Clicked on the eye icon
            const visibility = twistItem.classList.contains('is-visible');
            toggleTwistItemEye(twistItem);
            setTwistVisibility(map, twistId, !visibility);
        } else if (event.target.closest('.twist-header')) {
            showTwistOnMap(map, twistId);
            openTwistPopup(twistId);
        }
    });

    const PAN_THRESHOLD_METERS = 5000;
    /** @type {L.LatLng} */
    let cachedMapCenter = getVisualMapCenter(map);

    // Show button to manually update Twists on map move
    function updateManualUpdateButtonVisibility() {
        if (!manualUpdateButton) throw new Error("Critical element #refresh-twists-button is missing!");

        const distanceMoved = map.distance(cachedMapCenter, getVisualMapCenter(map));
        if (distanceMoved > PAN_THRESHOLD_METERS) {
            manualUpdateButton.classList.add('button--visible');
        }
    }
    map.on('dragend', debounce(updateManualUpdateButtonVisibility, 500));
    // map.on('zoomend', debounce(updateManualUpdateButtonVisibility, 500)); // TODO: cleanly ignore programatic zooms

    // On successful search, update Twists automatically
    map.on('geosearch/showlocation', () => {
        htmx.trigger(document.body, EVENTS.REFRESH_TWISTS);
    });

    hideAllTwists.addTo(map);

    // Include additional parameters for Twist list requests
    document.body.addEventListener('htmx:configRequest', function(event) {
        const customEvent = /** @type {CustomEvent<{path: string, parameters: Record<string, any>, triggeringEvent: Event | null}>} */ (event);

        // Check if this is a request to the Twist list endpoint
        if (customEvent.detail.path === '/twists/templates/list') {
            const p = customEvent.detail.parameters;
            const trigger = customEvent.detail.triggeringEvent;

            if (trigger && trigger.type === EVENTS.AUTH_CHANGE) {
                p['pages'] = numPagesLoaded;
            }

            // If it's the first page or the map center cache is empty, update the map center cache
            const pageNum = parseInt(p['page'], 10) || 1;
            if (pageNum === 1 || !cachedMapCenter) {
                cachedMapCenter = getVisualMapCenter(map);
            }

            // Always apply the cached map center to ensure pagination remains consistent
            if (cachedMapCenter) {
                p['map_center.lat'] = cachedMapCenter.lat;
                p['map_center.lng'] = cachedMapCenter.lng;
            }
        }
    });
}
