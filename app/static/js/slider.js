const GAP = 1.0;

/**
 * Initializes a range slider component.
 *
 * Binds input events to a pair of min/max range sliders to enforce a minimum gap,
 * updates their corresponding text output displays, and adjusts CSS custom
 * properties (`--pos`, `--a`, `--b`) on parent elements to visually represent
 * the selected track range.
 *
 * Expected DOM IDs based on the provided `idPrefix` (e.g., if prefix is "rating"):
 * - {idPrefix}-slider-min
 * - {idPrefix}-slider-max
 * - {idPrefix}-slider-min-out
 * - {idPrefix}-slider-max-out
 *
 * @param {string} idPrefix - The base identifier string used to query the slider elements.
 * @returns {void}
 */
export function initRangeSlider(idPrefix) {
    /** @type {HTMLElement | null} */
    const sliderMin = document.getElementById(`${idPrefix}-slider-min`);
    /** @type {HTMLElement | null} */
    const sliderMax = document.getElementById(`${idPrefix}-slider-max`);

    /** @type {HTMLElement | null} */
    const minOut = document.getElementById(`${idPrefix}-slider-min-out`);
    /** @type {HTMLElement | null} */
    const maxOut = document.getElementById(`${idPrefix}-slider-max-out`);

    if (!(sliderMin instanceof HTMLInputElement)) throw new Error(`Critical element #${idPrefix}-slider-min is missing!`);
    if (!(sliderMax instanceof HTMLInputElement)) throw new Error(`Critical element #${idPrefix}-slider-max is missing!`);
    if (!(minOut instanceof HTMLOutputElement || minOut instanceof HTMLInputElement)) throw new Error(`Critical element #${idPrefix}-slider-min-out is missing!`);
    if (!(maxOut instanceof HTMLOutputElement || maxOut instanceof HTMLInputElement)) throw new Error(`Critical element #${idPrefix}-slider-max-out is missing!`);

    const SCALE_MAX = parseFloat(sliderMax.max);

    /**
     * Event handler for the minimum slider input.
     *
     * Ensures the minimum value does not exceed the maximum value minus the defined gap.
     * Updates the corresponding text output and sets CSS variables for the visual track.
     *
     * @returns {void}
     */
    const updateMin = () => {
        let minVal = parseFloat(sliderMin.value);
        const maxVal = parseFloat(sliderMax.value);

        // Enforce gap
        if (minVal > maxVal - GAP) {
            minVal = maxVal - GAP;
            sliderMin.value = minVal.toString();
        }

        // Update output and position
        const percent = (minVal / SCALE_MAX) * 100;

        if (minOut) {
            minOut.value = minVal.toFixed(1);
            minOut.style.setProperty('--pos', percent.toString());
        }

        if (sliderMin.parentElement) {
            sliderMin.parentElement.style.setProperty('--a', `${percent}%`);
        }
    };

    /**
     * Event handler for the maximum slider input.
     *
     * Ensures the maximum value does not fall below the minimum value plus the defined gap.
     * Updates the corresponding text output and sets CSS variables for the visual track.
     *
     * @returns {void}
     */
    const updateMax = () => {
        const minVal = parseFloat(sliderMin.value);
        let maxVal = parseFloat(sliderMax.value);

        // Enforce gap
        if (maxVal < minVal + GAP) {
            maxVal = minVal + GAP;
            sliderMax.value = maxVal.toString();
        }

        // Update output and position
        const percent = (maxVal / SCALE_MAX) * 100;

        if (maxOut) {
            maxOut.value = maxVal.toFixed(1);
            maxOut.style.setProperty('--pos', percent.toString());
        }

        if (sliderMax.parentElement) {
            sliderMax.parentElement.style.setProperty('--b', `${percent}%`);
        }
    };

    // Attach listeners
    sliderMin.addEventListener('input', updateMin);
    sliderMax.addEventListener('input', updateMax);

    // Call once on init to ensure UI matches initial values
    updateMin();
    updateMax();
}
