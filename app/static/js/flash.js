import { EVENTS } from './constants.js';
import { getRootProperty, parseDuration } from './utils.js';

/** @type {HTMLUListElement | null} */
let flashContainer = document.querySelector('.flash-container');
if (!(flashContainer instanceof HTMLUListElement)) throw new Error("Critical element .flash-container is missing or not a <ul>!");

// Get the fade duraction by splitting the transition property
const fadeTransition = getRootProperty('--transition-fade');
const fadeDuration = parseDuration(fadeTransition.split(' ')[0]);
const staticDuration = 10  // Time that flash message should exist without transitioning

/**
 * Displays a flash message by creating and appending a new element.
 *
 * @param {string} message The message string to display. Can include HTML.
 * @param {object} [options] Configuration options.
 * @param {number} [options.duration=3000] How long to display in ms. 0 = persistent.
 * @param {'info'|'error'|'loading'} [options.type='info'] Message type for styling.
 * @returns {(() => void) | null} A remove function if persistent, else null.
 */
export function flash(message, options = {}) {
    if (!message) return null;
    const { duration = 3000, type = 'info' } = options;

    const assertedFlashContainer = /** @type {HTMLElement} */ (flashContainer);

    // Create the new element
    const flashElement = document.createElement('li');
    flashElement.className = 'flash-item';
    flashElement.classList.add(`flash-item--${type}`); // e.g., flash-item--error
    flashElement.innerHTML = message;

    // Force show the flash container popover over existing dialogs
    assertedFlashContainer.hidePopover();
    assertedFlashContainer.showPopover();
    assertedFlashContainer.appendChild(flashElement);

    // Force HTMX to process the new element in case there is HTMX content
    htmx.process(flashElement);

    // Force reflow to ensure the transition from opacity 0 -> 1 always plays
    // Track start time for persistent elements to ensure they exist for at least 500ms ()
    const startTime = Date.now();
    void flashElement.offsetWidth;
    flashElement.classList.add('flash-item--visible');

    const remove = () => {
        flashElement.classList.remove('flash-item--visible');
        flashElement.addEventListener('transitionend', () => {
            flashElement.remove();
        }, { once: true });
    };

    if (duration > 0) {
        // Auto-remove after duration
        setTimeout(remove, duration);
        return null;
    } else {
        // Return a "smart" remover function for manual calls
        const manualRemove = () => {
            const elapsedTime = Date.now() - startTime;
            const remainingTime = fadeDuration + staticDuration - elapsedTime;

            if (remainingTime > 0) {
                // Not enough time has passed, wait for the remainder
                setTimeout(remove, remainingTime);
            } else {
                // Minimum time has passed, remove immediately
                remove();
            }
        };

        return manualRemove;
    }
}

/**
 * Forces the flash container popover to show over newly opened dialogs
 */
const forceFlashSuperiority = () => {
    const assertedFlashContainer = /** @type {HTMLElement} */ (flashContainer);
    setTimeout(() => {
        assertedFlashContainer.hidePopover();
        console.log("hidden")
        assertedFlashContainer.showPopover();
    }, 0)
};


/**
 * Sets up all site-wide event listeners for automatically triggering flash messages.
 *
 * It attaches listeners for:
 * - The custom 'flashMessage' event (e.g., sent from the server via HTMX).
 * - The 'htmx:responseError' event to automatically flash error details.
 * - An initial page load, checking for a 'data-flash-message' attribute
 * on the '.flash-message' element.
 *
 * This should be called once on application startup.
 *
 * For manually triggering a flash message, import and call the `flash()`
 * function directly.
 *
 * @returns {void}
 */
export function registerFlashListeners() {
    // Listen for the flashMessage event from the server
    document.body.addEventListener(EVENTS.FLASH, (event) => {
        const customEvent = /** @type {CustomEvent<{value: string}>} */ (event);

        flash(customEvent.detail.value, { duration: 3000 });
    });

    // Listen for the response error event from the server
    document.body.addEventListener('htmx:responseError', function(event) {
        const customEvent = /** @type {CustomEvent<{xhr: XMLHttpRequest}>} */ (event);

        const xhr = customEvent.detail.xhr;
        let errorMessage = xhr.responseText; // Default to the raw response

        // Try to parse the response as JSON
        try {
            const errorObject = JSON.parse(xhr.responseText);
            // If parsing succeeds and a 'detail' key exists, use that.
            if (errorObject && errorObject.detail) {
                errorMessage = errorObject.detail;
            }
        } catch (e) {}

        // Display the flash as error type
        flash(errorMessage, { duration: 5000, type: 'error' });
    });

    // Check if the server loaded the page with a flash message to display
    document.addEventListener('DOMContentLoaded', () => {
        // Find the flash container
        const flashContainer = document.querySelector('.flash-container');
        if (!(flashContainer instanceof HTMLElement)) throw new Error("Critical element .flash-container is missing!");

        // Check if the data attribute exists
        const message = flashContainer.dataset.initialFlashMessage;
        if (message) {
            flash(message, { duration: 3000 });

            // Cleanup dataset
            delete flashContainer.dataset.initialFlashMessage;
        }
    });

    // Force the flash container to appear over newly opened dialogs
    document.querySelectorAll('dialog').forEach(dialog => {
        // Save a reference to the native methods
        const nativeShowModal = dialog.showModal;
        const nativeShow = dialog.show;

        // Redefine showModal() to force flash superiority first
        dialog.showModal = function(...args) {
            forceFlashSuperiority();
            nativeShowModal.apply(dialog, args);
        };

        // Redefine show() to force flash superiority first
        dialog.show = function(...args) {
            forceFlashSuperiority();
            nativeShow.apply(dialog, args);
        };
    });
}