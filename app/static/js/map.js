import { SETTINGS } from './constants.js';
import { debounce } from './utils.js';


export const startIcon = new L.Icon({
    iconUrl: '/static/images/marker-icon-green.png',
    shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    iconSize: [19, 31], iconAnchor: [10, 31], shadowSize: [31, 31]
});

export const endIcon = new L.Icon({
    iconUrl: '/static/images/marker-icon-red.png',
    shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    iconSize: [19, 31], iconAnchor: [10, 31], shadowSize: [31, 31]
});

export const waypointIcon = new L.Icon({
    iconUrl: '/static/images/marker-icon-blue.png',
    shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    iconSize: [19, 31], iconAnchor: [10, 31], shadowSize: [31, 31]
});

export const shapingPointIcon = new L.Icon({
    iconUrl: '/static/images/marker-icon-grey.png',
    shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    iconSize: [19, 31], iconAnchor: [10, 31], shadowSize: [31, 31]
});


/**
 * Saves the current map view (center and zoom) to localStorage.
 *
 * @param {L.Map} map The map to save the view from.
 */
function saveMapView(map) {
    try {
        const view = {
            center: map.getCenter(), // Gets a {lat, lng} object
            zoom: map.getZoom()
        };
        localStorage.setItem('mapView', JSON.stringify(view));
    } catch (e) {
        // Handle potential storage errors (e.g., private browsing, quota exceeded)
        console.error("Failed to save map view to localStorage:", e);
    }
}


/**
 * Initializes the map to either:
 * - The stored view (last view used)
 * - The current location view at zoom level 9
 * - The default view (Vancouver at zoom level 9)
 *
 * It also creates a tile layer and sets up event listeners
 * to save the map's center and zoom level to localStorage
 * after the user stops moving or zooming.
 *
 * This should be called once on application startup.
 *
 * @returns {L.Map} map The main Leaflet map instance.
 */
export function initMap() {
    // Assert the map container exists
    const mapContainer = document.querySelector('#map');
    if (!(mapContainer instanceof HTMLElement)) throw new Error("Critical element #map is missing!");

    const defaultView = {
        center: { lat: 49.2827, lng: -123.1207 },
        zoom: 9
    };

    let currentView = defaultView; // Start with the default view
    let viewLoadedFromStorage = false; // Flag to check if we loaded data

    // Try to load saved view from localStorage
    try {
        const savedView = localStorage.getItem('mapView');
        if (savedView) {
            const parsedView = JSON.parse(savedView);

            // Check if the loaded data has the correct structure
            if (parsedView.center &&
                typeof parsedView.center === 'object' &&
                typeof parsedView.center.lat === 'number' &&
                typeof parsedView.center.lng === 'number' &&
                typeof parsedView.zoom === 'number') {
                currentView = parsedView; // Overwrite default with the valid saved view
                viewLoadedFromStorage = true;
            } else {
                console.warn("Saved map view was corrupted or in an old format. Using defaults.");
            }
        }
    } catch (e) {
        console.error("Could not parse saved map view:", e);
    }

    // Initialize the map with the determined view (either default or loaded)
    // worldCopyJump is not an ideal solution here but it's better than confusing the user if they pan too far
    const map = L.map(mapContainer, {worldCopyJump: true}).setView(currentView.center, currentView.zoom);

    // Try to locate the user ONLY if we didn't load a saved view
    document.addEventListener('DOMContentLoaded', () => {
        if (!viewLoadedFromStorage) {
            // Only run this if the user is seeing the default view
            map.locate({ setView: true, maxZoom: defaultView.zoom });
        }
    });

    map.on('moveend', debounce(() => saveMapView(map), 500));
    map.on('zoomend', debounce(() => saveMapView(map), 500));

    // Add a tile layer
    L.tileLayer(SETTINGS.OSM_URL, {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    // Add map search button
    const provider = new GeoSearch.OpenStreetMapProvider();
    const search = new GeoSearch.GeoSearchControl({
        provider: provider,
        style: 'button',
        updateMap: true,
        autoClose: true,
    });
    search.addTo(map);

    return map;
}