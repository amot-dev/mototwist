import { EVENTS, SETTINGS } from './constants.js';
import { flash } from './flash.js';


/** @type {number | null} */
let warningTimerId = null;
/** @type {number | null} */
let expiryTimerId = null;
/** @type {number | null} */
let countdownIntervalId = null;
/** @type {(() => void) | null} */
let warningFlashRemover = null;


/**
 * Clears and resets all timers and the persistent warning flash.
 * @returns {void}
 */
function resetTimers() {
    if (warningTimerId !== null) {
        clearTimeout(warningTimerId);
        warningTimerId = null;
    }
    if (expiryTimerId !== null) {
        clearTimeout(expiryTimerId);
        expiryTimerId = null;
    }
    if (countdownIntervalId !== null) {
        clearInterval(countdownIntervalId);
        countdownIntervalId = null;
    }
    if (warningFlashRemover !== null) {
        warningFlashRemover();
        warningFlashRemover = null;
    }
}


/**
 * Handles the final session expiry. Triggers authChange.
 * @returns {void}
 */
function triggerAuthExpiry() {
    resetTimers();
    localStorage.removeItem('sessionExpiry');
    htmx.trigger(document.body, EVENTS.AUTH_CHANGE);
    flash('You have been logged out', { duration: 5000, type: 'info' });
}


/**
 * Starts the 1s live countdown and displays the warning flash message.
 * This is called exactly when the warning timeout hits.
 * @param {number} initialRemainingSeconds - The time left until final expiry.
 * @returns {void}
 */
function startLiveCountdown(initialRemainingSeconds) {
    if (countdownIntervalId) return; // Already running

    let secondsLeft = initialRemainingSeconds;

    warningFlashRemover = flash(`
        Session expires in <span id="session-countdown">${secondsLeft}</span> seconds!
        <button class="button button-link" hx-post="/refresh" hx-swap="none">
            Renew
        </button>
    `, { duration: 0, type: 'info' });

    // 3. Start the visual countdown (1s interval)
    countdownIntervalId = setInterval(() => {
        secondsLeft -= 1;

        const countdownElement = document.getElementById('session-countdown');
        if (countdownElement) countdownElement.textContent = `${secondsLeft}`;

        if (secondsLeft <= 0) {
            // The final expiry timeout will trigger shortly after this
            if (countdownIntervalId) clearInterval(countdownIntervalId);
        }
    }, 1000);
}


/**
 * Sets the session timers based on the stored expiry timestamp.
 * This function is called on load and after every successful renewal.
 * @returns {void}
 */
function setSessionTimers() {
    const storedExpiry = localStorage.getItem('sessionExpiry');
    if (!storedExpiry) return;

    const storedExpiry_s = parseInt(storedExpiry);
    const now_s = Math.floor(Date.now() / 1000);

    // Clear any existing timers before setting new ones
    resetTimers();

    // Check if we have valid state
    if (storedExpiry_s <= now_s) return;

    // Set authChange timer
    const timeRemaining_s = storedExpiry_s - now_s;
    expiryTimerId = setTimeout(() => {
        triggerAuthExpiry();
    }, timeRemaining_s * 1000);

    // Immediately return if not setting a warning
    const expiry_offset = SETTINGS.AUTH_EXPIRY_WARNING_OFFSET
    if (expiry_offset === 0) return;

    // If we are already past the warning point but still valid, start the countdown immediately
    if (timeRemaining_s < expiry_offset) {
        startLiveCountdown(timeRemaining_s);
    } else {
        const warningDelay_s = timeRemaining_s - expiry_offset
        warningTimerId = setTimeout(() => {
            startLiveCountdown(expiry_offset);
        }, warningDelay_s * 1000);
    }
}


/**
 * Sets up listeners for changes in session state.
 *
 * This should be called once on application startup.
 *
 * @returns {void}
 */
export function registerSessionListeners() {
    // Check local storage on page load and set the timers
    setSessionTimers();

    // Listen for logout
    document.body.addEventListener(EVENTS.SESSION_CLEARED, () => {
        resetTimers();
        localStorage.removeItem('sessionExpiry');
    });

    // Listen for login/refresh
    document.body.addEventListener(EVENTS.SESSION_SET, () => {
        // Assume the full lifetime has been restored
        const newExpiry_s = Math.floor(Date.now() / 1000) + SETTINGS.AUTH_COOKIE_MAX_AGE;
        localStorage.setItem('sessionExpiry', newExpiry_s.toString());
        setSessionTimers();
    });

    // Listen for 401/403
    document.body.addEventListener('htmx:afterRequest', (event) => {
        const customEvent = /** @type {CustomEvent<{xhr: XMLHttpRequest}>} */ (event);
        const xhr = customEvent.detail.xhr;

        // Immediately expire the session if authentication fails
        if (xhr.status === 401 || xhr.status === 403) triggerAuthExpiry();
    });
}