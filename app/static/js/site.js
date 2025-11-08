import { registerFlashListeners } from './flash.js';
import { registerSessionListeners } from './session.js';
import { registerCopyButtonListener, validateFormsInScope } from './utils.js';

/**
 * Finds all forms without the '.manual-validation' class and attaches input listeners.
 * A form's submit button will be disabled as long as the form is invalid
 * (e.g., 'required' fields are empty).
 */
function registerGlobalFormValidation() {
    validateFormsInScope(document);

    // Run for dynamically added forms after any htmx swap
    document.body.addEventListener('htmx:afterSwap', (event) => {
        const customEvent = /** @type {CustomEvent<{elt: Element}>} */ (event);
        validateFormsInScope(customEvent.detail.elt);
    });
}

registerFlashListeners();
registerSessionListeners();
registerGlobalFormValidation();
registerCopyButtonListener();