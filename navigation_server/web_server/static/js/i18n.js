import { updateEmsVisibility } from './api.js';
import { t } from './translations-bridge.js';

export { initPageTranslations };
export { translateAllElements };

    // Function to translate all data-i18n elements on the page
    function translateAllElements() {
const elements = document.querySelectorAll('[data-i18n]');
elements.forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (key) {
        el.textContent = t.t(key);
    }
});
    }
    
    // Call translation on page load and language change
    async function initPageTranslations() {
try {
    // Don't treat initialization errors as connection errors
    // Only show connection lost when main API calls fail
    await initWebTranslations();
    translateAllElements();
    // Also re-translate when language changes (if needed)
    
    // Check EnergyService availability and update UI
    emsAvailable = await updateEmsVisibility();
} catch (e) {
    // Don't show connection lost during initialization
    // This prevents false positives from config/config issues
    console.error("Initialization error:", e);
}
    }
