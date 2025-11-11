/**
 * @typedef {object} Settings
 * @property {string} SETTINGS.OSM_URL
 * @property {string} SETTINGS.OSRM_URL
 * @property {number} SETTINGS.AUTH_COOKIE_MAX_AGE
 * @property {number} SETTINGS.AUTH_EXPIRY_WARNING_OFFSET
 */

/**
 * @typedef {object} Events
 * @property {string} FLASH
 * @property {string} AUTH_CHANGE
 * @property {string} SESSION_SET
 * @property {string} SESSION_CLEARED
 * @property {string} RESET_FORM
 * @property {string} CLOSE_MODAL
 * @property {string} TWIST_ADDED
 * @property {string} TWIST_DELETED
 * @property {string} TWISTS_LOADED
 * @property {string} REFRESH_TWISTS
 * @property {string} LOAD_DROPDOWN
 * @property {string} PROFILE_LOADED
 */


/**
 * Safely loads and parses JSON data from a dedicated script tag.
 *
 * @template T
 * @param {string} elementId - The ID of the script tag (e.g., 'settings-json').
 * @returns {T} The parsed data object.
 * @throws {Error} If the element is missing or the content is malformed JSON.
 */
function loadConfigData(elementId) {
    const scriptElement = document.getElementById(elementId);
    if (!scriptElement) throw new Error(`Critical element #${elementId} is missing!`);

    try {
        return JSON.parse(scriptElement.textContent);
    } catch (e) {
        throw new Error(`Critical element #${elementId} contains malformed JSON!`);
    }
}


/** @type {Settings} */
export const SETTINGS = loadConfigData('settings-json');

/** @type {Events} */
export const EVENTS = loadConfigData('events-json');